from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID
from pixel_level_tool.services.level_serializer import load_level, save_level


class LevelConvertError(ValueError):
    pass


@dataclass
class ConvertSummary:
    converted: list[Path] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)


def _load_convertible(path: Path):
    """Load a level that is a supported, Pixel-only level worth converting.

    ``load_level`` already accepts both the legacy (NewRefactor.*) and current
    (Gameplay.MarbleFlow.*) namespaces and fail-fast rejects cargo/pixel-modifier
    subtypes. Here we additionally reject Classic levels that merely round-trip
    through the reader without being a Pixel level.
    """
    level = load_level(path)
    if level.grid_lanes:
        raise LevelConvertError("Level has cargo lanes (Classic level); not a Pixel level.")
    if not any(color_id != EMPTY_COLOR_ID for color_id in level.pixel_grid.color_ids):
        raise LevelConvertError("Level has no painted pixel data.")
    return level


def convert_file(path: str | Path) -> None:
    """Convert one level file to the new format in place (with a .bak backup)."""
    target = Path(path)
    level = _load_convertible(target)
    save_level(target, level, create_backup=True)


def convert_folder(folder: str | Path) -> ConvertSummary:
    """Convert every ``*.json`` level in ``folder`` in place.

    Unsupported or non-Pixel files are skipped with a reason instead of aborting
    the whole batch.
    """
    summary = ConvertSummary()
    for path in sorted(Path(folder).glob("*.json")):
        try:
            convert_file(path)
        except (OSError, ValueError) as exc:
            summary.skipped.append((path, str(exc)))
        else:
            summary.converted.append(path)
    return summary
