import json

import pytest

from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor, LockKeyGate, WoolCrateColor
from pixel_level_tool.domain.level_models import (
    ArrowLockCellEffectData,
    BoxCellData,
    ColorGateObstacleData,
    ElevatorLayerData,
    ElevatorObstacleData,
    FrozenCellEffectData,
    HiddenCellEffectData,
    KeyForLockedGateCellEffectData,
    LargeBlockObstacleData,
    LinkedContainerObstacleData,
    LockedGateObstacleData,
    PinsObstacleData,
    PixelGridData,
    PixelLevelData,
    ScissorForWoolCrateCellEffectData,
    WoolCrateObstacleData,
)
from pixel_level_tool.services.level_serializer import UnsupportedScopeError, dumps_level, level_from_dict


def make_full_level() -> PixelLevelData:
    first = BoxCellData(
        0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red, 10, False,
        [
            FrozenCellEffectData(2),
            HiddenCellEffectData(),
            ArrowLockCellEffectData(Direction.Right),
            KeyForLockedGateCellEffectData(LockKeyGate.Blue),
            ScissorForWoolCrateCellEffectData(WoolCrateColor.Green),
        ],
    )
    second = BoxCellData(3, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.DarkBlue, 20)
    hidden = BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Green, 0, True)
    return PixelLevelData(
        grid_rows=4,
        grid_cols=8,
        grid_cells=[second, first],
        pixel_grid=PixelGridData(9, 1, [7, 7, 7, 1, 1, 1, 3, 3, 3]),
        obstacles=[
            LinkedContainerObstacleData([first.internal_uid, second.internal_uid]),
            LargeBlockObstacleData(0, 0, 3, 1, 4),
            PinsObstacleData([first.internal_uid, second.internal_uid], Direction.Right),
            LockedGateObstacleData(0, 0, 3, 1, LockKeyGate.Blue, 2),
            WoolCrateObstacleData(0, 0, 3, 1, [WoolCrateColor.Green], 1),
            ColorGateObstacleData(3, 0, 3, 1, 5, ItemColor.DarkBlue),
            ElevatorObstacleData(0, 0, 3, 1, [ElevatorLayerData([hidden])]),
        ],
    )


def test_all_supported_effects_and_obstacles_round_trip_with_unity_types():
    written = json.loads(dumps_level(make_full_level()))
    effects = written["gridCells"][1]["effects"]
    assert [effect["$type"].split(".")[-1].split(",")[0] for effect in effects] == [
        "FrozenCellEffectData", "HiddenCellEffectData", "ArrowLockCellEffectData",
        "KeyForLockedGateCellEffectData", "ScissorForWoolCrateCellEffectData",
    ]
    assert [item["id"] for item in written["gridCells"]] == [301, 300]
    assert written["obstacles"][0]["targetIds"] == [300, 301]
    assert [item["id"] for item in written["obstacles"]] == [3001, 5001, 6001, 7001, 8001, 6501, 8501]
    assert written["obstacles"][-1]["layers"][0]["cells"][0]["id"] == 302

    loaded = level_from_dict(written)
    assert len(loaded.grid_cells[1].effects) == 5
    assert isinstance(loaded.obstacles[0], LinkedContainerObstacleData)
    assert isinstance(loaded.obstacles[-1], ElevatorObstacleData)
    assert json.loads(dumps_level(loaded))["obstacles"][0]["targetIds"] == [300, 301]


@pytest.mark.parametrize("type_name", [
    "NewRefactor.KeyForCargoCellEffectData, Assembly-CSharp",
    "NewRefactor.UnknownCellEffectData, Assembly-CSharp",
])
def test_unsupported_effects_fail_fast(type_name):
    data = json.loads(dumps_level(PixelLevelData(grid_cells=[BoxCellData(0, 0)])))
    data["gridCells"][0]["effects"] = [{"$type": type_name}]
    with pytest.raises(UnsupportedScopeError):
        level_from_dict(data)


def test_linked_cargo_fails_fast():
    level = PixelLevelData(grid_cells=[BoxCellData(0, 0)])
    data = json.loads(dumps_level(level))
    data["obstacles"] = [{"$type": "NewRefactor.LinkedCargoObstacleData, Assembly-CSharp", "targetIds": [], "id": 1}]
    with pytest.raises(UnsupportedScopeError, match="LinkedCargo"):
        level_from_dict(data)


def test_replace_color_updates_hidden_elevator_cells_and_color_gate():
    level = make_full_level()
    boxes, pixels = level.replace_color(ItemColor.Green, ItemColor.Yellow)
    assert boxes == 1
    assert pixels == 3
    assert level.obstacles[-1].layers[0].cells[0].color == ItemColor.Yellow
    level.obstacles[-2].required_color = ItemColor.Green
    level.replace_color(ItemColor.Green, ItemColor.Red)
    assert level.obstacles[-2].required_color == ItemColor.Red
