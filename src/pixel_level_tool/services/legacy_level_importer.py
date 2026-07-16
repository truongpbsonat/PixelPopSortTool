from __future__ import annotations

import json
from pathlib import Path

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID, ItemColor
from pixel_level_tool.domain.level_models import PixelGridData


class LegacyLevelImportError(ValueError):
    pass


def _object_field(data: dict[str, object], *names: str) -> object | None:
    for name in names:
        if name in data:
            return data[name]
    return None


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LegacyLevelImportError(f"{field} must be a positive integer.")
    return value


def legacy_pixel_grid_from_dict(data: dict[str, object]) -> PixelGridData:
    pixel_board = _object_field(data, "pixelBoard", "PixelBoard")
    if not isinstance(pixel_board, dict):
        raise LegacyLevelImportError("Legacy JSON does not contain a pixelBoard object.")

    dimensions = _object_field(pixel_board, "dimensions", "Dimensions")
    if not isinstance(dimensions, dict):
        raise LegacyLevelImportError("pixelBoard does not contain a dimensions object.")

    width = _positive_int(_object_field(dimensions, "cols", "Cols"), "pixelBoard.dimensions.cols")
    height = _positive_int(_object_field(dimensions, "rows", "Rows"), "pixelBoard.dimensions.rows")
    colors = _object_field(pixel_board, "colors", "Colors")
    if not isinstance(colors, list):
        raise LegacyLevelImportError("pixelBoard.colors must be an array.")

    expected = width * height
    if len(colors) != expected:
        raise LegacyLevelImportError(
            f"pixelBoard.colors contains {len(colors)} values; expected {expected} for a {width}x{height} grid."
        )

    for index, value in enumerate(colors):
        if isinstance(value, bool) or not isinstance(value, int):
            raise LegacyLevelImportError(f"pixelBoard.colors[{index}] must be an integer.")

    valid_color_ids = {int(color) for color in ItemColor}
    used_color_ids = {value for value in colors if value != 0 and value in valid_color_ids}
    available_color_ids = iter(sorted(valid_color_ids - used_color_ids))
    replacement_by_legacy_id: dict[int, int] = {}

    color_ids: list[int] = []
    for index, value in enumerate(colors):
        if value == 0:
            color_id = EMPTY_COLOR_ID
        elif value in valid_color_ids:
            color_id = value
        else:
            if value not in replacement_by_legacy_id:
                try:
                    replacement_by_legacy_id[value] = next(available_color_ids)
                except StopIteration as exc:
                    raise LegacyLevelImportError(
                        "Not enough unused current colors to replace all unsupported "
                        f"legacy color ids (cannot replace {value} at pixelBoard.colors[{index}])."
                    ) from exc
            color_id = replacement_by_legacy_id[value]
        color_ids.append(color_id)

    return PixelGridData(width=width, height=height, color_ids=color_ids)


def import_legacy_pixel_grid(path: str | Path) -> PixelGridData:
    try:
        with Path(path).open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LegacyLevelImportError(f"Could not read legacy JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise LegacyLevelImportError("Legacy JSON root must be an object.")
    return legacy_pixel_grid_from_dict(data)
