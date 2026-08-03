from __future__ import annotations

"""Deterministic gameplay model used to certify auto-generated Pixel levels.

The runtime rules assumed here are the ones the level designer confirmed:

* The pixel grid is consumed **from the top row downwards**, independently per
  column.  The *frontier* of a column is its topmost unfilled pixel, the exact
  value :meth:`PixelGridData.frontier_rows` already draws in the pixel editor.
* A picked box takes one of ``piece`` tray slots and keeps draining balls into
  any column whose frontier matches its color until the box is empty.
* The player loses when every tray slot holds a box that cannot drain.
* Every box on the grid can be picked, so the box grid layout decides how much
  searching the player has to do rather than what is reachable.
* A **tunnel** is the one exception: it is a queue, only its head can be taken,
  and taking the head reveals the next box.  An emptied tunnel does not vanish -
  it keeps its slot as a wall.  So a box buried in a tunnel forces the player to
  pull everything in front of it into the tray first, which is what
  :func:`resolve_pick_sequence` turns back into a plain pick order.

Two arbitrary choices make the simulation deterministic: a ball always fills the
left-most matching column, and the oldest tray box drains first.
"""

from collections import Counter
from dataclasses import dataclass, field

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID
from pixel_level_tool.domain.level_models import PixelGridData


BALLS_PER_BOX = 9


@dataclass(frozen=True)
class BoxSpec:
    """One poppable box reduced to what gameplay cares about."""

    color: int
    size: int

    def sort_key(self) -> tuple[int, int]:
        return self.color, self.size


@dataclass
class TrayBox:
    color: int
    size: int
    remaining: int


@dataclass(frozen=True)
class GameRules:
    tray_slots: int = 5


class GameplayError(ValueError):
    pass


class BoardState:
    """Per-column pixel queues plus how far each column has been filled."""

    __slots__ = ("columns", "heads")

    def __init__(self, columns: tuple[tuple[int, ...], ...], heads: list[int] | None = None) -> None:
        self.columns = columns
        self.heads = list(heads) if heads is not None else [0] * len(columns)

    @classmethod
    def from_pixel_grid(cls, grid: PixelGridData) -> "BoardState":
        columns: list[tuple[int, ...]] = []
        for column in range(grid.width):
            columns.append(
                tuple(
                    grid.get_color_id(row, column)
                    for row in range(grid.height)
                    if grid.get_color_id(row, column) != EMPTY_COLOR_ID
                )
            )
        return cls(tuple(columns))

    def clone(self) -> "BoardState":
        return BoardState(self.columns, self.heads)

    def done(self) -> bool:
        return all(head >= len(column) for head, column in zip(self.heads, self.columns))

    def remaining_pixels(self) -> int:
        return sum(len(column) - head for head, column in zip(self.heads, self.columns))

    def histogram(self) -> Counter[int]:
        hist: Counter[int] = Counter()
        for head, column in zip(self.heads, self.columns):
            hist.update(column[head:])
        return hist

    def frontier_colors(self) -> set[int]:
        return {
            column[self.heads[index]]
            for index, column in enumerate(self.columns)
            if self.heads[index] < len(column)
        }

    def run_capacity(self, color: int) -> int:
        """Balls of ``color`` the board can absorb without any other color moving."""
        total = 0
        for index, column in enumerate(self.columns):
            head = self.heads[index]
            while head < len(column) and column[head] == color:
                total += 1
                head += 1
        return total

    def fill(self, color: int, count: int) -> int:
        """Fill up to ``count`` pixels of ``color``, left-most column first."""
        consumed = 0
        for index, column in enumerate(self.columns):
            if consumed >= count:
                break
            head = self.heads[index]
            while consumed < count and head < len(column) and column[head] == color:
                head += 1
                consumed += 1
            self.heads[index] = head
        return consumed

    def state_key(self) -> tuple[int, ...]:
        return tuple(self.heads)


def drain(board: BoardState, tray: list[TrayBox]) -> None:
    """Let every tray box pour balls into the board until nothing moves."""
    progress = True
    while progress:
        progress = False
        for box in tray:
            if box.remaining <= 0:
                continue
            consumed = board.fill(box.color, box.remaining)
            if consumed:
                box.remaining -= consumed
                progress = True


def _prune(tray: list[TrayBox]) -> None:
    tray[:] = [box for box in tray if box.remaining > 0]


def box_multiset(board: BoardState, size: int = BALLS_PER_BOX) -> Counter[BoxSpec]:
    """The boxes a level must contain, which its pixel histogram fully determines.

    Every box is mono-color and holds ``size`` balls, and the source histogram has
    to equal the target histogram, so there is no freedom here at all.
    """
    boxes: Counter[BoxSpec] = Counter()
    for color, count in sorted(board.histogram().items()):
        if count % size:
            raise GameplayError(f"Color {color} has {count} pixels, not a multiple of {size}.")
        boxes[BoxSpec(color, size)] = count // size
    if not boxes:
        raise GameplayError("Pixel grid has no colored pixel.")
    return boxes


# --------------------------------------------------------------------------- #
# Solver
# --------------------------------------------------------------------------- #
@dataclass
class SolutionStep:
    box: BoxSpec
    tray_used: int
    safe_options: int = 0


@dataclass
class Solution:
    steps: list[SolutionStep] = field(default_factory=list)
    required_tray: int = 1
    nodes: int = 0

    @property
    def order(self) -> list[BoxSpec]:
        return [step.box for step in self.steps]


def _search_key(
    board: BoardState, tray: list[TrayBox], available: Counter[BoxSpec]
) -> tuple:
    return (
        board.state_key(),
        tuple(sorted((box.color, box.remaining) for box in tray)),
        tuple(sorted((spec.color, spec.size, count) for spec, count in available.items())),
    )


def _ranked_children(board: BoardState, available: Counter[BoxSpec]) -> list[BoxSpec]:
    """Candidate picks, best first: drain completely, then drain the most."""
    frontier = board.frontier_colors()
    scored = []
    for spec in available:
        capacity = board.run_capacity(spec.color)
        scored.append(
            (
                0 if spec.color in frontier else 1,
                0 if capacity >= spec.size else 1,
                -min(capacity, spec.size),
                spec.sort_key(),
                spec,
            )
        )
    scored.sort(key=lambda item: item[:4])
    return [item[4] for item in scored]


def solve_order(
    board: BoardState,
    available: Counter[BoxSpec],
    rules: GameRules,
    *,
    node_limit: int = 200_000,
) -> Solution | None:
    """Depth-first search for a pick order that empties the board.

    A plain greedy walk is far too weak here: on a hand-made 18x16 picture it
    demands two more tray slots than the level actually ships with, because one
    early commitment can block a slot for a long time. The search explores
    "drains completely" first, so the order it returns is also the one a player
    would call natural, and memoises states so it stays cheap.

    Returns ``None`` when no order wins within ``node_limit`` expansions.
    """
    seen: set[tuple] = set()
    nodes = 0
    stack: list[tuple[BoardState, list[TrayBox], Counter[BoxSpec], list[tuple[BoxSpec, int]]]] = [
        (board.clone(), [], Counter(available), [])
    ]

    while stack:
        state_board, tray, remaining, path = stack.pop()
        nodes += 1
        if nodes > node_limit:
            return None

        drain(state_board, tray)
        _prune(tray)
        if state_board.done() and not tray:
            solution = Solution(
                steps=[SolutionStep(spec, tray_used) for spec, tray_used in path],
                required_tray=max((tray_used for _, tray_used in path), default=1),
                nodes=nodes,
            )
            return solution

        key = _search_key(state_board, tray, remaining)
        if key in seen:
            continue
        seen.add(key)
        if len(tray) >= rules.tray_slots:
            continue

        # Pushed in reverse so the best-ranked child is popped first.
        for spec in reversed(_ranked_children(state_board, remaining)):
            child_remaining = Counter(remaining)
            child_remaining[spec] -= 1
            if child_remaining[spec] <= 0:
                del child_remaining[spec]
            child_tray = [TrayBox(box.color, box.size, box.remaining) for box in tray]
            child_tray.append(TrayBox(spec.color, spec.size, spec.size))
            stack.append(
                (state_board.clone(), child_tray, child_remaining, path + [(spec, len(child_tray))])
            )
    return None


def minimum_tray(
    board: BoardState,
    available: Counter[BoxSpec],
    *,
    max_slots: int = 8,
    node_limit: int = 60_000,
) -> int | None:
    """Smallest ``piece`` a perfect player needs, or ``None`` if none up to ``max_slots``."""
    for tray_slots in range(1, max_slots + 1):
        if solve_order(board, available, GameRules(tray_slots), node_limit=node_limit) is not None:
            return tray_slots
    return None


def is_feasible(
    board: BoardState,
    tray: list[TrayBox],
    available: Counter[BoxSpec],
    rules: GameRules,
    *,
    node_limit: int = 4_000,
) -> bool | None:
    """Can the run still be won from here? ``None`` means the search gave up."""
    seen: set[tuple] = set()
    nodes = 0
    stack = [(board.clone(), [TrayBox(box.color, box.size, box.remaining) for box in tray], Counter(available))]
    while stack:
        state_board, state_tray, remaining = stack.pop()
        nodes += 1
        if nodes > node_limit:
            return None
        drain(state_board, state_tray)
        _prune(state_tray)
        if state_board.done() and not state_tray:
            return True
        key = _search_key(state_board, state_tray, remaining)
        if key in seen:
            continue
        seen.add(key)
        if len(state_tray) >= rules.tray_slots:
            continue
        for spec in reversed(_ranked_children(state_board, remaining)):
            child_remaining = Counter(remaining)
            child_remaining[spec] -= 1
            if child_remaining[spec] <= 0:
                del child_remaining[spec]
            child_tray = [TrayBox(box.color, box.size, box.remaining) for box in state_tray]
            child_tray.append(TrayBox(spec.color, spec.size, spec.size))
            stack.append((state_board.clone(), child_tray, child_remaining))
    return False


# --------------------------------------------------------------------------- #
# Tunnels
# --------------------------------------------------------------------------- #
@dataclass
class TunnelRelease:
    """The pick order a walkthrough turns into once some boxes sit in tunnels.

    ``sequence`` holds walkthrough indices in the order the player actually pops
    them, and ``digs[i]`` counts the boxes that had to come out of a tunnel
    *before* the i-th needed tunnel box did - the "keep pulling and it still is
    not the color I want" pressure, measured in tray slots.
    """

    sequence: list[int] = field(default_factory=list)
    digs: list[int] = field(default_factory=list)

    @property
    def max_dig(self) -> int:
        return max(self.digs, default=0)

    @property
    def total_dig(self) -> int:
        return sum(self.digs)

    @property
    def mean_dig(self) -> float:
        return self.total_dig / len(self.digs) if self.digs else 0.0


def resolve_pick_sequence(box_count: int, tunnel_queues: list[list[int]]) -> TunnelRelease:
    """Replay a walkthrough against tunnel queues and report the real pick order.

    The walkthrough says *which* box is wanted next; a tunnel says *when* it can
    be had.  Wanting a box that is third in its tunnel means popping the two in
    front of it first, and those two land in the tray early instead of at their
    own walkthrough step.  Boxes already pulled out during an earlier dig are
    simply skipped when their own turn comes.
    """
    location: dict[int, tuple[int, int]] = {}
    for tunnel, queue in enumerate(tunnel_queues):
        for position, index in enumerate(queue):
            if index in location:
                raise GameplayError(f"Box {index} is stored in more than one tunnel.")
            if not 0 <= index < box_count:
                raise GameplayError(f"Tunnel holds unknown box {index}.")
            location[index] = (tunnel, position)

    heads = [0] * len(tunnel_queues)
    picked = [False] * box_count
    release = TunnelRelease()
    for index in range(box_count):
        if picked[index]:
            continue
        spot = location.get(index)
        if spot is None:
            picked[index] = True
            release.sequence.append(index)
            continue
        tunnel, position = spot
        dig = 0
        while heads[tunnel] <= position:
            candidate = tunnel_queues[tunnel][heads[tunnel]]
            heads[tunnel] += 1
            if picked[candidate]:
                continue
            picked[candidate] = True
            release.sequence.append(candidate)
            dig += candidate != index
        release.digs.append(dig)
    if len(release.sequence) != box_count:  # pragma: no cover - queues are walkthrough subsets
        raise GameplayError("Tunnel queues do not release every box.")
    return release


def simulate_order(board: BoardState, order: list[BoxSpec], rules: GameRules) -> bool:
    """Replay an exact pick order and report whether it wins."""
    board = board.clone()
    tray: list[TrayBox] = []
    for spec in order:
        drain(board, tray)
        _prune(tray)
        if len(tray) >= rules.tray_slots:
            return False
        tray.append(TrayBox(spec.color, spec.size, spec.size))
    drain(board, tray)
    _prune(tray)
    return board.done() and not tray


# --------------------------------------------------------------------------- #
# Difficulty measurement
# --------------------------------------------------------------------------- #
@dataclass
class DifficultyMetrics:
    total_balls: int = 0
    total_boxes: int = 0
    colors: int = 0
    tray_slots: int = 1
    required_tray: int = 1
    min_safe_options: int = 0
    mean_safe_options: float = 0.0
    mean_total_options: float = 0.0
    forced_steps: int = 0
    measured_steps: int = 0
    undecided_probes: int = 0

    @property
    def forced_ratio(self) -> float:
        """Share of sampled steps where only the intended pick survives."""
        return self.forced_steps / self.measured_steps if self.measured_steps else 0.0

    @property
    def risk_ratio(self) -> float:
        """Share of the visible picks that lose the run, averaged over the walkthrough."""
        if not self.mean_total_options:
            return 0.0
        return 1.0 - self.mean_safe_options / self.mean_total_options


def measure_difficulty(
    board: BoardState,
    solution: Solution,
    rules: GameRules,
    *,
    max_probes: int = 600,
    node_limit: int = 4_000,
) -> DifficultyMetrics:
    """Count how many *different* picks keep the level winnable at each step.

    ``safe_options == 1`` means the step is forced: any other box loses the run.
    The walkthrough's own pick always counts as safe because :func:`solve_order`
    already proved it wins.  Other branches go through :func:`is_feasible`; a
    branch whose search gives up counts as unsafe and is tallied in
    ``undecided_probes``, so the numbers lean "harder" rather than lying.
    """
    order = solution.order
    metrics = DifficultyMetrics(
        total_balls=board.remaining_pixels(),
        total_boxes=len(order),
        colors=len(board.histogram()),
        tray_slots=rules.tray_slots,
        required_tray=solution.required_tray,
    )
    if not order:
        return metrics

    distinct = max(1, len(set(order)))
    stride = max(1, (len(order) * distinct) // max(1, max_probes))

    live_board = board.clone()
    live_tray: list[TrayBox] = []
    live_available = Counter(order)
    samples: list[int] = []
    totals: list[int] = []

    for index, spec in enumerate(order):
        drain(live_board, live_tray)
        _prune(live_tray)
        if index % stride == 0 and not live_board.done():
            safe = 0
            totals.append(len(live_available))
            for candidate in sorted(live_available, key=BoxSpec.sort_key):
                if candidate == spec:
                    safe += 1  # proven winnable by solve_order
                    continue
                if len(live_tray) >= rules.tray_slots:
                    continue
                probe_available = Counter(live_available)
                probe_available[candidate] -= 1
                if probe_available[candidate] <= 0:
                    del probe_available[candidate]
                probe_tray = [TrayBox(box.color, box.size, box.remaining) for box in live_tray]
                probe_tray.append(TrayBox(candidate.color, candidate.size, candidate.size))
                verdict = is_feasible(
                    live_board, probe_tray, probe_available, rules, node_limit=node_limit
                )
                if verdict is None:
                    metrics.undecided_probes += 1
                elif verdict:
                    safe += 1
            samples.append(safe)
        live_available[spec] -= 1
        if live_available[spec] <= 0:
            del live_available[spec]
        live_tray.append(TrayBox(spec.color, spec.size, spec.size))

    if samples:
        metrics.measured_steps = len(samples)
        metrics.min_safe_options = min(samples)
        metrics.mean_safe_options = sum(samples) / len(samples)
        metrics.mean_total_options = sum(totals) / len(totals)
        metrics.forced_steps = sum(1 for value in samples if value <= 1)
    return metrics
