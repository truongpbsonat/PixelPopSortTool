from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor
from pixel_level_tool.domain.level_models import BoxCellData, PixelGridData, PixelLevelData
from pixel_level_tool.services.level_validator import LevelValidator


def test_valid_level_passes_with_only_warning():
    level = PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        level=1,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red, 300)],
        pixel_grid=PixelGridData(3, 1, [0, 0, 0]),
    )
    result = LevelValidator().validate(level)
    assert result.is_valid


def test_balance_error():
    level = PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        level=1,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red, 300)],
        pixel_grid=PixelGridData(3, 1, [0, 1, 0]),
    )
    messages = [message.message for message in LevelValidator().validate(level).errors]
    assert any("histogram" in message for message in messages)


def test_invalid_pixel_length():
    level = PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        level=1,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red, 300)],
        pixel_grid=PixelGridData(3, 1, [0, 0]),
    )
    assert any("length" in message.message for message in LevelValidator().validate(level).errors)


def test_grid_lanes_warn_but_do_not_invalidate_level():
    level = PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        level=1,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red, 300)],
        pixel_grid=PixelGridData(3, 1, [0, 0, 0]),
        grid_lanes=[{"laneId": 1}],
    )

    result = LevelValidator().validate(level)

    assert result.is_valid
    assert any("gridLanes" in message.message for message in result.warnings)


def test_cell_effects_warn_but_do_not_invalidate_level():
    level = PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        level=1,
        grid_cells=[
            BoxCellData(
                0,
                0,
                CellShape.Rectangle_3x1,
                Direction.Up,
                ItemColor.Red,
                300,
                effects=[{"type": "ice"}],
            )
        ],
        pixel_grid=PixelGridData(3, 1, [0, 0, 0]),
    )

    result = LevelValidator().validate(level)

    assert result.is_valid
    assert any("effects" in message.message for message in result.warnings)
