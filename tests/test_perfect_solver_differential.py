import random
import subprocess
import sys


def positions(count, seed):
    rng = random.Random(seed)
    result = []
    seen = set()
    while len(result) < count:
        moves = []
        heights = [0] * 7
        current = [set(), set()]
        turn = 0
        target = rng.randint(18, 34)
        for _ in range(target):
            legal = [c for c in range(7) if heights[c] < 6]
            col = rng.choice(legal)
            row = heights[col]
            heights[col] += 1
            current[turn].add((row, col))
            won = False
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                count_line = 1
                for sign in (-1, 1):
                    r, c = row + sign * dr, col + sign * dc
                    while (r, c) in current[turn]:
                        count_line += 1
                        r += sign * dr
                        c += sign * dc
                if count_line >= 4:
                    won = True
                    break
            if won:
                break
            moves.append(str(col + 1))
            turn = 1 - turn
        if len(moves) >= 16:
            sequence = "".join(moves)
            if sequence not in seen:
                seen.add(sequence)
                result.append(sequence)
    return result


def main():
    ours, oracle = sys.argv[1:3]
    opening = subprocess.run([ours], input="\n", text=True, capture_output=True, check=True, timeout=30)
    if int(opening.stdout.split()[0]) != 3:
        raise SystemExit("The empty-board opening must be the centre column")
    boards = ["4", "44", "444", "4444", "434343", "343434", "1234567", "7654321"] + positions(80, 94117)
    payload = "".join(board + "\n" for board in boards)
    actual = subprocess.run([ours], input=payload, text=True, capture_output=True, check=True, timeout=900)
    expected = subprocess.run([oracle, "-a", "-b", "/dev/null"], input=payload, text=True, capture_output=True, check=True, timeout=900)
    actual_lines = actual.stdout.splitlines()
    expected_lines = expected.stdout.splitlines()
    if len(actual_lines) != len(boards) or len(expected_lines) != len(boards):
        raise SystemExit(f"Output count mismatch: ours={len(actual_lines)}, oracle={len(expected_lines)}")
    for board, actual_line, expected_line in zip(boards, actual_lines, expected_lines):
        fields = actual_line.split()
        oracle_fields = expected_line.split()
        if len(fields) < 1 or len(oracle_fields) != 8:
            raise SystemExit(f"Malformed solver output for {board}: {actual_line!r} / {expected_line!r}")
        move = int(fields[0])
        scores = [int(value) for value in oracle_fields[1:]]
        best = max(value for value in scores if value != -1000)
        if move < 0 or move > 6 or scores[move] != best:
            raise SystemExit(f"Wrong move for {board}: selected={move}, oracle={scores}")
    print(f"PASS: {len(boards)} positions matched the exact solver's optimal move set")


if __name__ == "__main__":
    main()
