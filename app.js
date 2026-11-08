const boardElement = document.querySelector("#board");
const columnButtons = [...document.querySelectorAll(".column-button")];
const modeButtons = [...document.querySelectorAll(".mode-button")];
const statusHeading = document.querySelector("#game-status");
const roundLabel = document.querySelector("#round-label");
const turnPill = document.querySelector("#turn-pill");
const turnDisc = turnPill.querySelector("span");
const turnLabel = document.querySelector("#turn-label");
const modelStatus = document.querySelector("#model-status");
const nextTitle = document.querySelector("#next-title");
const nextCopy = document.querySelector("#next-copy");
const scoreX = document.querySelector("#score-x");
const scoreO = document.querySelector("#score-o");
const scoreDraw = document.querySelector("#score-draw");
const scoreXName = document.querySelector("#score-x-name");
const scoreOName = document.querySelector("#score-o-name");
const opponentName = document.querySelector("#opponent-name");
const secretHintButton = document.querySelector("#secret-hint");
const bookButton = document.querySelector("#download-book");
const bookStatus = document.querySelector("#book-status");
bookButton.disabled = true;

let mode = "ai";
let currentPlayer = "X";
let aiPlayer = "O";
let gameOver = false;
let aiBusy = false;
let engineReady = false;
let perfectSolverWorker = null;
let perfectSolverReady = false;
let bookInstalled = false;
let bookUpdateAvailable = false;
let perfectSolverLoading = null;
let solverRequestId = 0;
const pendingSolverRequests = new Map();
let moveSequence = [];
let gameVersion = 0;
let board = Array(42).fill("");
let winningLine = [];
let hintColumn = null;
let hintForPlayer = null;
const hintEnabled = { X: false, O: false };
const scores = { you: 0, ai: 0, player1: 0, player2: 0, draw: 0 };

function otherPlayer(player) {
  return player === "X" ? "O" : "X";
}

function setModelStatus(message, ready = false) {
  modelStatus.textContent = message;
  modelStatus.parentElement.querySelector(".status-dot").style.background = ready ? "#83b99c" : "#999";
}

function loadPerfectSolver() {
  if (perfectSolverReady) return Promise.resolve();
  if (perfectSolverLoading) return perfectSolverLoading;

  perfectSolverLoading = new Promise((resolve, reject) => {
    const worker = new Worker("perfect_solver_worker.js?v=4");
    perfectSolverWorker = worker;
    let settled = false;

    worker.onmessage = event => {
      const data = event.data;
      if (data.type === "ready") {
        settled = true;
        perfectSolverReady = true;
        updateBookStatus(data.bookAvailable, data.bookUpdateAvailable);
        resolve();
        return;
      }
      if (data.type === "book-downloaded") {
        updateBookStatus(true, false);
        return;
      }
      if (data.type === "book-error") {
        updateBookStatus(bookInstalled, bookUpdateAvailable);
        bookStatus.textContent = data.message;
        return;
      }
      if (data.type === "error" && data.id === undefined) {
        const error = new Error(data.message);
        if (!settled) {
          settled = true;
          reject(error);
          worker.terminate();
          perfectSolverWorker = null;
        }
        return;
      }
      const pending = pendingSolverRequests.get(data.id);
      if (!pending) return;
      pendingSolverRequests.delete(data.id);
      if (data.error) pending.reject(new Error(data.error));
      else pending.resolve(data.move);
    };

    worker.onerror = event => {
      const error = new Error(event.message || "The exact solver worker failed.");
      if (!settled) {
        settled = true;
        reject(error);
      }
      for (const pending of pendingSolverRequests.values()) pending.reject(error);
      pendingSolverRequests.clear();
      worker.terminate();
      perfectSolverWorker = null;
      perfectSolverReady = false;
      perfectSolverLoading = null;
    };
  }).catch(error => {
    perfectSolverLoading = null;
    throw error;
  });

  return perfectSolverLoading;
}

function updateBookStatus(available, updateAvailable = false) {
  bookInstalled = Boolean(available);
  bookUpdateAvailable = Boolean(updateAvailable);
  bookButton.disabled = bookInstalled && !bookUpdateAvailable;
  bookButton.textContent = bookUpdateAvailable
    ? "Update opening book (5 MB)"
    : bookInstalled ? "Opening book downloaded" : "Download opening book (5 MB)";
  bookStatus.textContent = bookUpdateAvailable
    ? "A newer opening book is available. Updating is optional."
    : bookInstalled
      ? "Saved on this device. Future visits will use the cached copy."
      : "Optional performance upgrade. Best downloaded over Wi-Fi.";
}

function resetSolverWorker() {
  if (perfectSolverWorker) perfectSolverWorker.terminate();
  for (const pending of pendingSolverRequests.values()) {
    pending.reject(new Error("The game was reset."));
  }
  pendingSolverRequests.clear();
  perfectSolverWorker = null;
  perfectSolverReady = false;
  perfectSolverLoading = null;
}

async function requestExactMove(moves) {
  await loadPerfectSolver();
  return new Promise((resolve, reject) => {
    const id = ++solverRequestId;
    pendingSolverRequests.set(id, { resolve, reject });
    perfectSolverWorker.postMessage({ id, moves });
  });
}

async function loadAI() {
  if (engineReady) return;
  setModelStatus("Loading exact solver...");
  await loadPerfectSolver();
  engineReady = true;
  setModelStatus("Exact solver ready", true);
}

function findWinningLine(position, player) {
  const directions = [[0, 1], [1, 0], [1, 1], [1, -1]];
  for (let row = 0; row < 6; row++) {
    for (let col = 0; col < 7; col++) {
      if (position[row * 7 + col] !== player) continue;
      for (const [dr, dc] of directions) {
        const line = [];
        for (let step = 0; step < 4; step++) {
          const r = row + dr * step;
          const c = col + dc * step;
          if (r < 0 || r >= 6 || c < 0 || c >= 7 || position[r * 7 + c] !== player) break;
          line.push(r * 7 + c);
        }
        if (line.length === 4) return line;
      }
    }
  }
  return [];
}

function render() {
  boardElement.replaceChildren();
  board.forEach((value, index) => {
    const cell = document.createElement("div");
    cell.className = "cell";
    if (value) cell.classList.add(value === "X" ? "x" : "o");
    if (winningLine.includes(index)) cell.classList.add("winning");
    cell.setAttribute("role", "gridcell");
    const row = Math.floor(index / 7) + 1;
    const col = index % 7 + 1;
    cell.setAttribute("aria-label", `Row ${row}, column ${col}, ${value || "empty"}`);
    boardElement.append(cell);
  });

  columnButtons.forEach((button, col) => {
    const full = board[col] !== "";
    button.disabled = !engineReady || gameOver || aiBusy || full || (mode === "ai" && currentPlayer === aiPlayer);
    button.classList.toggle("hinted", mode === "pvp" && hintForPlayer === currentPlayer &&
      hintEnabled[currentPlayer] && hintColumn === col && !gameOver);
  });
  secretHintButton.hidden = mode !== "pvp";
  secretHintButton.classList.toggle("active", mode === "pvp" && hintEnabled[currentPlayer]);

  scoreX.textContent = mode === "ai" ? scores.you : scores.player1;
  scoreO.textContent = mode === "ai" ? scores.ai : scores.player2;
  scoreDraw.textContent = scores.draw;
  turnPill.style.visibility = gameOver ? "hidden" : "visible";
  turnDisc.className = currentPlayer === "X" ? "x-disc" : "o-disc";
  turnLabel.textContent = mode === "ai"
    ? currentPlayer === aiPlayer ? "AI THINKING" : "YOUR MOVE"
    : `PLAYER ${currentPlayer === "X" ? "1" : "2"}`;
}

async function refreshHint() {
  hintColumn = null;
  hintForPlayer = null;
  if (mode !== "pvp" || !hintEnabled[currentPlayer] || gameOver || !engineReady) return;

  const sequence = moveSequence.join("");
  const player = currentPlayer;
  try {
    const action = Number(await requestExactMove(sequence));
    if (sequence !== moveSequence.join("") || player !== currentPlayer ||
        mode !== "pvp" || !hintEnabled[player] || gameOver) return;
    if (Number.isInteger(action) && action >= 0 && action < 7 && board[action] === "") {
      hintColumn = action;
      hintForPlayer = player;
      render();
    }
  } catch (error) {
    console.warn("Could not calculate move hint.", error);
  }
}

function updateModeLabels() {
  const aiMode = mode === "ai";
  scoreXName.textContent = aiMode ? aiPlayer === "X" ? "AI" : "YOU" : "PLAYER 1";
  scoreOName.textContent = aiMode ? aiPlayer === "O" ? "AI" : "YOU" : "PLAYER 2";
  opponentName.textContent = aiMode ? "AI" : "Player 2";
  scoreX.parentElement.querySelector(".score-disc").className = "score-disc x-disc";
  scoreO.parentElement.querySelector(".score-disc").className = "score-disc o-disc";
  const legend = document.querySelectorAll(".board-footer > span");
  legend[0].innerHTML = `<i class="x-disc"></i> ${aiMode ? aiPlayer === "X" ? "AI" : "YOU" : "PLAYER 1"}`;
  legend[1].innerHTML = `<i class="o-disc"></i> ${aiMode ? aiPlayer === "O" ? "AI" : "YOU" : "PLAYER 2"}`;
  nextTitle.textContent = aiMode ? currentPlayer === aiPlayer ? "AI turn" : "Your move" : `Player ${currentPlayer === "X" ? "1" : "2"} starts`;
  nextCopy.textContent = aiMode ? `You play ${aiPlayer === "X" ? "yellow" : "red"}. The AI plays ${aiPlayer === "X" ? "red" : "yellow"}.` : "Take turns dropping counters into the board.";
}

function updateTurnText() {
  if (gameOver) return;
  if (mode === "ai") {
    roundLabel.textContent = currentPlayer === aiPlayer ? "THE AI IS THINKING" : "YOUR TURN";
    statusHeading.textContent = currentPlayer === aiPlayer ? "The AI is choosing." : "Choose a column.";
    nextTitle.textContent = currentPlayer === aiPlayer ? "AI turn" : "Your move";
    nextCopy.textContent = currentPlayer === aiPlayer ? "The exact solver is choosing a move." : `You play ${currentPlayer === "X" ? "red" : "yellow"}. The AI plays ${aiPlayer === "X" ? "red" : "yellow"}.`;
  } else {
    const player = currentPlayer === "X" ? "1" : "2";
    roundLabel.textContent = `PLAYER ${player}'S TURN`;
    statusHeading.textContent = `Player ${player}, choose a column.`;
    nextTitle.textContent = `Player ${player}'s move`;
    nextCopy.textContent = `Drop a ${currentPlayer === "X" ? "red" : "yellow"} counter.`;
  }
}

function finishGame(winner) {
  gameOver = true;
  if (winner) {
    if (mode === "ai") scores[winner === aiPlayer ? "ai" : "you"] += 1;
    else scores[winner === "X" ? "player1" : "player2"] += 1;
    winningLine = findWinningLine(board, winner);
    statusHeading.textContent = mode === "ai"
      ? winner === aiPlayer ? "The AI wins." : "You win."
      : `Player ${winner === "X" ? "1" : "2"} wins.`;
    roundLabel.textContent = "GAME OVER";
    nextTitle.textContent = mode === "ai"
      ? winner === aiPlayer ? "AI wins" : "You win"
      : winner === "X" ? "Player 1 wins" : "Player 2 wins";
    nextCopy.textContent = "Four in a row.";
  } else {
    scores.draw += 1;
    statusHeading.textContent = "It's a draw.";
    roundLabel.textContent = "GAME OVER";
    nextTitle.textContent = "Draw";
    nextCopy.textContent = "The board is full.";
  }
  render();
}

function playColumn(column) {
  if (!Number.isInteger(column) || column < 0 || column >= 7 || board[column] !== "") return;
  let row = 5;
  while (row >= 0 && board[row * 7 + column] !== "") row--;
  if (row < 0) return;

  const mover = currentPlayer;
  board[row * 7 + column] = mover;
  moveSequence.push(String(column + 1));
  currentPlayer = otherPlayer(currentPlayer);

  if (findWinningLine(board, mover).length) {
    finishGame(mover);
    return;
  }
  if (board.every(Boolean)) {
    finishGame(null);
    return;
  }

  updateTurnText();
  render();
  refreshHint();
}

async function makeAIMove() {
  const version = gameVersion;
  const sequence = moveSequence.join("");
  aiBusy = true;
  updateTurnText();
  render();
  try {
    await loadAI();
    const action = Number(await requestExactMove(sequence));
    if (version !== gameVersion || sequence !== moveSequence.join("")) return;
    if (!Number.isInteger(action) || action < 0 || action >= 7 || board[action] !== "") {
      throw new Error("The exact solver returned an invalid move.");
    }
    aiBusy = false;
    playColumn(action);
  } catch (error) {
    if (version !== gameVersion) return;
    console.error(error);
    aiBusy = false;
    gameOver = true;
    statusHeading.textContent = "The AI couldn't move.";
    roundLabel.textContent = "AI ERROR";
    nextTitle.textContent = "AI unavailable";
    nextCopy.textContent = error?.message || String(error);
    setModelStatus("AI error: " + (error?.message || String(error)));
    render();
  }
}

function startGame(resetScores = false) {
  const version = ++gameVersion;
  if (pendingSolverRequests.size) resetSolverWorker();
  board = Array(42).fill("");
  moveSequence = [];
  currentPlayer = "X";
  aiPlayer = Math.random() < 0.5 ? "X" : "O";
  gameOver = false;
  aiBusy = false;
  winningLine = [];
  hintColumn = null;
  hintForPlayer = null;
  hintEnabled.X = false;
  hintEnabled.O = false;
  if (resetScores) {
    scores.you = 0;
    scores.ai = 0;
    scores.player1 = 0;
    scores.player2 = 0;
    scores.draw = 0;
  }
  updateModeLabels();
  updateTurnText();
  render();
  loadAI().then(() => {
    if (version === gameVersion) {
      render();
      if (mode === "ai" && currentPlayer === aiPlayer) makeAIMove();
    }
  }).catch(error => {
    if (version !== gameVersion) return;
    console.error(error);
    statusHeading.textContent = "The game engine couldn't start.";
    roundLabel.textContent = "AI ERROR";
    nextTitle.textContent = "Game setup failed";
    nextCopy.textContent = error?.message || String(error);
    setModelStatus("Setup error: " + (error?.message || String(error)));
  });
}

columnButtons.forEach(button => {
  button.addEventListener("click", async () => {
    if (!engineReady || gameOver || aiBusy) return;
    const column = Number(button.dataset.column);
    if (mode === "ai" && currentPlayer === aiPlayer) return;
    playColumn(column);
    if (mode === "ai" && !gameOver) await makeAIMove();
  });
});

modeButtons.forEach(button => {
  button.addEventListener("click", () => {
    if (mode === button.dataset.mode) return;
    mode = button.dataset.mode;
    modeButtons.forEach(item => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    startGame(true);
  });
});

secretHintButton.addEventListener("click", () => {
  if (mode !== "pvp" || gameOver || aiBusy || !engineReady) return;
  hintEnabled[currentPlayer] = !hintEnabled[currentPlayer];
  refreshHint();
  render();
});

bookButton.addEventListener("click", () => {
  if (!engineReady || bookButton.disabled) return;
  bookButton.disabled = true;
  bookButton.textContent = bookInstalled ? "Updating opening book..." : "Downloading opening book...";
  bookStatus.textContent = "Downloading and saving this device's copy.";
  perfectSolverWorker.postMessage({ type: "download-book" });
});

document.querySelector("#new-game").addEventListener("click", () => startGame());
document.querySelector("#reset-scores").addEventListener("click", () => startGame(true));

startGame();
