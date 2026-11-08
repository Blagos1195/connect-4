importScripts("perfect_solver.js?v=1");

let solver = null;

const ready = (async () => {
  solver = await CreateConnect4Solver({
    locateFile: path => path.endsWith(".wasm") ? "perfect_solver.wasm?v=1" : path
  });
  const response = await fetch("7x6_small.book");
  if (!response.ok) throw new Error("Could not load the exact opening book.");
  const bytes = new Uint8Array(await response.arrayBuffer());
  const pointer = solver._malloc(bytes.length);
  solver.HEAPU8.set(bytes, pointer);
  const loaded = solver.ccall("c4_load_book", "number", ["number", "number"], [pointer, bytes.length]);
  solver._free(pointer);
  if (!loaded) throw new Error("The exact opening book is invalid.");
  self.postMessage({ type: "ready" });
})().catch(error => {
  self.postMessage({ type: "error", message: error?.message || String(error) });
  throw error;
});

self.onmessage = async event => {
  const { id, moves } = event.data;
  try {
    await ready;
    const move = solver.ccall("c4_best_move", "number", ["string"], [moves]);
    self.postMessage({ id, move });
  } catch (error) {
    self.postMessage({ id, error: error?.message || String(error) });
  }
};
