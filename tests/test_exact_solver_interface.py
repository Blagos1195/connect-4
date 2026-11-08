from exact_solver import ExactSolver


def main():
    with ExactSolver() as solver:
        assert solver.choose_move("172736") == 3
        assert solver.choose_move("716273") == 3
    print("PASS: native exact solver interface")


if __name__ == "__main__":
    main()
