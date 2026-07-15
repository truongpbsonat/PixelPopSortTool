from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pixel_level_tool.domain.level_models import PixelLevelData


@dataclass
class SnapshotCommand:
    label: str
    before: PixelLevelData
    after: PixelLevelData


class CommandStack:
    def __init__(self, apply_snapshot: Callable[[PixelLevelData], None], limit: int = 150) -> None:
        self._apply_snapshot = apply_snapshot
        self._limit = limit
        self._undo: list[SnapshotCommand] = []
        self._redo: list[SnapshotCommand] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def push(self, label: str, before: PixelLevelData, after: PixelLevelData) -> None:
        self._undo.append(SnapshotCommand(label, before.clone(), after.clone()))
        if len(self._undo) > self._limit:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self) -> None:
        if not self._undo:
            return
        command = self._undo.pop()
        self._redo.append(command)
        self._apply_snapshot(command.before.clone())

    def redo(self) -> None:
        if not self._redo:
            return
        command = self._redo.pop()
        self._undo.append(command)
        self._apply_snapshot(command.after.clone())

