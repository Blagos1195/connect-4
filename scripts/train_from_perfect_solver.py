from __future__ import annotations

import argparse
import random
import subprocess
import time
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connect4_ntuple import (
    COLS, ROWS, STRIDE, PATTERNS, POWERS, NTupleAgent,
    ConnectFour, _pattern_indices,
)
from numba import njit


@njit(cache=True)
def train_epoch(currents, opponents, heights_all, targets, order, weights, rate):
    total = 0.0
    for k in range(len(order)):
        i = order[k]
        indices = _pattern_indices(currents[i], opponents[i], heights_all[i], PATTERNS)
        value = 0.0
        for p in range(PATTERNS.shape[0]):
            value += weights[p, indices[p]]
        delta = targets[i] - value
        total += delta * delta
        adjustment = rate * delta / PATTERNS.shape[0]
        for p in range(PATTERNS.shape[0]):
            weights[p, indices[p]] += adjustment
    return total / max(len(order), 1)


@njit(cache=True)
def predict(currents, opponents, heights_all, weights):
    values = np.empty(len(currents), dtype=np.float32)
    for i in range(len(currents)):
        indices = _pattern_indices(currents[i], opponents[i], heights_all[i], PATTERNS)
        value = 0.0
        for p in range(PATTERNS.shape[0]):
            value += weights[p, indices[p]]
        values[i] = value
    return values


def generate_positions(count, seed):
    rng = random.Random(seed)
    positions = []
    seen = set()
    while len(positions) < count:
        game = ConnectFour()
        sequence = []
        target_length = rng.randint(8, 34)
        while game.moves < target_length:
            legal = [c for c in range(COLS) if game.heights[c] < ROWS]
            if not legal:
                break
            col = rng.choice(legal)
            won, _ = game.play(col)
            sequence.append(str(col + 1))
            if won:
                sequence.pop()
                game = ConnectFour()
                for move in sequence:
                    game.play(int(move) - 1)
                break
        if len(sequence) < 8 or game.moves >= ROWS * COLS:
            continue
        key = (game.current, game.opponent)
        mirrored = (mirror_bits(game.current), mirror_bits(game.opponent))
        canonical = min(key, mirrored)
        if canonical in seen:
            continue
        seen.add(canonical)
        positions.append(("".join(sequence), game.current, game.opponent,
                          game.heights.copy()))
        if len(positions) % 500 == 0:
            print(f"Generated {len(positions):,}/{count:,} unique positions", flush=True)
    return positions


def mirror_bits(bits):
    mirrored = 0
    for col in range(COLS):
        for level in range(ROWS):
            if bits & (1 << (col * STRIDE + level)):
                mirrored |= 1 << ((COLS - 1 - col) * STRIDE + level)
    return mirrored


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", required=True)
    parser.add_argument("--positions", type=int, default=5000)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--learning-rate", type=float, default=0.015)
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--output", default="models/candidates/solver-trained.npz")
    args = parser.parse_args()

    started = time.perf_counter()
    positions = generate_positions(args.positions, args.seed)
    payload = "".join(item[0] + "\\n" for item in positions)
    result = subprocess.run(
        [args.solver, "-a", "-b", "/dev/null"],
        input=payload, text=True, capture_output=True, check=True,
        timeout=330 * 60,
    )
    lines = result.stdout.splitlines()
    if len(lines) != len(positions):
        raise RuntimeError(
            f"Solver returned {len(lines)} lines for {len(positions)} positions: "
            + result.stderr[-2000:]
        )

    currents = []
    opponents = []
    heights_all = []
    targets = []
    groups = [0]
    exact_scores = []
    skipped = 0

    for position, line in zip(positions, lines):
        parts = line.split()
        if len(parts) != 8:
            skipped += 1
            continue
        scores = [int(value) for value in parts[1:]]
        game_current, game_opponent, heights = position[1:]
        legal_scores = [(col, score) for col, score in enumerate(scores)
                        if score != -1000 and heights[col] < ROWS]
        if not legal_scores:
            skipped += 1
            continue
            for col, score in legal_scores:
            bit = 1 << (col * STRIDE + int(heights[col]))
            next_heights = heights.copy()
            next_heights[col] += 1
            currents.append(game_opponent)
            opponents.append(game_current | bit)
            heights_all.append(next_heights)
            targets.append(-score / 20.0)
            exact_scores.append(score)
        groups.append(len(currents))

    if len(currents) < 10000:
        raise RuntimeError(f"Only {len(currents):,} labelled moves were generated")

    currents = np.asarray(currents, dtype=np.int64)
    opponents = np.asarray(opponents, dtype=np.int64)
    heights_all = np.asarray(heights_all, dtype=np.int8)
    targets = np.asarray(targets, dtype=np.float32)
    exact_scores = np.asarray(exact_scores, dtype=np.int16)
    groups = np.asarray(groups, dtype=np.int32)

    rng = np.random.default_rng(args.seed)
    parent_count = len(groups) - 1
    parent_order = rng.permutation(parent_count)
    split = int(parent_count * 0.9)
    train_parents = parent_order[:split]
    validation_parents = parent_order[split:]
    train_indices = np.concatenate([
        np.arange(groups[p], groups[p + 1]) for p in train_parents
    ])
    validation_indices = np.concatenate([
        np.arange(groups[p], groups[p + 1]) for p in validation_parents
    ])

    agent = NTupleAgent(seed=args.seed)
    best_loss = float("inf")
    best_weights = agent.weights.copy()
    best_epoch = 0

    print(
        f"Exact solver labels: {len(positions) - skipped:,} positions, "
        f"{len(currents):,} legal moves; train {len(train_indices):,}, "
        f"validation {len(validation_indices):,}",
        flush=True,
    )

    for epoch in range(1, args.epochs + 1):
        epoch_started = time.perf_counter()
        rng.shuffle(train_indices)
        training_loss = train_epoch(
            currents, opponents, heights_all, targets, train_indices,
            agent.weights, args.learning_rate,
        )
        predicted = predict(
            currents[validation_indices], opponents[validation_indices],
            heights_all[validation_indices], agent.weights,
        )
        errors = targets[validation_indices] - predicted
        validation_mse = float(np.mean(errors * errors))
        if validation_mse < best_loss:
            best_loss = validation_mse
            best_epoch = epoch
            best_weights = agent.weights.copy()

        print(
            f"Epoch {epoch}/{args.epochs} | train MSE {training_loss:.6f} | "
            f"validation MSE {validation_mse:.6f} | "
            f"{time.perf_counter() - epoch_started:.1f}s"
            + (" | new best" if best_epoch == epoch else ""),
            flush=True,
        )

    agent.weights[:] = best_weights
    agent.save(args.output, best_epoch * len(train_indices))

    predictions = predict(currents, opponents, heights_all, agent.weights)
    top1 = 0
    evaluated = 0
    for parent in validation_parents:
        start, end = groups[parent], groups[parent + 1]
        if end <= start:
            continue
        chosen = start + int(np.argmin(predictions[start:end]))
        best = max(exact_scores[start:end])
        if exact_scores[chosen] == best:
            top1 += 1
        evaluated += 1

    print(
        f"Best checkpoint epoch {best_epoch} | validation MSE {best_loss:.6f} | "
        f"solver-optimal move rate {top1 / max(evaluated, 1):.4f} | "
        f"positions evaluated {evaluated:,} | "
        f"elapsed {time.perf_counter() - started:.1f}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
