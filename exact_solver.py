import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class ExactSolver:
    def __init__(self):
        root = Path(__file__).resolve().parent
        source = root / "perfect_solver.cpp"
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise RuntimeError("A C++ compiler is required for the exact solver.")

        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        suffix = ".exe" if os.name == "nt" else ""
        binary = Path(tempfile.gettempdir()) / f"connect4-perfect-{digest}{suffix}"

        if not binary.exists():
            subprocess.run(
                [compiler, "-std=c++17", "-O3", "-DNDEBUG", str(source), "-o", str(binary)],
                check=True,
                cwd=root,
            )

        self.process = subprocess.Popen(
            [str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=root,
        )

    def choose_move(self, moves):
        if self.process.poll() is not None:
            raise RuntimeError("The exact solver process has stopped.")
        self.process.stdin.write(moves + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("The exact solver returned no move.")
        move = int(line.split()[0])
        if not 0 <= move < 7:
            raise RuntimeError("The exact solver returned an invalid move.")
        return move

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=2)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
