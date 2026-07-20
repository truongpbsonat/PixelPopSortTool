from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from pixel_level_tool.domain.enums import CellShape, Direction, EMPTY_COLOR_ID, GameMode, ItemColor, LockKeyGate, WoolCrateColor
from pixel_level_tool.domain.level_models import (
    ArrowLockCellEffectData,
    BoxCellData,
    ColorGateObstacleData,
    ElevatorObstacleData,
    FrozenCellEffectData,
    HiddenCellEffectData,
    KeyForLockedGateCellEffectData,
    LargeBlockObstacleData,
    LinkedContainerObstacleData,
    LockedGateObstacleData,
    PinsObstacleData,
    PixelLevelData,
    ScissorForWoolCrateCellEffectData,
    TunnelCellData,
    WoolCrateObstacleData,
)


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
        if level.game_mode != int(GameMode.Classic):
            # Pop-Sort-2 only defines GameMode.Classic and overwrites gameMode at
            # load time, so this is advisory rather than blocking.
            warning("gameMode is not Classic; verify this matches the target project.")
        if level.grid_rows <= 0 or level.grid_cols <= 0:
            error("Box grid dimensions must be greater than 0.")
        if not level.grid_cells:
            error("Box grid must contain at least one source box.")
        if level.grid_lanes:
            warning("Cargo gridLanes are preserved unchanged but cannot be edited by this tool.")

        ids: set[int] = set()
        occupied: dict[tuple[int, int], int] = {}
        active_frozen = 0
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
            if isinstance(cell, TunnelCellData):
                if cell.effects:
                    error(f"Tunnel {index} cannot have cell effects; effects belong to storedCells.")
                if not cell.stored_cells:
                    error(f"Tunnel {index} must contain at least one stored cell.")
                for stored_index, stored_cell in enumerate(cell.stored_cells):
                    if type(stored_cell) is not BoxCellData:
                        error(f"Tunnel {index} stored cell {stored_index} must be a normal CellData.")
                    if not _is_member(CellShape, stored_cell.shape):
                        error(f"Tunnel {index} stored cell {stored_index} has an invalid shape.")
                    if not _is_member(Direction, stored_cell.direction):
                        error(f"Tunnel {index} stored cell {stored_index} has an invalid direction.")
                    if not _is_member(ItemColor, stored_cell.color):
                        error(f"Tunnel {index} stored cell {stored_index} has an invalid color.")
                    for effect in stored_cell.effects or []:
                        if isinstance(effect, FrozenCellEffectData) and effect.frozen_count < 0:
                            error(f"Tunnel {index} stored cell {stored_index} frozenCount must be non-negative.")
            effect_types: set[type] = set()
            for effect in cell.effects or []:
                if type(effect) in effect_types:
                    error(f"Box {index} has duplicate {type(effect).__name__} effects.")
                effect_types.add(type(effect))
                if isinstance(effect, FrozenCellEffectData):
                    if effect.frozen_count < 0:
                        error(f"Box {index} frozenCount must be non-negative.")
                    if effect.frozen_count > 0:
                        active_frozen += 1
                elif isinstance(effect, HiddenCellEffectData) and cell.is_active:
                    error(f"Box {index} cannot be Hidden while initially active.")
                elif isinstance(effect, ArrowLockCellEffectData):
                    if not _has_arrow_blocker(level, index, effect.required_direction):
                        error(f"Box {index} ArrowLock has no blocker in {effect.required_direction.name} direction.")
                elif isinstance(effect, KeyForLockedGateCellEffectData) and effect.lock_key_gate == LockKeyGate.None_:
                    error(f"Box {index} KeyForLockedGate cannot use None.")
                elif isinstance(effect, ScissorForWoolCrateCellEffectData) and effect.scissor_color == WoolCrateColor.None_:
                    error(f"Box {index} ScissorForWoolCrate cannot use None.")
            for x, y in cell.occupied_cells():
                if x < 0 or x >= level.grid_cols or y < 0 or y >= level.grid_rows:
                    error(f"Box {index} is outside box grid bounds.")
                    break
                previous = occupied.get((x, y))
                if previous is not None:
                    error(f"Box {index} overlaps box {previous} at ({x}, {y}).")
                    break
                occupied[(x, y)] = index
        if level.grid_cells and active_frozen >= len(level.grid_cells):
            error("All source boxes cannot be Frozen at the same time.")
        _validate_obstacles(level, error, warning)

        total_source = sum(level.source_histogram().values())
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


def _has_arrow_blocker(level: PixelLevelData, source_index: int, direction: Direction) -> bool:
    return _has_arrow_blocker_for_cell(level, level.grid_cells[source_index], direction)


def _has_arrow_blocker_for_cell(level: PixelLevelData, source, direction: Direction) -> bool:
    source_cells = source.occupied_cells()
    dx, dy = {
        Direction.Up: (0, 1),
        Direction.Down: (0, -1),
        Direction.Left: (-1, 0),
        Direction.Right: (1, 0),
    }[direction]
    for candidate in level.all_boxes():
        if candidate.internal_uid == source.internal_uid:
            continue
        target_cells = set(candidate.occupied_cells())
        for x, y in source_cells:
            cx, cy = x + dx, y + dy
            while 0 <= cx < level.grid_cols and 0 <= cy < level.grid_rows:
                if (cx, cy) in target_cells:
                    return True
                cx += dx
                cy += dy
    return False


def _rect_intersects_board(x: int, y: int, width: int, height: int, rows: int, cols: int) -> bool:
    return width > 0 and height > 0 and x < cols and y < rows and x + width > 0 and y + height > 0


def _effects_signature(cell) -> tuple:
    values = []
    for effect in cell.effects or []:
        if isinstance(effect, FrozenCellEffectData):
            values.append(("Frozen", effect.frozen_count))
        elif isinstance(effect, HiddenCellEffectData):
            values.append(("Hidden",))
        elif isinstance(effect, KeyForLockedGateCellEffectData):
            values.append(("GateKey", int(effect.lock_key_gate)))
        elif isinstance(effect, ScissorForWoolCrateCellEffectData):
            values.append(("Scissor", int(effect.scissor_color)))
        elif isinstance(effect, ArrowLockCellEffectData):
            values.append(("Arrow", int(effect.required_direction)))
    return tuple(sorted(values))


def _pins_form_chain(cells: list) -> bool:
    if len(cells) < 2:
        return False
    footprints = [set(cell.occupied_cells()) for cell in cells]

    def adjacent(left: int, right: int) -> bool:
        for x, y in footprints[left]:
            if any((x + dx, y + dy) in footprints[right] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                return True
        return False

    degrees = [sum(adjacent(i, j) for j in range(len(cells)) if i != j) for i in range(len(cells))]
    if all(1 <= degree <= 2 for degree in degrees) and degrees.count(1) == 2:
        return True
    same_row = len({cell.grid_y for cell in cells}) == 1
    same_col = len({cell.grid_x for cell in cells}) == 1
    if not same_row and not same_col:
        return False
    positions = sorted(cell.grid_x if same_row else cell.grid_y for cell in cells)
    step = positions[1] - positions[0]
    return step > 0 and all(positions[i] - positions[i - 1] == step for i in range(1, len(positions)))


def _validate_obstacles(level: PixelLevelData, error, warning) -> None:
    cells_by_uid = {cell.internal_uid: cell for cell in level.grid_cells}
    gate_keys: set[LockKeyGate] = set()
    rope_colors: set[WoolCrateColor] = set()
    elevators: list[ElevatorObstacleData] = []

    for index, obstacle in enumerate(level.obstacles):
        if isinstance(obstacle, LinkedContainerObstacleData):
            if len(obstacle.target_uids) != 2 or len(set(obstacle.target_uids)) != 2:
                error(f"LinkedContainer {index} must reference exactly two distinct boxes.")
                continue
            targets = [cells_by_uid.get(uid) for uid in obstacle.target_uids]
            if any(cell is None for cell in targets):
                error(f"LinkedContainer {index} references a missing box.")
            elif any(cell.has_effect(ArrowLockCellEffectData) for cell in targets):
                error(f"LinkedContainer {index} cannot target an ArrowLock box.")
            elif _effects_signature(targets[0]) != _effects_signature(targets[1]):
                error(f"LinkedContainer {index} target effects are not compatible.")
        elif isinstance(obstacle, PinsObstacleData):
            if len(obstacle.target_uids) < 2 or len(set(obstacle.target_uids)) != len(obstacle.target_uids):
                error(f"Pins {index} must reference at least two distinct boxes.")
                continue
            targets = [cells_by_uid.get(uid) for uid in obstacle.target_uids]
            if any(cell is None for cell in targets):
                error(f"Pins {index} references a missing box.")
            elif not _pins_form_chain(targets):
                error(f"Pins {index} targets must form a straight or edge-adjacent chain.")
        else:
            if not _rect_intersects_board(obstacle.grid_x, obstacle.grid_y, obstacle.width, obstacle.height, level.grid_rows, level.grid_cols):
                error(f"{type(obstacle).__name__} {index} has no valid area inside the Box Grid.")
            if isinstance(obstacle, (LargeBlockObstacleData, ColorGateObstacleData)) and obstacle.count <= 0:
                error(f"{type(obstacle).__name__} {index} count must be positive.")
            if isinstance(obstacle, LockedGateObstacleData):
                if obstacle.lock_key_gate == LockKeyGate.None_:
                    error(f"LockedGate {index} cannot use None.")
                if obstacle.priority < 0:
                    error(f"LockedGate {index} priority must be non-negative.")
                gate_keys.add(obstacle.lock_key_gate)
            elif isinstance(obstacle, WoolCrateObstacleData):
                valid_ropes = [color for color in obstacle.ropes if color != WoolCrateColor.None_]
                if not valid_ropes:
                    error(f"WoolCrate {index} needs at least one non-None rope.")
                if obstacle.priority < 0:
                    error(f"WoolCrate {index} priority must be non-negative.")
                rope_colors.update(valid_ropes)
            elif isinstance(obstacle, ElevatorObstacleData):
                elevators.append(obstacle)
                _validate_elevator(level, obstacle, index, error)

    for left in range(len(elevators)):
        a = elevators[left]
        for right in range(left + 1, len(elevators)):
            b = elevators[right]
            if a.grid_x < b.grid_x + b.width and a.grid_x + a.width > b.grid_x and a.grid_y < b.grid_y + b.height and a.grid_y + a.height > b.grid_y:
                error(f"Elevator {left} overlaps another Elevator.")

    for box_index, cell in enumerate(level.all_boxes()):
        for effect in cell.effects or []:
            if isinstance(effect, KeyForLockedGateCellEffectData) and effect.lock_key_gate not in gate_keys:
                warning(f"Box {box_index} has a gate key with no matching LockedGate.")
            elif isinstance(effect, ScissorForWoolCrateCellEffectData) and effect.scissor_color not in rope_colors:
                warning(f"Box {box_index} has scissors with no matching WoolCrate rope.")


def _validate_elevator(level: PixelLevelData, elevator: ElevatorObstacleData, index: int, error) -> None:
    rect = (elevator.grid_x, elevator.grid_y, elevator.grid_x + elevator.width, elevator.grid_y + elevator.height)
    anchors: set[tuple[int, int]] = set()
    for layer_index, layer in enumerate(elevator.layers):
        seen: set[tuple[int, int]] = set()
        for cell in layer.cells:
            anchor = (cell.grid_x, cell.grid_y)
            if not (rect[0] <= anchor[0] < rect[2] and rect[1] <= anchor[1] < rect[3]):
                error(f"Elevator {index} layer {layer_index} has a cell anchor outside its rect.")
            if anchor in seen:
                error(f"Elevator {index} layer {layer_index} has duplicate cell anchor {anchor}.")
            seen.add(anchor)
            anchors.add(anchor)
            if not _is_member(CellShape, cell.shape) or not _is_member(Direction, cell.direction) or not _is_member(ItemColor, cell.color):
                error(f"Elevator {index} layer {layer_index} contains an invalid cell enum.")
            effect_types: set[type] = set()
            for effect in cell.effects or []:
                if type(effect) in effect_types:
                    error(f"Elevator {index} layer {layer_index} has a duplicate cell effect.")
                effect_types.add(type(effect))
                if isinstance(effect, FrozenCellEffectData) and effect.frozen_count < 0:
                    error(f"Elevator {index} layer {layer_index} frozenCount must be non-negative.")
                elif isinstance(effect, ArrowLockCellEffectData) and not _has_arrow_blocker_for_cell(level, cell, effect.required_direction):
                    error(f"Elevator {index} layer {layer_index} ArrowLock has no blocker.")
                elif isinstance(effect, KeyForLockedGateCellEffectData) and effect.lock_key_gate == LockKeyGate.None_:
                    error(f"Elevator {index} layer {layer_index} gate key cannot use None.")
                elif isinstance(effect, ScissorForWoolCrateCellEffectData) and effect.scissor_color == WoolCrateColor.None_:
                    error(f"Elevator {index} layer {layer_index} scissors cannot use None.")
    surface_anchors = {(cell.grid_x, cell.grid_y) for cell in level.grid_cells}
    for anchor in anchors:
        if anchor not in surface_anchors:
            error(f"Elevator {index} has no surface box at {anchor}.")
