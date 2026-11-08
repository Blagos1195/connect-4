from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from numba import njit
from bitbully_databases import BitBullyDatabases

from connect4_ntuple import COLS, ROWS, STRIDE, PATTERNS, NTupleAgent, _pattern_indices


def decode_position(key):
    encoded = int(key) & 0xFFFFFFFF
    bits = [(encoded >> shift) & 1 for shift in range(31, -1, -1)]
    board = [[0] * COLS for _ in range(ROWS)]
    current = 0
    opponent = 0
    heights = [0] * COLS
    offset = 0

    for col in range(COLS):
        while True:
            if offset >= 32:
                raise ValueError("Invalid opening-book position encoding")
            if bits[offset] == 0:
                offset += 1
                break
            if offset + 1 >= 32:
                raise ValueError("Incomplete token in opening-book position")
            player = 1 if bits[offset + 1] == 0 else 2
            level = heights[col]
            row = ROWS - 1 - level
            board[row][col] = player
            bit = 1 << (col * STRIDE + level)
            if player == 1:
                current |= bit
            else:
                opponent |= bit
            heights[col] += 1
            offset += 2

    if offset != 31 or bits[31] != 0 or sum(heights) != 12:
        raise ValueError("Opening-book entry is not a valid 12-ply position")

    return board, current, opponent, np.asarray(heights, dtype=np.int8)


def mirror_bits(bits):
    mirrored = 0
    for col in range(COLS):
        for level in range(ROWS):
            if bits & (1 << (col * STRIDE + level)):
                mirrored |= 1 << ((COLS - 1 - col) * STRIDE + level)
    return mirrored


def canonical_key(current, opponent):
    direct = (current, opponent)
    mirrored = (mirror_bits(current), mirror_bits(opponent))
    return min(direct, mirrored)


def collect_database(database, seed):
    entries = database.book
    if entries is None or len(entries) != 4200899:
        raise RuntimeError("The complete 12-ply-dist database was not loaded")

    count = len(entries)
    currents = np.empty(count, dtype=np.int64)
    opponents = np.empty(count, dtype=np.int64)
    heights_all = np.empty((count, COLS), dtype=np.int8)
    targets = np.empty(count, dtype=np.float32)
    validation_mask = np.zeros(count, dtype=np.bool_)

    started = time.perf_counter()
    score_counts = {"wins": 0, "draws": 0, "losses": 0}
    score_min = 127
    score_max = -128

    for index, (key, score) in enumerate(entries):
        board, current, opponent, heights = decode_position(key)
        if index < 1000:
            if database._to_huffman(board) != key:
                raise RuntimeError(f"Opening-book decode verification failed at entry {index}")
            if database.get_book_value(board) != score:
                raise RuntimeError(f"Opening-book score verification failed at entry {index}")

        currents[index] = current
        opponents[index] = opponent
        heights_all[index] = heights
        targets[index] = score / 100.0

        if score > 0:
            score_counts["wins"] += 1
        elif score < 0:
            score_counts["losses"] += 1
        else:
            score_counts["draws"] += 1

        score_min = min(score_min, score)
        score_max = max(score_max, score)

        canonical_current, canonical_opponent = canonical_key(current, opponent)
        mixed = (
            canonical_current * 11400714819323198485
            ^ canonical_opponent * 14029467366897019727
            ^ seed
        ) & 0xFFFFFFFFFFFFFFFF
        validation_mask[index] = mixed % 10 == 0

        if (index + 1) % 500000 == 0:
            elapsed = time.perf_counter() - started
            print(
                f"Decoded {index + 1:,}/{count:,} positions in {elapsed:.1f}s",
                flush=True,
            )

    validation = np.flatnonzero(validation_mask).astype(np.int32)
    training = np.flatnonzero(~validation_mask).astype(np.int32)
    if len(validation) < 100000 or len(training) < 1000000:
        raise RuntimeError("The grouped training/validation split is unexpectedly small")

    print(
        f"Loaded {count:,} exact positions | training {len(training):,} | "
        f"validation {len(validation):,}",
        flush=True,
    )
    print(
        f"Database outcomes: {score_counts['wins']:,} wins, "
        f"{score_counts['draws']:,} draws, {score_counts['losses']:,} losses | "
        f"scores {score_min} to {score_max}",
        flush=True,
    )

    return currents, opponents, heights_all, targets, training, validation, score_counts


@njit(cache=True)
def train_epoch(currents, opponents, heights_all, targets, order, weights, learning_rate):
    total_loss = 0.0
    for position in range(len(order)):
        sample = order[position]
        indices = _pattern_indices(
            currents[sample], opponents[sample], heights_all[sample], PATTERNS
        )
        value = 0.0
        for pattern in range(PATTERNS.shape[0]):
            value += weights[pattern, indices[pattern]]
        delta = targets[sample] - value
        total_loss += delta * delta
        adjustment = learning_rate * delta / PATTERNS.shape[0]
        for pattern in range(PATTERNS.shape[0]):
            weights[pattern, indices[pattern]] += adjustment
    return total_loss / max(len(order), 1)


@njit(cache=True)
def evaluate_values(currents, opponents, heights_all, targets, order, weights):
    correct = 0
    total_loss = 0.0
    win_total = win_correct = 0
    draw_total = draw_correct = 0
    loss_total = loss_correct = 0
    distance_error = 0.0
    decisive_total = 0

    for position in range(len(order)):
        sample = order[position]
        indices = _pattern_indices(
            currents[sample], opponents[sample], heights_all[sample], PATTERNS
        )
        value = 0.0
        for pattern in range(PATTERNS.shape[0]):
            value += weights[pattern, indices[pattern]]

        target = targets[sample]
        delta = target - value
        total_loss += delta * delta

        predicted = 1 if value > 0 else (-1 if value < 0 else 0)
        actual = 1 if target > 0 else (-1 if target < 0 else 0)
        if predicted == actual:
            correct += 1

        if actual > 0:
            win_total += 1
            if predicted > 0:
                win_correct += 1
        elif actual < 0:
            loss_total += 1
            if predicted < 0:
                loss_correct += 1
        else:
            draw_total += 1
            if predicted == 0:
                draw_correct += 1

        if actual != 0:
            distance_error += abs(abs(value) - abs(target)) * 100.0
            decisive_total += 1

    total = max(len(order), 1)
    return (
        correct / total,
        total_loss / total,
        win_correct / max(win_total, 1),
        draw_correct / max(draw_total, 1),
        loss_correct / max(loss_total, 1),
        distance_error / max(decisive_total, 1),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/connect4_ntuple.npz")
    parser.add_argument("--output", default="models/candidates/latest.npz")
    parser.add_argument("--best-output", default="models/candidates/book-pretrained.npz")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--learning-rate", type=float, default=0.00002)
    parser.add_argument("--seed", type=int, default=31)
    parser.add_argument("--report", default="book_training_report.json")
    args = parser.parse_args()

    if args.epochs < 1 or args.learning_rate <= 0:
        parser.error("epochs and learning-rate must be positive")

    started = time.perf_counter()
    database = BitBullyDatabases("12-ply-dist")
    print(
        f"Loaded 12-ply-dist: {database.get_book_size():,} entries, "
        f"{database.get_book_memory_size() / 1024 / 1024:.1f} MiB reported memory",
        flush=True,
    )

    data = collect_database(database, args.seed)
    currents, opponents, heights, targets, training, validation, score_counts = data

    rng = np.random.default_rng(args.seed)
    agent = NTupleAgent(seed=args.seed)
    agent.load(args.model)

    initial = evaluate_values(
        currents, opponents, heights, targets, validation, agent.weights
    )
    print(
        f"Initial validation | accuracy {initial[0]:.4f} | MSE {initial[1]:.6f} | "
        f"win {initial[2]:.4f} | draw {initial[3]:.4f} | loss {initial[4]:.4f} | "
        f"distance MAE {initial[5]:.2f}",
        flush=True,
    )

    best_weights = agent.weights.copy()
    best_loss = initial[1]
    best_epoch = 0
    agent.save(args.best_output, 0)
    history = []

    for epoch in range(1, args.epochs + 1):
        epoch_started = time.perf_counter()
        rng.shuffle(training)
        training_loss = train_epoch(
            currents, opponents, heights, targets, training,
            agent.weights, args.learning_rate
        )
        metrics = evaluate_values(
            currents, opponents, heights, targets, validation, agent.weights
        )
        agent.save(args.output, epoch * len(training))

        improved = metrics[1] < best_loss
        if improved:
            best_loss = metrics[1]
            best_epoch = epoch
            best_weights = agent.weights.copy()
            agent.save(args.best_output, epoch * len(training))

        record = {
            "epoch": epoch,
            "training_mse": float(training_loss),
            "validation_accuracy": float(metrics[0]),
            "validation_mse": float(metrics[1]),
            "win_accuracy": float(metrics[2]),
            "draw_accuracy": float(metrics[3]),
            "loss_accuracy": float(metrics[4]),
            "decisive_distance_mae": float(metrics[5]),
            "seconds": time.perf_counter() - epoch_started,
            "best_so_far": bool(improved),
        }
        history.append(record)
        print(
            f"Epoch {epoch}/{args.epochs} | train MSE {training_loss:.6f} | "
            f"validation MSE {metrics[1]:.6f} | accuracy {metrics[0]:.4f} | "
            f"win/draw/loss {metrics[2]:.4f}/{metrics[3]:.4f}/{metrics[4]:.4f} | "
            f"distance MAE {metrics[5]:.2f} | {record['seconds']:.1f}s"
            + (" | new best" if improved else ""),
            flush=True,
        )

    agent.weights[:] = best_weights
    agent.save(args.best_output, best_epoch * len(training))

    report = {
        "database": "BitBully 12-ply-dist",
        "database_entries": database.get_book_size(),
        "training_positions": len(training),
        "validation_positions": len(validation),
        "outcome_counts": score_counts,
        "target_encoding": "signed database score divided by 100; preserves win/loss distance",
        "initial_validation": {
            "accuracy": float(initial[0]),
            "mse": float(initial[1]),
            "win_accuracy": float(initial[2]),
            "draw_accuracy": float(initial[3]),
            "loss_accuracy": float(initial[4]),
            "decisive_distance_mae": float(initial[5]),
        },
        "best_epoch": best_epoch,
        "best_validation_mse": float(best_loss),
        "epochs": history,
        "elapsed_seconds": time.perf_counter() - started,
    }
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"Training complete | best epoch {best_epoch} | "
        f"best validation MSE {best_loss:.6f} | "
        f"elapsed {(time.perf_counter() - started) / 60:.1f} minutes",
        flush=True,
    )


if __name__ == "__main__":
    main()
