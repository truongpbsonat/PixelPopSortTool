from __future__ import annotations

from pathlib import Path

from pixel_level_tool.services.settings_service import SettingsService


class RecentFilesService:
    def __init__(self, settings: SettingsService, limit: int = 10) -> None:
        self.settings = settings
        self.limit = limit

    def list(self) -> list[str]:
        return [path for path in self.settings.get("recent_files", []) if Path(path).exists()]

    def add(self, path: str | Path) -> None:
        normalized = str(Path(path))
        items = [item for item in self.settings.get("recent_files", []) if item != normalized]
        items.insert(0, normalized)
        self.settings.set("recent_files", items[: self.limit])

