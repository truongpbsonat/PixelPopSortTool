import json

from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor
from pixel_level_tool.domain.level_models import BoxCellData, FrozenCellEffectData, PixelGridData, PixelLevelData, TunnelCellData
from pixel_level_tool.services.level_serializer import CELL_TYPE_NAME, TUNNEL_TYPE_NAME, dumps_level, level_from_dict, level_to_dict


def make_level():
    return PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        level=1,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red)],
        pixel_grid=PixelGridData(3, 1, [7, 7, 7]),
    )


def test_serializer_writes_unity_type_and_int_enums():
    content = dumps_level(make_level())
    data = json.loads(content)
    cell = data["gridCells"][0]
    assert cell["$type"] == CELL_TYPE_NAME
    assert cell["shape"] == 3
    assert cell["direction"] == 0
    assert cell["colorList"] == [7]
    assert cell["effects"] is None
    assert data["gridLanes"] == []
    assert data["obstacles"] == []
    assert '"colorList": [7]' in content


def test_round_trip_preserves_core_data():
    data = json.loads(dumps_level(make_level()))
    loaded = level_from_dict(data)
    assert loaded.pixel_grid.color_ids == [7, 7, 7]
    assert loaded.grid_cells[0].shape == CellShape.Rectangle_3x1


def test_load_allows_missing_pixel_grid():
    data = json.loads(dumps_level(make_level()))
    del data["pixelGrid"]

    loaded = level_from_dict(data)

    assert loaded.pixel_grid.width == 8
    assert loaded.pixel_grid.height == 8
    assert len(loaded.pixel_grid.color_ids) == 64
    assert loaded.grid_cells[0].shape == CellShape.Rectangle_3x1


def test_load_and_save_preserve_cargo_grid_lanes():
    data = json.loads(dumps_level(make_level()))
    data["gridLanes"] = [{"laneId": 1, "cells": [0, 1]}]

    loaded = level_from_dict(data)
    written = json.loads(dumps_level(loaded))

    assert loaded.grid_lanes == data["gridLanes"]
    assert written["gridLanes"] == data["gridLanes"]


def test_load_preserves_typed_cell_effects():
    data = json.loads(dumps_level(make_level()))
    data["gridCells"][0]["effects"] = [{"$type": "NewRefactor.FrozenCellEffectData, Assembly-CSharp", "frozenCount": 2}]

    loaded = level_from_dict(data)
    written = json.loads(dumps_level(loaded))

    assert loaded.grid_cells[0].effects == [FrozenCellEffectData(2)]
    assert written["gridCells"][0]["effects"][0]["frozenCount"] == 2


def test_load_preserves_supported_root_metadata():
    data = json.loads(dumps_level(make_level()))
    data["gameMode"] = 7
    data["mapType"] = 9
    data["board"] = 4
    data["difficulty"] = 2
    data["category"] = 11

    loaded = level_from_dict(data)
    written = json.loads(dumps_level(loaded))

    assert loaded.game_mode == 7
    assert loaded.level_grid_version == 1
    assert loaded.map_type == 9
    assert loaded.board == 4
    assert loaded.difficulty == 2
    assert loaded.category == 11
    assert written["gameMode"] == 7
    assert written["levelGridVersion"] == 1
    assert written["mapType"] == 9
    assert written["board"] == 4
    assert written["difficulty"] == 2
    assert written["category"] == 11


def test_load_and_save_preserve_any_grid_version():
    data = json.loads(dumps_level(make_level()))
    data["levelGridVersion"] = 3

    loaded = level_from_dict(data)
    written = json.loads(dumps_level(loaded))

    assert loaded.level_grid_version == 3
    assert written["levelGridVersion"] == 3


def test_tunnel_cell_round_trip_preserves_color_direction_and_stored_cells():
    data = json.loads(dumps_level(make_level()))
    stored = {
        "$type": CELL_TYPE_NAME,
        "colorList": [int(ItemColor.Green)],
        "effects": [{"$type": "NewRefactor.FrozenCellEffectData, Assembly-CSharp", "frozenCount": 2}],
        "gridX": 0,
        "gridY": 0,
        "shape": int(CellShape.Rectangle_3x1),
        "direction": int(Direction.Up),
        "id": 171,
        "isActive": True,
    }
    tunnel = {
        "$type": TUNNEL_TYPE_NAME,
        "color": int(ItemColor.DarkBlue),
        "storedCells": [stored],
        "gridX": 1,
        "gridY": 1,
        "shape": int(CellShape.Square_3x3),
        "direction": int(Direction.Right),
        "id": 17,
        "isActive": True,
    }
    data["gridCells"] = [tunnel]

    loaded = level_from_dict(data)
    written = level_to_dict(loaded, assign_ids=False)["gridCells"][0]

    assert isinstance(loaded.grid_cells[0], TunnelCellData)
    assert loaded.grid_cells[0].color == ItemColor.DarkBlue
    assert loaded.grid_cells[0].direction == Direction.Right
    assert loaded.grid_cells[0].stored_cells[0].effects == [FrozenCellEffectData(2)]
    assert written == tunnel


def test_tunnel_source_histogram_uses_stored_cell_colors():
    tunnel = TunnelCellData(
        0,
        0,
        CellShape.Square_3x3,
        Direction.Up,
        ItemColor.DarkBlue,
        stored_cells=[
            BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red),
            BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Green),
        ],
    )
    level = PixelLevelData(grid_cells=[tunnel])

    assert level.source_histogram() == {int(ItemColor.Red): 3, int(ItemColor.Green): 3}
