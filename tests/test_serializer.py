import json

from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor
from pixel_level_tool.domain.level_models import BoxCellData, FrozenCellEffectData, PixelGridData, PixelLevelData, TunnelCellData
from pixel_level_tool.services.level_serializer import dumps_level, level_from_dict, level_to_dict


def make_level():
    return PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        level=1,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red)],
        pixel_grid=PixelGridData(3, 1, [int(ItemColor.Red)] * 3),
    )


def test_serializer_writes_new_pop_sort_2_format():
    content = dumps_level(make_level())
    data = json.loads(content)

    # Nested boxGrid / pixelGrid, no $type anywhere, no dropped legacy root keys.
    assert set(data) == {
        "pixelGrid",
        "boxGrid",
        "mapType",
        "time",
        "piece",
        "gameMode",
        "difficulty",
        "level",
        "category",
        "mechanics",
    }
    assert "$type" not in content
    for dropped in ("levelName", "levelGridVersion", "gridLanes", "gridRows", "gridCols"):
        assert dropped not in data

    box_grid = data["boxGrid"]
    assert box_grid["gridRows"] == 3
    assert box_grid["gridCols"] == 3
    assert box_grid["board"] == 1
    assert box_grid["obstacles"] == []

    cell = box_grid["gridCells"][0]
    assert cell["type"] == "Normal"
    assert cell["shape"] == "Rectangle_3x1"
    assert cell["direction"] == "Up"
    assert cell["colorList"] == ["Red"]
    assert cell["effects"] is None

    assert data["pixelGrid"]["colorIds"] == [int(ItemColor.Red)] * 3
    assert data["mapType"] == "None"
    assert data["gameMode"] == "Classic"
    assert data["difficulty"] == "Easy"
    assert data["mechanics"] == []
    assert data["time"] == 60
    assert data["piece"] == 5
    # colorList collapses onto one line; colorIds stays one value per line.
    assert '"colorList": ["Red"]' in content


def test_time_and_piece_round_trip():
    level = make_level()
    level.time = 45
    level.piece = 7
    loaded = level_from_dict(json.loads(dumps_level(level)))
    assert loaded.time == 45
    assert loaded.piece == 7


def test_load_defaults_time_and_piece_when_absent():
    data = json.loads(dumps_level(make_level()))
    del data["time"]
    del data["piece"]
    loaded = level_from_dict(data)
    assert loaded.time == 60
    assert loaded.piece == 5


def test_round_trip_preserves_core_data():
    data = json.loads(dumps_level(make_level()))
    loaded = level_from_dict(data)
    assert loaded.pixel_grid.color_ids == [int(ItemColor.Red)] * 3
    assert loaded.grid_cells[0].shape == CellShape.Rectangle_3x1
    assert loaded.grid_cells[0].color == ItemColor.Red


def test_load_allows_missing_pixel_grid():
    data = json.loads(dumps_level(make_level()))
    del data["pixelGrid"]

    loaded = level_from_dict(data)

    assert loaded.pixel_grid.width == 8
    assert loaded.pixel_grid.height == 8
    assert len(loaded.pixel_grid.color_ids) == 64
    assert loaded.grid_cells[0].shape == CellShape.Rectangle_3x1


def test_load_defaults_when_box_grid_absent():
    data = json.loads(dumps_level(make_level()))
    del data["boxGrid"]

    loaded = level_from_dict(data)

    assert loaded.grid_rows == 10
    assert loaded.grid_cols == 10
    assert loaded.grid_cells == []


def test_load_preserves_root_metadata_names():
    data = json.loads(dumps_level(make_level()))
    data["mapType"] = "Map3"
    data["gameMode"] = "Classic"
    data["difficulty"] = "Hard"
    data["board"] = 4  # board lives under boxGrid; root value is ignored
    data["boxGrid"]["board"] = 4
    data["category"] = 11

    loaded = level_from_dict(data)
    written = json.loads(dumps_level(loaded))

    assert loaded.map_type == 3
    assert loaded.game_mode == 0
    assert loaded.difficulty == 2
    assert loaded.board == 4
    assert loaded.category == 11
    assert written["mapType"] == "Map3"
    assert written["gameMode"] == "Classic"
    assert written["difficulty"] == "Hard"
    assert written["boxGrid"]["board"] == 4
    assert written["category"] == 11


def test_mechanics_round_trip():
    level = make_level()
    level.mechanics = ["frozen", "hidden"]
    loaded = level_from_dict(json.loads(dumps_level(level)))
    assert loaded.mechanics == ["frozen", "hidden"]


def test_is_active_forced_false_on_load():
    data = json.loads(dumps_level(make_level()))
    assert data["boxGrid"]["gridCells"][0]["isActive"] is True
    loaded = level_from_dict(data)
    assert loaded.grid_cells[0].is_active is False


def test_tunnel_cell_round_trip_preserves_color_direction_and_stored_cells():
    data = json.loads(dumps_level(make_level()))
    stored = {
        "type": "Normal",
        "colorList": ["Green"],
        "effects": [{"type": "Frozen", "frozenCount": 2}],
        "gridX": 0,
        "gridY": 0,
        "shape": "Rectangle_3x1",
        "direction": "Up",
        "id": 171,
        "isActive": True,
    }
    tunnel = {
        "type": "Tunnel",
        "color": "Blue",
        "storedCells": [stored],
        "gridX": 1,
        "gridY": 1,
        "shape": "Square_3x3",
        "direction": "Right",
        "id": 17,
        "isActive": True,
    }
    data["boxGrid"]["gridCells"] = [tunnel]

    loaded = level_from_dict(data)
    written = level_to_dict(loaded, assign_ids=False)["boxGrid"]["gridCells"][0]

    assert isinstance(loaded.grid_cells[0], TunnelCellData)
    assert loaded.grid_cells[0].color == ItemColor.Blue
    assert loaded.grid_cells[0].direction == Direction.Right
    assert loaded.grid_cells[0].stored_cells[0].effects == [FrozenCellEffectData(2)]
    # isActive is always forced to False on load, regardless of the saved value.
    expected = {**tunnel, "isActive": False, "storedCells": [{**stored, "isActive": False}]}
    assert written == expected


def test_tunnel_source_histogram_uses_stored_cell_colors():
    tunnel = TunnelCellData(
        0,
        0,
        CellShape.Square_3x3,
        Direction.Up,
        ItemColor.Blue,
        stored_cells=[
            BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red),
            BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Green),
        ],
    )
    level = PixelLevelData(grid_cells=[tunnel])

    assert level.source_histogram() == {int(ItemColor.Red): 3, int(ItemColor.Green): 3}
