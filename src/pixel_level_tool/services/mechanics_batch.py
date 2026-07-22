from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pixel_level_tool.services.level_serializer import load_level_document, save_level_document
from pixel_level_tool.services.mechanics_scanner import MechanicsScanner


@dataclass
class MechanicsBatchFailure:
    path: Path
    error: str


@dataclass
class MechanicsBatchWarning:
    path: Path
    message: str


@dataclass
class MechanicsBatchSummary:
    total: int
    changed: int = 0
    unchanged: int = 0
    failed: int = 0
    cancelled: bool = False
    failures: list[MechanicsBatchFailure] = field(default_factory=list)
    warnings: list[MechanicsBatchWarning] = field(default_factory=list)


def scan_mechanics_in_folder(
    folder: str | Path,
    *,
    dry_run: bool = False,
    progress: Callable[[int, int, Path], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    scanner: MechanicsScanner | None = None,
) -> MechanicsBatchSummary:
    root = Path(folder)
    paths = sorted(path for path in root.rglob("*.json") if path.is_file())
    summary = MechanicsBatchSummary(total=len(paths))
    active_scanner = scanner or MechanicsScanner()

    for index, path in enumerate(paths, start=1):
        if should_cancel is not None and should_cancel():
            summary.cancelled = True
            break
        if progress is not None:
            progress(index, summary.total, path)
        try:
            document = load_level_document(path)
            result = active_scanner.scan_document(document)
            previous = document.get("mechanics")
            changed = previous != result.mechanics
            if changed and not dry_run:
                document["mechanics"] = result.mechanics
                save_level_document(path, document)
        except (OSError, ValueError, TypeError) as exc:
            summary.failed += 1
            summary.failures.append(MechanicsBatchFailure(path, str(exc)))
            continue
        for warning in result.warnings:
            summary.warnings.append(MechanicsBatchWarning(path, warning))
        if changed:
            summary.changed += 1
        else:
            summary.unchanged += 1
    return summary
