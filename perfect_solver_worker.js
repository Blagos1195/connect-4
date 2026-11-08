importScripts("perfect_solver.js?v=2");

const DATABASE_NAME = "connect-four-cache";
const DATABASE_VERSION = 1;
const OPENING_BOOK_KEY = "opening-book";
const BOOK_VERSION_URL = "book-version.json?v=1";
const SOLVER_VERSION = "solver-v1";

let solver = null;
let database = null;
let bookAvailable = false;
let bookUpdateAvailable = false;
let latestBookVersion = 1;

function openDatabase() {
  return new Promise(resolve => {
    if (!("indexedDB" in self)) {
      resolve(null);
      return;
    }
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("positions")) db.createObjectStore("positions", { keyPath: "key" });
      if (!db.objectStoreNames.contains("assets")) db.createObjectStore("assets", { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => resolve(null);
  });
}

function readRecord(storeName, key) {
  if (!database) return Promise.resolve(null);
  return new Promise(resolve => {
    const request = database.transaction(storeName, "readonly").objectStore(storeName).get(key);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => resolve(null);
  });
}

function writeRecord(storeName, value) {
  if (!database) return Promise.resolve();
  return new Promise(resolve => {
    const transaction = database.transaction(storeName, "readwrite");
    transaction.objectStore(storeName).put(value);
    transaction.oncomplete = resolve;
    transaction.onerror = resolve;
    transaction.onabort = resolve;
  });
}

function deleteRecord(storeName, key) {
  if (!database) return Promise.resolve();
  return new Promise(resolve => {
    const transaction = database.transaction(storeName, "readwrite");
    transaction.objectStore(storeName).delete(key);
    transaction.oncomplete = resolve;
    transaction.onerror = resolve;
    transaction.onabort = resolve;
  });
}

async function loadBook(compressed) {
  if (!("DecompressionStream" in self)) throw new Error("This browser does not support compressed opening books.");
  const stream = new Blob([compressed]).stream().pipeThrough(new DecompressionStream("gzip"));
  const bytes = new Uint8Array(await new Response(stream).arrayBuffer());
  const pointer = solver._malloc(bytes.length);
  let loaded;
  try {
    solver.HEAPU8.set(bytes, pointer);
    loaded = solver.ccall("c4_load_book", "number", ["number", "number"], [pointer, bytes.length]);
  } finally {
    solver._free(pointer);
  }
  if (!loaded) throw new Error("The exact opening book is invalid.");
  bookAvailable = true;
}

async function fetchLatestBookVersion() {
  try {
    const response = await fetch(BOOK_VERSION_URL, { cache: "no-store" });
    if (!response.ok) throw new Error("Book version check failed.");
    const data = await response.json();
    if (Number.isInteger(data.version) && data.version > 0) return data.version;
  } catch {}
  return 1;
}

async function restoreBook() {
  const saved = await readRecord("assets", OPENING_BOOK_KEY);
  if (!saved) return;
  latestBookVersion = await fetchLatestBookVersion();
  latestBookVersion = Math.max(latestBookVersion, saved.version || 1);
  try {
    await loadBook(saved.data);
    bookUpdateAvailable = (saved.version || 1) < latestBookVersion;
  } catch {
    await deleteRecord("assets", OPENING_BOOK_KEY);
  }
}

async function downloadBook() {
  try {
    latestBookVersion = await fetchLatestBookVersion();
    const response = await fetch("7x6_small.book.gz?v=" + latestBookVersion);
    if (!response.ok) throw new Error("Could not download the opening book.");
    const compressed = await response.arrayBuffer();
    await loadBook(compressed);
    await writeRecord("assets", { key: OPENING_BOOK_KEY, version: latestBookVersion, data: compressed });
    bookUpdateAvailable = false;
    self.postMessage({ type: "book-downloaded" });
  } catch (error) {
    self.postMessage({ type: "book-error", message: error?.message || String(error) });
  }
}

function cacheKey(moves) {
  const columns = Array.from({ length: 7 }, () => []);
  for (let i = 0; i < moves.length; i++) {
    columns[Number(moves[i]) - 1].push(i % 2 === 0 ? "X" : "O");
  }
  const forward = columns.map(column => column.join("")).join("/");
  const reverse = [...columns].reverse().map(column => column.join("")).join("/");
  const mirrored = forward > reverse;
  return {
    key: SOLVER_VERSION + ":" + (moves.length % 2) + ":" + (mirrored ? reverse : forward),
    mirrored
  };
}

async function findMove(moves) {
  const { key, mirrored } = cacheKey(moves);
  const cached = await readRecord("positions", key);
  if (cached && Number.isInteger(cached.move)) {
    return mirrored ? 6 - cached.move : cached.move;
  }

  const move = solver.ccall("c4_best_move", "number", ["string"], [moves]);
  if (move >= 0 && move < 7) {
    void writeRecord("positions", {
      key,
      move: mirrored ? 6 - move : move
    });
  }
  return move;
}

const ready = (async () => {
  solver = await CreateConnect4Solver({
    locateFile: path => path.endsWith(".wasm") ? "perfect_solver.wasm?v=1" : path
  });
  database = await openDatabase();
  await restoreBook();
  self.postMessage({ type: "ready", bookAvailable, bookUpdateAvailable });
})().catch(error => {
  self.postMessage({ type: "error", message: error?.message || String(error) });
  throw error;
});

self.onmessage = async event => {
  const { id, moves, type } = event.data;
  try {
    await ready;
    if (type === "download-book") {
      await downloadBook();
      return;
    }
    const move = await findMove(moves);
    self.postMessage({ id, move });
  } catch (error) {
    self.postMessage({ id, error: error?.message || String(error) });
  }
};
