from __future__ import annotations

"""Read a pixel picture the way the runtime eats it, and score how hard it is.

The runtime clears the picture in **one fixed pass**: the top row first, and
inside a row from the right edge leftwards.  An empty cell is not a stop - a
ball skips it and lands on the next painted pixel - so the whole picture
collapses into a single sequence of colors, :func:`play_sequence`.

That sequence is the only thing gameplay sees, and two facts follow from it:

* **The frontier is one cell.**  Exactly one color can be spent at any moment,
  so a box whose color is not the frontier color sits on the belt doing
  nothing.
* **The belt is the real constraint.**  A box holds nine balls and the belt is
  as wide as the level's ``piece`` - five boxes, so 45 balls, in the hand-made
  levels.  Whenever the sequence alternates between more colors than the belt
  can hold at once, the level is lost no matter how well it is played.

:func:`belt_demand` turns the second point into a number.  It replays the
sequence tapping every box **as late as legally possible** - a box of color
``c`` is only tapped when the frontier asks for ``c`` and nothing live can pay
for it.  No winning play can do better than that, so its peak occupancy is a
**lower bound** on the belt any play needs.  If that lower bound already
exceeds the belt, the picture is unwinnable and no search has to be run.

The difficulty tiers come from the color count, which is what a designer reads
off the picture at a glance.  The belt demand is a separate reading: it says how
much of the conveyor the picture spends by itself, and therefore how much is
left over for burying boxes and linking them.  The two are independent - a
twelve-color picture painted in bands leaves far more room than a six-color one
painted as noise.
"""

from collections import Counter
from dataclasses import dataclass, field
from itertools import groupby

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID, LevelDifficulty
from pixel_level_tool.domain.level_models import PixelGridData


BALLS_PER_BOX = 9
# Fallback belt for a scan with no level behind it. Real runs size the belt from
# the level's own `piece` (see `box_autogen.belt_for_level`); this is only the
# floor a bare `scan_picture` call is measured against.
DEFAULT_BELT_SLOTS = 30

# How many colors a picture may carry at each tier. The designer reads these off
# the picture, so they stay plain counts rather than anything derived.
EASY_MAX_COLORS = 3
MEDIUM_MAX_COLORS = 8
HARD_MAX_COLORS = 12

# Above this share of "the picture is one long colour switch", a picture plays a
# tier harder than its colour count alone suggests.
FRAGMENTED = 0.5


def play_sequence(grid: PixelGridData) -> list[int]:
    """The picture as the single color sequence the runtime clears it in.

    Top row down, right to left inside a row, empty cells skipped entirely.
    """
    return [
        grid.get_color_id(row, column)
        for row in range(grid.height)
        for column in range(grid.width - 1, -1, -1)
        if grid.get_color_id(row, column) != EMPTY_COLOR_ID
    ]


def play_cells(grid: PixelGridData) -> list[tuple[int, int]]:
    """``(row, column)`` of every painted cell, in the order the runtime eats them.

    The same walk as :func:`play_sequence`, kept beside it so a step of the play
    can be pointed at on the canvas. A jam reported as "pixel 175" is a number
    nobody can find; the same jam reported as "hàng 7, cột 12" is a place.
    """
    return [
        (row, column)
        for row in range(grid.height)
        for column in range(grid.width - 1, -1, -1)
        if grid.get_color_id(row, column) != EMPTY_COLOR_ID
    ]


def colour_runs(sequence: list[int]) -> list[tuple[int, int]]:
    """``(color, length)`` for each stretch of one color in play order."""
    return [(color, len(list(group))) for color, group in groupby(sequence)]


@dataclass(frozen=True)
class BeltDemand:
    """What the picture asks of the conveyor, from both ends.

    ``peak_balls`` is the **lower bound**: no play clears the picture with a
    smaller conveyor, so a belt under it is a proof of failure. ``peak_boxes`` is
    the same moment counted in boxes, which is what the level file's ``piece``
    field is measured in.

    ``peak_tap`` is the other end, an **upper bound that is known to work**: the
    belt this very play needs to be legal, counting the nine balls a tap pours in
    at once. A tap is only allowed while a whole box of room is free, so a belt
    that merely matches ``peak_balls`` can be one where nothing may ever be
    tapped. The width to hand a designer is therefore ``peak_tap``: at that belt
    the late-tapping play - the one that always exists - wins.
    """

    peak_balls: int = 0
    peak_boxes: int = 0
    peak_at: int = 0
    peak_colors: tuple[int, ...] = ()
    peak_tap: int = 0

    def fits(self, belt_slots: int = DEFAULT_BELT_SLOTS) -> bool:
        return self.peak_balls <= belt_slots

    def wins(self, belt_slots: int = DEFAULT_BELT_SLOTS) -> bool:
        """Is the belt wide enough that the late-tapping play is legal throughout?"""
        return self.peak_tap <= belt_slots

    def piece(self, box_size: int = BALLS_PER_BOX) -> int:
        """The level's ``piece`` this picture needs: the belt in whole boxes."""
        return -(-self.peak_tap // box_size)


@dataclass(frozen=True)
class BeltJam:
    """The first moment the picture cannot be played on, and what is in the way.

    A jam is never about the picture being *large*. It is about leftovers: a tap
    pours a whole box, the frontier is one cell, so a color whose run is shorter
    than a box leaves the rest of that box on the belt until the picture asks for
    that color again - which can be a hundred pixels later. Enough colors doing
    that at once and the belt has under a box of room, at which point the next
    tap is illegal and the play is over.

    So the useful thing to report is not the total, it is the *list*: which
    colors are squatting, how many balls each, and how far away the pixel that
    would finally spend them is.
    """

    at: int = 0
    wanted: int = 0
    used: int = 0
    belt_slots: int = 0
    # (color, balls left on the belt, pixels until that color is wanted again or
    # -1 when the picture never asks for it again).
    stuck: tuple[tuple[int, int, int], ...] = ()

    @property
    def free(self) -> int:
        return self.belt_slots - self.used


def belt_jam(
    sequence: list[int], belt_slots: int, box_size: int = BALLS_PER_BOX
) -> BeltJam | None:
    """The first tap this belt cannot afford, or None when the picture plays out.

    This walks the same late-tapping play :func:`belt_demand` measures, which is
    the play that holds the least at every step - so the first tap *it* cannot
    make is one no play could have made either.
    """
    live: Counter[int] = Counter()
    for index, color in enumerate(sequence):
        if not live[color]:
            used = sum(live.values())
            if used + box_size > belt_slots:
                stuck = []
                for held, balls in live.items():
                    ahead = next(
                        (step - index for step in range(index, len(sequence))
                         if sequence[step] == held),
                        -1,
                    )
                    stuck.append((held, balls, ahead))
                stuck.sort(key=lambda item: (-item[1], item[0]))
                return BeltJam(
                    at=index,
                    wanted=color,
                    used=used,
                    belt_slots=belt_slots,
                    stuck=tuple(stuck),
                )
            live[color] = box_size
        live[color] -= 1
        if not live[color]:
            del live[color]
    return None


def belt_demand(sequence: list[int], box_size: int = BALLS_PER_BOX) -> BeltDemand:
    """Lower bound on the belt this picture needs, by tapping as late as possible.

    A pixel cannot be cleared without a live box of its color, so at every step
    the lazy play holds the least any play could hold. Walking it once gives the
    worst moment, which is the number the belt has to beat.
    """
    live: Counter[int] = Counter()
    best = BeltDemand()
    peak_tap = 0
    for index, color in enumerate(sequence):
        if not live[color]:
            # The tap itself needs a whole box of free room on top of what is
            # already on the belt, which is the width this play has to have.
            peak_tap = max(peak_tap, sum(live.values()) + box_size)
            live[color] = box_size
        live[color] -= 1
        if not live[color]:
            del live[color]
        balls = sum(live.values())
        if balls > best.peak_balls:
            best = BeltDemand(
                peak_balls=balls,
                peak_boxes=len(live),
                peak_at=index,
                peak_colors=tuple(sorted(live)),
            )
    return BeltDemand(
        peak_balls=best.peak_balls,
        peak_boxes=best.peak_boxes,
        peak_at=best.peak_at,
        peak_colors=best.peak_colors,
        peak_tap=peak_tap,
    )


@dataclass
class PictureScan:
    """Everything Auto Gen Box needs to read off a picture before generating."""

    width: int = 0
    height: int = 0
    painted: int = 0
    histogram: Counter[int] = field(default_factory=Counter)
    sequence: list[int] = field(default_factory=list)
    # Where each step of `sequence` sits on the canvas, same order, same length.
    cells: list[tuple[int, int]] = field(default_factory=list)
    runs: list[tuple[int, int]] = field(default_factory=list)
    demand: BeltDemand = field(default_factory=BeltDemand)
    belt_slots: int = DEFAULT_BELT_SLOTS
    box_size: int = BALLS_PER_BOX
    # Boundary of the painted content, and the gaps inside it.
    bounds: tuple[int, int, int, int] | None = None
    empty_columns: list[int] = field(default_factory=list)
    empty_rows: list[int] = field(default_factory=list)
    holes: int = 0
    # What colour balancing already did before this scan ran. A scan of a
    # balanced picture reports no leftover of its own, so without these the whole
    # divisible-by-nine pass would be invisible to whoever is reading the scan.
    # Deleting is only the last of the three moves: `added` are the pixels it
    # painted into empty cells to top a colour up, and `moved` the ones it
    # recoloured from one colour into another when the picture had no room left.
    deleted: Counter[int] = field(default_factory=Counter)
    added: Counter[int] = field(default_factory=Counter)
    moved: Counter[tuple[int, int]] = field(default_factory=Counter)

    @property
    def colors(self) -> int:
        return len(self.histogram)

    @property
    def boxes(self) -> int:
        """Boxes the picture is worth once every color is trimmed to a multiple."""
        return sum(count // self.box_size for count in self.histogram.values())

    @property
    def trimmed_pixels(self) -> int:
        """Pixels colour balancing still has to delete, plus any it already did."""
        return sum(count % self.box_size for count in self.histogram.values()) + sum(
            self.deleted.values()
        )

    @property
    def added_pixels(self) -> int:
        """Pixels balancing painted in, which is how a colour is topped up."""
        return sum(self.added.values())

    @property
    def moved_pixels(self) -> int:
        """Pixels balancing recoloured, one colour paying another on a full picture."""
        return sum(self.moved.values())

    @property
    def balanced(self) -> bool:
        """Did balancing have to touch the picture at all?"""
        return bool(self.deleted or self.added or self.moved)

    @property
    def run_count(self) -> int:
        return len(self.runs)

    @property
    def mean_run(self) -> float:
        return self.painted / len(self.runs) if self.runs else 0.0

    @property
    def longest_run(self) -> int:
        return max((length for _, length in self.runs), default=0)

    @property
    def playable(self) -> bool:
        """Is the belt even large enough for the picture's own lower bound?"""
        return self.demand.fits(self.belt_slots)

    @property
    def required_belt(self) -> int:
        """Balls the belt needs, rounded up to the whole boxes ``piece`` is made of.

        The raw width is ``demand.peak_tap``, but the level file has no knob for
        it: it stores ``piece``, a count of boxes. A belt of 62 balls is a
        ``piece`` of 6 and a half, which rounds *down* to a belt of 54 when the
        level is loaded, so the number to quote is the whole box above.
        """
        return self.required_piece * self.box_size

    def cell_at(self, step: int) -> tuple[int, int] | None:
        """The canvas cell one step of the play order sits on."""
        return self.cells[step] if 0 <= step < len(self.cells) else None

    def jam(self) -> "BeltJam | None":
        """Where this picture stops being playable on its own belt, if it does."""
        return belt_jam(self.sequence, self.belt_slots, self.box_size)

    @property
    def short_runs(self) -> int:
        """Runs shorter than a box, i.e. taps that leave part of the box behind."""
        return sum(1 for _, length in self.runs if length < self.box_size)

    @property
    def wasted_per_tap(self) -> float:
        """Balls an average tap cannot spend at once, so they wait on the belt."""
        return max(0.0, self.box_size - self.mean_run)

    @property
    def required_piece(self) -> int:
        """The ``piece`` this picture needs, which is the number to hand a designer."""
        return self.demand.piece(self.box_size)

    @property
    def piece(self) -> int:
        """The ``piece`` the belt this scan was measured against is worth."""
        return self.belt_slots // self.box_size

    @property
    def belt_headroom(self) -> int:
        return self.belt_slots - self.demand.peak_balls

    @property
    def max_boxes(self) -> int:
        return self.belt_slots // self.box_size

    @property
    def fragmentation(self) -> float:
        """0 = every color in one solid band, 1 = every pixel a different color.

        This is what separates a twelve-color picture that plays like a ramp from
        one that plays like noise, and it moves independently of the color count.
        """
        if self.painted <= 1 or self.colors <= 1:
            return 0.0
        # One run per color is the floor; one run per pixel is the ceiling.
        return (len(self.runs) - self.colors) / max(1, self.painted - self.colors)


def scan_picture(
    grid: PixelGridData,
    *,
    belt_slots: int = DEFAULT_BELT_SLOTS,
    box_size: int = BALLS_PER_BOX,
) -> PictureScan:
    """Read a picture in play order and measure what generating from it costs."""
    grid.ensure_dense()
    sequence = play_sequence(grid)
    painted_cells = [
        (row, column)
        for row in range(grid.height)
        for column in range(grid.width)
        if grid.get_color_id(row, column) != EMPTY_COLOR_ID
    ]
    bounds = None
    holes = 0
    if painted_cells:
        rows = [row for row, _ in painted_cells]
        columns = [column for _, column in painted_cells]
        bounds = (min(rows), min(columns), max(rows), max(columns))
        top, left, bottom, right = bounds
        holes = (bottom - top + 1) * (right - left + 1) - len(painted_cells)
    return PictureScan(
        width=grid.width,
        height=grid.height,
        painted=len(sequence),
        histogram=Counter(sequence),
        sequence=sequence,
        cells=play_cells(grid),
        runs=colour_runs(sequence),
        demand=belt_demand(sequence, box_size),
        belt_slots=belt_slots,
        box_size=box_size,
        bounds=bounds,
        empty_columns=[
            column
            for column in range(grid.width)
            if all(
                grid.get_color_id(row, column) == EMPTY_COLOR_ID for row in range(grid.height)
            )
        ],
        empty_rows=[
            row
            for row in range(grid.height)
            if all(
                grid.get_color_id(row, column) == EMPTY_COLOR_ID for column in range(grid.width)
            )
        ],
        holes=holes,
    )


def difficulty_for_colors(colors: int) -> int:
    """The tier a picture lands in, read straight off its color count.

    The designer's scale is three wide - easy under four colors, medium up to
    eight, hard from nine to twelve - and anything past twelve is beyond what the
    scale was drawn for, so it goes to SuperHard rather than being clamped into
    Hard and pretending it is the same thing.
    """
    if colors <= EASY_MAX_COLORS:
        return int(LevelDifficulty.Easy)
    if colors <= MEDIUM_MAX_COLORS:
        return int(LevelDifficulty.Medium)
    if colors <= HARD_MAX_COLORS:
        return int(LevelDifficulty.Hard)
    return int(LevelDifficulty.SuperHard)


def suggest_difficulty(scan: PictureScan) -> int:
    """The tier for a scanned picture: colors set it, fragmentation can raise it.

    A picture painted as noise plays harder than its color count suggests, so a
    heavily fragmented one is pushed up a tier. It is never pushed *down*: a
    twelve-color picture in neat bands is still twelve colors to read, which is
    the thing the count was measuring in the first place.
    """
    tier = difficulty_for_colors(scan.colors)
    if scan.fragmentation >= FRAGMENTED and tier < int(LevelDifficulty.SuperHard):
        tier += 1
    return tier
