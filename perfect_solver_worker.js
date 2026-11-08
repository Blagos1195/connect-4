importScripts("perfect_solver.js?v=1");

let solver = null;

const ready = CreateConnect4Solver({
  locateFile: path => path.endsWith(".wasm") ? "perfect_solver.wasm?v=1" : path
}).then(module => {
  solver = module;
  self.postMessage({ type: "ready" });
}).catch(error => {
  self.postMessage({ type: "error", message: error?.message || String(error) });
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
