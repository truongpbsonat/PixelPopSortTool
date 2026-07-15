from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor
from pixel_level_tool.domain.level_models import BoxCellData, LargeBlockObstacleData, LinkedContainerObstacleData, PixelLevelData


def test_placement_bounds_overlap_and_ids():
    level = PixelLevelData(grid_rows=5, grid_cols=5)
    assert level.add_box(BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red))
    assert not level.add_box(BoxCellData(2, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.DarkBlue))
    assert not level.add_box(BoxCellData(4, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.DarkBlue))
    assert level.add_box(BoxCellData(0, 2, CellShape.Rectangle_3x1, Direction.Up, ItemColor.DarkBlue))
    level.assign_deterministic_ids()
    assert [cell.id for cell in level.grid_cells] == [300, 301]


def test_delete_box_cascades_invalid_target_obstacles():
    level = PixelLevelData(grid_rows=3, grid_cols=6)
    first = BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red)
    second = BoxCellData(3, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.DarkBlue)
    level.grid_cells = [first, second]
    level.obstacles = [LinkedContainerObstacleData([first.internal_uid, second.internal_uid])]
    level.remove_box(0)
    assert level.obstacles == []


def test_resize_requires_explicit_drop_for_invalid_obstacles():
    level = PixelLevelData(grid_rows=6, grid_cols=6)
    level.grid_cells = [BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red)]
    level.obstacles = [LargeBlockObstacleData(3, 3, 3, 3)]
    level.resize_box_grid(4, 4, drop_out_of_bounds=False)
    assert (level.grid_rows, level.grid_cols) == (6, 6)
    assert len(level.obstacles) == 1
    level.resize_box_grid(4, 4, drop_out_of_bounds=True)
    assert (level.grid_rows, level.grid_cols) == (4, 4)
    assert level.obstacles == []
