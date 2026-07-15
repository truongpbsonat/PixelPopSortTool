from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from pixel_level_tool.domain.enums import CellShape, Direction, EMPTY_COLOR_ID, ItemColor
from pixel_level_tool.domain.level_models import PixelLevelData


@dataclass(frozen=True)
class ValidationMessage:
    severity: str
    message: str


@dataclass
class ValidationResult:
    messages: list[ValidationMessage]

    @property
    def errors(self) -> list[ValidationMessage]:
        return [message for message in self.messages if message.severity == "error"]

    @property
    def warnings(self) -> list[ValidationMessage]:
        return [message for message in self.messages if message.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        return not self.errors


class LevelValidator:
    def validate(self, level: PixelLevelData) -> ValidationResult:
        messages: list[ValidationMessage] = []

        def error(text: str) -> None:
            messages.append(ValidationMessage("error", text))

        def warning(text: str) -> None:
            messages.append(ValidationMessage("warning", text))

        if level.level <= 0:
            error("level must be greater than 0.")
        if level.game_mode != 1:
            error("gameMode must be 1 for Pixel mode.")
        if level.level_grid_version != 1:
            error("levelGridVersion must be 1.")
        if level.grid_rows <= 0 or level.grid_cols <= 0:
            error("Box grid dimensions must be greater than 0.")
        if not level.grid_cells:
            error("Box grid must contain at least one source box.")
        if level.grid_lanes:
            warning("gridLanes are present but are not edited by this tool.")
        if level.obstacles:
            warning("Source obstacles are present but are not edited by this tool.")

        ids: set[int] = set()
        occupied: dict[tuple[int, int], int] = {}
        total_source = 0
        for index, cell in enumerate(level.grid_cells):
            if cell.id in ids:
                error(f"Duplicate box id {cell.id}.")
            ids.add(cell.id)
            if not _is_member(CellShape, cell.shape):
                error(f"Box {index} has invalid shape {cell.shape}.")
            if not _is_member(Direction, cell.direction):
                error(f"Box {index} has invalid direction {cell.direction}.")
            if not _is_member(ItemColor, cell.color):
                error(f"Box {index} has invalid color {cell.color}.")
            if cell.effects is not None:
                warning(f"Box {index} has effects but they are not edited by this tool.")
            if cell.is_active:
                total_source += cell.ball_count
            for x, y in cell.occupied_cells():
                if x < 0 or x >= level.grid_cols or y < 0 or y >= level.grid_rows:
                    error(f"Box {index} is outside box grid bounds.")
                    break
                previous = occupied.get((x, y))
                if previous is not None:
                    error(f"Box {index} overlaps box {previous} at ({x}, {y}).")
                    break
                occupied[(x, y)] = index
        if total_source == 0:
            error("Total source ball count must be greater than 0.")

        grid = level.pixel_grid
        if grid.width <= 0 or grid.height <= 0:
            error("Pixel grid dimensions must be greater than 0.")
        if len(grid.color_ids) != grid.width * grid.height:
            error("pixelGrid.colorIds length must equal width * height.")
        if grid.modifiers:
            error("pixelGrid.modifiers must be empty.")
        if grid.obstacles:
            error("pixelGrid.obstacles must be empty.")

        target_hist: Counter[int] = Counter()
        for index, color_id in enumerate(grid.color_ids):
            if color_id == EMPTY_COLOR_ID:
                continue
            if color_id not in {int(color) for color in ItemColor}:
                error(f"pixelGrid.colorIds[{index}] has invalid color id {color_id}.")
            else:
                target_hist[color_id] += 1
        if sum(target_hist.values()) == 0:
            error("Pixel grid must contain at least one colored pixel.")

        source_hist = level.source_histogram()
        if sum(source_hist.values()) != sum(target_hist.values()):
            error("Total source balls does not match total target pixels.")
        if source_hist != target_hist:
            error("Source color histogram does not match target pixel histogram.")

        if grid.width * grid.height > 4096:
            warning("Pixel grid is large; verify performance in Unity.")
        if level.grid_rows * level.grid_cols > 1200:
            warning("Box grid is large; verify readability and performance.")
        if len(target_hist) > 12:
            warning("Level uses many colors.")
        if len(grid.color_ids) == grid.width * grid.height and grid.width > 0 and grid.height > 0:
            for column, frontier in enumerate(grid.frontier_rows()):
                if frontier is None:
                    warning(f"Pixel grid column {column} has no colored pixel.")
        warning("Histogram balance is not a solvability proof; play-test in Unity.")

        return ValidationResult(messages)


def _is_member(enum_type: type, value: object) -> bool:
    try:
        enum_type(int(value))
        return True
    except (TypeError, ValueError):
        return False
