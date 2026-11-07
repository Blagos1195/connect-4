import numpy as np

from scripts.train_from_book import board_from_state, canonical_key
from connect4_ntuple import ConnectFour


def test_database_board_orientation_and_players():
    game = ConnectFour()
    for column in (3, 2, 3, 2, 4, 1, 4, 1, 5, 0, 5, 0):
        game.play(column)
    board = board_from_state(game.current, game.opponent, game.heights)
    assert len(board) == 6
    assert all(len(row) == 7 for row in board)
    assert sum(cell == 1 for row in board for cell in row) == 6
    assert sum(cell == 2 for row in board for cell in row) == 6


def test_canonical_key_handles_horizontal_mirror():
    game = ConnectFour()
    for column in (0, 1, 0, 2, 3, 2, 3, 4, 5, 4, 5, 6):
        game.play(column)
    mirrored_columns = tuple(6 - column for column in (0, 1, 0, 2, 3, 2, 3, 4, 5, 4, 5, 6))
    mirrored = ConnectFour()
    for column in mirrored_columns:
        mirrored.play(column)
    assert canonical_key(game.current, game.opponent) == canonical_key(
        mirrored.current, mirrored.opponent
    )
