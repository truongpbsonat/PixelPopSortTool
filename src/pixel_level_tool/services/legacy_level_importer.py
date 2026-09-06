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

    Ids that already match a current ``ItemColor`` pass through unchanged.
    Unrecognized ids are assigned an unused current color id on first sight, so
    the same legacy id always resolves the same way and the picture keeps its
    shape even when its palette does not survive.

    ``empty`` is the value that means "no pixel here", and it differs by export:
    the oldest ``pixelBoard`` and ``map`` shapes write ``0``, while the
    ``pixelGrid`` shape already uses ``-1`` like the current files - so there
    ``0`` is a real color (Red) and must not be swallowed.
    """

    def __init__(self, raw_values: list[int], *, empty: int = 0) -> None:
        self._empty = empty
        self._valid_color_ids = {int(color) for color in ItemColor}
        used = {value for value in raw_values if value != empty and value in self._valid_color_ids}
        self._available = iter(sorted(self._valid_color_ids - used))
        self._replacement_by_legacy_id: dict[int, int] = {}

    def resolve(self, value: int, error: str) -> int:
        if value == self._empty:
            return EMPTY_COLOR_ID
        if value in self._valid_color_ids:
            return value
        if value not in self._replacement_by_legacy_id:
            try:
                self._replacement_by_legacy_id[value] = next(self._available)
            except StopIteration as exc:
                raise LegacyLevelImportError(error) from exc
        return self._replacement_by_legacy_id[value]

    @property
    def remapped(self) -> dict[int, int]:
        """Legacy id -> current id, for the ids that had no current equivalent."""
        return dict(self._replacement_by_legacy_id)


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


def _pixel_grid_from_pixel_grid(pixel_grid: dict[str, object]) -> PixelGridData:
    """The ``pixelGrid`` export: ``width``/``height`` plus one dense colour array.

    This shape is already row-major and already writes ``-1`` for an empty cell,
    so the only thing standing between it and the editor is its palette: these
    exports carry colour ids past the end of the current :class:`ItemColor`
    (17, 18, 23 and so on), which get folded onto free current ids.

    The box side of the same file (``gridBoard``) is deliberately not read. Its
    boxes carry a per-box ``capacity`` anywhere from 8 to 54 balls, and the
    editor only builds ``Square_3x3`` boxes of exactly nine, so importing them
    would mean inventing a box grid that is not the one in the file. The picture
    is lossless; the boxes would not be, and Auto Gen Box rebuilds them anyway.
    """
    width = _positive_int(_object_field(pixel_grid, "width", "Width"), "pixelGrid.width")
    height = _positive_int(_object_field(pixel_grid, "height", "Height"), "pixelGrid.height")
    # "colors" is what these exports write; "colorIds" is what the editor writes,
    # and accepting both means a current file can be imported as a picture too.
    colors = _object_field(pixel_grid, "colors", "Colors", "colorIds", "ColorIds")
    if not isinstance(colors, list):
        raise LegacyLevelImportError("pixelGrid.colors must be an array.")

    expected = width * height
    if len(colors) != expected:
        raise LegacyLevelImportError(
            f"pixelGrid.colors contains {len(colors)} values; expected {expected} "
            f"for a {width}x{height} grid."
        )

    for index, value in enumerate(colors):
        if isinstance(value, bool) or not isinstance(value, int):
            raise LegacyLevelImportError(f"pixelGrid.colors[{index}] must be an integer.")

    remapper = _LegacyColorRemapper(colors, empty=EMPTY_COLOR_ID)
    color_ids = [
        remapper.resolve(
            value,
            "Not enough unused current colors to replace all unsupported "
            f"legacy color ids (cannot replace {value} at pixelGrid.colors[{index}]).",
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

    pixel_grid = _object_field(data, "pixelGrid", "PixelGrid")
    if isinstance(pixel_grid, dict):
        return _pixel_grid_from_pixel_grid(pixel_grid)

    sparse_map = _object_field(data, "map", "Map")
    if isinstance(sparse_map, list):
        return _pixel_grid_from_sparse_map(sparse_map)

    raise LegacyLevelImportError(
        "Legacy JSON does not contain a pixelBoard object, a pixelGrid object or a map array."
    )


def import_legacy_pixel_grid(path: str | Path) -> PixelGridData:
    try:
        with Path(path).open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LegacyLevelImportError(f"Could not read legacy JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise LegacyLevelImportError("Legacy JSON root must be an object.")
    return legacy_pixel_grid_from_dict(data)
