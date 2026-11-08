# Noah's AI Games

## Connect Four

The browser game is served from the repository root through GitHub Pages. Its AI uses the exact-search engine in `perfect_solver.cpp`, compiled to WebAssembly. The browser no longer uses the trained n-tuple checkpoint to choose moves.

The native game uses the same C++ engine. On first launch, `play_connect4.py` compiles it with `g++` or `clang++` and keeps the solver running so its transposition table is reused between moves. If no C++ compiler is available, it falls back to the trained model.

The solver searches to the end of the game using alpha-beta search, tactical move pruning, symmetry-aware transpositions and threat-based move ordering. It has no learned evaluation cutoff. A returned move is optimal for the current position, although search time depends on the position and available memory.

Connect Four is a first-player win under perfect play. That means a perfect AI playing second cannot prevent a loss against a perfect first player. The engine still chooses the mathematically best move in every position.

## Training

The n-tuple self-play trainer remains available for experiments. Its checkpoint is retained, but it is not used by the exact-search AI when the solver is available.

Install:

```bash
python -m pip install -r requirements.txt
```

Train from scratch:

```bash
python main.py --games 100000 --eval-every 5000
```

Resume a checkpoint:

```bash
python main.py --games 100000 --resume models/connect4_ntuple.npz
```

The default checkpoint is `models/connect4_ntuple.npz`. Training progress is appended to `training_connect4.csv`.

Play against the AI:

```bash
python play_connect4.py
```

Play AI against itself:

```bash
python play_connect4.py --mode self-play
```
