import json

import pytest

from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor
from pixel_level_tool.domain.level_models import BoxCellData, PixelGridData, PixelLevelData
from pixel_level_tool.services.level_serializer import CELL_TYPE_NAME, UnsupportedScopeError, dumps_level, level_from_dict


def make_level():
    return PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        level=1,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red)],
        pixel_grid=PixelGridData(3, 1, [0, 0, 0]),
    )


def test_serializer_writes_unity_type_and_int_enums():
    content = dumps_level(make_level())
    data = json.loads(content)
    cell = data["gridCells"][0]
    assert cell["$type"] == CELL_TYPE_NAME
    assert cell["shape"] == 3
    assert cell["direction"] == 0
    assert cell["colorList"] == [0]
    assert cell["effects"] is None
    assert data["gridLanes"] == []
    assert data["obstacles"] == []
    assert '"colorList": [0]' in content


def test_round_trip_preserves_core_data():
    data = json.loads(dumps_level(make_level()))
    loaded = level_from_dict(data)
    assert loaded.pixel_grid.color_ids == [0, 0, 0]
    assert loaded.grid_cells[0].shape == CellShape.Rectangle_3x1


def test_load_allows_missing_pixel_grid():
    data = json.loads(dumps_level(make_level()))
    del data["pixelGrid"]

    loaded = level_from_dict(data)

    assert loaded.pixel_grid.width == 8
    assert loaded.pixel_grid.height == 8
    assert len(loaded.pixel_grid.color_ids) == 64
    assert loaded.grid_cells[0].shape == CellShape.Rectangle_3x1


def test_save_clears_grid_lanes_loaded_from_existing_level():
    data = json.loads(dumps_level(make_level()))
    data["gridLanes"] = [{"laneId": 1, "cells": [0, 1]}]

    loaded = level_from_dict(data)
    written = json.loads(dumps_level(loaded))

    assert loaded.grid_lanes == [{"laneId": 1, "cells": [0, 1]}]
    assert written["gridLanes"] == []


def test_load_preserves_cell_effects():
    data = json.loads(dumps_level(make_level()))
    data["gridCells"][0]["effects"] = [{"type": "ice", "value": 2}]

    loaded = level_from_dict(data)
    written = json.loads(dumps_level(loaded))

    assert loaded.grid_cells[0].effects == [{"type": "ice", "value": 2}]
    assert written["gridCells"][0]["effects"] == [{"type": "ice", "value": 2}]


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


def test_load_rejects_unsupported_grid_version():
    data = json.loads(dumps_level(make_level()))
    data["levelGridVersion"] = 0

    with pytest.raises(UnsupportedScopeError):
        level_from_dict(data)
