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

from connect4_ntuple import (
    COLS, ROWS, STRIDE, PATTERNS, NTupleAgent, ConnectFour,
    _pattern_indices
)


def board_from_state(current, opponent, heights):
    board = [[0] * COLS for _ in range(ROWS)]
    for col in range(COLS):
        for level in range(int(heights[col])):
            bit = 1 << (col * STRIDE + level)
            row = ROWS - 1 - level
            if current & bit:
                board[row][col] = 1
            elif opponent & bit:
                board[row][col] = 2
    return board


def mirror_bits(bits):
    mirrored = 0
    for col in range(COLS):
        for level in range(ROWS):
            if bits & (1 << (col * STRIDE + level)):
                mirrored |= 1 << ((COLS - 1 - col) * STRIDE + level)
    return mirrored


def canonical_key(current, opponent):
    direct = (int(current), int(opponent))
    mirrored = (mirror_bits(current), mirror_bits(opponent))
    return min(direct, mirrored)


def collect_positions(database, target_count, seed, max_attempts):
    rng = random.Random(seed)
    seen = set()
    currents = []
    opponents = []
    heights_all = []
    targets = []
    scores = []
    attempts = 0
    started = time.perf_counter()

    while len(targets) < target_count and attempts < max_attempts:
        attempts += 1
        game = ConnectFour()
        terminal = False
        for _ in range(12):
            legal = [col for col in range(COLS) if game.heights[col] < ROWS]
            if not legal:
                terminal = True
                break
            won, draw = game.play(rng.choice(legal))
            if won or draw:
                terminal = True
                break
        if terminal or game.moves != 12:
            continue

        key = canonical_key(game.current, game.opponent)
        if key in seen:
            continue

        board = board_from_state(game.current, game.opponent, game.heights)
        score = database.get_book_value(board)
        if score is None:
            continue

        seen.add(key)
        currents.append(game.current)
        opponents.append(game.opponent)
        heights_all.append(game.heights.copy())
        targets.append(0.0 if score == 0 else (1.0 if score > 0 else -1.0))
        scores.append(score)

        if len(targets) and len(targets) % 50000 == 0:
            elapsed = time.perf_counter() - started
            print(
                f"Collected {len(targets):,}/{target_count:,} exact positions "
                f"from {attempts:,} sampled games in {elapsed:.1f}s",
                flush=True,
            )

    if len(targets) < min(target_count, 10000):
        raise RuntimeError(
            f"Only found {len(targets):,} database positions after {attempts:,} games"
        )

    print(
        f"Collected {len(targets):,} unique exact positions from {attempts:,} games",
        flush=True,
    )
    values, counts = np.unique(np.asarray(targets), return_counts=True)
    print(
        "Outcome distribution: " +
        ", ".join(f"{int(value):+d}: {int(count):,}" for value, count in zip(values, counts)),
        flush=True,
    )
    return (
        np.asarray(currents, dtype=np.int64),
        np.asarray(opponents, dtype=np.int64),
        np.asarray(heights_all, dtype=np.int8),
        np.asarray(targets, dtype=np.float32),
        np.asarray(scores, dtype=np.int16),
    )


@njit(cache=True)
def train_epoch(currents, opponents, heights_all, targets, weights, learning_rate):
    total_loss = 0.0
    for sample in range(len(targets)):
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
    return total_loss / max(len(targets), 1)


@njit(cache=True)
def evaluate_values(currents, opponents, heights_all, targets, weights):
    correct = 0
    total_loss = 0.0
    for sample in range(len(targets)):
        indices = _pattern_indices(
            currents[sample], opponents[sample], heights_all[sample], PATTERNS
        )
        value = 0.0
        for pattern in range(PATTERNS.shape[0]):
            value += weights[pattern, indices[pattern]]
        target = targets[sample]
        if (value > 0 and target > 0) or (value < 0 and target < 0) or (value == 0 and target == 0):
            correct += 1
        delta = target - value
        total_loss += delta * delta
    return correct / max(len(targets), 1), total_loss / max(len(targets), 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/connect4_ntuple.npz")
    parser.add_argument("--output", default="models/candidates/book-pretrained.npz")
    parser.add_argument("--positions", type=int, default=300000)
    parser.add_argument("--max-attempts", type=int, default=3000000)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--learning-rate", type=float, default=0.0002)
    parser.add_argument("--seed", type=int, default=31)
    parser.add_argument("--report", default="book_training_report.json")
    args = parser.parse_args()

    if args.positions < 10000 or args.max_attempts < args.positions or args.epochs < 1:
        parser.error("positions must be at least 10000, max-attempts must cover positions, and epochs must be positive")
    if args.learning_rate <= 0:
        parser.error("learning-rate must be positive")

    started = time.perf_counter()
    database = BitBullyDatabases("12-ply-dist")
    print(
        f"Loaded 12-ply-dist database: {database.get_book_size():,} entries, "
        f"{database.get_book_memory_size() / 1024 / 1024:.1f} MiB in memory",
        flush=True,
    )

    currents, opponents, heights, targets, scores = collect_positions(
        database, args.positions, args.seed, args.max_attempts
    )
    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(targets))
    validation_size = max(1, len(order) // 10)
    validation = order[:validation_size]
    training = order[validation_size:]

    agent = NTupleAgent(seed=args.seed)
    agent.load(args.model)
    initial_accuracy, initial_loss = evaluate_values(
        currents[validation], opponents[validation], heights[validation],
        targets[validation], agent.weights
    )
    best_weights = agent.weights.copy()
    best_accuracy = initial_accuracy
    best_loss = initial_loss
    history = []

    print(
        f"Initial validation: outcome accuracy {initial_accuracy:.4f}, "
        f"MSE {initial_loss:.6f}",
        flush=True,
    )

    for epoch in range(1, args.epochs + 1):
        rng.shuffle(training)
        loss = train_epoch(
            currents[training], opponents[training], heights[training],
            targets[training], agent.weights, args.learning_rate
        )
        accuracy, validation_loss = evaluate_values(
            currents[validation], opponents[validation], heights[validation],
            targets[validation], agent.weights
        )
        history.append({
            "epoch": epoch,
            "training_mse": float(loss),
            "validation_accuracy": float(accuracy),
            "validation_mse": float(validation_loss),
        })
        print(
            f"Epoch {epoch}/{args.epochs} | training MSE {loss:.6f} | "
            f"validation accuracy {accuracy:.4f} | validation MSE {validation_loss:.6f}",
            flush=True,
        )
        if validation_loss < best_loss:
            best_accuracy = accuracy
            best_loss = validation_loss
            best_weights = agent.weights.copy()
            agent.weights[:] = best_weights
            agent.save(args.output, epoch * len(training))
            print("Saved improved exact-database checkpoint.", flush=True)

    agent.weights[:] = best_weights
    agent.save(args.output, len(training) * args.epochs)
    report = {
        "database": "BitBully 12-ply-dist",
        "database_entries": database.get_book_size(),
        "sampled_positions": len(targets),
        "validation_positions": len(validation),
        "training_positions": len(training),
        "outcome_scores": {
            "wins": int(np.count_nonzero(targets > 0)),
            "draws": int(np.count_nonzero(targets == 0)),
            "losses": int(np.count_nonzero(targets < 0)),
            "score_min": int(scores.min()),
            "score_max": int(scores.max()),
        },
        "initial_validation_accuracy": float(initial_accuracy),
        "initial_validation_mse": float(initial_loss),
        "best_validation_accuracy": float(best_accuracy),
        "best_validation_mse": float(best_loss),
        "epochs": history,
        "elapsed_seconds": time.perf_counter() - started,
    }
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Exact-database pretraining saved to {args.output}", flush=True)


if __name__ == "__main__":
    main()
