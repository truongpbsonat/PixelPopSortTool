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


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LegacyLevelImportError(f"{field} must be a non-negative integer.")
    return value


class _LegacyColorRemapper:
    """Maps legacy color ids onto the current ``ItemColor`` ids.

    ``0`` is treated as empty. Ids that already match a current ``ItemColor``
    pass through unchanged. Unrecognized ids are assigned an unused current
    color id on first sight, so the same legacy id always resolves the same way.
    """

    def __init__(self, raw_values: list[int]) -> None:
        self._valid_color_ids = {int(color) for color in ItemColor}
        used = {value for value in raw_values if value != 0 and value in self._valid_color_ids}
        self._available = iter(sorted(self._valid_color_ids - used))
        self._replacement_by_legacy_id: dict[int, int] = {}

    def resolve(self, value: int, error: str) -> int:
        if value == 0:
            return EMPTY_COLOR_ID
        if value in self._valid_color_ids:
            return value
        if value not in self._replacement_by_legacy_id:
            try:
                self._replacement_by_legacy_id[value] = next(self._available)
            except StopIteration as exc:
                raise LegacyLevelImportError(error) from exc
        return self._replacement_by_legacy_id[value]


def _pixel_grid_from_pixel_board(pixel_board: dict[str, object]) -> PixelGridData:
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

    remapper = _LegacyColorRemapper(colors)
    color_ids = [
        remapper.resolve(
            value,
            "Not enough unused current colors to replace all unsupported "
            f"legacy color ids (cannot replace {value} at pixelBoard.colors[{index}]).",
        )
        for index, value in enumerate(colors)
    ]

    return PixelGridData(width=width, height=height, color_ids=color_ids)


def _pixel_grid_from_sparse_map(entries: list[object]) -> PixelGridData:
    if not entries:
        raise LegacyLevelImportError("map must contain at least one cell.")

    cells: list[tuple[int, int, int]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise LegacyLevelImportError(f"map[{index}] must be an object.")
        row = _non_negative_int(_object_field(entry, "r", "R"), f"map[{index}].r")
        column = _non_negative_int(_object_field(entry, "c", "C"), f"map[{index}].c")
        color = _object_field(entry, "color", "Color")
        if isinstance(color, bool) or not isinstance(color, int):
            raise LegacyLevelImportError(f"map[{index}].color must be an integer.")
        cells.append((row, column, color))

    width = max(column for _, column, _ in cells) + 1
    height = max(row for row, _, _ in cells) + 1

    remapper = _LegacyColorRemapper([color for _, _, color in cells])
    color_ids = [EMPTY_COLOR_ID] * (width * height)
    for index, (row, column, color) in enumerate(cells):
        color_ids[row * width + column] = remapper.resolve(
            color,
            "Not enough unused current colors to replace all unsupported "
            f"legacy color ids (cannot replace {color} at map[{index}] (r={row}, c={column})).",
        )

    return PixelGridData(width=width, height=height, color_ids=color_ids)


def legacy_pixel_grid_from_dict(data: dict[str, object]) -> PixelGridData:
    pixel_board = _object_field(data, "pixelBoard", "PixelBoard")
    if isinstance(pixel_board, dict):
        return _pixel_grid_from_pixel_board(pixel_board)

    sparse_map = _object_field(data, "map", "Map")
    if isinstance(sparse_map, list):
        return _pixel_grid_from_sparse_map(sparse_map)

    raise LegacyLevelImportError("Legacy JSON does not contain a pixelBoard object or a map array.")


def import_legacy_pixel_grid(path: str | Path) -> PixelGridData:
    try:
        with Path(path).open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LegacyLevelImportError(f"Could not read legacy JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise LegacyLevelImportError("Legacy JSON root must be an object.")
    return legacy_pixel_grid_from_dict(data)
