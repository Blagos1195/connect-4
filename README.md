# Connect Four

A Connect Four game for the browser and desktop, powered by the same exact-search AI.

## Play in a browser

Open the [GitHub Pages game](https://blagos1195.github.io/connect-4/).

The browser runs the C++ solver compiled to WebAssembly in a Web Worker. The exact solver works without an opening-book download. An optional 5 MB compressed opening book can be downloaded from the game and is saved in IndexedDB for later visits. The worker also caches exact best moves for positions reached during play, including mirrored positions, so familiar positions can be answered without searching again. Cache entries are versioned separately from the opening book. The worker keeps calculations off the page's main thread, so the interface remains responsive.\n\nThe opening book is never downloaded automatically. The download button is a manual choice, with a reminder that it is best done over Wi-Fi. Browsers do not consistently expose Wi-Fi status, so the game does not try to detect or enforce it.

No Python installation or server is needed for the browser version. To run it locally, open the repository folder in VS Code and use the **Live Server** extension, or start a local server from the repository root:

```bash
python -m http.server 8000
```

Then open http://localhost:8000.

Do not open `index.html` directly as a `file://` URL. Browsers restrict the worker and WebAssembly resources in that mode.

## Run the desktop game in VS Code

### Requirements

- Python 3.11 recommended
- A C++17 compiler: `g++` or `clang++`
- VS Code with the Python extension

Install a compiler if needed:

- **Windows:** install MinGW-w64 and make sure `g++` is on PATH.
- **macOS:** install Xcode Command Line Tools with `xcode-select --install`.
- **Ubuntu/Debian:** install `g++` with `sudo apt install g++`.

### Setup

Open the cloned repository folder in VS Code. In its integrated terminal, run:

```bash
python -m venv .venv
```

Activate the environment:

**Windows PowerShell**
```powershell
.venv\Scripts\Activate.ps1
```

**macOS/Linux**
```bash
source .venv/bin/activate
```

Install the Python packages:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

In VS Code, select the `.venv` interpreter with **Python: Select Interpreter**.

### Play

Start a human-versus-AI game:

```bash
python play_connect4.py
```

Run AI versus AI:

```bash
python play_connect4.py --mode self-play
```

The first launch compiles `perfect_solver.cpp` with the available C++ compiler. The compiled executable is cached in the system temporary folder and reused. Keep `7x6_small.book` in the repository root: the native solver loads it when it starts.

## AI

The browser and desktop games use the same exact-search engine. The solver uses the opening book, tactical move pruning, symmetry-aware transposition tables and threat-based move ordering. It does not use the trained neural or n-tuple model to select moves.

Connect Four is a first-player win under perfect play. Therefore, a perfect AI playing second cannot force a win against a perfect first player. The solver instead chooses an optimal move for the current position.

## Experimental training

The n-tuple self-play trainer and its training scripts are retained for experiments. They are separate from the AI used in either game.

Install the requirements above, then see the available options with:

```bash
python main.py --help
```

The default model is `models/connect4_ntuple.npz`. Training logs are written to `training_connect4.csv`. The GitHub Actions workflows also include optional training from the opening-book and labelled-position datasets.
