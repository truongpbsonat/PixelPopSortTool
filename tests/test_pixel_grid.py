from pixel_level_tool.domain.enums import EMPTY_COLOR_ID, ItemColor
from pixel_level_tool.domain.level_models import PixelGridData


def test_row_major_index_and_top_row():
    grid = PixelGridData(3, 2, [0, 1, 2, 3, 4, 5])
    assert grid.index(0, 0) == 0
    assert grid.index(1, 0) == 3
    assert grid.get_color_id(0, 2) == 2


def test_paint_erase_resize_preserves_top_left():
    grid = PixelGridData(2, 2, [0, 1, 2, 3])
    grid.set_color_id(0, 1, int(ItemColor.Cyan))
    assert grid.get_color_id(0, 1) == int(ItemColor.Cyan)
    grid.set_color_id(0, 1, EMPTY_COLOR_ID)
    assert grid.get_color_id(0, 1) == EMPTY_COLOR_ID
    grid.resize(3, 3)
    assert grid.color_ids == [0, EMPTY_COLOR_ID, -1, 2, 3, -1, -1, -1, -1]


def test_trim_empty_borders_keeps_empty_rows_and_columns_inside_content():
    empty = EMPTY_COLOR_ID
    grid = PixelGridData(
        6,
        6,
        [
            empty, empty, empty, empty, empty, empty,
            empty, empty, empty, empty, empty, empty,
            empty, 1, empty, empty, 2, empty,
            empty, empty, empty, empty, empty, empty,
            empty, empty, 3, empty, empty, empty,
            empty, empty, empty, empty, empty, empty,
        ],
    )

    assert grid.trim_empty_borders()
    assert (grid.width, grid.height) == (4, 3)
    assert grid.color_ids == [
        1, empty, empty, 2,
        empty, empty, empty, empty,
        empty, 3, empty, empty,
    ]


def test_trim_empty_borders_leaves_fully_empty_grid_unchanged():
    grid = PixelGridData(3, 2)

    assert not grid.trim_empty_borders()
    assert (grid.width, grid.height) == (3, 2)
    assert grid.color_ids == [EMPTY_COLOR_ID] * 6


def test_replace_color_changes_all_matching_pixels_only():
    grid = PixelGridData(5, 1, [0, 1, 0, EMPTY_COLOR_ID, 2])

    assert grid.replace_color(ItemColor.Red, ItemColor.Cyan) == 2
    assert grid.color_ids == [9, 1, 9, EMPTY_COLOR_ID, 2]
