import json

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


def test_rejects_unsupported_color_id():
    with pytest.raises(LegacyLevelImportError, match="unsupported color id 99"):
        legacy_pixel_grid_from_dict(
            {"pixelBoard": {"dimensions": {"cols": 1, "rows": 1}, "colors": [99]}}
        )
