import json
from collections import Counter

import pytest

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID
from pixel_level_tool.services.legacy_level_importer import (
    LegacyLevelImportError,
    import_legacy_pixel_grid,
    legacy_pixel_grid_from_dict,
)


def test_imports_legacy_colors_as_row_major_pixel_grid(tmp_path):
    path = tmp_path / "old-level.json"
    path.write_text(
        json.dumps(
            {
                "level": 3,
                "pixelBoard": {
                    "dimensions": {"cols": 3, "rows": 2},
                    "colors": [0, 2, 8, 12, 14, 0],
                },
            }
        ),
        encoding="utf-8",
    )

    grid = import_legacy_pixel_grid(path)

    assert grid.width == 3
    assert grid.height == 2
    assert grid.color_ids == [EMPTY_COLOR_ID, 2, 8, 12, 14, EMPTY_COLOR_ID]


def test_accepts_pascal_case_legacy_fields():
    grid = legacy_pixel_grid_from_dict(
        {"PixelBoard": {"Dimensions": {"Cols": 2, "Rows": 1}, "Colors": [0, 1]}}
    )

    assert grid.color_ids == [EMPTY_COLOR_ID, 1]


def test_rejects_color_count_that_does_not_match_dimensions():
    with pytest.raises(LegacyLevelImportError, match="expected 4"):
        legacy_pixel_grid_from_dict(
            {"pixelBoard": {"dimensions": {"cols": 2, "rows": 2}, "colors": [0, 2, 3]}}
        )


def test_replaces_unsupported_color_with_unused_current_color():
    grid = legacy_pixel_grid_from_dict(
        {
            "pixelBoard": {
                "dimensions": {"cols": 6, "rows": 1},
                "colors": [99, 2, 100, 99, 1, 100],
            }
        }
    )

    assert grid.color_ids == [0, 2, 3, 0, 1, 3]


def test_replacement_reserves_valid_colors_even_when_they_appear_later():
    grid = legacy_pixel_grid_from_dict(
        {"pixelBoard": {"dimensions": {"cols": 2, "rows": 1}, "colors": [99, 1]}}
    )

    assert grid.color_ids == [0, 1]


def test_rejects_when_there_are_not_enough_unused_current_colors():
    colors = [*range(1, 17), 99, 100]

    with pytest.raises(LegacyLevelImportError, match="Not enough unused current colors"):
        legacy_pixel_grid_from_dict(
            {
                "pixelBoard": {
                    "dimensions": {"cols": len(colors), "rows": 1},
                    "colors": colors,
                }
            }
        )


def test_imports_sparse_map_array_as_row_major_pixel_grid():
    grid = legacy_pixel_grid_from_dict(
        {
            "map": [
                {"r": 0, "c": 0, "color": 2},
                {"r": 0, "c": 2, "color": 8},
                {"r": 1, "c": 1, "color": 12},
            ]
        }
    )

    assert grid.width == 3
    assert grid.height == 2
    assert grid.color_ids == [2, EMPTY_COLOR_ID, 8, EMPTY_COLOR_ID, 12, EMPTY_COLOR_ID]


def test_sparse_map_replaces_unsupported_color_with_unused_current_color():
    grid = legacy_pixel_grid_from_dict(
        {
            "map": [
                {"r": 0, "c": 0, "color": 99},
                {"r": 0, "c": 1, "color": 2},
                {"r": 0, "c": 2, "color": 99},
            ]
        }
    )

    assert grid.color_ids == [0, 2, 0]


def test_sparse_map_requires_at_least_one_cell():
    with pytest.raises(LegacyLevelImportError, match="at least one cell"):
        legacy_pixel_grid_from_dict({"map": []})


def test_rejects_when_no_known_picture_shape_is_present():
    with pytest.raises(LegacyLevelImportError, match="pixelBoard object, a pixelGrid object"):
        legacy_pixel_grid_from_dict({"level": 1})


# --------------------------------------------------------------------------- #
# The pixelGrid export: dense, row-major, -1 for empty, palette past ItemColor
# --------------------------------------------------------------------------- #
def test_imports_the_pixel_grid_shape_with_width_and_height():
    grid = legacy_pixel_grid_from_dict(
        {"pixelGrid": {"width": 3, "height": 2, "colors": [-1, 2, 8, 12, 14, -1]}}
    )

    assert (grid.width, grid.height) == (3, 2)
    assert grid.color_ids == [EMPTY_COLOR_ID, 2, 8, 12, 14, EMPTY_COLOR_ID]


def test_pixel_grid_treats_minus_one_as_empty_and_zero_as_a_real_colour():
    """The older shapes write 0 for empty; this one writes -1, so 0 is Red."""
    grid = legacy_pixel_grid_from_dict(
        {"pixelGrid": {"width": 2, "height": 1, "colors": [0, -1]}}
    )

    assert grid.color_ids == [0, EMPTY_COLOR_ID]


def test_pixel_grid_folds_colours_past_the_current_palette_onto_free_ids():
    """These exports carry ids like 17/18/23; the picture must survive them."""
    grid = legacy_pixel_grid_from_dict(
        {"pixelGrid": {"width": 4, "height": 1, "colors": [3, 17, 18, 23]}}
    )

    assert grid.color_ids[0] == 3, "an id the palette already has is left alone"
    folded = grid.color_ids[1:]
    assert all(0 <= value <= 16 for value in folded)
    assert len(set(folded)) == 3, "two legacy colours must never merge into one"
    assert 3 not in folded, "a colour already in use cannot be handed out again"


def test_pixel_grid_accepts_the_editors_own_colour_ids_key():
    grid = legacy_pixel_grid_from_dict(
        {"pixelGrid": {"width": 2, "height": 1, "colorIds": [4, -1]}}
    )

    assert grid.color_ids == [4, EMPTY_COLOR_ID]


def test_pixel_grid_rejects_a_colour_count_that_does_not_match_its_size():
    with pytest.raises(LegacyLevelImportError, match="expected 6"):
        legacy_pixel_grid_from_dict(
            {"pixelGrid": {"width": 3, "height": 2, "colors": [1, 2, 3]}}
        )


def test_pixel_board_still_wins_when_a_file_carries_both_shapes():
    grid = legacy_pixel_grid_from_dict(
        {
            "pixelBoard": {"dimensions": {"cols": 1, "rows": 1}, "colors": [4]},
            "pixelGrid": {"width": 2, "height": 1, "colors": [5, 6]},
        }
    )

    assert (grid.width, grid.height) == (1, 1)


def test_a_real_pixel_grid_export_keeps_its_shape_and_its_colour_counts(tmp_path):
    """Level 5 as the game exports it: 21x25, 447 painted cells, palette to 23.

    Nothing about the picture may move. The empty cells have to land in exactly
    the same places, no two source colours may collapse into one, and every
    colour has to keep its pixel count - that count is what decides how many
    boxes the picture is worth.
    """
    source = [-1] * 21 + [-1, 13] + [18] * 17 + [13, -1]
    source += [3, 17, 23, 0] * 5 + [7] * 22
    width, height = 21, len(source) // 21
    source = source[: width * height]
    path = tmp_path / "5.json"
    path.write_text(
        json.dumps(
            {
                "level": 5,
                "piece": 5,
                "pixelGrid": {"width": width, "height": height, "colors": source},
                "gridBoard": {"columns": 3, "rows": 7, "cells": []},
            }
        ),
        encoding="utf-8",
    )

    grid = import_legacy_pixel_grid(path)

    assert (grid.width, grid.height) == (width, height)
    holes = [index for index, value in enumerate(source) if value == -1]
    assert [
        index for index, value in enumerate(grid.color_ids) if value == EMPTY_COLOR_ID
    ] == holes

    mapping = {
        value: grid.color_ids[index]
        for index, value in enumerate(source)
        if value != -1
    }
    assert len(set(mapping.values())) == len(mapping), "colours must stay distinct"
    assert Counter(source).pop(-1) == len(holes)
    assert sorted(Counter(v for v in source if v != -1).values()) == sorted(
        Counter(v for v in grid.color_ids if v != EMPTY_COLOR_ID).values()
    )
