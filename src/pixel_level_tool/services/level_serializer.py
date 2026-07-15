from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor
from pixel_level_tool.domain.level_models import BoxCellData, PixelGridData, PixelLevelData


CELL_TYPE_NAME = "NewRefactor.CellData, Assembly-CSharp"
ROOT_KEYS = {
    "pixelGrid",
    "levelGridVersion",
    "levelName",
    "mapType",
    "gridRows",
    "gridCols",
    "board",
    "gridCells",
    "gridLanes",
    "obstacles",
    "gameMode",
    "difficulty",
    "level",
    "category",
}

_COLOR_LIST_BLOCK_PATTERN = re.compile(r'(?m)^(\s*"colorList": )\[\n((?:\s+-?\d+,?\n)+)\s*\]')


class LevelSerializationError(ValueError):
    pass


class UnsupportedScopeError(LevelSerializationError):
    pass


def cell_to_dict(cell: BoxCellData) -> dict[str, Any]:
    return {
        "$type": CELL_TYPE_NAME,
        "colorList": [int(cell.color)],
        "effects": cell.effects,
        "gridX": cell.grid_x,
        "gridY": cell.grid_y,
        "shape": int(cell.shape),
        "direction": int(cell.direction),
        "id": cell.id,
        "isActive": cell.is_active,
    }


def level_to_dict(level: PixelLevelData, *, assign_ids: bool = True) -> dict[str, Any]:
    snapshot = level.clone()
    if assign_ids:
        snapshot.assign_deterministic_ids()
    data: dict[str, Any] = dict(snapshot.extra_fields)
    data.update(
        {
            "pixelGrid": {
                "width": snapshot.pixel_grid.width,
                "height": snapshot.pixel_grid.height,
                "colorIds": list(snapshot.pixel_grid.color_ids),
                "modifiers": [],
                "obstacles": [],
            },
            "levelGridVersion": snapshot.level_grid_version,
            "levelName": snapshot.level_name,
            "mapType": snapshot.map_type,
            "gridRows": snapshot.grid_rows,
            "gridCols": snapshot.grid_cols,
            "board": snapshot.board,
            "gridCells": [cell_to_dict(cell) for cell in snapshot.grid_cells],
            "gridLanes": [],
            "obstacles": list(snapshot.obstacles),
            "gameMode": snapshot.game_mode,
            "difficulty": snapshot.difficulty,
            "level": snapshot.level,
            "category": snapshot.category,
        }
    )
    return data


def _require_int_enum(enum_type: type, value: object, field: str) -> Any:
    try:
        return enum_type(int(value))
    except (TypeError, ValueError) as exc:
        raise LevelSerializationError(f"Invalid {field}: {value!r}") from exc


def cell_from_dict(data: dict[str, Any]) -> BoxCellData:
    type_name = data.get("$type")
    if type_name != CELL_TYPE_NAME:
        raise UnsupportedScopeError(f"Unsupported grid cell type: {type_name!r}")
    colors = data.get("colorList")
    if not isinstance(colors, list) or len(colors) != 1:
        raise UnsupportedScopeError("Pixel-only cells must contain exactly one color in colorList.")
    return BoxCellData(
        grid_x=int(data.get("gridX", 0)),
        grid_y=int(data.get("gridY", 0)),
        shape=_require_int_enum(CellShape, data.get("shape", 0), "shape"),
        direction=_require_int_enum(Direction, data.get("direction", 0), "direction"),
        color=_require_int_enum(ItemColor, colors[0], "colorList[0]"),
        id=int(data.get("id", 0)),
        is_active=bool(data.get("isActive", True)),
        effects=data.get("effects"),
    )


def level_from_dict(data: dict[str, Any]) -> PixelLevelData:
    try:
        level_grid_version = int(data.get("levelGridVersion", 1))
    except (TypeError, ValueError) as exc:
        raise LevelSerializationError("levelGridVersion must be an integer.") from exc
    pixel_grid_data = data.get("pixelGrid")
    if isinstance(pixel_grid_data, dict):
        if pixel_grid_data.get("modifiers") not in (None, []):
            raise UnsupportedScopeError("Pixel modifiers are outside Pixel-only tool scope.")
        if pixel_grid_data.get("obstacles") not in (None, []):
            raise UnsupportedScopeError("Pixel obstacles are outside Pixel-only tool scope.")
        pixel_grid = PixelGridData(
            width=int(pixel_grid_data.get("width", 0)),
            height=int(pixel_grid_data.get("height", 0)),
            color_ids=[int(value) for value in pixel_grid_data.get("colorIds", [])],
            modifiers=list(pixel_grid_data.get("modifiers") or []),
            obstacles=list(pixel_grid_data.get("obstacles") or []),
        )
    else:
        pixel_grid = PixelGridData()
    level = PixelLevelData(
        level_grid_version=level_grid_version,
        level_name=data.get("levelName"),
        map_type=int(data.get("mapType", 0)),
        grid_rows=int(data.get("gridRows", 10)),
        grid_cols=int(data.get("gridCols", 10)),
        board=int(data.get("board", 1)),
        grid_cells=[cell_from_dict(cell) for cell in data.get("gridCells", [])],
        grid_lanes=list(data.get("gridLanes") or []),
        obstacles=list(data.get("obstacles") or []),
        pixel_grid=pixel_grid,
        game_mode=int(data.get("gameMode", 1)),
        difficulty=int(data.get("difficulty", 0)),
        level=int(data.get("level", 1)),
        category=int(data.get("category", 0)),
        extra_fields={key: value for key, value in data.items() if key not in ROOT_KEYS},
    )
    return level


def load_level(path: str | Path) -> PixelLevelData:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise LevelSerializationError("Root JSON must be an object.")
    return level_from_dict(data)


def _collapse_color_list_blocks(content: str) -> str:
    def repl(match: re.Match[str]) -> str:
        values = re.findall(r"-?\d+", match.group(2))
        return f'{match.group(1)}[{", ".join(values)}]'

    return _COLOR_LIST_BLOCK_PATTERN.sub(repl, content)


def dumps_level(level: PixelLevelData) -> str:
    content = json.dumps(level_to_dict(level), ensure_ascii=False, allow_nan=False, indent=2)
    return _collapse_color_list_blocks(content) + "\n"


def save_level(path: str | Path, level: PixelLevelData, *, create_backup: bool = False) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if create_backup and target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        backup.write_bytes(target.read_bytes())
    content = dumps_level(level)
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        finally:
            raise
