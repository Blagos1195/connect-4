const createSolver = require("../perfect_solver.js");
const path = require("path");

async function main() {
  const solver = await createSolver({
    locateFile: file => path.join(__dirname, "..", file)
  });

  const cases = [
    { moves: "", expected: 3 },
    { moves: "172736", expected: 3 },
    { moves: "717263", expected: 3 }
  ];

  for (const item of cases) {
    const move = solver.ccall("c4_best_move", "number", ["string"], [item.moves]);
    if (move !== item.expected) {
      throw new Error(`For ${item.moves || "empty board"}, expected ${item.expected}, got ${move}`);
    }
  }

  console.log(`PASS: ${cases.length} WebAssembly solver positions`);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
