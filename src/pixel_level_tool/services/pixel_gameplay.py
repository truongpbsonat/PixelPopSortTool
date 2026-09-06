from __future__ import annotations

"""Deterministic gameplay model used to certify auto-generated Pixel levels.

The runtime rules assumed here are the ones the level designer confirmed:

* The pixel grid is consumed in **one fixed pass**: the top row first, and
  inside a row from the **right edge leftwards**.  An empty cell is not a stop -
  a ball skips it and lands on the next painted pixel - so the picture reduces
  to the single color sequence :func:`picture_scan.play_sequence` returns, and
  the *frontier* is one cell rather than one per column.
* A picked box pours its nine balls onto the **conveyor**, which holds thirty.
  Tapping needs room for a whole box, so a tap is legal only while nine slots
  are free and three full boxes is the ceiling.
* Balls leave the conveyor by paying for the frontier pixel, so a box whose
  color is not wanted yet just sits there taking up room.
* The player loses when no tap is legal and nothing on the conveyor can drain -
  the conveyor is jammed with colors the picture is not asking for.
* Every box on the grid can be picked, so the box grid layout decides how much
  searching the player has to do rather than what is reachable.
* A **tunnel** is the one exception: it is a queue, only its head can be taken,
  and taking the head reveals the next box.  An emptied tunnel does not vanish -
  it keeps its slot as a wall.  So a box buried in a tunnel forces the player to
  pull everything in front of it into the tray first, which is what
  :func:`resolve_pick_sequence` turns back into a plain pick order.
* A **LinkedContainer** ties two boxes together: picking either one sends *both*
  down, so the pick costs two tray slots at the same instant rather than one at a
  time.  :func:`resolve_link_groups` folds the partners into one pick and
  :func:`simulate_groups` is the replay that charges both slots at once.
* An **ArrowLock** box cannot be opened until a box in the direction its arrow
  points at has been opened.  That is a pure ordering constraint - it never
  changes what lands in the tray - so it is enforced on the pick order in
  :mod:`box_autogen` rather than modelled here.

One arbitrary choice makes the simulation deterministic: when several boxes on
the conveyor carry the frontier color, the oldest one pays.
"""

from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass, field

from pixel_level_tool.domain.level_models import PixelGridData
from pixel_level_tool.services.picture_scan import (
    BALLS_PER_BOX,
    DEFAULT_BELT_SLOTS,
    play_sequence,
)


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
    """The conveyor, measured in balls rather than in boxes.

    A tap pours a whole box on at once, so ``belt_slots`` divided by
    ``box_size`` is the real ceiling and the remainder is dead room: thirty
    slots take three nine-ball boxes and the last three slots can never be
    filled by a fourth.
    """

    belt_slots: int = DEFAULT_BELT_SLOTS
    box_size: int = BALLS_PER_BOX

    @property
    def max_boxes(self) -> int:
        return self.belt_slots // self.box_size


def belt_used(tray: list["TrayBox"]) -> int:
    """Balls sitting on the conveyor right now."""
    return sum(box.remaining for box in tray)


def can_tap(tray: list["TrayBox"], rules: GameRules, boxes: int = 1) -> bool:
    """Is there room to drop ``boxes`` more boxes on the conveyor?

    The whole box lands at once, so partial room is no room at all - this is the
    rule the player loses to, not a tray-slot count.
    """
    return rules.belt_slots - belt_used(tray) >= rules.box_size * boxes


class GameplayError(ValueError):
    pass


def _index_positions(sequence: tuple[int, ...]) -> dict[int, tuple[int, ...]]:
    """Where each color appears, so ``next_gap`` is a lookup rather than a scan."""
    positions: dict[int, list[int]] = {}
    for index, color in enumerate(sequence):
        positions.setdefault(color, []).append(index)
    return {color: tuple(spots) for color, spots in positions.items()}


class BoardState:
    """The picture as the one sequence the runtime clears it in, plus a cursor.

    Top row down, right to left inside a row, empty cells skipped - so the whole
    board is ``sequence`` and how far it has been paid for is ``cursor``. Only
    the color at the cursor can be spent, which is what makes the conveyor tight:
    every other box on it is waiting rather than working.
    """

    __slots__ = ("sequence", "positions", "cursor")

    def __init__(
        self,
        sequence: tuple[int, ...],
        positions: dict[int, tuple[int, ...]] | None = None,
        cursor: int = 0,
    ) -> None:
        self.sequence = sequence
        # Shared across clones: it only depends on the picture, never on progress.
        self.positions = _index_positions(sequence) if positions is None else positions
        self.cursor = cursor

    @classmethod
    def from_pixel_grid(cls, grid: PixelGridData) -> "BoardState":
        return cls(tuple(play_sequence(grid)))

    def clone(self) -> "BoardState":
        return BoardState(self.sequence, self.positions, self.cursor)

    def done(self) -> bool:
        return self.cursor >= len(self.sequence)

    def remaining_pixels(self) -> int:
        return len(self.sequence) - self.cursor

    def histogram(self) -> Counter[int]:
        return Counter(self.sequence[self.cursor :])

    def frontier_colors(self) -> set[int]:
        """The one color that can be spent, or nothing once the picture is done."""
        return set() if self.done() else {self.sequence[self.cursor]}

    def run_capacity(self, color: int) -> int:
        """Balls of ``color`` the board absorbs before any other color is wanted."""
        total = 0
        cursor = self.cursor
        while cursor < len(self.sequence) and self.sequence[cursor] == color:
            total += 1
            cursor += 1
        return total

    def next_gap(self, color: int) -> int:
        """Pixels to clear before ``color`` is wanted again, or ``-1`` if never.

        A box tapped early holds conveyor room for exactly this long, so it is
        what ranks the picks that are not the frontier color.
        """
        spots = self.positions.get(color)
        if not spots:
            return -1
        index = bisect_left(spots, self.cursor)
        return -1 if index >= len(spots) else spots[index] - self.cursor

    def fill(self, color: int, count: int) -> int:
        """Pay for up to ``count`` frontier pixels with balls of ``color``."""
        consumed = 0
        while (
            consumed < count
            and self.cursor < len(self.sequence)
            and self.sequence[self.cursor] == color
        ):
            self.cursor += 1
            consumed += 1
        return consumed

    def state_key(self) -> int:
        return self.cursor


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
    belt_used: int
    safe_options: int = 0


@dataclass
class Solution:
    steps: list[SolutionStep] = field(default_factory=list)
    required_belt: int = 0
    peak_boxes: int = 0
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
    """Candidate picks, best first: pay the frontier, then the soonest colour.

    With a single frontier cell only one box can work at a time, so the pick that
    matters most is the one the picture is asking for right now. Everything else
    is a bet on the future and is ranked by how long it would squat on the
    conveyor before paying off - a color wanted in three pixels is a far cheaper
    bet than one wanted in eighty. Colors the picture never asks for again sort
    last; they are pure dead weight.
    """
    frontier = board.frontier_colors()
    horizon = board.remaining_pixels() + 1
    scored = []
    for spec in available:
        gap = board.next_gap(spec.color)
        capacity = board.run_capacity(spec.color)
        scored.append(
            (
                0 if spec.color in frontier else 1,
                horizon if gap < 0 else gap,
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

    A plain greedy walk is far too weak here: paying the frontier is usually
    right but not always, because the box that pays it now may be the one whose
    leftovers jam the conveyor twenty pixels later. The search explores "pay the
    frontier" first, so the order it returns is also the one a player would call
    natural, and memoises states so it stays cheap.

    Returns ``None`` when no order wins within ``node_limit`` expansions.
    """
    seen: set[tuple] = set()
    nodes = 0
    stack: list[tuple[BoardState, list[TrayBox], Counter[BoxSpec], list[tuple[BoxSpec, int, int]]]] = [
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
            return Solution(
                steps=[SolutionStep(spec, used) for spec, used, _ in path],
                required_belt=max((used for _, used, _ in path), default=0),
                peak_boxes=max((boxes for _, _, boxes in path), default=0),
                nodes=nodes,
            )

        key = _search_key(state_board, tray, remaining)
        if key in seen:
            continue
        seen.add(key)
        if not can_tap(tray, rules):
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
                (
                    state_board.clone(),
                    child_tray,
                    child_remaining,
                    path + [(spec, belt_used(child_tray), len(child_tray))],
                )
            )
    return None


def lazy_order(
    board: BoardState,
    available: Counter[BoxSpec],
    box_size: int = BALLS_PER_BOX,
) -> Solution:
    """The pick order that taps as late as legally possible. It always exists.

    The frontier is a single cell, so at every moment exactly one color can be
    spent. This play taps a box only when the picture is asking for that color
    and nothing already on the belt can pay for it - which is the same play
    :func:`picture_scan.belt_demand` measures, and no play holds less at any
    point. It never gets stuck: the pixel histogram *is* the box multiset, so a
    box of the frontier color is always left to tap, and it therefore wins on any
    belt at least as wide as ``required_belt``.

    That is what makes it the answer to "this picture wins on no belt the search
    could find": it is not a better order than :func:`solve_order` looks for, it
    is the one that is guaranteed to be there, and its ``required_belt`` says
    exactly how wide the conveyor has to be for it.
    """
    state = board.clone()
    remaining = Counter(available)
    tray: list[TrayBox] = []
    steps: list[SolutionStep] = []
    peak_boxes = 0
    drain(state, tray)
    _prune(tray)
    while not state.done():
        color = next(iter(state.frontier_colors()))
        spec = next(
            (spec for spec in sorted(remaining, key=BoxSpec.sort_key) if spec.color == color),
            None,
        )
        if spec is None:  # pragma: no cover - box_multiset is built from this histogram
            raise GameplayError(
                f"The picture still wants color {color} but no box of it is left."
            )
        remaining[spec] -= 1
        if remaining[spec] <= 0:
            del remaining[spec]
        tray.append(TrayBox(spec.color, spec.size, spec.size))
        # Recorded the way solve_order records it: after the tap, before draining,
        # so the number is the belt the tap itself needed.
        steps.append(SolutionStep(spec, belt_used(tray)))
        peak_boxes = max(peak_boxes, len(tray))
        drain(state, tray)
        _prune(tray)
    return Solution(
        steps=steps,
        required_belt=max((step.belt_used for step in steps), default=0),
        peak_boxes=peak_boxes,
    )


def minimum_belt(
    board: BoardState,
    available: Counter[BoxSpec],
    *,
    box_size: int = BALLS_PER_BOX,
    max_slots: int = DEFAULT_BELT_SLOTS,
    min_slots: int = 0,
    node_limit: int = 60_000,
) -> int | None:
    """Smallest conveyor a perfect player needs, or ``None`` if even ``max_slots`` loses.

    Only whole boxes of room ever change the answer - a tap needs a whole box, so
    a belt of 30 and a belt of 35 allow exactly the same three - which is why
    this steps by ``box_size`` instead of walking every ball.

    ``min_slots`` skips the belts that are known losers before the search runs:
    the picture's own demand is a lower bound no play beats, so searching under it
    only spends the node limit proving what the bound already said.
    """
    for boxes in range(max(1, -(-min_slots // box_size)), max_slots // box_size + 1):
        slots = boxes * box_size
        rules = GameRules(belt_slots=slots, box_size=box_size)
        if solve_order(board, available, rules, node_limit=node_limit) is not None:
            return slots
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
        if not can_tap(state_tray, rules):
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
    return simulate_groups(board, [[spec] for spec in order], rules)


# --------------------------------------------------------------------------- #
# Linked containers
# --------------------------------------------------------------------------- #
def simulate_groups(board: BoardState, groups: list[list[BoxSpec]], rules: GameRules) -> bool:
    """Replay a pick order where one pick can drop several boxes into the tray at once.

    A linked pair is exactly that: the player taps one box and both slide down
    together, so the tray has to have room for *all* of them at that instant. A
    group of two therefore fails on a tray with one slot left, even though the
    second box would have drained the moment the first emptied - the game never
    gives the player that pause.
    """
    board = board.clone()
    tray: list[TrayBox] = []
    for group in groups:
        drain(board, tray)
        _prune(tray)
        if not can_tap(tray, rules, len(group)):
            return False
        for spec in group:
            tray.append(TrayBox(spec.color, spec.size, spec.size))
    drain(board, tray)
    _prune(tray)
    return board.done() and not tray


def belt_peak(board: BoardState, groups: list[list[BoxSpec]], rules: GameRules) -> int | None:
    """Fullest the conveyor ever gets while these picks are played, or None if they lose.

    :func:`simulate_groups` answers "does this win", which is the only thing the
    generator may not ship without. This answers the question after it: *how
    close* did it come. The two are the same walk, so the peak costs nothing on
    top of the check it replaces.

    Measured the way :func:`solve_order` measures a step - right after the tap and
    before the drain - so a play order's peak is directly comparable with the
    ``belt_used`` of the walkthrough it was forced out of. The difference between
    the two is what the obstacles cost the player.
    """
    board = board.clone()
    tray: list[TrayBox] = []
    peak = 0
    for group in groups:
        drain(board, tray)
        _prune(tray)
        if not can_tap(tray, rules, len(group)):
            return None
        for spec in group:
            tray.append(TrayBox(spec.color, spec.size, spec.size))
        peak = max(peak, belt_used(tray))
    drain(board, tray)
    _prune(tray)
    if not board.done() or tray:
        return None
    return peak


def tap_progress(
    board: BoardState, groups: list[list[BoxSpec]], rules: GameRules
) -> list[int] | None:
    """Pixels already cleared off the picture at each tap, or None if the play loses.

    This is the counter the two lock mechanics open on. ``Frozen`` and
    ``LargeBlock`` do not name a box or a partner the way an ArrowLock does -
    they name a number, and the runtime opens them when the picture has lost
    that many pixels. So a lock whose count is at most ``progress[i]`` is
    already open by the time step ``i`` comes round, and cannot delay - let
    alone deadlock - this particular play order.

    Read *before* the tap rather than after it, unlike :func:`belt_peak`,
    because before the tap is when the runtime decides whether the tap is
    allowed. Same walk otherwise, so the two are directly comparable.
    """
    board = board.clone()
    tray: list[TrayBox] = []
    progress: list[int] = []
    for group in groups:
        drain(board, tray)
        _prune(tray)
        progress.append(board.cursor)
        if not can_tap(tray, rules, len(group)):
            return None
        for spec in group:
            tray.append(TrayBox(spec.color, spec.size, spec.size))
    drain(board, tray)
    _prune(tray)
    if not board.done() or tray:
        return None
    return progress


def resolve_link_groups(sequence: list[int], links: list[tuple[int, int]]) -> list[list[int]]:
    """Fold linked partners into a single pick, at whichever of the two comes first.

    Taking either half of a pair takes both, so the pair happens at the earlier of
    its two walkthrough steps and the later step is simply gone - the box is
    already in the tray by then. A partner is only ever pulled *forward*, never
    delayed, which is what keeps every other ordering constraint on the level
    (tunnel releases, arrow locks) still satisfied afterwards.
    """
    partner: dict[int, int] = {}
    for left, right in links:
        if left == right:
            raise GameplayError(f"A LinkedContainer cannot link box {left} to itself.")
        for index in (left, right):
            if index in partner:
                raise GameplayError(f"Box {index} belongs to more than one LinkedContainer.")
        partner[left] = right
        partner[right] = left

    groups: list[list[int]] = []
    taken: set[int] = set()
    for index in sequence:
        if index in taken:
            continue
        group = [index]
        taken.add(index)
        mate = partner.get(index)
        if mate is not None and mate not in taken:
            group.append(mate)
            taken.add(mate)
        groups.append(group)
    if sum(len(group) for group in groups) != len(sequence):  # pragma: no cover - folding is exact
        raise GameplayError("Linked containers do not release every box exactly once.")
    return groups


# --------------------------------------------------------------------------- #
# Difficulty measurement
# --------------------------------------------------------------------------- #
@dataclass
class DifficultyMetrics:
    total_balls: int = 0
    total_boxes: int = 0
    colors: int = 0
    belt_slots: int = DEFAULT_BELT_SLOTS
    required_belt: int = 0
    peak_boxes: int = 0
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
        belt_slots=rules.belt_slots,
        required_belt=solution.required_belt,
        peak_boxes=solution.peak_boxes,
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
                if not can_tap(live_tray, rules):
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
