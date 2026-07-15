from pixel_level_tool.domain.enums import CellShape, Direction
from pixel_level_tool.domain.shapes import ball_count, footprint, oriented_dimensions


def test_shape_ball_counts():
    assert ball_count(CellShape.Square_3x3) == 9
    assert ball_count(CellShape.Rectangle_3x2) == 6
    assert ball_count(CellShape.L3x4) == 6
    assert ball_count(CellShape.Rectangle_3x1) == 3
    assert ball_count(CellShape.Rectangle_6x1) == 6
    assert ball_count(CellShape.Rectangle_9x1) == 9
    assert ball_count(CellShape.LL3x4) == 6


def test_rotation_matches_unity_transform():
    assert footprint(CellShape.L3x4, Direction.Up) == ((0, 0), (1, 0), (2, 0), (1, 1), (1, 2), (1, 3))
    assert footprint(CellShape.L3x4, Direction.Left) == ((0, 0), (0, 1), (1, 1), (2, 1), (3, 1), (0, 2))
    assert footprint(CellShape.L3x4, Direction.Right) == ((3, 0), (0, 1), (1, 1), (2, 1), (3, 1), (3, 2))
    assert footprint(CellShape.L3x4, Direction.Down) == ((1, 0), (1, 1), (1, 2), (0, 3), (1, 3), (2, 3))


def test_oriented_dimensions_swap_left_right():
    assert oriented_dimensions(CellShape.Rectangle_3x2, Direction.Up) == (2, 3)
    assert oriented_dimensions(CellShape.Rectangle_3x2, Direction.Left) == (3, 2)
