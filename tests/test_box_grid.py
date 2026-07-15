from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor
from pixel_level_tool.domain.level_models import BoxCellData, PixelLevelData


def test_placement_bounds_overlap_and_ids():
    level = PixelLevelData(grid_rows=5, grid_cols=5)
    assert level.add_box(BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red))
    assert not level.add_box(BoxCellData(2, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Blue))
    assert not level.add_box(BoxCellData(4, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Blue))
    assert level.add_box(BoxCellData(0, 2, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Blue))
    level.assign_deterministic_ids()
    assert [cell.id for cell in level.grid_cells] == [300, 301]

