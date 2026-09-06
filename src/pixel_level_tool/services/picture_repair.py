from __future__ import annotations

"""Repaint a picture the conveyor cannot hold until it can be played.

A tap pours a whole nine-ball box, the frontier is one cell, and the picture is
eaten in one fixed pass - so a colour whose pixels come in *short runs* is the
thing that jams a level. A run of four spends four balls and leaves five on the
belt until that colour is asked for again, which can be a hundred pixels later.
Enough colours doing that at once and no tap is legal any more.

Level 15 is the case this exists for: ten colours over 648 pixels, but 127 of its
148 runs are shorter than a box and the mean run is 4.4 pixels, so it needs a
54-ball belt while shipping ``piece: 5``. Nothing is wrong with its *contents* -
72 boxes, every colour a whole number of them - only with how they are scattered.

So the repair is a **recolour, never a deletion**: a short run is merged into the
colour beside it, and exactly as many pixels are given back to it beside its own
largest region. Both colours keep their pixel count to the pixel, which is what
makes this safe to run: the box multiset comes straight off the histogram, so a
repaired picture builds the *same boxes* as the original and only the order they
are wanted in changes. What the player sees change is a speck moving next to its
own kind.

:func:`repair_picture` repeats that until the picture plays on the belt it has, or
until it runs out of short runs to merge - and reports every move it made, so a
designer can see their artwork's edits as a list rather than as a diff.
"""

from dataclasses import dataclass, field
from itertools import groupby

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID
from pixel_level_tool.domain.level_models import PixelGridData
from pixel_level_tool.services.picture_scan import (
    BALLS_PER_BOX,
    play_cells,
    play_sequence,
)


# A run this long or longer is spent by the tap that pours it, so it costs the
# belt nothing and is never worth merging away.
WHOLE_RUN = BALLS_PER_BOX

# Repairing is bounded work, not a search: each move merges one run away, and a
# picture needing more moves than this is not scattered, it is noise, and the
# honest answer for it is a wider `piece`.
MAX_MOVES = 60


@dataclass(frozen=True)
class RepairMove:
    """One consolidation, in the terms a designer reads it in.

    ``pixels`` of ``color`` at ``at`` became ``into``, and the same number of
    ``into`` pixels near ``paid_at`` became ``color`` - so both colours still own
    exactly what they owned, and ``color`` now sits in one piece instead of two.
    """

    color: int
    into: int
    pixels: int
    at: tuple[int, int]
    paid_at: tuple[int, int]


@dataclass
class RepairReport:
    """What the repair did, and whether it was enough."""

    moves: list[RepairMove] = field(default_factory=list)
    # Belt the picture needed before and after, in balls, and the run counts that
    # explain the difference.
    belt_before: int = 0
    belt_after: int = 0
    runs_before: int = 0
    runs_after: int = 0
    short_before: int = 0
    short_after: int = 0
    belt_slots: int = 0
    # Ran out of moves rather than out of need.
    exhausted: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.moves)

    @property
    def pixels(self) -> int:
        """Pixels recoloured, counting both halves of every move."""
        return sum(move.pixels * 2 for move in self.moves)

    @property
    def wins(self) -> bool:
        return self.belt_after <= self.belt_slots

    @property
    def gained(self) -> int:
        """Balls of conveyor the repair gave back."""
        return max(0, self.belt_before - self.belt_after)


def _runs_with_positions(sequence: list[int]) -> list[tuple[int, int, int]]:
    """``(color, start, length)`` for every stretch of one colour in play order."""
    runs: list[tuple[int, int, int]] = []
    start = 0
    for color, group in groupby(sequence):
        length = len(list(group))
        runs.append((color, start, length))
        start += length
    return runs


def belt_for_play(sequence: list[int], box_size: int = BALLS_PER_BOX) -> int:
    """Belt the late-tapping play needs on this sequence, in balls.

    The same walk as :func:`picture_scan.belt_demand`, kept here as a plain number
    because the repair loop calls it once per candidate move and only ever
    compares it against itself.
    """
    live: dict[int, int] = {}
    peak = 0
    for color in sequence:
        if not live.get(color):
            peak = max(peak, sum(live.values()) + box_size)
            live[color] = box_size
        live[color] -= 1
        if not live[color]:
            del live[color]
    return peak


def _shortest_runs(sequence: list[int]) -> list[tuple[int, int, int]]:
    """Runs worth merging away, shortest first.

    A run at least a box long is spent by its own tap, so it is left alone. A
    colour with only one run left is left alone too: merging it would take the
    colour off the picture, and the pay-back has nowhere to go.
    """
    runs = _runs_with_positions(sequence)
    counts: dict[int, int] = {}
    for color, _, _ in runs:
        counts[color] = counts.get(color, 0) + 1
    return sorted(
        (run for run in runs if run[2] < WHOLE_RUN and counts[run[0]] > 1),
        key=lambda run: (run[2], run[1]),
    )


def _hosts_for(runs: list[tuple[int, int, int]], index: int) -> list[int]:
    """Colours run ``index`` may be merged into, longest neighbour first.

    Only the two colours *touching* the speck qualify: merging it into anything
    else would leave its own neighbours still separated, so the run count would
    not come down and the whole loop would stop making progress.

    Both are offered rather than just the longer one, because the merge is only
    half the move - the other half needs that same colour to have pixels against
    a run of the speck's colour somewhere, and which of the two neighbours can
    pay is not something the lengths predict.
    """
    before = runs[index - 1] if index > 0 else None
    after = runs[index + 1] if index + 1 < len(runs) else None
    options = [run for run in (before, after) if run is not None]
    return [run[0] for run in sorted(options, key=lambda run: -run[2])]


def _payback_steps(
    sequence: list[int], home: tuple[int, int, int], host: int, needed: int
) -> list[int]:
    """``needed`` steps of ``host`` **touching** ``home``, or empty when there are none.

    Touching is the whole requirement, and it is strict. The pay-back has to
    *extend* the colour's own run, which only happens when the pixels handed over
    are the ones immediately before or after it in play order. Pixels of the right
    colour further away would leave the count correct and the picture *more*
    broken up than before - a new run of the merged colour opened somewhere else,
    and the host's own run split in two around it.

    So a move is only offered when the run has host-coloured pixels right up
    against one of its ends; otherwise the caller tries another home, or another
    run entirely.
    """
    _, start, length = home
    after = start + length
    ahead = list(range(after, min(after + needed, len(sequence))))
    if len(ahead) == needed and all(sequence[step] == host for step in ahead):
        return ahead
    behind = list(range(max(0, start - needed), start))
    if len(behind) == needed and all(sequence[step] == host for step in behind):
        return behind
    return []


# How many candidate merges to weigh against each other before committing to one.
# Shortest-run-first is a good ordering but not a reliable one: two merges that
# both tidy the picture can do very different things to the one worst instant the
# belt is measured at. Weighing a handful costs one sequence walk each and is the
# difference between a repair that finishes and one that stalls.
CANDIDATES = 12


def _candidate_moves(sequence: list[int]) -> list[tuple[int, int, int, int, list[int]]]:
    """``(color, start, length, host, payback)`` for the merges worth weighing.

    Shortest run first, and only merges that can actually be paid for: the speck
    goes into a colour touching it, and that colour has pixels right up against
    another run of the speck's own colour to hand back. Both halves together are
    what keeps the histogram still and the run count falling.
    """
    runs = _runs_with_positions(sequence)
    position = {run[1]: index for index, run in enumerate(runs)}
    found: list[tuple[int, int, int, int, list[int]]] = []
    for color, start, length in _shortest_runs(sequence):
        # Longest home first: the longer the run being extended, the more likely
        # its ends are deep inside a stretch of some neighbour's colour.
        homes = sorted(
            (run for run in runs if run[0] == color and run[1] != start),
            key=lambda run: -run[2],
        )
        for host in _hosts_for(runs, position[start]):
            if host == color:
                continue
            for home in homes:
                payback = _payback_steps(sequence, home, host, length)
                if payback:
                    found.append((color, start, length, host, payback))
                    break
            else:
                continue
            break
        if len(found) >= CANDIDATES:
            break
    return found


def _apply(
    grid: PixelGridData,
    cells: list[tuple[int, int]],
    candidate: tuple[int, int, int, int, list[int]],
) -> RepairMove:
    """Carry out one merge on the grid and describe it."""
    color, start, length, host, payback = candidate
    # The speck becomes its neighbour...
    for step in range(start, start + length):
        row, column = cells[step]
        grid.set_color_id(row, column, host)
    # ...and the neighbour hands the same number of pixels back right up against
    # the colour's own run, so neither count moves and the colour ends up in one
    # piece instead of two.
    for step in payback:
        row, column = cells[step]
        grid.set_color_id(row, column, color)
    return RepairMove(
        color=color,
        into=host,
        pixels=length,
        at=cells[start],
        paid_at=cells[payback[0]],
    )


def consolidate_once(
    grid: PixelGridData,
    sequence: list[int],
    cells: list[tuple[int, int]],
    box_size: int = BALLS_PER_BOX,
) -> RepairMove | None:
    """Make the merge that buys the most conveyor, paying its colour back beside itself.

    Returns the move, having applied it to ``grid``, or None when no run is left
    that can be merged *and* paid for without breaking the picture up further.

    The candidates are weighed rather than taken in order: each one is played out
    on a copy and scored by the belt the picture then needs, because tidying the
    picture and lowering its worst instant are not the same thing and only the
    second is what the level needs. Ties go to the merge that leaves the fewest
    runs, and every move lowers the run count by construction - which is what
    makes the loop above terminate.
    """
    candidates = _candidate_moves(sequence)
    if not candidates:
        return None
    before = list(grid.color_ids)
    best_score: tuple[int, int] | None = None
    best_candidate = candidates[0]
    for candidate in candidates:
        _apply(grid, cells, candidate)
        played = play_sequence(grid)
        score = (belt_for_play(played, box_size), len(_runs_with_positions(played)))
        grid.color_ids = list(before)
        if best_score is None or score < best_score:
            best_score, best_candidate = score, candidate
    return _apply(grid, cells, best_candidate)


def repair_picture(
    grid: PixelGridData,
    *,
    belt_slots: int,
    box_size: int = BALLS_PER_BOX,
    max_moves: int = MAX_MOVES,
    margin: int | None = None,
) -> RepairReport:
    """Consolidate short runs until the picture plays on ``belt_slots``.

    The belt is the goal but it is *not* what the loop climbs. A single merge
    almost never moves the peak - the peak is one worst instant over hundreds of
    pixels, and it takes many merges to lift it - so keeping only the moves that
    lower it immediately stops after the first one and repairs nothing. What the
    loop climbs is the **run count**, which every move lowers by construction, and
    it reads the belt on the side to know when it is done and which state was
    best.

    So the artwork is only ever left in the best state seen: the first one that
    reaches the target, or failing that the one that needed the narrowest belt. A
    picture that already plays is not touched at all - a level that works does not
    get its art rewritten for tidiness.

    ``margin`` is how much conveyor to aim to leave *over* winning, and it
    defaults to one box. Merging only until the picture exactly wins leaves a
    level with no room at all: at the peak instant every slot is taken, so the
    player has to play it perfectly and any obstacle laid on top has nothing to
    spend. One box is the smallest margin that means anything, because a tap
    pours a box or nothing.
    """
    grid.ensure_dense()
    sequence = play_sequence(grid)
    cells = play_cells(grid)
    runs = _runs_with_positions(sequence)
    start_belt = belt_for_play(sequence, box_size)
    report = RepairReport(
        belt_before=start_belt,
        belt_after=start_belt,
        runs_before=len(runs),
        runs_after=len(runs),
        short_before=sum(1 for _, _, length in runs if length < box_size),
        short_after=sum(1 for _, _, length in runs if length < box_size),
        belt_slots=belt_slots,
    )
    target = belt_slots - (box_size if margin is None else max(0, margin))
    if start_belt <= belt_slots:
        return report

    histogram = grid.histogram()
    # The best picture seen so far, as the flat colour list, with the moves that
    # produced it. Restored at the end, so a run of merges that made things worse
    # leaves the artwork alone.
    best_pixels = list(grid.color_ids)
    best_belt = start_belt
    best_moves: list[RepairMove] = []
    moves: list[RepairMove] = []
    exhausted = False

    for _ in range(max_moves):
        move = consolidate_once(grid, sequence, cells)
        if move is None:
            exhausted = True
            break
        moves.append(move)
        sequence = play_sequence(grid)
        cells = play_cells(grid)
        belt = belt_for_play(sequence, box_size)
        if belt < best_belt:
            best_belt, best_pixels, best_moves = belt, list(grid.color_ids), list(moves)
        if belt <= target:
            break

    grid.color_ids = best_pixels
    grid.ensure_dense()
    runs = _runs_with_positions(play_sequence(grid))
    report.moves = best_moves
    report.belt_after = best_belt
    report.runs_after = len(runs)
    report.short_after = sum(1 for _, _, length in runs if length < box_size)
    report.exhausted = exhausted and not report.wins

    if grid.histogram() != histogram:  # pragma: no cover - every move is paid for
        raise ValueError(
            "Internal error: repairing the picture changed how many pixels a colour has."
        )
    return report


def repair_summary(report: RepairReport) -> str:
    """The repair as one sentence, for the confirmation prompt and the report."""
    if not report.changed:
        return "không phải sửa gì"
    moves = len(report.moves)
    return (
        f"gom {moves} đốm màu lẻ ({report.pixels} pixel đổi màu, số pixel mỗi màu không đổi): "
        f"băng cần giảm từ {report.belt_before} xuống {report.belt_after}/{report.belt_slots} bóng, "
        f"mảng màu từ {report.runs_before} xuống {report.runs_after} "
        f"({report.short_before} → {report.short_after} mảng ngắn hơn {BALLS_PER_BOX} pixel)"
    )
