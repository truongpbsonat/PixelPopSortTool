from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from uuid import uuid4

from pixel_level_tool.domain.enums import (
    EMPTY_COLOR_ID,
    CellShape,
    LockKeyGate,
    Direction,
    GameMode,
    ItemColor,
    LevelDifficulty,
    WoolCrateColor,
)
from pixel_level_tool.domain.shapes import ball_count, footprint, oriented_dimensions


@dataclass
class FrozenCellEffectData:
    frozen_count: int = 1


@dataclass
class HiddenCellEffectData:
    pass


@dataclass
class ArrowLockCellEffectData:
    required_direction: Direction = Direction.Up


@dataclass
class KeyForLockedGateCellEffectData:
    lock_key_gate: LockKeyGate = LockKeyGate.Red


@dataclass
class ScissorForWoolCrateCellEffectData:
    scissor_color: WoolCrateColor = WoolCrateColor.Red


CellEffectData = (
    FrozenCellEffectData
    | HiddenCellEffectData
    | ArrowLockCellEffectData
    | KeyForLockedGateCellEffectData
    | ScissorForWoolCrateCellEffectData
)


@dataclass
class BoxCellData:
    grid_x: int
    grid_y: int
    shape: CellShape = CellShape.Square_3x3
    direction: Direction = Direction.Up
    color: ItemColor = ItemColor.Red
    id: int = 0
    is_active: bool = True
    effects: list[CellEffectData] | None = None
    internal_uid: str = field(default_factory=lambda: uuid4().hex, repr=False)

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

    def has_effect(self, effect_type: type[CellEffectData]) -> bool:
        return any(isinstance(effect, effect_type) for effect in self.effects or [])


@dataclass
class TunnelCellData(BoxCellData):
    """A fixed grid tunnel whose ball containers are stored off-grid."""

    stored_cells: list[BoxCellData] = field(default_factory=list)

    @property
    def ball_count(self) -> int:
        return sum(cell.ball_count for cell in self.stored_cells)


@dataclass
class LinkedContainerObstacleData:
    target_uids: list[str] = field(default_factory=list)
    id: int = 0


@dataclass
class LargeBlockObstacleData:
    grid_x: int = 0
    grid_y: int = 0
    width: int = 1
    height: int = 1
    count: int = 1
    id: int = 0


@dataclass
class PinsObstacleData:
    target_uids: list[str] = field(default_factory=list)
    required_direction: Direction = Direction.Up
    id: int = 0


@dataclass
class LockedGateObstacleData:
    grid_x: int = 0
    grid_y: int = 0
    width: int = 1
    height: int = 1
    lock_key_gate: LockKeyGate = LockKeyGate.Red
    priority: int = 0
    id: int = 0


@dataclass
class WoolCrateObstacleData:
    grid_x: int = 0
    grid_y: int = 0
    width: int = 1
    height: int = 1
    ropes: list[WoolCrateColor] = field(default_factory=lambda: [WoolCrateColor.Red])
    priority: int = 0
    id: int = 0


@dataclass
class ColorGateObstacleData:
    grid_x: int = 0
    grid_y: int = 0
    width: int = 1
    height: int = 1
    count: int = 1
    required_color: ItemColor = ItemColor.DarkBlue
    id: int = 0


@dataclass
class ElevatorLayerData:
    cells: list[BoxCellData] = field(default_factory=list)


@dataclass
class ElevatorObstacleData:
    grid_x: int = 0
    grid_y: int = 0
    width: int = 1
    height: int = 1
    layers: list[ElevatorLayerData] = field(default_factory=list)
    id: int = 0


ObstacleData = (
    LinkedContainerObstacleData
    | LargeBlockObstacleData
    | PinsObstacleData
    | LockedGateObstacleData
    | WoolCrateObstacleData
    | ColorGateObstacleData
    | ElevatorObstacleData
)


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

    def rotate_clockwise(self) -> None:
        """Rotate every pixel 90 degrees clockwise around the grid bounds."""
        old_width, old_height = self.width, self.height
        old_color_ids = self.color_ids
        self.width = old_height
        self.height = old_width
        self.color_ids = [
            old_color_ids[row * old_width + column]
            for column in range(old_width)
            for row in range(old_height - 1, -1, -1)
        ]

    def fill(self, color_id: int) -> None:
        self.color_ids = [color_id] * (self.width * self.height)

    def clear(self) -> None:
        self.fill(EMPTY_COLOR_ID)

    def replace_color(self, source: ItemColor, target: ItemColor) -> int:
        """Replace every occurrence of ``source`` and return the pixel count."""
        source_id = int(source)
        target_id = int(target)
        replaced = sum(color_id == source_id for color_id in self.color_ids)
        if replaced:
            self.color_ids = [target_id if color_id == source_id else color_id for color_id in self.color_ids]
        return replaced

    def trim_empty_borders(self) -> bool:
        """Remove consecutive empty rows and columns around painted content."""
        if self.width <= 0 or self.height <= 0:
            return False

        painted_indices = [
            index for index, color_id in enumerate(self.color_ids) if color_id != EMPTY_COLOR_ID
        ]
        if not painted_indices:
            return False

        painted_rows = [index // self.width for index in painted_indices]
        painted_columns = [index % self.width for index in painted_indices]
        top, bottom = min(painted_rows), max(painted_rows)
        left, right = min(painted_columns), max(painted_columns)
        new_width = right - left + 1
        new_height = bottom - top + 1
        if new_width == self.width and new_height == self.height:
            return False

        old_width = self.width
        old_color_ids = self.color_ids
        self.width = new_width
        self.height = new_height
        self.color_ids = [
            old_color_ids[row * old_width + column]
            for row in range(top, bottom + 1)
            for column in range(left, right + 1)
        ]
        return True

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
    obstacles: list[ObstacleData] = field(default_factory=list)
    extra_fields: dict[str, object] = field(default_factory=dict)

    def clone(self) -> "PixelLevelData":
        return deepcopy(self)

    def source_histogram(self) -> Counter[int]:
        hist: Counter[int] = Counter()

        def add_cell(cell: BoxCellData) -> None:
            if isinstance(cell, TunnelCellData):
                for stored_cell in cell.stored_cells:
                    add_cell(stored_cell)
            else:
                hist[int(cell.color)] += cell.ball_count

        for cell in self.all_boxes():
            add_cell(cell)
        return hist

    def all_boxes(self) -> list[BoxCellData]:
        boxes = list(self.grid_cells)
        for obstacle in self.obstacles:
            if isinstance(obstacle, ElevatorObstacleData):
                for layer in obstacle.layers:
                    boxes.extend(layer.cells)
        return boxes

    def target_histogram(self) -> Counter[int]:
        return self.pixel_grid.histogram()

    def replace_color(self, source: ItemColor, target: ItemColor) -> tuple[int, int]:
        """Replace a color in both source boxes and target pixels.

        Returns the number of changed box cells and pixel cells respectively.
        """
        if source == target:
            return 0, 0
        box_count = 0
        def replace_cell(cell: BoxCellData) -> None:
            nonlocal box_count
            if cell.color == source:
                cell.color = target
                box_count += 1
            if isinstance(cell, TunnelCellData):
                for stored_cell in cell.stored_cells:
                    replace_cell(stored_cell)

        for cell in self.all_boxes():
            replace_cell(cell)
        for obstacle in self.obstacles:
            if isinstance(obstacle, ColorGateObstacleData) and obstacle.required_color == source:
                obstacle.required_color = target
        return box_count, self.pixel_grid.replace_color(source, target)

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
        next_id = start + len(ordered)
        for _, cell in ordered:
            if not isinstance(cell, TunnelCellData):
                continue
            for stored_cell in cell.stored_cells:
                stored_cell.id = next_id
                next_id += 1
        for obstacle in self.obstacles:
            if not isinstance(obstacle, ElevatorObstacleData):
                continue
            for layer in obstacle.layers:
                for cell in sorted(layer.cells, key=lambda item: (item.grid_y, item.grid_x)):
                    cell.id = next_id
                    next_id += 1

        next_ids: dict[type, int] = {
            LinkedContainerObstacleData: 3001,
            LargeBlockObstacleData: 5001,
            PinsObstacleData: 6001,
            ColorGateObstacleData: 6501,
            LockedGateObstacleData: 7001,
            WoolCrateObstacleData: 8001,
            ElevatorObstacleData: 8501,
        }
        for obstacle in self.obstacles:
            obstacle_type = type(obstacle)
            if obstacle_type in next_ids:
                obstacle.id = next_ids[obstacle_type]
                next_ids[obstacle_type] += 1

    def box_by_uid(self, uid: str) -> BoxCellData | None:
        return next((cell for cell in self.grid_cells if cell.internal_uid == uid), None)

    def remove_box(self, index: int) -> BoxCellData:
        removed = self.grid_cells.pop(index)
        kept: list[ObstacleData] = []
        for obstacle in self.obstacles:
            if isinstance(obstacle, LinkedContainerObstacleData):
                obstacle.target_uids = [uid for uid in obstacle.target_uids if uid != removed.internal_uid]
                if len(obstacle.target_uids) != 2:
                    continue
            elif isinstance(obstacle, PinsObstacleData):
                obstacle.target_uids = [uid for uid in obstacle.target_uids if uid != removed.internal_uid]
                if len(obstacle.target_uids) < 2:
                    continue
            kept.append(obstacle)
        self.obstacles = kept
        return removed

    def resize_box_grid(self, rows: int, cols: int, drop_out_of_bounds: bool = False) -> list[BoxCellData]:
        removed, invalid_obstacles = self.resize_issues(rows, cols)
        if (removed or invalid_obstacles) and not drop_out_of_bounds:
            return removed
        self.grid_rows, self.grid_cols = rows, cols
        removed_uids = {cell.internal_uid for cell in removed}
        for index in range(len(self.grid_cells) - 1, -1, -1):
            if self.grid_cells[index].internal_uid in removed_uids:
                self.remove_box(index)
        invalid_ids = {id(obstacle) for obstacle in invalid_obstacles}
        self.obstacles = [obstacle for obstacle in self.obstacles if id(obstacle) not in invalid_ids]
        return removed

    def resize_issues(self, rows: int, cols: int) -> tuple[list[BoxCellData], list[ObstacleData]]:
        removed = [
            cell for cell in self.grid_cells
            if any(x < 0 or x >= cols or y < 0 or y >= rows for x, y in cell.occupied_cells())
        ]
        invalid: list[ObstacleData] = []
        for obstacle in self.obstacles:
            if isinstance(obstacle, (LinkedContainerObstacleData, PinsObstacleData)):
                continue
            outside = (
                obstacle.width <= 0 or obstacle.height <= 0 or obstacle.grid_x < 0 or obstacle.grid_y < 0
                or obstacle.grid_x + obstacle.width > cols or obstacle.grid_y + obstacle.height > rows
            )
            if isinstance(obstacle, ElevatorObstacleData):
                outside = outside or any(
                    cell.grid_x < 0 or cell.grid_x >= cols or cell.grid_y < 0 or cell.grid_y >= rows
                    for layer in obstacle.layers for cell in layer.cells
                )
            if outside:
                invalid.append(obstacle)
        return removed, invalid
