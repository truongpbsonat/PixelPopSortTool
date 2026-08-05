from __future__ import annotations

"""Generate a complete, playable Box Ball Grid from the current Pixel Grid.

The output matches the shape of the hand-made levels: the box grid is a full
rectangle of ``Square_3x3`` boxes anchored on a 3-cell lattice, every box is
mono-color and inactive, and the difficulty comes from how many boxes carry the
``Hidden`` effect rather than from the tray size.

Five stages:

1. **Balance** - a box holds exactly nine balls, so pixels whose color count is
   not a multiple of nine are deleted from the pixel grid (bottom-most,
   edge-most first).
2. **Walkthrough** - the pixel histogram fully determines the box multiset, so
   only the pick order is open; :func:`pixel_gameplay.solve_order` searches for
   an order that wins at the target ``piece``.
3. **Layout** - the boxes fill the smallest lattice of 3x3 slots that holds them
   all, no larger than the configured slot limit (8x8 slots = 24x24 cells = 576
   balls). Walkthrough order maps onto the slots front row first, scrambled by
   difficulty. A picture too big for the whole lattice overflows into tunnels,
   and ``tunnel_mode="mechanic"`` asks for tunnels even when everything fits.
   Any slot the boxes do not fill is a **wall**: it blocks the route to the
   boxes around it, so Hard and SuperHard reserve a couple on purpose to pinch a
   box down to a single way in.
4. **Queue** - each tunnel gets a contiguous block of the walkthrough, and the
   block is buried by difficulty: ``dig_window == 1`` releases every box exactly
   at the step it is needed, a wider window reverses that many boxes so the
   wanted color sits at the *back* of the window and the player has to keep
   pulling to reach it. The window is only as wide as the tray survives. Each
   tunnel's ``direction`` is the side it hands its queue out on, so it is aimed
   at a neighbouring slot that really holds a box - never at a wall, another
   tunnel or off the edge of the lattice, all of which would seal the mouth.
5. **Hide** - a difficulty-driven share of the boxes gets the ``Hidden`` effect,
   weighted towards the back rows and never on the front row, so the player can
   always see what is immediately available but not what is coming.
6. **Link** - opt-in ``LinkedContainer`` obstacles tie pairs of neighbouring boxes
   together: tapping one sends both down, so the pick costs two tray slots at
   once. ``linked_mode="sync"`` pairs boxes the board wants within a step or two
   of each other, so the second half drains straight away and the link is a
   freebie; ``"stall"`` deliberately pairs a wanted box with one needed much
   later, so the partner squats in the tray and the conveyor runs full.
7. **Lock** - opt-in ``ArrowLock`` effects shut a box until a box in the arrow's
   direction has been opened. The arrow only ever points at a real neighbouring
   box that the walkthrough opens *earlier*, never at a wall, a tunnel or off the
   grid, so the lock always has a key and the certified order stays legal.
8. **Certify** - the level is replayed with
   :func:`pixel_gameplay.simulate_order`, both in walkthrough order and in the
   order the tunnels, links and locks actually force, its histograms are checked
   against the pixel grid, and :func:`pixel_gameplay.measure_difficulty` scores
   it.
"""

import random
from collections import Counter
from dataclasses import dataclass, field

from pixel_level_tool.domain.enums import (
    EMPTY_COLOR_ID,
    CellShape,
    COLOR_NAMES,
    Direction,
    ItemColor,
    LevelDifficulty,
    ThemeId,
)
from pixel_level_tool.domain.level_models import (
    ArrowLockCellEffectData,
    BoxCellData,
    CellEffectData,
    HiddenCellEffectData,
    LinkedContainerObstacleData,
    PixelGridData,
    PixelLevelData,
    TunnelCellData,
)
from pixel_level_tool.services.pixel_gameplay import (
    BoardState,
    BoxSpec,
    DifficultyMetrics,
    GameRules,
    GameplayError,
    Solution,
    TunnelRelease,
    box_multiset,
    measure_difficulty,
    minimum_tray,
    resolve_link_groups,
    resolve_pick_sequence,
    simulate_groups,
    simulate_order,
    solve_order,
)


# A Square_3x3 box covers a 3x3 block of grid cells and holds nine balls, so the
# box grid is a lattice of 3-cell slots: `gridCols = 3 * slot columns`.
SLOT = 3
BALLS_PER_BOX = 9
MAX_BOX_SLOTS = 8
MAX_TRAY_SLOTS = 8
ACTIVE_POLICIES = ("none", "row0", "all")
SCRAMBLE_MODES = ("ordered", "local", "global")
TUNNEL_MODES = ("overflow", "mechanic")
LINKED_MODES = ("auto", "sync", "stall")

# How far the correct next box may sit from the front of the grid, in boxes,
# when the layout is only locally scrambled.
LOCAL_SCRAMBLE_WINDOW = 4

# A tunnel is a queue with no visible depth limit, but a very deep one just hides
# most of the level, so overflow spreads over more tunnels instead.
MAX_TUNNEL_DEPTH = 16

# A wall costs a whole slot and narrows the way in to its neighbours, so it is
# the most expensive difficulty knob here: at most one wall per this many boxes.
WALL_BOX_BUDGET = 4

# An ArrowLock box is dead weight until its key box goes, so a grid full of them
# leaves the player nothing to tap: at most one locked box per this many boxes.
ARROW_BOX_BUDGET = 3

# A linked pair spends two tray slots on one tap, so it is priced like a wall:
# at most one pair (two boxes) per this many boxes.
LINK_BOX_BUDGET = 4

# How far apart, in picks, the two halves of a link may be.  A "sync" pair is
# wanted at almost the same moment, so the second half drains at once and the
# link costs nothing; a "stall" pair reaches this far ahead for its partner, so
# the partner sits in the tray with no column to pour into.
MAX_SYNC_GAP = 2
MIN_STALL_GAP = 3

# Mirrors LevelValidator._has_arrow_blocker_for_cell: the box grid's gridY grows
# away from the front row, so Up is +1 and Down is -1. Both the ArrowLock arrows
# and the tunnel mouths step through this.
DIRECTION_STEPS: dict[Direction, tuple[int, int]] = {
    Direction.Up: (0, 1),
    Direction.Down: (0, -1),
    Direction.Left: (-1, 0),
    Direction.Right: (1, 0),
}

# Which way a tunnel would rather face when several sides are equally usable.
# Down first: a tunnel is parked on a back row, so facing the front row aims it
# at the part of the grid the player drains first, the way the hand-made levels
# point their edge tunnels inwards.
TUNNEL_FACING_ORDER = (Direction.Down, Direction.Left, Direction.Right, Direction.Up)


class AutoGenError(ValueError):
    pass


# --------------------------------------------------------------------------- #
# Difficulty profiles
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DifficultyProfile:
    """How a difficulty label turns into concrete level knobs.

    The hand-made levels keep ``piece`` at 5 at every difficulty and get their
    bite from ``Hidden``: a hidden box shows no color, so the player cannot tell
    whether picking it wastes a tray slot. ``hidden_ratio`` is therefore the main
    dial, and ``scramble`` decides how far from the front row the next needed box
    may sit, i.e. how much searching is required.
    """

    hidden_ratio: float
    tray_slots: int
    scramble: str
    label: str
    # Tunnels, for `tunnel_mode="mechanic"`: how many to plant and how deep.
    tunnels: int = 1
    tunnel_depth: int = 3
    # Boxes the player pops before the one they wanted, when it is buried worst.
    # 1 means "never buried": the head of the queue is always the next box needed.
    dig_window: int = 1
    # Slots left empty on purpose. A wall blocks the way in to the boxes beside
    # it, so this stays tiny: two walls pinch one box down to a single approach,
    # which is the whole point, and more than that just strangles the grid.
    walls: int = 0
    # ArrowLock, only when the option is on. An arrow box is shut until the box it
    # points at is gone, which is a hard mechanic even in small doses, so this
    # share stays well under the ARROW_BOX_BUDGET ceiling at the easy end.
    arrow_ratio: float = 0.0
    # LinkedContainer, only when the option is on: how many pairs to tie, and
    # whether the partner is a box the board wants right away ("sync", a freebie)
    # or one it will not want for a while ("stall", a squatted tray slot).
    linked_pairs: int = 0
    linked_mode: str = "sync"


DIFFICULTY_PROFILES: dict[int, DifficultyProfile] = {
    int(LevelDifficulty.Easy): DifficultyProfile(
        0.00, 5, "ordered", "Easy", tunnels=1, tunnel_depth=3, dig_window=1, walls=0,
        arrow_ratio=0.08, linked_pairs=2, linked_mode="sync",
    ),
    int(LevelDifficulty.Medium): DifficultyProfile(
        0.15, 5, "ordered", "Medium", tunnels=1, tunnel_depth=4, dig_window=2, walls=0,
        arrow_ratio=0.15, linked_pairs=3, linked_mode="sync",
    ),
    int(LevelDifficulty.Hard): DifficultyProfile(
        0.40, 5, "local", "Hard", tunnels=2, tunnel_depth=4, dig_window=3, walls=2,
        arrow_ratio=0.25, linked_pairs=3, linked_mode="stall",
    ),
    int(LevelDifficulty.SuperHard): DifficultyProfile(
        0.60, 5, "global", "SuperHard", tunnels=2, tunnel_depth=5, dig_window=4, walls=4,
        arrow_ratio=0.33, linked_pairs=4, linked_mode="stall",
    ),
}

# Mirrors MainWindow._DIFFICULTY_FORCED_THEME so a generated level lands on the
# theme the rest of the tool would pick for that difficulty.
DIFFICULTY_FORCED_THEME: dict[int, int] = {
    int(LevelDifficulty.Hard): int(ThemeId.Hard),
    int(LevelDifficulty.SuperHard): int(ThemeId.SuperHard),
}


@dataclass
class AutoGenOptions:
    difficulty: int = int(LevelDifficulty.Easy)
    max_slot_cols: int = MAX_BOX_SLOTS
    max_slot_rows: int = MAX_BOX_SLOTS
    hidden_ratio: float | None = None
    tray_slots: int = 0
    active_policy: str = "none"
    allow_tunnels: bool = True
    max_tunnels: int = 4
    tunnel_mode: str = "overflow"
    tunnel_depth: int = 0
    dig_window: int | None = None
    walls: int | None = None
    # Both mechanics are opt-in per level: the designer decides up front whether
    # this level has them at all, and only then does the difficulty set the dose.
    use_arrow_lock: bool = False
    arrow_ratio: float | None = None
    use_linked_container: bool = False
    linked_pairs: int | None = None
    linked_mode: str = "auto"
    apply_theme: bool = True
    seed: int | None = None


@dataclass
class AutoGenResult:
    level: PixelLevelData
    metrics: DifficultyMetrics
    solution: Solution
    slot_cols: int = 0
    slot_rows: int = 0
    surface_boxes: int = 0
    tunnel_boxes: int = 0
    tunnel_count: int = 0
    dig_windows: list[int] = field(default_factory=list)
    release: TunnelRelease = field(default_factory=TunnelRelease)
    tunnel_queues: list[list[int]] = field(default_factory=list)
    # Per tunnel actually used: its slot and the direction its mouth faces.
    tunnel_mouths: list[tuple[tuple[int, int], Direction]] = field(default_factory=list)
    wall_slots: list[tuple[int, int]] = field(default_factory=list)
    pinched_slots: list[tuple[int, int]] = field(default_factory=list)
    hidden_boxes: int = 0
    hidden_by_slot_row: list[tuple[int, int]] = field(default_factory=list)
    hidden_by_color: list[tuple[int, int, int]] = field(default_factory=list)
    # Per ArrowLock box: its slot, the direction the arrow points, the slot of the
    # key box it points at, and how many picks later than the key it is opened.
    arrow_locks: list[tuple[tuple[int, int], Direction, tuple[int, int], int]] = field(
        default_factory=list
    )
    # (slot, slot, gap in picks) per LinkedContainer pair.
    linked_pairs: list[tuple[tuple[int, int], tuple[int, int], int]] = field(default_factory=list)
    linked_mode: str = "sync"
    play_groups: list[list[int]] = field(default_factory=list)
    removed_pixels: Counter[int] = field(default_factory=Counter)
    emptied_columns: list[int] = field(default_factory=list)
    dropped_obstacles: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def grid_cols(self) -> int:
        return self.slot_cols * SLOT

    @property
    def grid_rows(self) -> int:
        return self.slot_rows * SLOT

    @property
    def total_boxes(self) -> int:
        return self.surface_boxes + self.tunnel_boxes

    @property
    def wall_count(self) -> int:
        return len(self.wall_slots)

    @property
    def hidden_ratio(self) -> float:
        return self.hidden_boxes / self.total_boxes if self.total_boxes else 0.0

    @property
    def surface_hidden_ratio(self) -> float:
        """Hidden share of the boxes that *could* be hidden, i.e. not the stored ones.

        A tunnel already conceals everything behind its head, so the ``Hidden``
        budget is only ever spent on the surface and only means something there.
        """
        return self.hidden_boxes / self.surface_boxes if self.surface_boxes else 0.0

    @property
    def dig_window(self) -> int:
        """Deepest a wanted box is buried in any tunnel, in boxes to pop first."""
        return max(self.dig_windows, default=1)

    @property
    def arrow_count(self) -> int:
        return len(self.arrow_locks)

    @property
    def link_count(self) -> int:
        return len(self.linked_pairs)

    @property
    def max_link_gap(self) -> int:
        """Longest a linked partner squats in the tray, in picks."""
        return max((gap for _, _, gap in self.linked_pairs), default=0)

    @property
    def max_arrow_wait(self) -> int:
        """Longest an arrow lock stays shut after the level starts, in picks."""
        return max((wait for _, _, _, wait in self.arrow_locks), default=0)

    @property
    def play_groups_specs(self) -> list[list[BoxSpec]]:
        """The real play order, one entry per tap, several boxes when they are linked."""
        order = self.solution.order
        groups = self.play_groups or [[index] for index in self.release.sequence]
        return [[order[index] for index in group] for group in groups]

    @property
    def play_order(self) -> list[BoxSpec]:
        """The walkthrough as the tunnels and links force it to be played."""
        return [spec for group in self.play_groups_specs for spec in group]


# --------------------------------------------------------------------------- #
# Stage 1 - balance the pixel grid
# --------------------------------------------------------------------------- #
def balance_pixel_grid(grid: PixelGridData, unit: int = BALLS_PER_BOX) -> tuple[Counter[int], list[int]]:
    """Delete the fewest pixels that make every color count a multiple of ``unit``.

    Pixels are eaten top-down, so the deletions start at the bottom of the
    picture and prefer columns away from the centre; a column is only emptied
    when no other pixel of that color is left.
    """
    grid.ensure_dense()
    removed: Counter[int] = Counter()
    for color_id, count in sorted(grid.histogram().items()):
        for _ in range(count % unit):
            target = _least_valuable_pixel(grid, color_id)
            if target is None:  # pragma: no cover - histogram guarantees a pixel exists
                break
            grid.set_color_id(target[0], target[1], EMPTY_COLOR_ID)
            removed[color_id] += 1
    emptied = [
        column
        for column in range(grid.width)
        if all(grid.get_color_id(row, column) == EMPTY_COLOR_ID for row in range(grid.height))
    ]
    return removed, emptied


def _least_valuable_pixel(grid: PixelGridData, color_id: int) -> tuple[int, int] | None:
    painted_per_column = [
        sum(grid.get_color_id(row, column) != EMPTY_COLOR_ID for row in range(grid.height))
        for column in range(grid.width)
    ]
    centre = (grid.width - 1) / 2
    best: tuple[int, int] | None = None
    best_key: tuple[int, int, float] | None = None
    for row in range(grid.height):
        for column in range(grid.width):
            if grid.get_color_id(row, column) != color_id:
                continue
            key = (
                0 if painted_per_column[column] > 1 else 1,
                -row,
                -abs(column - centre),
            )
            if best_key is None or key < best_key:
                best, best_key = (row, column), key
    return best


# --------------------------------------------------------------------------- #
# Stage 3 - lattice layout
# --------------------------------------------------------------------------- #
@dataclass
class Placement:
    spec: BoxSpec
    order_index: int
    slot_x: int
    slot_y: int

    @property
    def grid_x(self) -> int:
        return self.slot_x * SLOT

    @property
    def grid_y(self) -> int:
        return self.slot_y * SLOT


def choose_lattice(box_count: int, max_cols: int, max_rows: int) -> tuple[int, int]:
    """Smallest slot rectangle that holds every box, preferring an exact fit.

    Ties break towards the squarest shape and then towards more rows than
    columns, which is how the hand-made levels are laid out (30 boxes -> 5x6).
    """
    best: tuple[int, int] | None = None
    best_key: tuple[int, int, int] | None = None
    for cols in range(1, max_cols + 1):
        for rows in range(1, max_rows + 1):
            if cols * rows < box_count:
                continue
            key = (cols * rows - box_count, abs(cols - rows), cols)
            if best_key is None or key < best_key:
                best, best_key = (cols, rows), key
    if best is None:
        return max_cols, max_rows
    return best


def _slot_sequence(cols: int, rows: int) -> list[tuple[int, int]]:
    """Slots from the front row (``slot_y == 0``, drawn at the bottom) backwards."""
    return [(slot_x, slot_y) for slot_y in range(rows) for slot_x in range(cols)]


def _scramble(order: list[int], mode: str, rng: random.Random) -> list[int]:
    shuffled = list(order)
    if mode == "global":
        rng.shuffle(shuffled)
    elif mode == "local":
        for start in range(0, len(shuffled), LOCAL_SCRAMBLE_WINDOW):
            window = shuffled[start : start + LOCAL_SCRAMBLE_WINDOW]
            rng.shuffle(window)
            shuffled[start : start + LOCAL_SCRAMBLE_WINDOW] = window
    return shuffled


def plan_tunnels(
    box_count: int,
    capacity: int,
    options: AutoGenOptions,
    profile: DifficultyProfile,
) -> tuple[int, int]:
    """How many tunnels to build and how many boxes they swallow.

    A tunnel pays for itself twice: it stores boxes, but it also eats a surface
    slot forever, because an emptied tunnel stays on the grid as a wall. So an
    overflowing picture needs tunnels for ``box_count - (capacity - tunnels)``
    boxes, not just for ``box_count - capacity``.

    In ``mechanic`` mode the tunnels are wanted for their own sake, so the
    difficulty's count and depth apply even when everything would have fit.
    """
    max_tunnels = max(1, options.max_tunnels)
    wanted = min(profile.tunnels, max_tunnels) if options.tunnel_mode == "mechanic" else 0
    tunnels = wanted
    if box_count > capacity - tunnels:
        tunnels = max(tunnels, 1)
        while tunnels < max_tunnels and box_count - (capacity - tunnels) > tunnels * MAX_TUNNEL_DEPTH:
            tunnels += 1
    if not tunnels:
        return 0, 0
    if not options.allow_tunnels:
        raise AutoGenError(
            f"{box_count} boxes ({box_count * BALLS_PER_BOX} balls) do not fit in a "
            f"{capacity} slot box grid and tunnels are disabled."
        )
    if capacity - tunnels < 1:
        raise AutoGenError("The box grid slot limit has no room for both boxes and tunnels.")

    forced = max(0, box_count - (capacity - tunnels))
    depth = options.tunnel_depth or (profile.tunnel_depth if options.tunnel_mode == "mechanic" else 1)
    stored = max(forced, min(tunnels * depth, box_count - 1))
    return tunnels, stored


def _tunnel_slots(slots: list[tuple[int, int]], count: int) -> list[tuple[int, int]]:
    """Park tunnels on the back rows, outermost column first.

    The hand-made levels put their tunnels at the edges: a permanent wall hurts
    least there, and the outer columns keep the middle of the grid readable. A
    narrow lattice has fewer edge slots than tunnels, so this keeps walking
    forward row by row rather than running out of slots.
    """
    if count <= 0:
        return []
    centre = max(slot_x for slot_x, _ in slots) / 2
    ordered = sorted(slots, key=lambda slot: (-slot[1], -abs(slot[0] - centre), slot[0]))
    if count > len(ordered):  # pragma: no cover - plan_tunnels keeps a slot per tunnel
        raise AutoGenError("The box grid lattice has fewer slots than the level needs tunnels.")
    return sorted(ordered[:count], key=lambda slot: (slot[1], slot[0]))


# --------------------------------------------------------------------------- #
# Stage 3b - walls
# --------------------------------------------------------------------------- #
def slot_neighbours(slot: tuple[int, int], cols: int, rows: int) -> list[tuple[int, int]]:
    """The four slots sharing a side with ``slot``, clipped to the lattice."""
    x, y = slot
    return [
        (nx, ny)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
        if 0 <= nx < cols and 0 <= ny < rows
    ]


def reachable_slots(cols: int, rows: int, blocked: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Slots the player can still route to from outside the lattice.

    The flood starts on the border, because a box on the edge always has the
    outside of the grid on one of its sides, and spreads through every slot that
    is not blocked.
    """
    stack = [
        (x, y)
        for y in range(rows)
        for x in range(cols)
        if (x, y) not in blocked and (x in (0, cols - 1) or y in (0, rows - 1))
    ]
    seen = set(stack)
    while stack:
        for neighbour in slot_neighbours(stack.pop(), cols, rows):
            if neighbour in seen or neighbour in blocked:
                continue
            seen.add(neighbour)
            stack.append(neighbour)
    return seen


def layout_is_open(
    cols: int,
    rows: int,
    walls: list[tuple[int, int]],
    tunnels: list[tuple[int, int]],
) -> bool:
    """Can every box still be reached once the walls and tunnels block their slots?

    A wall blocks the way in to the box beside it and never opens up again, so
    walling two sides of a box leaves only the remaining sides to come around
    through - and walling *every* side strands it for good, which is the one
    thing this has to rule out. Boxes themselves are walked straight through:
    the designer confirmed every box on the grid can be picked, so they narrow
    nothing. A tunnel is permanent too - an emptied one stays as a wall - so it
    blocks like one and only has to be approachable itself.
    """
    blocked = set(walls) | set(tunnels)
    reachable = reachable_slots(cols, rows, blocked)
    for y in range(rows):
        for x in range(cols):
            if (x, y) not in blocked and (x, y) not in reachable:
                return False
    for slot in tunnels:
        x, y = slot
        if x in (0, cols - 1) or y in (0, rows - 1):
            continue
        if not any(
            neighbour in reachable for neighbour in slot_neighbours(slot, cols, rows)
        ):
            return False
    return True


def plan_walls(surface_boxes: int, options: AutoGenOptions, profile: DifficultyProfile) -> int:
    """How many slots to reserve as walls, before the lattice knows its size.

    Walls are the most expensive knob in here - each one eats a slot *and*
    narrows its neighbours - so the difficulty's count is capped at one wall per
    :data:`WALL_BOX_BUDGET` boxes: a small picture cannot afford the same pinch a
    large one shrugs off.
    """
    wanted = profile.walls if options.walls is None else options.walls
    if wanted <= 0:
        return 0
    return min(wanted, surface_boxes // WALL_BOX_BUDGET)


def _wall_groups(cols: int, rows: int):
    """Wall placements to try, best first.

    A **pinch** - two walls flanking one box - is what the mechanic is for: the
    box keeps a single way in, so the player has to come around to it instead of
    taking the direct route. Pairs are mirrored around the middle column by
    construction, like the hand-made levels, and the middle rows go first
    because a pinch on the border only removes an approach the outside already
    offers. Whatever the budget cannot spend on a pinch falls back to the
    corners, where a wall costs its slot without narrowing anything.


    ``strict`` asks the caller to keep the group clear of the walls already
    placed, so walls stay separate pinches instead of merging into one bar that
    cuts the grid in half. It is dropped for the fallbacks, which exist to find
    room for leftovers no difficulty asked for.
    """
    centre_x, centre_y = (cols - 1) / 2, (rows - 1) / 2
    centres = sorted(
        ((x, y) for x in range(1, cols - 1) for y in range(1, rows - 1)),
        key=lambda slot: (abs(slot[1] - centre_y), abs(slot[0] - centre_x), slot[1], slot[0]),
    )
    for x, y in centres:
        yield [(x - 1, y), (x + 1, y)], (x, y), True

    border = sorted(
        (
            (x, y)
            for y in range(rows)
            for x in range(cols)
            if x in (0, cols - 1) or y in (0, rows - 1)
        ),
        key=lambda slot: (-slot[1], -abs(slot[0] - centre_x), slot[0]),
    )
    for slot in border:
        yield [slot], None, True
    for slot in border:
        yield [slot], None, False
    # Last resort for a lattice so full of leftovers that the border runs out.
    for y in range(rows):
        for x in range(cols):
            yield [(x, y)], None, False


def _wall_slots(
    cols: int,
    rows: int,
    tunnel_slots: list[tuple[int, int]],
    count: int,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Place ``count`` walls, and report which boxes they pinched.

    Every slot the boxes do not fill *is* a wall, so this runs for leftovers the
    packing forced as well as for the ones a difficulty asked for - better to
    choose where they land than to let them pile up wherever the lattice ran out.
    """
    if count <= 0:
        return [], []
    chosen: list[tuple[int, int]] = []
    pinched: list[tuple[int, int]] = []
    pinched_rows: set[int] = set()
    for group, pinch, strict in _wall_groups(cols, rows):
        if len(chosen) >= count:
            break
        if len(chosen) + len(group) > count:
            continue
        # A pinched box must stay a box: walling it later would turn the pinch
        # into a plain hole and cost the level the one approach it was built for.
        if any(slot in tunnel_slots or slot in chosen or slot in pinched for slot in group):
            continue
        if pinch is not None:
            if pinch in tunnel_slots or pinch in chosen:
                continue
            # Neighbouring rows would let two pinches grow into a solid bar.
            if any(abs(pinch[1] - row) <= 1 for row in pinched_rows):
                continue
        if strict and any(
            neighbour in chosen
            for slot in group
            for neighbour in slot_neighbours(slot, cols, rows)
        ):
            continue
        if not layout_is_open(cols, rows, chosen + group, tunnel_slots):
            continue
        chosen.extend(group)
        if pinch is not None:
            pinched.append(pinch)
            pinched_rows.add(pinch[1])
    if len(chosen) != count:  # pragma: no cover - the border always has room first
        raise AutoGenError(
            f"Cannot leave {count} slot(s) empty in a {cols}x{rows} lattice without sealing a "
            "box off from every side. Raise the slot limit or lower the wall count."
        )
    return sorted(chosen, key=lambda slot: (slot[1], slot[0])), pinched


# --------------------------------------------------------------------------- #
# Stage 3c - which way each tunnel faces
# --------------------------------------------------------------------------- #
def tunnel_directions(
    tunnel_slots: list[tuple[int, int]],
    box_slots: list[tuple[int, int]],
    wall_slots: list[tuple[int, int]],
    cols: int,
    rows: int,
) -> list[Direction]:
    """Point every tunnel's mouth at a slot that actually holds a box.

    ``direction`` is where the tunnel hands its queue out, so the slot in front
    of the mouth decides whether the queue is reachable at all:

    * **Never off the lattice.** A tunnel on the border facing outwards - and a
      corner tunnel has *two* such sides - releases its boxes into nothing.
    * **Never a wall or another tunnel.** Both are permanent: a wall never opens
      and an emptied tunnel stays on the grid as one, so a mouth aimed at either
      is sealed for the whole level, not just for a while.
    * **Always a real box.** A box is the one neighbour that clears, so facing
      one is the only way the mouth is guaranteed to open up as the level is
      played.

    Ranking is by those tiers, so a usable side always beats a sealed one, and
    within a tier by :data:`TUNNEL_FACING_ORDER` - front row first, then the
    sides, and only then away from the player.

    A tunnel with no box on any side keeps the best side it has (an in-lattice
    neighbour over the outside) rather than raising: the layout has already been
    certified as playable and a lattice that small has nowhere better to point.
    """
    boxes = set(box_slots)
    blocked = set(wall_slots) | set(tunnel_slots)
    facings: list[Direction] = []
    for slot_x, slot_y in tunnel_slots:
        ranked = []
        for rank, direction in enumerate(TUNNEL_FACING_ORDER):
            dx, dy = DIRECTION_STEPS[direction]
            front = (slot_x + dx, slot_y + dy)
            if not (0 <= front[0] < cols and 0 <= front[1] < rows):
                tier = 3
            elif front in blocked:
                tier = 2
            elif front in boxes:
                tier = 0
            else:  # inside the lattice, but nothing there to hand a box to
                tier = 1
            ranked.append((tier, rank, direction))
        facings.append(min(ranked)[2])
    return facings


def tunnel_blocks(box_count: int, per_tunnel: list[int]) -> list[list[int]]:
    """Split the walkthrough into one contiguous block per tunnel, evenly spread.

    Contiguity is what keeps a buried box fair: everything the player digs out to
    reach it was needed within a few steps anyway, so the tray takes the hit for a
    moment instead of holding dead boxes for the rest of the level. The blocks are
    spread over the walkthrough - and never start at step 0 while surface boxes
    are left - so the tunnels stay in play instead of all draining at the end.
    """
    total = sum(per_tunnel)
    if total <= 0:
        return [[] for _ in per_tunnel]
    if total > box_count:  # pragma: no cover - callers clamp to box_count
        raise AutoGenError("Tunnels cannot store more boxes than the level has.")
    free = box_count - total
    gaps = [free // (len(per_tunnel) + 1)] * (len(per_tunnel) + 1)
    for index in range(free - sum(gaps)):
        gaps[index] += 1

    blocks: list[list[int]] = []
    cursor = 0
    for gap, count in zip(gaps, per_tunnel):
        cursor += gap
        blocks.append(list(range(cursor, cursor + count)))
        cursor += count
    return blocks


def _split_evenly(total: int, buckets: int) -> list[int]:
    base, extra = divmod(total, buckets)
    return [base + (index < extra) for index in range(buckets)]


def _layout(
    solution: Solution,
    options: AutoGenOptions,
    rng: random.Random,
) -> tuple[
    int,
    int,
    list[Placement],
    list[list[int]],
    list[tuple[int, int]],
    list[Direction],
    list[tuple[int, int]],
    list[tuple[int, int]],
]:
    specs = list(enumerate(solution.order))
    max_cols = max(1, min(options.max_slot_cols, MAX_BOX_SLOTS))
    max_rows = max(1, min(options.max_slot_rows, MAX_BOX_SLOTS))
    capacity = max_cols * max_rows
    profile = DIFFICULTY_PROFILES[options.difficulty]

    tunnel_count, stored = plan_tunnels(len(specs), capacity, options, profile)

    # Walls need slots of their own, so the lattice is sized for them up front -
    # asking for them afterwards would only steal room the boxes already claimed.
    walls = plan_walls(len(specs) - stored, options, profile)
    walls = min(walls, max(0, capacity - (len(specs) - stored) - tunnel_count))
    cols, rows = choose_lattice(
        min(len(specs) - stored + tunnel_count + walls, capacity), max_cols, max_rows
    )
    slots = _slot_sequence(cols, rows)
    tunnel_slots = _tunnel_slots(slots, tunnel_count)
    open_slots = [slot for slot in slots if slot not in tunnel_slots]
    # Rounding the lattice down can leave fewer surface slots than planned; the
    # tunnels are elastic, so they absorb the difference.
    stored = max(stored, len(specs) - len(open_slots))

    # Whatever the boxes do not fill is a wall, whether a difficulty asked for it
    # or the packing simply left it over.
    wall_slots, pinched = _wall_slots(
        cols, rows, tunnel_slots, len(open_slots) - (len(specs) - stored)
    )
    surface_slots = [slot for slot in open_slots if slot not in set(wall_slots)]

    blocks = tunnel_blocks(len(specs), _split_evenly(stored, tunnel_count)) if tunnel_count else []
    in_tunnel = {index for block in blocks for index in block}

    spec_by_index = dict(specs)
    surface = _scramble([index for index, _ in specs if index not in in_tunnel], profile.scramble, rng)
    placements = [
        Placement(spec_by_index[order_index], order_index, slot_x, slot_y)
        for order_index, (slot_x, slot_y) in zip(surface, surface_slots)
    ]
    # The mouths are aimed last, because they need the finished picture: which
    # slots ended up as walls and which ones really carry a box.
    facings = tunnel_directions(
        tunnel_slots,
        [(placement.slot_x, placement.slot_y) for placement in placements],
        wall_slots,
        cols,
        rows,
    )
    return cols, rows, placements, blocks, tunnel_slots, facings, wall_slots, pinched


# --------------------------------------------------------------------------- #
# Stage 4 - bury the tunnel queues
# --------------------------------------------------------------------------- #
def bury_queue(block: list[int], window: int) -> list[int]:
    """Order one tunnel's queue so the next needed box sits ``window - 1`` deep.

    ``window == 1`` hands the boxes out exactly when the walkthrough asks for
    them: the head of the queue is always the color the pixel grid wants next, so
    the tunnel never gets in the way. Widening the window reverses that many
    consecutive boxes, which puts the soonest-needed box at the *back* of the
    window - the player pops one wrong color after another and only then reaches
    the one they came for. Reversal, rather than a shuffle, is what makes the dig
    depth exactly ``window - 1`` and therefore something the tray can be checked
    against.
    """
    if window <= 1:
        return list(block)
    buried: list[int] = []
    for start in range(0, len(block), window):
        buried.extend(reversed(block[start : start + window]))
    return buried


def plan_queues(
    board: BoardState,
    order: list[BoxSpec],
    blocks: list[list[int]],
    window: int,
    rules: GameRules,
) -> tuple[list[list[int]], list[int], TunnelRelease]:
    """Bury each queue as deeply as the tray survives, and prove it still wins.

    Digging costs tray slots: every box pulled out ahead of time sits there until
    the pixel grid can drain it. So this starts from the always-winnable
    ``window == 1`` - where the pick order *is* the certified walkthrough - and
    widens one tunnel at a time, keeping a widening only when the run still wins.
    Per tunnel rather than globally, because one block that happens to sit over a
    tray-tight stretch of the walkthrough should not flatten the others.
    """
    if not blocks:
        return [], [], resolve_pick_sequence(len(order), [])

    def release_for(windows: list[int]) -> TunnelRelease | None:
        queues = [bury_queue(block, size) for block, size in zip(blocks, windows)]
        release = resolve_pick_sequence(len(order), queues)
        if not simulate_order(board, [order[index] for index in release.sequence], rules):
            return None
        return release

    windows = [1] * len(blocks)
    best = release_for(windows)
    if best is None:  # pragma: no cover - window 1 replays the certified order
        raise AutoGenError("Internal error: even an unburied tunnel queue does not win.")
    for tunnel in range(len(blocks)):
        for candidate in range(max(1, window), windows[tunnel], -1):
            trial = list(windows)
            trial[tunnel] = candidate
            release = release_for(trial)
            if release is not None:
                windows, best = trial, release
                break
    queues = [bury_queue(block, size) for block, size in zip(blocks, windows)]
    return queues, windows, best


# --------------------------------------------------------------------------- #
# Stage 5 - hide boxes
# --------------------------------------------------------------------------- #
def choose_hidden(
    placements: list[Placement],
    ratio: float,
    rng: random.Random,
) -> set[int]:
    """Pick which surface boxes carry ``Hidden``, rarest color first.

    ``Hidden`` exists to make the player hunt for a color, so it has to be spent
    where it actually removes information. Hiding one of a dozen identical boxes
    hides nothing - the player simply uses a visible one instead - while hiding
    the only box of a color forces a search. The hand-made levels follow exactly
    this: of 30 boxes, the 12 Black ones (the bulk color) are all visible and
    every single-or-double color is fully hidden.

    Within a color that is only partly hidden, the picks are spread over distinct
    slot rows so the hidden boxes stay scattered instead of forming a solid band.
    The front row is never hidden, so the player can always read what is
    immediately available.
    """
    if ratio <= 0.0:
        return set()
    candidates = [placement for placement in placements if placement.slot_y > 0]
    wanted = min(len(candidates), round(ratio * len(placements)))
    if wanted <= 0:
        return set()

    total_per_color: Counter[int] = Counter(placement.spec.color for placement in placements)
    by_color: dict[int, list[Placement]] = {}
    for placement in candidates:
        by_color.setdefault(placement.spec.color, []).append(placement)

    hidden: set[int] = set()
    for color in sorted(by_color, key=lambda value: (total_per_color[value], value)):
        if len(hidden) >= wanted:
            break
        group = by_color[color]
        take = min(len(group), wanted - len(hidden))
        hidden.update(placement.order_index for placement in _spread_over_rows(group, take, rng))
    return hidden


def _spread_over_rows(group: list[Placement], take: int, rng: random.Random) -> list[Placement]:
    """Take ``take`` boxes from ``group``, one row at a time starting at the back."""
    if take >= len(group):
        return list(group)
    rows: dict[int, list[Placement]] = {}
    for placement in group:
        rows.setdefault(placement.slot_y, []).append(placement)
    for bucket in rows.values():
        bucket.sort(key=lambda placement: (rng.random(), placement.order_index))

    chosen: list[Placement] = []
    depth = 0
    row_order = sorted(rows, reverse=True)
    while len(chosen) < take:
        for slot_y in row_order:
            if depth < len(rows[slot_y]):
                chosen.append(rows[slot_y][depth])
                if len(chosen) == take:
                    break
        depth += 1
    return chosen


# --------------------------------------------------------------------------- #
# Stage 6 - link boxes in pairs
# --------------------------------------------------------------------------- #
def plan_link_count(surface_boxes: int, options: AutoGenOptions, profile: DifficultyProfile) -> int:
    """How many LinkedContainer pairs to tie, before knowing which boxes can take one."""
    if not options.use_linked_container:
        return 0
    wanted = profile.linked_pairs if options.linked_pairs is None else options.linked_pairs
    if wanted <= 0:
        return 0
    # Two boxes per pair, and a pair spends two tray slots on one tap, so a small
    # grid cannot carry the same number of links a large one shrugs off.
    return min(wanted, surface_boxes // LINK_BOX_BUDGET)


def link_candidates(
    placements: list[Placement],
    hidden: set[int],
    position: dict[int, int],
    mode: str,
    rng: random.Random,
) -> list[tuple[Placement, Placement, int]]:
    """Pairs of side-by-side boxes that may be linked, best first for ``mode``.

    A link is only ever tied between two boxes that sit next to each other on the
    grid - that is what the obstacle draws - and only between two boxes with the
    same effects, because the validator rejects a pair where one half is hidden
    and the other is not.

    ``gap`` is how far apart the two halves sit in the pick order, which is the
    whole difficulty of the mechanic. ``sync`` wants it as small as possible: both
    colors are wanted at once, the tray drains them immediately and the link is a
    gift. ``stall`` wants it as large as the level survives: the partner is a color
    nothing below is asking for, so it squats in the tray and the conveyor fills
    up.
    """
    by_slot = {(placement.slot_x, placement.slot_y): placement for placement in placements}
    pairs: list[tuple[Placement, Placement, int]] = []
    for placement in placements:
        # Right and up only: every orthogonal pair is then visited exactly once.
        for dx, dy in ((1, 0), (0, 1)):
            mate = by_slot.get((placement.slot_x + dx, placement.slot_y + dy))
            if mate is None:
                continue
            if (placement.order_index in hidden) != (mate.order_index in hidden):
                continue
            gap = abs(position[placement.order_index] - position[mate.order_index])
            if mode == "stall" and gap < MIN_STALL_GAP:
                continue
            if mode == "sync" and gap > MAX_SYNC_GAP:
                continue
            # The random tie-break keeps equally good pairs from all clustering in
            # one corner of the grid.
            rank = (-gap if mode == "stall" else gap, rng.random())
            pairs.append((rank, placement, mate, gap))
    pairs.sort(key=lambda pair: pair[0])
    return [(left, right, gap) for _, left, right, gap in pairs]


def plan_links(
    board: BoardState,
    order: list[BoxSpec],
    sequence: list[int],
    placements: list[Placement],
    hidden: set[int],
    count: int,
    mode: str,
    rules: GameRules,
    rng: random.Random,
) -> tuple[list[tuple[Placement, Placement, int]], list[list[int]]]:
    """Tie up to ``count`` pairs, keeping only the ones the tray survives.

    A link is never fair by construction: dropping two boxes on one tap needs two
    free tray slots at that instant, and a ``stall`` partner then holds one of them
    for the next ``gap`` picks. So each candidate is tried against a full replay
    and kept only if the run still wins - the level stays beatable with the chosen
    ``piece`` no matter how mean the pairing looks.
    """
    groups = [[index] for index in sequence]
    if count <= 0:
        return [], groups
    position = {index: slot for slot, index in enumerate(sequence)}
    chosen: list[tuple[Placement, Placement, int]] = []
    used: set[int] = set()
    for left, right, gap in link_candidates(placements, hidden, position, mode, rng):
        if len(chosen) >= count:
            break
        if left.order_index in used or right.order_index in used:
            continue
        links = [(pair[0].order_index, pair[1].order_index) for pair in chosen]
        links.append((left.order_index, right.order_index))
        trial = resolve_link_groups(sequence, links)
        if not simulate_groups(board, [[order[index] for index in group] for group in trial], rules):
            continue
        chosen.append((left, right, gap))
        used.update({left.order_index, right.order_index})
        groups = trial
    return chosen, groups


# --------------------------------------------------------------------------- #
# Stage 7 - lock boxes behind an arrow
# --------------------------------------------------------------------------- #
def plan_arrow_count(surface_boxes: int, options: AutoGenOptions, profile: DifficultyProfile) -> int:
    """How many boxes to lock behind an arrow, before knowing which ones can take one."""
    if not options.use_arrow_lock:
        return 0
    ratio = profile.arrow_ratio if options.arrow_ratio is None else options.arrow_ratio
    wanted = round(ratio * surface_boxes)
    if wanted <= 0:
        return 0
    # A locked box is unavailable until its key goes, so locking too many at once
    # leaves the player staring at a grid with nothing tappable on it.
    return min(wanted, surface_boxes // ARROW_BOX_BUDGET)


def arrow_candidates(
    placements: list[Placement],
    position: dict[int, int],
    blocked: set[int],
) -> list[tuple[Placement, Direction, Placement]]:
    """Boxes that can carry an ArrowLock, with the direction and the key box.

    Two rules decide this, and both come straight from what the mechanic does:

    * The arrow has to point at a **real box** on the neighbouring slot. Pointing
      at a wall, at a tunnel or off the edge of the grid gives the lock no key at
      all and the box can never be opened - that is the failure the designer
      called out, and the validator rejects it too.
    * That key box has to be opened **before** the locked one in the certified
      walkthrough. Otherwise the order the solver proved wins is illegal, and the
      level would need a different solution nobody has checked.

    The direction chosen per box is the one whose key is opened as late as still
    allowed, so the lock stays shut for as long as possible instead of being
    pointed at something the player clears in the first few taps.
    """
    by_slot = {(placement.slot_x, placement.slot_y): placement for placement in placements}
    candidates: list[tuple[Placement, Direction, Placement]] = []
    for placement in placements:
        if placement.order_index in blocked:
            continue
        best: tuple[int, int, Direction, Placement] | None = None
        for direction, (dx, dy) in DIRECTION_STEPS.items():
            key = by_slot.get((placement.slot_x + dx, placement.slot_y + dy))
            if key is None:
                continue
            if position[key.order_index] >= position[placement.order_index]:
                continue
            option = (
                position[placement.order_index] - position[key.order_index],
                -int(direction),
                direction,
                key,
            )
            if best is None or option[:2] > best[:2]:
                best = option
        if best is not None:
            candidates.append((placement, best[2], best[3]))
    return candidates


def plan_arrow_locks(
    placements: list[Placement],
    position: dict[int, int],
    blocked: set[int],
    count: int,
    rng: random.Random,
) -> dict[int, tuple[Direction, Placement]]:
    """Pick which boxes get an ArrowLock, scattered over the grid.

    ``blocked`` holds the boxes that must stay plain: the hidden ones, because a
    box that shows neither its color nor an open state is unreadable, and the
    linked ones, because the validator forbids a LinkedContainer from targeting an
    ArrowLock box.
    """
    if count <= 0:
        return {}
    candidates = arrow_candidates(placements, position, blocked)
    rng.shuffle(candidates)
    chosen: dict[int, tuple[Direction, Placement]] = {}
    keys: set[int] = set()
    for placement, direction, key in candidates:
        if len(chosen) >= count:
            break
        # No chains: a key that is itself locked makes the player clear two locks
        # to open one box, which reads as a bug rather than as difficulty.
        if key.order_index in chosen or placement.order_index in keys:
            continue
        chosen[placement.order_index] = (direction, key)
        keys.add(key.order_index)
    return chosen


def arrow_order_holds(
    arrows: dict[int, tuple[Direction, Placement]],
    position: dict[int, int],
) -> bool:
    """Is every locked box still opened after the box its arrow points at?"""
    return all(
        position[key.order_index] < position[order_index]
        for order_index, (_, key) in arrows.items()
    )


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def _is_active(slot_y: int, policy: str, hidden: bool) -> bool:
    # The validator rejects a Hidden box that starts active, and the runtime
    # derives the active state from the front row anyway.
    if hidden or policy == "none":
        return False
    if policy == "all":
        return True
    return slot_y == 0


def _box(
    spec: BoxSpec,
    grid_x: int,
    grid_y: int,
    is_active: bool,
    hidden: bool,
    arrow: Direction | None = None,
) -> BoxCellData:
    effects: list[CellEffectData] = []
    if hidden:
        effects.append(HiddenCellEffectData())
    if arrow is not None:
        effects.append(ArrowLockCellEffectData(required_direction=arrow))
    return BoxCellData(
        grid_x=grid_x,
        grid_y=grid_y,
        shape=CellShape.Square_3x3,
        direction=Direction.Up,
        color=ItemColor(spec.color),
        is_active=is_active,
        effects=effects or None,
    )


def auto_generate_boxes(level: PixelLevelData, options: AutoGenOptions) -> AutoGenResult:
    """Build a full Box Ball Grid for ``level``'s pixel grid at a given difficulty."""
    if options.difficulty not in DIFFICULTY_PROFILES:
        raise AutoGenError(f"Unsupported difficulty {options.difficulty}.")
    if options.active_policy not in ACTIVE_POLICIES:
        raise AutoGenError(f"Unsupported isActive policy {options.active_policy!r}.")
    if options.tunnel_mode not in TUNNEL_MODES:
        raise AutoGenError(f"Unsupported tunnel mode {options.tunnel_mode!r}.")
    if options.dig_window is not None and options.dig_window < 1:
        raise AutoGenError(f"Tunnel dig window must be at least 1, got {options.dig_window}.")
    if options.walls is not None and options.walls < 0:
        raise AutoGenError(f"Wall count cannot be negative, got {options.walls}.")
    if options.linked_mode not in LINKED_MODES:
        raise AutoGenError(f"Unsupported linked container mode {options.linked_mode!r}.")
    if options.linked_pairs is not None and options.linked_pairs < 0:
        raise AutoGenError(f"Linked pair count cannot be negative, got {options.linked_pairs}.")
    if options.arrow_ratio is not None and not 0.0 <= options.arrow_ratio <= 1.0:
        raise AutoGenError(f"Arrow lock ratio must be between 0 and 1, got {options.arrow_ratio}.")

    profile = DIFFICULTY_PROFILES[options.difficulty]
    working = level.clone()
    grid = working.pixel_grid
    if grid.width <= 0 or grid.height <= 0:
        raise AutoGenError("Pixel grid must have a positive width and height.")
    grid.ensure_dense()
    if not grid.histogram():
        raise AutoGenError("Paint the pixel grid before generating boxes.")

    removed, emptied = balance_pixel_grid(grid, BALLS_PER_BOX)
    if not grid.histogram():
        raise AutoGenError(
            f"Every color has fewer than {BALLS_PER_BOX} pixels, so not a single box can be "
            "built. Paint at least nine pixels of one color."
        )

    board = BoardState.from_pixel_grid(grid)
    try:
        boxes = box_multiset(board, BALLS_PER_BOX)
    except GameplayError as exc:  # pragma: no cover - balancing guarantees multiples of nine
        raise AutoGenError(str(exc)) from exc

    # The requested piece is the target; only raise it when the picture genuinely
    # cannot be played with that many slots.
    target_tray = options.tray_slots or profile.tray_slots
    solution: Solution | None = None
    tray_slots = target_tray
    for tray_slots in range(target_tray, MAX_TRAY_SLOTS + 1):
        solution = solve_order(board, boxes, GameRules(tray_slots))
        if solution is not None:
            break
    if solution is None:
        raise AutoGenError(
            f"No pick order wins this pixel grid with piece up to {MAX_TRAY_SLOTS}. The colors are "
            "interleaved so finely that boxes pile up in the tray; simplify the picture."
        )
    rules = GameRules(tray_slots=tray_slots)
    solution.required_tray = minimum_tray(board, boxes, max_slots=tray_slots) or tray_slots
    seed = options.seed if options.seed is not None else working.level * 1000 + options.difficulty
    rng = random.Random(seed)
    cols, rows, placements, blocks, tunnel_slots, facings, wall_slots, pinched = _layout(
        solution, options, rng
    )

    wanted_window = profile.dig_window if options.dig_window is None else options.dig_window
    queues, dig_windows, release = plan_queues(
        board, solution.order, blocks, wanted_window, rules
    )

    ratio = profile.hidden_ratio if options.hidden_ratio is None else options.hidden_ratio
    if not 0.0 <= ratio <= 1.0:
        raise AutoGenError(f"Hidden ratio must be between 0 and 1, got {ratio}.")
    hidden = choose_hidden(placements, ratio, rng)

    # Links come before locks: a linked pair may not carry an ArrowLock, and the
    # links move boxes forward in the pick order, which is exactly what the locks
    # have to be checked against.
    linked_mode = profile.linked_mode if options.linked_mode == "auto" else options.linked_mode
    link_count = plan_link_count(len(placements), options, profile)
    linked, play_groups = plan_links(
        board,
        solution.order,
        release.sequence,
        placements,
        hidden,
        link_count,
        linked_mode,
        rules,
        rng,
    )
    linked_indices = {
        placement.order_index for left, right, _ in linked for placement in (left, right)
    }
    play_position = {
        index: step for step, group in enumerate(play_groups) for index in group
    }

    arrow_count = plan_arrow_count(len(placements), options, profile)
    arrows = plan_arrow_locks(
        placements, play_position, hidden | linked_indices, arrow_count, rng
    )

    placement_by_index = {placement.order_index: placement for placement in placements}
    cells: list[BoxCellData] = []
    cell_by_order_index: dict[int, BoxCellData] = {}
    for placement in placements:
        is_hidden = placement.order_index in hidden
        arrow = arrows.get(placement.order_index)
        cell = _box(
            placement.spec,
            placement.grid_x,
            placement.grid_y,
            # A locked box cannot be opened yet, so it never starts active either.
            _is_active(placement.slot_y, options.active_policy, is_hidden or arrow is not None),
            is_hidden,
            arrow[0] if arrow else None,
        )
        cells.append(cell)
        cell_by_order_index[placement.order_index] = cell

    tunnel_boxes = 0
    used_tunnels = 0
    tunnel_mouths: list[tuple[tuple[int, int], Direction]] = []
    # strict: a queue without a slot would silently swallow its boxes.
    for (slot_x, slot_y), queue, facing in zip(tunnel_slots, queues, facings, strict=True):
        if not queue:
            continue
        used_tunnels += 1
        tunnel_boxes += len(queue)
        tunnel_mouths.append(((slot_x, slot_y), facing))
        grid_x, grid_y = slot_x * SLOT, slot_y * SLOT
        cells.append(
            TunnelCellData(
                grid_x=grid_x,
                grid_y=grid_y,
                shape=CellShape.Square_3x3,
                # Where the queue is handed out: always at a real box, never at a
                # wall, another tunnel or off the grid.
                direction=facing,
                # The tunnel shows the color of its head, the only box on offer.
                color=ItemColor(solution.order[queue[0]].color),
                is_active=_is_active(slot_y, options.active_policy, False),
                stored_cells=[
                    _box(solution.order[index], grid_x, grid_y, False, False) for index in queue
                ],
            )
        )

    dropped_obstacles = len(working.obstacles)
    working.grid_cols = cols * SLOT
    working.grid_rows = rows * SLOT
    working.grid_cells = cells
    working.obstacles = [
        LinkedContainerObstacleData(
            target_uids=[
                cell_by_order_index[left.order_index].internal_uid,
                cell_by_order_index[right.order_index].internal_uid,
            ]
        )
        for left, right, _ in linked
    ]
    working.piece = tray_slots
    working.difficulty = options.difficulty
    if options.apply_theme and options.difficulty in DIFFICULTY_FORCED_THEME:
        working.theme_id = DIFFICULTY_FORCED_THEME[options.difficulty]

    expected_boxes = len(solution.order)
    if len(placements) + tunnel_boxes != expected_boxes:
        raise AutoGenError("Internal error: some generated boxes were dropped during layout.")
    if working.source_histogram() != working.target_histogram():
        raise AutoGenError("Internal error: generated boxes do not match the pixel grid.")
    if not layout_is_open(cols, rows, wall_slots, tunnel_slots):
        raise AutoGenError("Internal error: a wall seals a box off from every side.")
    if not simulate_order(board, solution.order, rules):
        raise AutoGenError(
            f"Internal error: the generated walkthrough does not win with piece={tray_slots}."
        )
    play_order = [solution.order[index] for index in release.sequence]
    if not simulate_order(board, play_order, rules):
        raise AutoGenError(
            f"Internal error: the tunnel queues force a pick order that loses with piece={tray_slots}."
        )
    play_specs = [[solution.order[index] for index in group] for group in play_groups]
    if not simulate_groups(board, play_specs, rules):
        raise AutoGenError(
            f"Internal error: the linked containers force a pick order that loses with "
            f"piece={tray_slots}."
        )
    if not arrow_order_holds(arrows, play_position):
        raise AutoGenError(
            "Internal error: an ArrowLock box is opened before the box its arrow points at."
        )
    metrics = measure_difficulty(board, solution, rules)

    hidden_by_slot_row = [
        (
            slot_row,
            sum(
                1
                for placement in placements
                if placement.slot_y == slot_row and placement.order_index in hidden
            ),
        )
        for slot_row in range(rows)
    ]
    total_per_color: Counter[int] = Counter(placement.spec.color for placement in placements)
    hidden_per_color: Counter[int] = Counter(
        placement.spec.color for placement in placements if placement.order_index in hidden
    )
    hidden_by_color = sorted(
        (
            (color, hidden_per_color.get(color, 0), total)
            for color, total in total_per_color.items()
        ),
        key=lambda item: (item[2], item[0]),
    )

    warnings: list[str] = []
    if emptied:
        warnings.append(
            "Việc cân bằng màu đã làm trống cột pixel "
            + ", ".join(str(column) for column in emptied)
            + "; validator sẽ cảnh báo về các cột này."
        )
    if dropped_obstacles:
        warnings.append(
            f"Đã xoá {dropped_obstacles} obstacle cũ vì chúng tham chiếu tới các box bị thay thế."
        )
    if tunnel_boxes:
        buried = (
            f"màu cần bị chôn sâu tối đa {release.max_dig} box"
            if release.max_dig
            else "mỗi box được nhả ra đúng lúc pixel grid cần"
        )
        warnings.append(
            f"{tunnel_boxes}/{expected_boxes} box được cất trong {used_tunnels} tunnel; "
            f"{buried}. Tunnel hết box vẫn nằm lại trên lưới như một bức tường."
        )
        box_slots = {(placement.slot_x, placement.slot_y) for placement in placements}
        stuck = [
            (slot, facing)
            for slot, facing in tunnel_mouths
            if (
                slot[0] + DIRECTION_STEPS[facing][0],
                slot[1] + DIRECTION_STEPS[facing][1],
            )
            not in box_slots
        ]
        if stuck:
            warnings.append(
                "Không tìm được hướng nhả box hợp lệ cho tunnel "
                + ", ".join(f"({x}, {y}) → {facing.name}" for (x, y), facing in stuck)
                + ": mọi cạnh của nó đều là wall, tunnel khác hoặc ra ngoài lưới. Lưới quá nhỏ "
                "hoặc quá nhiều wall — hạ walls hoặc nâng giới hạn slot để miệng tunnel chỉ vào "
                "một box thật."
            )
    if blocks and any(window < wanted_window for window in dig_windows):
        warnings.append(
            f"Độ chôn của tunnel bị thu hẹp từ {wanted_window} xuống "
            + "/".join(str(window) for window in dig_windows)
            + f": chôn sâu hơn sẽ dồn nhiều box vào khay cùng lúc hơn mức piece={tray_slots} "
            "chứa được. Muốn đào sâu hơn thì nâng piece hoặc rút ngắn tunnel."
        )
    if wall_slots:
        pinch = (
            "; "
            + ", ".join(f"({x}, {y})" for x, y in pinched)
            + f" bị kẹp hai bên nên chỉ còn một đường vòng vào"
            if pinched
            else ""
        )
        warnings.append(
            f"{len(wall_slots)} slot của lưới {cols}x{rows} là wall{pinch}. Wall chặn đường vào "
            "các box bên cạnh và không bao giờ mở ra, nên nó vừa ăn một slot vừa làm level khó "
            "hơn hẳn — đặt walls=0 nếu thấy quá tay."
        )
    if options.use_linked_container and not linked:
        warnings.append(
            f"Không nối được cặp LinkedContainer nào ở chế độ {linked_mode!r}: cần hai box nằm sát "
            "nhau, cùng trạng thái ẩn, và khoảng cách trong thứ tự giải phải phù hợp — mà thả hai "
            f"box cùng lúc vẫn không được vượt piece={tray_slots}."
        )
    elif linked:
        gaps = sorted((gap for _, _, gap in linked), reverse=True)
        feel = (
            "cả hai box đều là màu bên dưới đang cần nên khay rút cạn ngay, link gần như miễn phí"
            if linked_mode == "sync"
            else "box đi kèm là màu bên dưới chưa cần, nên nó ngồi chiếm ô khay và làm băng chuyền "
            "đầy lên — đây chính là mức khó của link"
        )
        warnings.append(
            f"{len(linked)} cặp LinkedContainer ({len(linked) * 2}/{len(placements)} box mặt ngoài) "
            f"ở chế độ {linked_mode}: {feel}. Chênh lệch thứ tự lấy của từng cặp: "
            + "/".join(str(gap) for gap in gaps)
            + " lượt."
        )
    if link_count and len(linked) < link_count:
        warnings.append(
            f"Chỉ nối được {len(linked)}/{link_count} cặp LinkedContainer: những cặp còn lại làm "
            f"tràn khay piece={tray_slots} nên đã bị bỏ. Muốn nhiều link hơn thì nâng piece hoặc "
            "chuyển sang chế độ sync."
        )
    if options.use_arrow_lock and not arrows:
        warnings.append(
            "Không đặt được ArrowLock nào: mỗi box khoá cần một box thật nằm sát nó theo hướng mũi "
            "tên, và box đó phải được mở trước trong thứ tự giải. Lưới quá nhỏ, quá nhiều wall, "
            "hoặc box ẩn/box đã bị link đã chiếm hết các ứng viên."
        )
    elif arrows:
        longest_wait = max(
            play_position[order_index] - play_position[key.order_index]
            for order_index, (_, key) in arrows.items()
        )
        warnings.append(
            f"{len(arrows)}/{len(placements)} box mặt ngoài mang ArrowLock. Mũi tên luôn chỉ vào một "
            "box thật nằm sát bên và box đó chắc chắn được mở trước, nên khoá luôn có chìa — không "
            "bao giờ chỉ vào wall, vào tunnel hay ra ngoài lưới. Khoá mở muộn nhất sau "
            f"{longest_wait} lượt lấy box."
        )
    if arrow_count and len(arrows) < arrow_count:
        warnings.append(
            f"Chỉ khoá được {len(arrows)}/{arrow_count} box bằng ArrowLock: các box còn lại không có "
            "box nào sát bên được mở trước để làm chìa."
        )
    if tray_slots > target_tray:
        warnings.append(
            f"piece đã được nâng từ {target_tray} lên {tray_slots}: bức ảnh này có những đoạn không "
            "box nào rút cạn được, nên khay cần thêm chỗ."
        )
    if ratio > 0.0 and not hidden:
        warnings.append(
            "Không ẩn được box nào: mọi box đều nằm ở hàng trước, vốn luôn hiển thị."
        )

    return AutoGenResult(
        level=working,
        metrics=metrics,
        solution=solution,
        slot_cols=cols,
        slot_rows=rows,
        surface_boxes=len(placements),
        tunnel_boxes=tunnel_boxes,
        tunnel_count=used_tunnels,
        dig_windows=dig_windows,
        release=release,
        tunnel_queues=queues,
        tunnel_mouths=tunnel_mouths,
        wall_slots=wall_slots,
        pinched_slots=pinched,
        hidden_boxes=len(hidden),
        hidden_by_slot_row=hidden_by_slot_row,
        hidden_by_color=hidden_by_color,
        arrow_locks=sorted(
            (
                (
                    (placement_by_index[order_index].slot_x, placement_by_index[order_index].slot_y),
                    direction,
                    (key.slot_x, key.slot_y),
                    play_position[order_index] - play_position[key.order_index],
                )
                for order_index, (direction, key) in arrows.items()
            ),
            key=lambda item: (item[0][1], item[0][0]),
        ),
        linked_pairs=sorted(
            (
                ((left.slot_x, left.slot_y), (right.slot_x, right.slot_y), gap)
                for left, right, gap in linked
            ),
            key=lambda item: (item[0][1], item[0][0]),
        ),
        linked_mode=linked_mode,
        play_groups=play_groups,
        removed_pixels=removed,
        emptied_columns=emptied,
        dropped_obstacles=dropped_obstacles,
        warnings=warnings,
    )


def format_report(result: AutoGenResult, options: AutoGenOptions) -> str:
    profile = DIFFICULTY_PROFILES[options.difficulty]
    metrics = result.metrics
    lines = [
        f"Độ khó: {profile.label}",
        f"Lưới box: {result.slot_cols}x{result.slot_rows} slot"
        f" = gridCols {result.grid_cols}, gridRows {result.grid_rows}",
        f"Số box: {result.total_boxes} Square_3x3"
        + (f" ({result.tunnel_boxes} box nằm trong {result.tunnel_count} tunnel)" if result.tunnel_boxes else "")
        + f"   Số ball: {metrics.total_balls}   Số màu: {metrics.colors}",
        f"Box ẩn (Hidden): {result.hidden_boxes}/{result.surface_boxes} box mặt ngoài,"
        f" {result.surface_hidden_ratio:.0%} (mục tiêu {profile.hidden_ratio:.0%})",
        "  theo màu, màu hiếm trước: "
        + ", ".join(
            f"{COLOR_NAMES[ItemColor(color)]} {count}/{total}"
            for color, count, total in result.hidden_by_color
        ),
        "  theo hàng slot, hàng trước trước: "
        + ", ".join(f"hàng {row}: {count}" for row, count in result.hidden_by_slot_row),
        f"piece (số ô khay): {metrics.tray_slots}"
        f"   tối thiểu lời giải cần: {metrics.required_tray}",
        "",
        "Lời giải đã kiểm chứng:",
        f"  số bước: {len(result.solution.steps)}",
        f"  lựa chọn an toàn mỗi bước: ít nhất {metrics.min_safe_options},"
        f" trung bình {metrics.mean_safe_options:.2f} trên {metrics.mean_total_options:.2f} box nhìn thấy",
        f"  bước ép buộc (chỉ có 1 nước an toàn): {metrics.forced_steps}/{metrics.measured_steps}"
        f" ({metrics.forced_ratio * 100:.0f}%)",
    ]
    if result.tunnel_count:
        lines += [
            "",
            f"Tunnel: {result.tunnel_count} tunnel chứa {result.tunnel_boxes} box"
            f"   độ chôn (dig window): "
            + "/".join(str(window) for window in result.dig_windows)
            + f" (mục tiêu {profile.dig_window})",
            f"  phải đào: tối đa {result.release.max_dig} box thừa trước khi tới box cần,"
            f" trung bình {result.release.mean_dig:.2f}",
        ]
        lines.append(
            "  hướng nhả box (slot → hướng): "
            + ", ".join(
                f"({x}, {y}) → {facing.name}" for (x, y), facing in result.tunnel_mouths
            )
        )
        order = result.solution.order
        for position, queue in enumerate(result.tunnel_queues):
            lines.append(
                f"  tunnel {position} từ đầu hàng: "
                + " > ".join(COLOR_NAMES[ItemColor(order[index].color)] for index in queue)
            )
    if result.linked_pairs:
        mode = (
            "sync — cả hai màu đều đang cần bên dưới, khay rút cạn ngay"
            if result.linked_mode == "sync"
            else "stall — box đi kèm là màu chưa cần, nó chiếm ô khay và làm băng chuyền đầy lên"
        )
        lines += [
            "",
            f"LinkedContainer: {result.link_count} cặp ({result.link_count * 2} box), chế độ {mode}",
            f"  chênh lệch thứ tự lấy lớn nhất: {result.max_link_gap} lượt",
            "  các cặp slot (x, y): "
            + ", ".join(
                f"({left[0]}, {left[1]})-({right[0]}, {right[1]}) cách {gap}"
                for left, right, gap in result.linked_pairs
            ),
        ]
    if result.arrow_locks:
        lines += [
            "",
            f"ArrowLock: {result.arrow_count} box bị khoá"
            f" (mục tiêu {profile.arrow_ratio:.0%} box mặt ngoài)",
            f"  khoá mở muộn nhất sau {result.max_arrow_wait} lượt lấy box",
            "  slot (x, y) → hướng → slot chìa: "
            + ", ".join(
                f"({slot[0]}, {slot[1]}) → {direction.name} → ({key[0]}, {key[1]}) sau {wait} lượt"
                for slot, direction, key, wait in result.arrow_locks
            ),
        ]
    if result.wall_slots:
        lines += [
            "",
            f"Wall: {result.wall_count} slot bỏ trống (mục tiêu {profile.walls})",
            "  vị trí slot (x, y): "
            + ", ".join(f"({x}, {y})" for x, y in result.wall_slots),
            "  box bị kẹp giữa hai wall: "
            + (
                ", ".join(f"({x}, {y})" for x, y in result.pinched_slots)
                if result.pinched_slots
                else "không có, wall chỉ nằm ở rìa lưới"
            ),
        ]
    if result.removed_pixels:
        total = sum(result.removed_pixels.values())
        detail = ", ".join(
            f"{COLOR_NAMES[ItemColor(color)]} {count}"
            for color, count in sorted(result.removed_pixels.items())
        )
        lines += ["", f"Đã xoá {total} pixel để cân bằng màu: {detail}"]
    if result.warnings:
        lines += [""] + [f"- {warning}" for warning in result.warnings]
    return "\n".join(lines)
