from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor, LockKeyGate, WoolCrateColor
from pixel_level_tool.domain.level_models import (
    ArrowLockCellEffectData,
    BoxCellData,
    ElevatorLayerData,
    ElevatorObstacleData,
    FrozenCellEffectData,
    HiddenCellEffectData,
    KeyForLockedGateCellEffectData,
    LinkedContainerObstacleData,
    LockedGateObstacleData,
    PinsObstacleData,
    PixelGridData,
    PixelLevelData,
    ScissorForWoolCrateCellEffectData,
    WoolCrateObstacleData,
)
from pixel_level_tool.services.level_validator import LevelValidator


def base_level() -> PixelLevelData:
    first = BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red, 300)
    second = BoxCellData(3, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Blue, 301)
    return PixelLevelData(
        grid_rows=3,
        grid_cols=6,
        grid_cells=[first, second],
        pixel_grid=PixelGridData(6, 1, [int(ItemColor.Red)] * 3 + [int(ItemColor.Blue)] * 3),
    )


def messages(level):
    return [item.message for item in LevelValidator().validate(level).errors]


def test_linked_container_and_pins_validate_targets_and_geometry():
    level = base_level(); a, b = level.grid_cells
    level.obstacles = [LinkedContainerObstacleData([a.internal_uid, b.internal_uid]), PinsObstacleData([a.internal_uid, b.internal_uid], Direction.Right)]
    assert not messages(level)
    level.obstacles[0].target_uids = [a.internal_uid, a.internal_uid]
    assert any("distinct" in text for text in messages(level))


def test_effect_runtime_constraints_are_errors():
    level = base_level()
    level.grid_cells[0].effects = [HiddenCellEffectData(), FrozenCellEffectData(-1), ArrowLockCellEffectData(Direction.Left)]
    errors = messages(level)
    assert any("Hidden" in text for text in errors)
    assert any("non-negative" in text for text in errors)
    assert any("no blocker" in text for text in errors)


def test_gate_and_scissor_pairing_and_elevator_balance():
    level = base_level(); first = level.grid_cells[0]
    first.is_active = False
    first.effects = [KeyForLockedGateCellEffectData(LockKeyGate.Red), ScissorForWoolCrateCellEffectData(WoolCrateColor.Blue)]
    hidden = BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Green)
    level.obstacles = [
        LockedGateObstacleData(0, 0, 3, 1, LockKeyGate.Red),
        WoolCrateObstacleData(0, 0, 3, 1, [WoolCrateColor.Blue]),
        ElevatorObstacleData(0, 0, 3, 1, [ElevatorLayerData([hidden])]),
    ]
    level.pixel_grid = PixelGridData(
        9,
        1,
        [int(ItemColor.Red)] * 3 + [int(ItemColor.Blue)] * 3 + [int(ItemColor.Green)] * 3,
    )
    result = LevelValidator().validate(level)
    assert result.is_valid
    assert sum(level.source_histogram().values()) == 9


def test_elevator_requires_surface_anchor_and_non_overlapping_rects():
    level = base_level()
    hidden = BoxCellData(1, 1, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red)
    level.obstacles = [
        ElevatorObstacleData(0, 0, 3, 2, [ElevatorLayerData([hidden])]),
        ElevatorObstacleData(1, 0, 3, 2, []),
    ]
    errors = messages(level)
    assert any("surface box" in text for text in errors)
    assert any("overlaps" in text for text in errors)
