"""Per-level Auto Gen Box presets, kept as ``genlv{level}.json`` in one folder.

The knobs of a generated level are not recoverable from the level file: the box
grid records the *outcome*, not the difficulty, the hidden share or the seed that
produced it. So the options are written beside it, in a folder the designer picks
once, and read back the next time that level is opened.

The file name mirrors the level file it belongs to, so a folder of presets reads
like the folder of levels: ``1.json`` pairs with ``genlv1.json``, and the
category variant ``1.2.json`` with ``genlv1.2.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from pixel_level_tool.services.box_autogen import AutoGenOptions
from pixel_level_tool.services.level_serializer import write_content_atomic


class AutoGenConfigError(ValueError):
    pass


# Bumped only if a key changes meaning. Adding a knob does not need a new version:
# an unknown key is ignored and a missing one keeps its AutoGenOptions default, so
# files written by either side of such a change still load.
#
# 2: the conveyor is measured in balls, not in box slots. ``traySlots`` is gone
#    rather than renamed - a v1 file's 5 meant five boxes and would read as five
#    balls here, so it is dropped and ``beltSlots`` takes its default instead.
# 3: ``useArrowLock`` and ``useLinkedContainer`` accept null, which means "let the
#    difficulty decide" - the new default. A v2 file's ``false`` still reads as
#    off, but it was written by a dialog whose box was unticked by default, so a
#    v2 preset keeps those two mechanics off where a fresh one would not.
#    ``tunnelMode`` gained "auto" for the same reason and defaults to it.
# 4: ``maxTunnels`` gained 0, meaning "measure the ceiling off the picture", and
#    that is the new default. Every file written before this carries the old
#    fixed 4, which nobody typed - it was the dialog's default - so reading it
#    back as an instruction would hold those levels to a ceiling the picture was
#    never measured against. A pre-v4 file therefore loads as Auto; a v4 file's
#    number is one somebody chose and stands.
CONFIG_VERSION = 4

FILE_PREFIX = "genlv"


def _as_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise AutoGenConfigError(f"expected true or false, got {value!r}")
    return value


def _as_int(value: Any) -> int:
    # bool is an int in Python, but a tick mark where a count belongs is a typo.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AutoGenConfigError(f"expected a number, got {value!r}")
    return int(value)


def _as_float(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AutoGenConfigError(f"expected a number, got {value!r}")
    return float(value)


def _as_str(value: Any) -> str:
    if not isinstance(value, str):
        raise AutoGenConfigError(f"expected a string, got {value!r}")
    return value


def _optional(coerce: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """null stays null: for these knobs it means Auto, not zero."""

    def read(value: Any) -> Any:
        return None if value is None else coerce(value)

    return read


# (AutoGenOptions attribute, JSON key, reader). The JSON keys are camelCase to
# match the level files the presets sit next to.
_SPEC: tuple[tuple[str, str, Callable[[Any], Any]], ...] = (
    ("difficulty", "difficulty", _as_int),
    ("auto_difficulty", "autoDifficulty", _as_bool),
    ("max_slot_cols", "maxSlotCols", _as_int),
    ("max_slot_rows", "maxSlotRows", _as_int),
    ("hidden_ratio", "hiddenRatio", _optional(_as_float)),
    ("hidden_boxes", "hiddenBoxes", _optional(_as_int)),
    ("belt_slots", "beltSlots", _as_int),
    ("active_policy", "activePolicy", _as_str),
    ("allow_tunnels", "allowTunnels", _as_bool),
    ("max_tunnels", "maxTunnels", _as_int),
    ("tunnel_count", "tunnelCount", _optional(_as_int)),
    ("tunnel_mode", "tunnelMode", _as_str),
    ("tunnel_placement", "tunnelPlacement", _as_str),
    ("tunnel_depth", "tunnelDepth", _as_int),
    ("dig_window", "digWindow", _optional(_as_int)),
    ("walls", "walls", _optional(_as_int)),
    ("use_arrow_lock", "useArrowLock", _optional(_as_bool)),
    ("arrow_ratio", "arrowRatio", _optional(_as_float)),
    ("arrow_boxes", "arrowBoxes", _optional(_as_int)),
    ("use_linked_container", "useLinkedContainer", _optional(_as_bool)),
    ("linked_pairs", "linkedPairs", _optional(_as_int)),
    ("linked_mode", "linkedMode", _as_str),
    ("frozen_boxes", "frozenBoxes", _optional(_as_int)),
    ("blocks", "blocks", _optional(_as_int)),
    ("lock_margin", "lockMargin", _as_int),
    ("lock_rounding", "lockRounding", _as_str),
    ("shuffle_obstacles", "shuffleObstacles", _as_bool),
    ("obstacle_relief", "obstacleRelief", _as_bool),
    ("repair_picture", "repairPicture", _as_bool),
    ("ease_difficulty", "easeDifficulty", _as_int),
    ("ease_obstacles", "easeObstacles", _as_int),
    ("shuffle_attempts", "shuffleAttempts", _as_int),
    ("apply_theme", "applyTheme", _as_bool),
    ("seed", "seed", _optional(_as_int)),
)


def config_file_name(level: int, category: int = 0) -> str:
    return f"{FILE_PREFIX}{level}.json" if category == 0 else f"{FILE_PREFIX}{level}.{category}.json"


def config_path(folder: str | Path, level: int, category: int = 0) -> Path:
    return Path(folder) / config_file_name(level, category)


def options_to_document(options: AutoGenOptions, *, level: int, category: int = 0) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": CONFIG_VERSION,
        "level": int(level),
        "category": int(category),
    }
    for attribute, key, _ in _SPEC:
        document[key] = getattr(options, attribute)
    return document


def options_from_document(document: Any) -> AutoGenOptions:
    if not isinstance(document, dict):
        raise AutoGenConfigError("Root JSON must be an object.")
    options = AutoGenOptions()
    for attribute, key, read in _SPEC:
        if key not in document:
            continue
        try:
            setattr(options, attribute, read(document[key]))
        except AutoGenConfigError as exc:
            raise AutoGenConfigError(f"{key}: {exc}") from exc
    version = document.get("version")
    if isinstance(version, int) and version < 4:
        # See the note on CONFIG_VERSION: the tunnel ceiling in an older preset is
        # the dialog's old default, not a decision, so it goes back to Auto.
        options.max_tunnels = 0
    return options


def dumps_autogen_config(options: AutoGenOptions, *, level: int, category: int = 0) -> str:
    document = options_to_document(options, level=level, category=category)
    return json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n"


def save_autogen_config(
    folder: str | Path, level: int, category: int, options: AutoGenOptions
) -> Path:
    target = config_path(folder, level, category)
    write_content_atomic(target, dumps_autogen_config(options, level=level, category=category))
    return target


def load_autogen_config(
    folder: str | Path, level: int, category: int = 0
) -> AutoGenOptions | None:
    """The saved options for one level, or None when that level has no preset yet."""
    path = config_path(folder, level, category)
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AutoGenConfigError(f"{path.name}: {exc}") from exc
    try:
        return options_from_document(document)
    except AutoGenConfigError as exc:
        raise AutoGenConfigError(f"{path.name}: {exc}") from exc
