from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from pixel_level_tool.domain.enums import (
    CellShape,
    Direction,
    GameMode,
    ItemColor,
    LevelDifficulty,
    LockKeyGate,
    MapType,
    WoolCrateColor,
    enum_name,
    enum_name_from_value,
)
from pixel_level_tool.domain.level_models import (
    ArrowLockCellEffectData,
    BoxCellData,
    ColorGateObstacleData,
    ElevatorLayerData,
    ElevatorObstacleData,
    FrozenCellEffectData,
    HiddenCellEffectData,
    KeyForLockedGateCellEffectData,
    LargeBlockObstacleData,
    LinkedContainerObstacleData,
    LockedGateObstacleData,
    PinsObstacleData,
    PixelGridData,
    PixelLevelData,
    ScissorForWoolCrateCellEffectData,
    TunnelCellData,
    WoolCrateObstacleData,
)


class LevelSerializationError(ValueError):
    pass


class UnsupportedScopeError(LevelSerializationError):
    pass


# The tool writes the current Pop-Sort-2 LevelData format: no $type metadata, a
# nested boxGrid, and every enum encoded as its name string. Polymorphic elements
# carry a "type" discriminator whose value is the C# enum name of the subtype.
DISCRIMINATOR = "type"

CELL_TYPE_BY_CLASS: dict[type, str] = {
    BoxCellData: "Normal",
    TunnelCellData: "Tunnel",
}
EFFECT_TYPE_BY_CLASS: dict[type, str] = {
    FrozenCellEffectData: "Frozen",
    HiddenCellEffectData: "Hidden",
    ArrowLockCellEffectData: "ArrowLock",
    KeyForLockedGateCellEffectData: "KeyForLockedGate",
    ScissorForWoolCrateCellEffectData: "ScissorForWoolCrate",
}
OBSTACLE_TYPE_BY_CLASS: dict[type, str] = {
    LinkedContainerObstacleData: "LinkedContainer",
    LargeBlockObstacleData: "LargeBlock",
    PinsObstacleData: "Pins",
    LockedGateObstacleData: "LockedGate",
    WoolCrateObstacleData: "WoolCrate",
    ColorGateObstacleData: "ColorGate",
    ElevatorObstacleData: "Elevator",
}


# --------------------------------------------------------------------------- #
# Write (current Pop-Sort-2 format)
# --------------------------------------------------------------------------- #
def effect_to_dict(effect: object) -> dict[str, Any]:
    type_name = EFFECT_TYPE_BY_CLASS.get(type(effect))
    if type_name is None:
        raise UnsupportedScopeError(f"Unsupported cell effect: {type(effect).__name__}")
    data: dict[str, Any] = {DISCRIMINATOR: type_name}
    if isinstance(effect, FrozenCellEffectData):
        data["frozenCount"] = effect.frozen_count
    elif isinstance(effect, ArrowLockCellEffectData):
        data["requiredDirection"] = enum_name(effect.required_direction)
    elif isinstance(effect, KeyForLockedGateCellEffectData):
        data["lockKeyGate"] = enum_name(effect.lock_key_gate)
    elif isinstance(effect, ScissorForWoolCrateCellEffectData):
        data["scissorColor"] = enum_name(effect.scissor_color)
    return data


def cell_to_dict(cell: BoxCellData) -> dict[str, Any]:
    common = {
        "gridX": cell.grid_x,
        "gridY": cell.grid_y,
        "shape": enum_name(cell.shape),
        "direction": enum_name(cell.direction),
        "id": cell.id,
        "isActive": cell.is_active,
    }
    if isinstance(cell, TunnelCellData):
        return {
            DISCRIMINATOR: "Tunnel",
            "color": enum_name(cell.color),
            "storedCells": [cell_to_dict(stored_cell) for stored_cell in cell.stored_cells],
            **common,
        }
    if type(cell) is not BoxCellData:
        raise UnsupportedScopeError(f"Unsupported grid cell subtype: {type(cell).__name__}")
    return {
        DISCRIMINATOR: "Normal",
        "colorList": [enum_name(cell.color)],
        "effects": [effect_to_dict(effect) for effect in cell.effects] if cell.effects else None,
        **common,
    }


def obstacle_to_dict(obstacle: object, uid_to_id: dict[str, int]) -> dict[str, Any]:
    type_name = OBSTACLE_TYPE_BY_CLASS.get(type(obstacle))
    if type_name is None:
        raise UnsupportedScopeError(f"Unsupported source-grid obstacle: {type(obstacle).__name__}")
    data: dict[str, Any] = {DISCRIMINATOR: type_name, "id": obstacle.id}
    if isinstance(obstacle, (LinkedContainerObstacleData, PinsObstacleData)):
        try:
            data["targetIds"] = [uid_to_id[uid] for uid in obstacle.target_uids]
        except KeyError as exc:
            raise LevelSerializationError(f"Obstacle references a deleted box ({exc.args[0]}).") from exc
        if isinstance(obstacle, PinsObstacleData):
            data["requiredDirection"] = enum_name(obstacle.required_direction)
        return data
    # Remaining obstacles are anchored on the grid.
    data.update(
        {
            "gridX": obstacle.grid_x,
            "gridY": obstacle.grid_y,
            "width": obstacle.width,
            "height": obstacle.height,
        }
    )
    if isinstance(obstacle, LargeBlockObstacleData):
        data["count"] = obstacle.count
    elif isinstance(obstacle, ColorGateObstacleData):
        data["count"] = obstacle.count
        data["requiredColor"] = enum_name(obstacle.required_color)
    elif isinstance(obstacle, LockedGateObstacleData):
        data["lockKeyGate"] = enum_name(obstacle.lock_key_gate)
        data["priority"] = obstacle.priority
    elif isinstance(obstacle, WoolCrateObstacleData):
        data["ropes"] = [enum_name(color) for color in obstacle.ropes]
        data["priority"] = obstacle.priority
    elif isinstance(obstacle, ElevatorObstacleData):
        data["layers"] = [{"cells": [cell_to_dict(cell) for cell in layer.cells]} for layer in obstacle.layers]
    return data


def level_to_dict(level: PixelLevelData, *, assign_ids: bool = True) -> dict[str, Any]:
    snapshot = level.clone()
    if assign_ids:
        snapshot.assign_deterministic_ids()
    uid_to_id = {cell.internal_uid: cell.id for cell in snapshot.grid_cells}
    if len(uid_to_id) != len(snapshot.grid_cells):
        raise LevelSerializationError("Duplicate internal box identities cannot be serialized.")
    return {
        "pixelGrid": {
            "width": snapshot.pixel_grid.width,
            "height": snapshot.pixel_grid.height,
            "colorIds": list(snapshot.pixel_grid.color_ids),
            "modifiers": [],
            "obstacles": [],
        },
        "boxGrid": {
            "gridRows": snapshot.grid_rows,
            "gridCols": snapshot.grid_cols,
            "board": snapshot.board,
            "gridCells": [cell_to_dict(cell) for cell in snapshot.grid_cells],
            "obstacles": [obstacle_to_dict(obstacle, uid_to_id) for obstacle in snapshot.obstacles],
        },
        "mapType": enum_name_from_value(MapType, snapshot.map_type, MapType.None_),
        "time": snapshot.time,
        "piece": snapshot.piece,
        "gameMode": enum_name_from_value(GameMode, snapshot.game_mode, GameMode.Classic),
        "difficulty": enum_name_from_value(LevelDifficulty, snapshot.difficulty, LevelDifficulty.Easy),
        "level": snapshot.level,
        "category": snapshot.category,
        "mechanics": list(snapshot.mechanics),
    }


# --------------------------------------------------------------------------- #
# Read (current Pop-Sort-2 format)
# --------------------------------------------------------------------------- #
def _enum_from_json(enum_type: type[Any], value: object, field: str) -> Any:
    """Parse an enum from a name string (``None`` -> ``None_``) or an int value."""
    if isinstance(value, bool):
        raise LevelSerializationError(f"Invalid {field}: {value!r}")
    if isinstance(value, int):
        try:
            return enum_type(value)
        except ValueError as exc:
            raise LevelSerializationError(f"Invalid {field}: {value!r}") from exc
    if isinstance(value, str):
        try:
            return enum_type[value]
        except KeyError:
            pass
        if value == "None":
            try:
                return enum_type["None_"]
            except KeyError:
                pass
        if value.lstrip("-").isdigit():
            try:
                return enum_type(int(value))
            except ValueError:
                pass
    raise LevelSerializationError(f"Invalid {field}: {value!r}")


def effect_from_dict(data: dict[str, Any]) -> object:
    type_name = data.get(DISCRIMINATOR)
    if type_name == "Frozen":
        return FrozenCellEffectData(int(data.get("frozenCount", 0)))
    if type_name == "Hidden":
        return HiddenCellEffectData()
    if type_name == "ArrowLock":
        return ArrowLockCellEffectData(_enum_from_json(Direction, data.get("requiredDirection", 0), "requiredDirection"))
    if type_name == "KeyForLockedGate":
        return KeyForLockedGateCellEffectData(_enum_from_json(LockKeyGate, data.get("lockKeyGate", 0), "lockKeyGate"))
    if type_name == "ScissorForWoolCrate":
        return ScissorForWoolCrateCellEffectData(_enum_from_json(WoolCrateColor, data.get("scissorColor", 0), "scissorColor"))
    raise UnsupportedScopeError(f"Unsupported cell effect type: {type_name!r}")


def cell_from_dict(data: dict[str, Any]) -> BoxCellData:
    type_name = data.get(DISCRIMINATOR)
    common = {
        "grid_x": int(data.get("gridX", 0)),
        "grid_y": int(data.get("gridY", 0)),
        "shape": _enum_from_json(CellShape, data.get("shape", 0), "shape"),
        "direction": _enum_from_json(Direction, data.get("direction", 0), "direction"),
        "id": int(data.get("id", 0)),
        "is_active": False,
    }
    if type_name == "Tunnel":
        stored_data = data.get("storedCells")
        if stored_data is None:
            stored_data = []
        if not isinstance(stored_data, list):
            raise LevelSerializationError("Tunnel storedCells must be a JSON array or null.")
        stored_cells = [cell_from_dict(item) for item in stored_data]
        if any(type(cell) is not BoxCellData for cell in stored_cells):
            raise UnsupportedScopeError("Tunnel storedCells currently support normal cells only.")
        return TunnelCellData(
            **common,
            color=_enum_from_json(ItemColor, data.get("color", int(ItemColor.Blue)), "color"),
            stored_cells=stored_cells,
        )
    if type_name != "Normal":
        raise UnsupportedScopeError(f"Unsupported grid cell type: {type_name!r}")
    colors = data.get("colorList")
    if not isinstance(colors, list) or len(colors) != 1:
        raise UnsupportedScopeError("Pixel-only cells must contain exactly one color in colorList.")
    effects_data = data.get("effects")
    if effects_data is not None and not isinstance(effects_data, list):
        raise LevelSerializationError("Cell effects must be a JSON array or null.")
    return BoxCellData(
        **common,
        color=_enum_from_json(ItemColor, colors[0], "colorList[0]"),
        effects=[effect_from_dict(effect) for effect in effects_data] if effects_data else None,
    )


def obstacle_from_dict(data: dict[str, Any], id_to_uid: dict[int, str]) -> object:
    type_name = data.get(DISCRIMINATOR)
    obstacle_id = int(data.get("id", 0))

    def target_uids() -> list[str]:
        result: list[str] = []
        for value in data.get("targetIds") or []:
            target_id = int(value)
            if target_id not in id_to_uid:
                raise LevelSerializationError(f"Obstacle {obstacle_id} references missing box id {target_id}.")
            result.append(id_to_uid[target_id])
        return result

    common = {
        "grid_x": int(data.get("gridX", 0)),
        "grid_y": int(data.get("gridY", 0)),
        "width": int(data.get("width", 1)),
        "height": int(data.get("height", 1)),
    }
    if type_name == "LinkedContainer":
        return LinkedContainerObstacleData(target_uids(), obstacle_id)
    if type_name == "Pins":
        return PinsObstacleData(target_uids(), _enum_from_json(Direction, data.get("requiredDirection", 0), "requiredDirection"), obstacle_id)
    if type_name == "LargeBlock":
        return LargeBlockObstacleData(**common, count=int(data.get("count", 1)), id=obstacle_id)
    if type_name == "LockedGate":
        return LockedGateObstacleData(**common, lock_key_gate=_enum_from_json(LockKeyGate, data.get("lockKeyGate", 0), "lockKeyGate"), priority=int(data.get("priority", 0)), id=obstacle_id)
    if type_name == "WoolCrate":
        ropes = [_enum_from_json(WoolCrateColor, value, "ropes") for value in data.get("ropes") or []]
        return WoolCrateObstacleData(**common, ropes=ropes, priority=int(data.get("priority", 0)), id=obstacle_id)
    if type_name == "ColorGate":
        return ColorGateObstacleData(**common, count=int(data.get("count", 1)), required_color=_enum_from_json(ItemColor, data.get("requiredColor", 0), "requiredColor"), id=obstacle_id)
    if type_name == "Elevator":
        layers = []
        for layer_data in data.get("layers") or []:
            layers.append(ElevatorLayerData([cell_from_dict(cell) for cell in layer_data.get("cells") or []]))
        return ElevatorObstacleData(**common, layers=layers, id=obstacle_id)
    raise UnsupportedScopeError(f"Unsupported source-grid obstacle type: {type_name!r}")


def _pixel_grid_from_dict(pixel_grid_data: object) -> PixelGridData:
    if not isinstance(pixel_grid_data, dict):
        return PixelGridData()
    if pixel_grid_data.get("modifiers") not in (None, []):
        raise UnsupportedScopeError("Pixel modifiers are outside Pixel-only tool scope.")
    if pixel_grid_data.get("obstacles") not in (None, []):
        raise UnsupportedScopeError("Pixel obstacles are outside Pixel-only tool scope.")
    return PixelGridData(
        width=int(pixel_grid_data.get("width", 0)),
        height=int(pixel_grid_data.get("height", 0)),
        color_ids=[int(value) for value in pixel_grid_data.get("colorIds", [])],
        modifiers=list(pixel_grid_data.get("modifiers") or []),
        obstacles=list(pixel_grid_data.get("obstacles") or []),
    )


def level_from_dict(data: dict[str, Any]) -> PixelLevelData:
    if "$type" in data:
        raise LevelSerializationError("$type metadata is not supported in the current format.")
    box_grid = data.get("boxGrid")
    if not isinstance(box_grid, dict):
        box_grid = {}
    pixel_grid = _pixel_grid_from_dict(data.get("pixelGrid"))
    cells = [cell_from_dict(cell) for cell in box_grid.get("gridCells") or []]
    id_to_uid = {cell.id: cell.internal_uid for cell in cells if cell.id > 0}
    if len(id_to_uid) != sum(cell.id > 0 for cell in cells):
        raise LevelSerializationError("Duplicate positive box ids cannot be used by obstacle targetIds.")
    obstacles = [obstacle_from_dict(obstacle, id_to_uid) for obstacle in box_grid.get("obstacles") or []]
    return PixelLevelData(
        grid_rows=int(box_grid.get("gridRows", 10)),
        grid_cols=int(box_grid.get("gridCols", 10)),
        board=int(box_grid.get("board", 1)),
        grid_cells=cells,
        obstacles=obstacles,
        pixel_grid=pixel_grid,
        map_type=int(_enum_from_json(MapType, data.get("mapType", "None"), "mapType")),
        time=int(data.get("time", 60)),
        piece=int(data.get("piece", 5)),
        game_mode=int(_enum_from_json(GameMode, data.get("gameMode", "Classic"), "gameMode")),
        difficulty=int(_enum_from_json(LevelDifficulty, data.get("difficulty", "Easy"), "difficulty")),
        level=int(data.get("level", 1)),
        category=int(data.get("category", 0)),
        mechanics=[str(value) for value in data.get("mechanics") or []],
    )


def load_level(path: str | Path) -> PixelLevelData:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise LevelSerializationError("Root JSON must be an object.")
    return level_from_dict(data)


# --------------------------------------------------------------------------- #
# Serialize to text / disk
# --------------------------------------------------------------------------- #
# Collapse the (single-element) colorList block back onto one line, matching the
# on-disk layout used by the game's level files; colorIds stays one value per line.
_COLOR_LIST_BLOCK_PATTERN = re.compile(
    r'(?m)^(\s*"colorList": )\[\n((?:\s+(?:"[^"]*"|-?\d+),?\n)+)\s*\]'
)


def _collapse_color_list_blocks(content: str) -> str:
    def repl(match: re.Match[str]) -> str:
        tokens = re.findall(r'"[^"]*"|-?\d+', match.group(2))
        return f'{match.group(1)}[{", ".join(tokens)}]'

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
        if target.exists() and not os.access(target, os.W_OK):
            # A read-only destination (e.g. extracted from a zip, or a git checkout
            # with the attribute preserved) makes os.replace() fail with
            # PermissionError on Windows, even though it was just backed up above.
            target.chmod(stat.S_IWRITE)
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        finally:
            raise


# --------------------------------------------------------------------------- #
# Legacy read ($type namespaces) — used only by the Convert feature.
# Accepts both the Marble-Sort (NewRefactor.*) and the intermediate
# (Gameplay.MarbleFlow.Level.*) $type spellings, with integer enums and a
# root-level gridCells/obstacles layout, and loads them into the model so the
# current save path can rewrite them forward.
# --------------------------------------------------------------------------- #
_LEGACY_NEW_NAMESPACE = "Gameplay.MarbleFlow.Level."
_LEGACY_OLD_NAMESPACE = "NewRefactor."


def _legacy(type_name: str) -> str:
    return type_name.replace(_LEGACY_NEW_NAMESPACE, _LEGACY_OLD_NAMESPACE, 1)


_LEGACY_CELL_TYPE_NAME = "Gameplay.MarbleFlow.Level.CellData, Assembly-CSharp"
_LEGACY_TUNNEL_TYPE_NAME = "Gameplay.MarbleFlow.Level.TunnelData, Assembly-CSharp"
_LEGACY_CELL_TYPE_NAMES = {_LEGACY_CELL_TYPE_NAME, _legacy(_LEGACY_CELL_TYPE_NAME)}
_LEGACY_TUNNEL_TYPE_NAMES = {_LEGACY_TUNNEL_TYPE_NAME, _legacy(_LEGACY_TUNNEL_TYPE_NAME)}
_LEGACY_EFFECT_TYPE_NAMES = {
    FrozenCellEffectData: "Gameplay.MarbleFlow.Level.FrozenCellEffectData, Assembly-CSharp",
    HiddenCellEffectData: "Gameplay.MarbleFlow.Level.HiddenCellEffectData, Assembly-CSharp",
    ArrowLockCellEffectData: "Gameplay.MarbleFlow.Level.ArrowLockCellEffectData, Assembly-CSharp",
    KeyForLockedGateCellEffectData: "Gameplay.MarbleFlow.Level.KeyForLockedGateCellEffectData, Assembly-CSharp",
    ScissorForWoolCrateCellEffectData: "Gameplay.MarbleFlow.Level.ScissorForWoolCrateCellEffectData, Assembly-CSharp",
}
_LEGACY_OBSTACLE_TYPE_NAMES = {
    LinkedContainerObstacleData: "Gameplay.MarbleFlow.Level.LinkedContainerObstacleData, Assembly-CSharp",
    LargeBlockObstacleData: "Gameplay.MarbleFlow.Level.LargeBlockObstacleData, Assembly-CSharp",
    PinsObstacleData: "Gameplay.MarbleFlow.Level.PinsObstacleData, Assembly-CSharp",
    LockedGateObstacleData: "Gameplay.MarbleFlow.Level.LockedGateObstacleData, Assembly-CSharp",
    WoolCrateObstacleData: "Gameplay.MarbleFlow.Level.WoolCrateObstacleData, Assembly-CSharp",
    ColorGateObstacleData: "Gameplay.MarbleFlow.Level.ColorGateObstacleData, Assembly-CSharp",
    ElevatorObstacleData: "Gameplay.MarbleFlow.Level.ElevatorObstacleData, Assembly-CSharp",
}
_LEGACY_EFFECT_TYPES_READ = {
    type_name: effect_type
    for effect_type, new_name in _LEGACY_EFFECT_TYPE_NAMES.items()
    for type_name in (new_name, _legacy(new_name))
}
_LEGACY_OBSTACLE_TYPES_READ = {
    type_name: obstacle_type
    for obstacle_type, new_name in _LEGACY_OBSTACLE_TYPE_NAMES.items()
    for type_name in (new_name, _legacy(new_name))
}
_LEGACY_CARGO_EFFECT_TYPE_NAMES = {
    "Gameplay.MarbleFlow.Level.KeyForCargoCellEffectData, Assembly-CSharp",
    "NewRefactor.KeyForCargoCellEffectData, Assembly-CSharp",
}
_LEGACY_CARGO_OBSTACLE_TYPE_NAMES = {
    "Gameplay.MarbleFlow.Level.LinkedCargoObstacleData, Assembly-CSharp",
    "NewRefactor.LinkedCargoObstacleData, Assembly-CSharp",
}
_LEGACY_ROOT_KEYS = {
    "pixelGrid",
    "levelGridVersion",
    "levelName",
    "mapType",
    "gridRows",
    "gridCols",
    "board",
    "time",
    "piece",
    "gridCells",
    "gridLanes",
    "obstacles",
    "gameMode",
    "difficulty",
    "level",
    "category",
}


def _require_int_enum(enum_type: type, value: object, field: str) -> Any:
    try:
        return enum_type(int(value))
    except (TypeError, ValueError) as exc:
        raise LevelSerializationError(f"Invalid {field}: {value!r}") from exc


def _legacy_effect_from_dict(data: dict[str, Any]) -> object:
    type_name = data.get("$type")
    effect_type = _LEGACY_EFFECT_TYPES_READ.get(type_name)
    if effect_type is FrozenCellEffectData:
        return FrozenCellEffectData(int(data.get("frozenCount", 0)))
    if effect_type is HiddenCellEffectData:
        return HiddenCellEffectData()
    if effect_type is ArrowLockCellEffectData:
        return ArrowLockCellEffectData(_require_int_enum(Direction, data.get("requiredDirection", 0), "requiredDirection"))
    if effect_type is KeyForLockedGateCellEffectData:
        return KeyForLockedGateCellEffectData(_require_int_enum(LockKeyGate, data.get("lockKeyGate", 0), "lockKeyGate"))
    if effect_type is ScissorForWoolCrateCellEffectData:
        return ScissorForWoolCrateCellEffectData(_require_int_enum(WoolCrateColor, data.get("scissorColor", 0), "scissorColor"))
    if type_name in _LEGACY_CARGO_EFFECT_TYPE_NAMES:
        raise UnsupportedScopeError("KeyForCargo is cargo-related and is not supported by this tool.")
    raise UnsupportedScopeError(f"Unsupported cell effect type: {type_name!r}")


def _legacy_cell_from_dict(data: dict[str, Any]) -> BoxCellData:
    type_name = data.get("$type")
    common = {
        "grid_x": int(data.get("gridX", 0)),
        "grid_y": int(data.get("gridY", 0)),
        "shape": _require_int_enum(CellShape, data.get("shape", 0), "shape"),
        "direction": _require_int_enum(Direction, data.get("direction", 0), "direction"),
        "id": int(data.get("id", 0)),
        "is_active": False,
    }
    if type_name in _LEGACY_TUNNEL_TYPE_NAMES:
        stored_data = data.get("storedCells")
        if stored_data is None:
            stored_data = []
        if not isinstance(stored_data, list):
            raise LevelSerializationError("Tunnel storedCells must be a JSON array or null.")
        stored_cells = [_legacy_cell_from_dict(item) for item in stored_data]
        if any(type(cell) is not BoxCellData for cell in stored_cells):
            raise UnsupportedScopeError("Tunnel storedCells currently support normal CellData only.")
        return TunnelCellData(
            **common,
            color=_require_int_enum(ItemColor, data.get("color", int(ItemColor.Blue)), "color"),
            stored_cells=stored_cells,
        )
    if type_name not in _LEGACY_CELL_TYPE_NAMES:
        raise UnsupportedScopeError(f"Unsupported grid cell type: {type_name!r}")
    colors = data.get("colorList")
    if not isinstance(colors, list) or len(colors) != 1:
        raise UnsupportedScopeError("Pixel-only cells must contain exactly one color in colorList.")
    effects_data = data.get("effects")
    if effects_data is not None and not isinstance(effects_data, list):
        raise LevelSerializationError("Cell effects must be a JSON array or null.")
    return BoxCellData(
        **common,
        color=_require_int_enum(ItemColor, colors[0], "colorList[0]"),
        effects=[_legacy_effect_from_dict(effect) for effect in effects_data] if effects_data else None,
    )


def _legacy_obstacle_from_dict(data: dict[str, Any], id_to_uid: dict[int, str]) -> object:
    type_name = data.get("$type")
    obstacle_id = int(data.get("id", 0))

    def target_uids() -> list[str]:
        result: list[str] = []
        for value in data.get("targetIds") or []:
            target_id = int(value)
            if target_id not in id_to_uid:
                raise LevelSerializationError(f"Obstacle {obstacle_id} references missing box id {target_id}.")
            result.append(id_to_uid[target_id])
        return result

    common = {
        "grid_x": int(data.get("gridX", 0)),
        "grid_y": int(data.get("gridY", 0)),
        "width": int(data.get("width", 1)),
        "height": int(data.get("height", 1)),
    }
    obstacle_type = _LEGACY_OBSTACLE_TYPES_READ.get(type_name)
    if obstacle_type is LinkedContainerObstacleData:
        return LinkedContainerObstacleData(target_uids(), obstacle_id)
    if obstacle_type is PinsObstacleData:
        return PinsObstacleData(target_uids(), _require_int_enum(Direction, data.get("requiredDirection", 0), "requiredDirection"), obstacle_id)
    if obstacle_type is LargeBlockObstacleData:
        return LargeBlockObstacleData(**common, count=int(data.get("count", 1)), id=obstacle_id)
    if obstacle_type is LockedGateObstacleData:
        return LockedGateObstacleData(**common, lock_key_gate=_require_int_enum(LockKeyGate, data.get("lockKeyGate", 0), "lockKeyGate"), priority=int(data.get("priority", 0)), id=obstacle_id)
    if obstacle_type is WoolCrateObstacleData:
        ropes = [_require_int_enum(WoolCrateColor, value, "ropes") for value in data.get("ropes") or []]
        return WoolCrateObstacleData(**common, ropes=ropes, priority=int(data.get("priority", 0)), id=obstacle_id)
    if obstacle_type is ColorGateObstacleData:
        return ColorGateObstacleData(**common, count=int(data.get("count", 1)), required_color=_require_int_enum(ItemColor, data.get("requiredColor", 0), "requiredColor"), id=obstacle_id)
    if obstacle_type is ElevatorObstacleData:
        layers = []
        for layer_data in data.get("layers") or []:
            layers.append(ElevatorLayerData([_legacy_cell_from_dict(cell) for cell in layer_data.get("cells") or []]))
        return ElevatorObstacleData(**common, layers=layers, id=obstacle_id)
    if type_name in _LEGACY_CARGO_OBSTACLE_TYPE_NAMES:
        raise UnsupportedScopeError("LinkedCargo is cargo-related and is not supported by this tool.")
    raise UnsupportedScopeError(f"Unsupported source-grid obstacle type: {type_name!r}")


def legacy_level_from_dict(data: dict[str, Any]) -> PixelLevelData:
    if "$type" in data:
        raise LevelSerializationError("Root $type discriminators are not supported.")
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
    grid_lanes = data.get("gridLanes")
    if grid_lanes is None:
        grid_lanes = []
    elif not isinstance(grid_lanes, list):
        raise LevelSerializationError("gridLanes must be a JSON array or null.")
    cells = [_legacy_cell_from_dict(cell) for cell in data.get("gridCells", [])]
    id_to_uid = {cell.id: cell.internal_uid for cell in cells if cell.id > 0}
    if len(id_to_uid) != sum(cell.id > 0 for cell in cells):
        raise LevelSerializationError("Duplicate positive box ids cannot be used by obstacle targetIds.")
    obstacles = [_legacy_obstacle_from_dict(obstacle, id_to_uid) for obstacle in data.get("obstacles") or []]
    return PixelLevelData(
        level_grid_version=level_grid_version,
        level_name=data.get("levelName"),
        map_type=int(data.get("mapType", 0)),
        grid_rows=int(data.get("gridRows", 10)),
        grid_cols=int(data.get("gridCols", 10)),
        board=int(data.get("board", 1)),
        time=int(data.get("time", 60)),
        piece=int(data.get("piece", 5)),
        grid_cells=cells,
        grid_lanes=grid_lanes,
        obstacles=obstacles,
        pixel_grid=pixel_grid,
        game_mode=int(data.get("gameMode", 1)),
        difficulty=int(data.get("difficulty", 0)),
        level=int(data.get("level", 1)),
        category=int(data.get("category", 0)),
        extra_fields={key: value for key, value in data.items() if key not in _LEGACY_ROOT_KEYS},
    )


def load_legacy_level(path: str | Path) -> PixelLevelData:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise LevelSerializationError("Root JSON must be an object.")
    return legacy_level_from_dict(data)
