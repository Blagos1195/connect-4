const createSolver = require("../perfect_solver.js");
const fs = require("fs");
const path = require("path");

async function main() {
  const solver = await createSolver({
    locateFile: file => path.join(__dirname, "..", file)
  });
  const book = fs.readFileSync(path.join(__dirname, "..", "7x6_small.book"));
  const pointer = solver._malloc(book.length);
  solver.HEAPU8.set(book, pointer);
  const loaded = solver.ccall("c4_load_book", "number", ["number", "number"], [pointer, book.length]);
  solver._free(pointer);
  if (!loaded) throw new Error("The opening book did not load.");

  const cases = [
    { moves: "", expected: 3 },
    { moves: "172736", expected: 3 },
    { moves: "716273", expected: 3 }
  ];

  for (const item of cases) {
    const move = solver.ccall("c4_best_move", "number", ["string"], [item.moves]);
    if (move !== item.expected) {
      throw new Error(`For ${item.moves || "empty board"}, expected ${item.expected}, got ${move}`);
    }
  }

  console.log(`PASS: ${cases.length} WebAssembly solver positions with opening book`);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
