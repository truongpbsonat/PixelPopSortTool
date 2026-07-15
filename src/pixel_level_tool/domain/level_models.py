from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field

from pixel_level_tool.domain.enums import (
    EMPTY_COLOR_ID,
    CellShape,
    Direction,
    GameMode,
    ItemColor,
    LevelDifficulty,
)
from pixel_level_tool.domain.shapes import ball_count, footprint, oriented_dimensions


@dataclass
class BoxCellData:
    grid_x: int
    grid_y: int
    shape: CellShape = CellShape.Square_3x3
    direction: Direction = Direction.Up
    color: ItemColor = ItemColor.Red
    id: int = 0
    is_active: bool = True
    effects: object | None = None

    def occupied_cells(self) -> tuple[tuple[int, int], ...]:
        return tuple((self.grid_x + dx, self.grid_y + dy) for dx, dy in footprint(self.shape, self.direction))

    @property
    def width(self) -> int:
        return oriented_dimensions(self.shape, self.direction)[0]

    @property
    def height(self) -> int:
        return oriented_dimensions(self.shape, self.direction)[1]

    @property
    def ball_count(self) -> int:
        return ball_count(self.shape)


@dataclass
class PixelGridData:
    width: int = 8
    height: int = 8
    color_ids: list[int] | None = None
    modifiers: list[object] = field(default_factory=list)
    obstacles: list[object] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.color_ids is None:
            self.color_ids = [EMPTY_COLOR_ID] * max(0, self.width * self.height)

    def ensure_dense(self) -> None:
        expected = max(0, self.width * self.height)
        if len(self.color_ids) < expected:
            self.color_ids.extend([EMPTY_COLOR_ID] * (expected - len(self.color_ids)))
        elif len(self.color_ids) > expected:
            del self.color_ids[expected:]

    def index(self, row: int, column: int) -> int:
        if row < 0 or row >= self.height or column < 0 or column >= self.width:
            raise IndexError(f"Pixel ({row}, {column}) is outside {self.width}x{self.height}.")
        return row * self.width + column

    def get_color_id(self, row: int, column: int) -> int:
        return self.color_ids[self.index(row, column)]

    def set_color_id(self, row: int, column: int, color_id: int) -> None:
        self.color_ids[self.index(row, column)] = color_id

    def resize(self, width: int, height: int) -> None:
        old_width, old_height = self.width, self.height
        old = list(self.color_ids)
        self.width = width
        self.height = height
        self.color_ids = [EMPTY_COLOR_ID] * (width * height)
        copy_width = min(old_width, width)
        copy_height = min(old_height, height)
        for row in range(copy_height):
            for column in range(copy_width):
                self.color_ids[row * width + column] = old[row * old_width + column]

    def fill(self, color_id: int) -> None:
        self.color_ids = [color_id] * (self.width * self.height)

    def clear(self) -> None:
        self.fill(EMPTY_COLOR_ID)

    def histogram(self) -> Counter[int]:
        return Counter(color_id for color_id in self.color_ids if color_id != EMPTY_COLOR_ID)

    def frontier_rows(self) -> list[int | None]:
        result: list[int | None] = []
        for column in range(self.width):
            frontier = None
            for row in range(self.height):
                if self.get_color_id(row, column) != EMPTY_COLOR_ID:
                    frontier = row
                    break
            result.append(frontier)
        return result


@dataclass
class PixelLevelData:
    grid_rows: int = 10
    grid_cols: int = 10
    level: int = 1
    level_name: str | None = "Pixel Level 1"
    level_grid_version: int = 1
    map_type: int = 0
    board: int = 1
    grid_cells: list[BoxCellData] = field(default_factory=list)
    pixel_grid: PixelGridData = field(default_factory=PixelGridData)
    game_mode: int = int(GameMode.Pixel)
    difficulty: int = int(LevelDifficulty.Normal)
    category: int = 0
    grid_lanes: list[object] = field(default_factory=list)
    obstacles: list[object] = field(default_factory=list)
    extra_fields: dict[str, object] = field(default_factory=dict)

    def clone(self) -> "PixelLevelData":
        return deepcopy(self)

    def source_histogram(self) -> Counter[int]:
        hist: Counter[int] = Counter()
        for cell in self.grid_cells:
            if cell.is_active:
                hist[int(cell.color)] += cell.ball_count
        return hist

    def target_histogram(self) -> Counter[int]:
        return self.pixel_grid.histogram()

    def can_place(self, candidate: BoxCellData, ignore_index: int | None = None) -> bool:
        occupied: set[tuple[int, int]] = set()
        for index, cell in enumerate(self.grid_cells):
            if ignore_index is not None and index == ignore_index:
                continue
            occupied.update(cell.occupied_cells())
        for x, y in candidate.occupied_cells():
            if x < 0 or x >= self.grid_cols or y < 0 or y >= self.grid_rows:
                return False
            if (x, y) in occupied:
                return False
        return True

    def add_box(self, box: BoxCellData) -> bool:
        if not self.can_place(box):
            return False
        self.grid_cells.append(box)
        return True

    def assign_deterministic_ids(self, start: int = 300) -> None:
        ordered = sorted(enumerate(self.grid_cells), key=lambda item: (item[1].grid_y, item[1].grid_x, item[0]))
        for offset, (_, cell) in enumerate(ordered):
            cell.id = start + offset

    def resize_box_grid(self, rows: int, cols: int, drop_out_of_bounds: bool = False) -> list[BoxCellData]:
        old_rows, old_cols = self.grid_rows, self.grid_cols
        self.grid_rows, self.grid_cols = rows, cols
        removed: list[BoxCellData] = []
        kept: list[BoxCellData] = []
        for cell in self.grid_cells:
            if self.can_place(cell, ignore_index=self.grid_cells.index(cell)):
                kept.append(cell)
            else:
                removed.append(cell)
        if removed and not drop_out_of_bounds:
            self.grid_rows, self.grid_cols = old_rows, old_cols
            return removed
        self.grid_cells = kept
        return removed
