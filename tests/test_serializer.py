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
        "time",
        "piece",
        "gameMode",
        "difficulty",
        "themeId",
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
    assert data["gameMode"] == "Classic"
    assert data["difficulty"] == "Easy"
    assert data["themeId"] == "None"
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
    data["gameMode"] = "Classic"
    data["difficulty"] = "Hard"
    data["board"] = 4  # board lives under boxGrid; root value is ignored
    data["boxGrid"]["board"] = 4
    data["category"] = 11

    loaded = level_from_dict(data)
    written = json.loads(dumps_level(loaded))

    assert loaded.game_mode == 0
    assert loaded.difficulty == 2
    assert loaded.board == 4
    assert loaded.category == 11
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


# --------------------------------------------------------------------------- #
# A pixelGrid this format cannot read
# --------------------------------------------------------------------------- #
# Reading one as a *blank* picture is the worst thing to do with it: every caller
# downstream then complains about an empty picture instead of a file it could not
# read. A hand-made 25x25 template whose pixels sat under "colors" made Auto Gen
# Box say "Paint the pixel grid before generating boxes" about a fully painted
# level, and a folder run turned that into one "sinh box thất bại" row per file.
def _sized_grid_doc(pixel_grid: dict) -> dict:
    return {"pixelGrid": pixel_grid, "boxGrid": {}, "level": 21}


def test_a_pixel_grid_that_declares_a_size_must_carry_that_many_pixels():
    import pytest

    from pixel_level_tool.services.level_serializer import LevelSerializationError

    with pytest.raises(LevelSerializationError) as caught:
        level_from_dict(_sized_grid_doc({"width": 25, "height": 25, "colorIds": []}))

    assert "25x25 = 625 pixel" in str(caught.value)
    assert "0 colorIds" in str(caught.value)


def test_the_error_names_the_key_the_pixels_are_actually_under():
    import pytest

    from pixel_level_tool.services.level_serializer import LevelSerializationError

    with pytest.raises(LevelSerializationError) as caught:
        level_from_dict(
            _sized_grid_doc({"width": 5, "height": 5, "colors": [7] * 25})
        )

    message = str(caught.value)
    assert "'colors'" in message, "the fix is a rename, so the key has to be named"
    assert "colorIds" in message


def test_a_blank_canvas_of_a_real_size_still_round_trips():
    """The check must not reject the tool's own output: a blank grid is written full.

    `save_level` writes width*height EMPTY_COLOR_IDs for an unpainted canvas
    rather than omitting the key, which is what makes the rule above safe.
    """
    blank = PixelLevelData(pixel_grid=PixelGridData(25, 25))

    document = level_to_dict(blank)
    assert len(document["pixelGrid"]["colorIds"]) == 625

    back = level_from_dict(document)
    assert back.pixel_grid.width == 25 and back.pixel_grid.height == 25
    assert not back.pixel_grid.histogram(), "still blank, just not malformed"


def test_a_grid_with_no_size_is_left_alone():
    """A brand-new level has no size and no pixels, and that is not an error."""
    level = level_from_dict(_sized_grid_doc({"width": 0, "height": 0, "colorIds": []}))

    assert level.pixel_grid.width == 0
    assert level.pixel_grid.color_ids == []
