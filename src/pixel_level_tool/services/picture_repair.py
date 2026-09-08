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

from collections import Counter
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


@dataclass(frozen=True)
class ColorDrop:
    """One box worth of a colour's specks given up on, and what they became.

    Exactly ``pixels`` (one box) of ``color`` - its *shortest* stretches, the
    ones that jam the belt - became ``into``, and ``runs_removed`` stretches
    disappeared from the picture's pass as a result. ``gone`` is true only when
    that was the whole of ``color``, which is what happens to a colour that owned
    a single box and had it sprinkled: the palette loses it. Every other colour
    keeps every pixel it had.
    """

    color: int
    into: int
    pixels: int
    runs_removed: int
    gone: bool
    at: tuple[int, int]

    @property
    def boxes(self) -> int:
        return self.pixels // BALLS_PER_BOX


@dataclass
class RepairReport:
    """What the repair did, and whether it was enough."""

    moves: list[RepairMove] = field(default_factory=list)
    # Colours the second pass gave up on entirely, in the order it dropped them.
    # Empty unless the designer ticked for it: this one changes the artwork's
    # palette, which `moves` never does.
    drops: list[ColorDrop] = field(default_factory=list)
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
        return bool(self.moves or self.drops)

    @property
    def pixels(self) -> int:
        """Pixels recoloured, counting both halves of every move."""
        return sum(move.pixels * 2 for move in self.moves)

    @property
    def dropped_pixels(self) -> int:
        """Pixels that changed colour because their colour was dropped."""
        return sum(drop.pixels for drop in self.drops)

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


# --------------------------------------------------------------------------- #
# The second pass: thin the specks a colour cannot be paid back for
# --------------------------------------------------------------------------- #
# `repair_picture` never changes what a colour owns, which is what makes it safe
# to leave on by default - and also what limits it. Its merge is a *swap*: the
# speck becomes its neighbour and the neighbour hands the same number of pixels
# back beside the colour's own large region. A colour with no large region has
# nowhere to be paid back from, so no swap exists, and the pass reports
# `exhausted` with the belt still short.
#
# The move that is left is a **one-way** merge: the speck becomes its neighbour
# and nothing comes back. That changes what a colour owns, which is why it is
# opt-in - but it does not have to change much. The unit is one box, nine
# pixels, because that is the smallest edit the histogram permits: every colour
# has to stay a whole number of boxes or the level cannot be built at all. So
# each step gives up exactly one box of one colour's *shortest* stretches, the
# belt is read again, and the loop stops the instant the picture wins.
#
# Nine pixels at a time is the whole point. Picking the colour with the most
# short runs sounds right and is wrong: that is the *biggest* scattered colour,
# and giving it up whole repaints the picture's own subject. What actually wants
# thinning is the minor colour sprinkled as dust - the one whose runs are
# shortest, so nine pixels buys the most runs removed.
#
# A picture with fewer colours than this is not a level any more, so the pass
# stops rather than keep going.
MIN_COLORS_KEPT = 3

# Share of the painted picture the pass may recolour before it gives up. A
# picture needing more than this is not artwork with dust on it, it is noise, and
# the honest answer for it is a wider `piece` - so the artwork is put back
# exactly as it was and the level ships as a jam. Better a jam than a different
# picture.
#
# Measured on 24x24 pictures that are part painted bands and part per-pixel
# noise, after the safe pass has already run: a picture 60% noise wins on 11% of
# its pixels recoloured, one 70% noise wants 19%, and pure noise never wins at
# all. So this sits above the first and below the second - the cases it refuses
# are the ones where "repair" would have meant "repaint".
MAX_THIN_SHARE = 0.12


def color_scatter(sequence: list[int]) -> dict[int, tuple[int, int, float]]:
    """``(runs, short runs, mean short run)`` per colour, in play order.

    The three numbers that say whether a colour is *painted* or *sprinkled*. A
    colour the picture asks for in two long stretches costs the belt nothing; the
    same number of pixels in twenty specks is what no tap order can absorb.

    The mean is taken over the **short** runs only, because that is the number
    that says how much one box of thinning buys: nine pixels of one-pixel dust
    removes nine runs, nine pixels of four-pixel specks removes two.
    """
    runs = _runs_with_positions(sequence)
    per_color: dict[int, list[int]] = {}
    for color, _, length in runs:
        per_color.setdefault(color, []).append(length)
    scatter: dict[int, tuple[int, int, float]] = {}
    for color, lengths in per_color.items():
        short = [length for length in lengths if length < WHOLE_RUN]
        scatter[color] = (
            len(lengths),
            len(short),
            sum(short) / len(short) if short else 0.0,
        )
    return scatter


def thinnable_colors(sequence: list[int]) -> list[int]:
    """Colours with a whole box of dust to give up, dustiest and smallest first.

    A colour with no stretch shorter than a box has nothing to give: each of its
    runs is spent by the tap that pours it and costs the belt nothing. A colour
    with fewer than nine pixels in short stretches has dust but not a box of it,
    and a box is the smallest edit the histogram permits.

    The order is a preference, not a decision - :func:`most_scattered_color`
    reads it when nothing else separates two candidates.
    """
    scatter = color_scatter(sequence)
    runs = _runs_with_positions(sequence)
    dust: Counter[int] = Counter()
    for color, _, length in runs:
        if length < WHOLE_RUN:
            dust[color] += length
    owned = Counter(sequence)
    ranked = [
        (mean, owned[color], color)
        for color, (_, short, mean) in scatter.items()
        if short and dust[color] >= BALLS_PER_BOX
    ]
    return [color for _, _, color in sorted(ranked)]


def most_scattered_color(sequence: list[int]) -> int | None:
    """The dustiest colour with a box to give up, or ``None`` if there is none.

    Ranked by how short its stretches are, then by how few pixels it owns: of two
    equally dusty colours the minor one is the one to thin, because it is the one
    the picture is least about.

    Deliberately *not* "the colour with the most short runs". That is the biggest
    scattered colour, and thinning it first repaints the picture's own subject.
    This is only the tie-breaker, though: what actually chooses each step is
    which colour's box of dust buys the most belt back - see :func:`best_thin`.
    """
    ranked = thinnable_colors(sequence)
    return ranked[0] if ranked else None


def best_thin(
    grid: PixelGridData, sequence: list[int], box_size: int = BALLS_PER_BOX
) -> tuple[int, int] | None:
    """``(belt, colour)`` for the box of dust that buys the most belt back.

    Greedy on the thing that actually matters, because a greedy on dustiness is
    not just weaker - it is **wrong**. Merging a colour's specks into a
    neighbour lengthens that neighbour's runs and shortens nothing else, so it
    can leave the picture needing a *wider* belt than before: measured on a
    half-noise picture, thinning the dustiest colour first took the belt from 49
    to 57 and needed a quarter of the artwork recoloured before it came back.

    So every candidate is tried on a copy and scored by the belt it leaves.
    Ties go to the smaller colour, so dust is sacrificed before subject.
    ``None`` when no colour has a whole box of dust to give.
    """
    owned = Counter(sequence)
    best: tuple[tuple[int, int, int], int] | None = None
    for color in thinnable_colors(sequence):
        trial = PixelGridData(grid.width, grid.height, list(grid.color_ids))
        if thin_once(trial, sequence, play_cells(trial), color) is None:
            continue
        belt = belt_for_play(play_sequence(trial), box_size)
        key = (belt, owned[color], color)
        if best is None or key < best[0]:
            best = (key, color)
    return (best[0][0], best[1]) if best is not None else None


def _neighbour_of(sequence: list[int], start: int, length: int, color: int) -> int | None:
    """The colour a stretch of ``color`` sits against in the picture's own pass."""
    before = next(
        (sequence[i] for i in range(start - 1, -1, -1) if sequence[i] != color), None
    )
    after = next(
        (sequence[i] for i in range(start + length, len(sequence)) if sequence[i] != color),
        None,
    )
    return before if before is not None else after


def thin_once(
    grid: PixelGridData, sequence: list[int], cells: list[tuple[int, int]], color: int
) -> ColorDrop | None:
    """Give up exactly one box of ``color``'s shortest stretches. One-way.

    Shortest first, because those cost the belt most per pixel: a one-pixel speck
    spends one ball and holds the other eight until that colour comes round
    again. Taken until nine pixels are gathered, the last stretch contributing
    only as much as is needed - a partial merge, which is what the safe pass does
    too.

    All nine go to **one** receiver, and that is forced rather than chosen: nine
    pixels cannot be split into two whole boxes, so any other split leaves a
    receiver with a remainder and the level unbuildable. The receiver is the
    colour most of the nine already sit against, so the edit reads as dust
    settling onto what was beside it.

    ``None`` when ``color`` has fewer than nine pixels in stretches shorter than
    a box - there is no whole box of dust to give up.
    """
    short = sorted(
        (length, start)
        for value, start, length in _runs_with_positions(sequence)
        if value == color and length < WHOLE_RUN
    )
    taken: list[int] = []
    receivers: Counter[int] = Counter()
    removed = 0
    for length, start in short:
        neighbour = _neighbour_of(sequence, start, length, color)
        if neighbour is None:
            continue
        want = min(length, BALLS_PER_BOX - len(taken))
        taken.extend(range(start, start + want))
        receivers[neighbour] += want
        # A stretch only leaves the picture's pass when all of it goes.
        if want == length:
            removed += 1
        if len(taken) == BALLS_PER_BOX:
            break
    if len(taken) < BALLS_PER_BOX:
        return None

    into = receivers.most_common(1)[0][0]
    for step in taken:
        row, column = cells[step]
        grid.set_color_id(row, column, into)
    return ColorDrop(
        color=color,
        into=into,
        pixels=len(taken),
        runs_removed=removed,
        gone=sum(1 for value in sequence if value == color) == len(taken),
        at=cells[taken[0]],
    )


def drop_scattered_colors(
    grid: PixelGridData,
    *,
    belt_slots: int,
    box_size: int = BALLS_PER_BOX,
    margin: int | None = None,
    min_colors: int = MIN_COLORS_KEPT,
    max_share: float = MAX_THIN_SHARE,
    report: RepairReport | None = None,
) -> RepairReport:
    """Thin dust one box at a time, taking the box that buys the most belt back.

    The last resort, and the only repair that changes what a colour owns - so it
    is written to change as little as it can get away with:

    * **one box per step**, the smallest edit a histogram of whole boxes allows;
    * the box that **lowers the belt most**, chosen by trying every candidate -
      see :func:`best_thin` for why dustiness alone is the wrong objective;
    * it stops **the moment the belt wins**, not one box past it and not when
      the palette looks tidy. The safe pass aims for margin; this one is only
      ever buying the win, so it buys exactly that;
    * a step that makes the belt *worse* is undone rather than kept, and the
      artwork is only ever left in the best state seen;
    * and if it cannot win inside ``max_share`` of the picture, the artwork is
      **put back exactly as it was**. A picture needing more than a few per cent
      recoloured is noise rather than art with dust on it, and the honest answer
      for it is a wider ``piece``, not a different picture.

    A colour only leaves the palette when the box given up was all it had, which
    is the case this exists for: one box of a colour, sprinkled. Colours the
    picture is actually made of keep every pixel of their real regions and lose
    only dust.
    """
    grid.ensure_dense()
    sequence = play_sequence(grid)
    start_belt = belt_for_play(sequence, box_size)
    if report is None:
        runs = _runs_with_positions(sequence)
        report = RepairReport(
            belt_before=start_belt,
            belt_after=start_belt,
            runs_before=len(runs),
            runs_after=len(runs),
            short_before=sum(1 for _, _, length in runs if length < box_size),
            short_after=sum(1 for _, _, length in runs if length < box_size),
            belt_slots=belt_slots,
        )
    if start_belt <= belt_slots:
        return report

    before = list(grid.color_ids)
    target = belt_slots - max(0, margin or 0)
    budget = max(box_size, int(len(sequence) * max(0.0, max_share)))
    drops: list[ColorDrop] = []
    spent = 0
    # The narrowest belt seen, and the artwork that produced it. A step is only
    # worth keeping if it left the picture better than the best so far - which
    # is not automatic, because merging dust into a neighbour lengthens that
    # neighbour's runs and can widen the belt it needs.
    best_belt = start_belt
    best_pixels = list(grid.color_ids)
    best_drops: list[ColorDrop] = []

    while spent + box_size <= budget and len(grid.histogram()) > max(1, min_colors):
        choice = best_thin(grid, sequence, box_size)
        if choice is None:
            break
        _, color = choice
        drop = thin_once(grid, sequence, play_cells(grid), color)
        if drop is None:
            break
        drops.append(drop)
        spent += drop.pixels
        grid.ensure_dense()
        sequence = play_sequence(grid)
        belt = belt_for_play(sequence, box_size)
        if belt < best_belt:
            best_belt, best_pixels, best_drops = belt, list(grid.color_ids), list(drops)
        if belt <= target:
            break

    grid.color_ids = best_pixels
    grid.ensure_dense()
    drops = best_drops
    belt = best_belt
    if belt > belt_slots:
        # It did not buy a win, so it bought nothing worth the edit.
        grid.color_ids = before
        grid.ensure_dense()
        drops = []
        belt = belt_for_play(play_sequence(grid), box_size)
    sequence = play_sequence(grid)

    runs = _runs_with_positions(sequence)
    report.drops = drops
    report.belt_after = belt
    report.runs_after = len(runs)
    report.short_after = sum(1 for _, _, length in runs if length < box_size)
    report.exhausted = not report.wins
    return report


def repair_summary(report: RepairReport) -> str:
    """The repair as one sentence, for the confirmation prompt and the report.

    The two passes are said separately on purpose. Merging specks keeps every
    colour's pixel count to the pixel, so a designer can leave it on and never
    look; dropping a colour takes it off the palette, so it has to be spelled out
    with the colour named and how scattered it was - that is the number that
    justifies the edit.
    """
    if not report.changed:
        return "không phải sửa gì"
    parts = [text for text in (merge_summary(report), drop_summary(report)) if text]
    return " · ".join(parts) + ": " + belt_summary(report)


def merge_summary(report: RepairReport) -> str:
    """The safe pass on its own, so a caller can say what it did without the drops."""
    if not report.moves:
        return ""
    return (
        f"gom {len(report.moves)} đốm màu lẻ ({report.pixels} pixel đổi màu, "
        "số pixel mỗi màu không đổi)"
    )


def drop_summary(report: RepairReport) -> str:
    """The dust given up on, measured, so the edit can be justified."""
    if not report.drops:
        return ""
    gone = [drop.color for drop in report.drops if drop.gone]
    return (
        f"bỏ {len(report.drops)} box đốm màu vụn ({report.dropped_pixels} pixel đổi màu, "
        "mảng lớn của mọi màu giữ nguyên"
        + (
            f", mất màu {', '.join(str(color) for color in gone)}"
            if gone
            else ", không mất màu nào"
        )
        + "): "
        + ", ".join(
            f"màu {drop.color} → {drop.into} (mất {drop.runs_removed} mảng vụn)"
            for drop in report.drops
        )
    )


def belt_summary(report: RepairReport) -> str:
    """What the repair bought, in belt balls and in run counts."""
    return (
        f"băng cần giảm từ {report.belt_before} xuống "
        f"{report.belt_after}/{report.belt_slots} bóng, "
        f"mảng màu từ {report.runs_before} xuống {report.runs_after} "
        f"({report.short_before} → {report.short_after} mảng ngắn hơn {BALLS_PER_BOX} pixel)"
    )
