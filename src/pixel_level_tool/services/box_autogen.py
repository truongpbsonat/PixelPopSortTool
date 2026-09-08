from __future__ import annotations

"""Generate a complete, playable Box Ball Grid from the current Pixel Grid.

The output matches the shape of the hand-made levels: the box grid is a full
rectangle of ``Square_3x3`` boxes anchored on a 3-cell lattice, every box is
mono-color and inactive, and the difficulty comes from how many boxes carry the
``Hidden`` effect rather than from the size of the conveyor.

The conveyor is the thing everything else is measured against. It is as wide as
the level's own ``piece`` - five boxes, so 45 balls, in every hand-made level -
a tap pours a whole nine-ball box onto it, and the player loses the moment no
tap is legal and nothing on the belt can drain.

That belt is a **budget, not a veto**. A level is made hard by deliberately
forcing spare boxes onto it: burying a box in a tunnel means digging out the
ones in front of it, and a stalled link means a partner squatting there. The
walkthrough itself is expected to be cheap; what has to stay inside the belt is
the pressure the obstacles add on top. So the picture is never refused up front -
if the belt genuinely cannot hold it, the search says so and stage 2's numbers
explain where it jams.

The picture and the obstacles are therefore two difficulties that add up in the
same place, and the tier is read off the picture - so the hardest pictures are
exactly the ones that ask for the hardest obstacle forms while having no belt
left to pay for them. That sum is *measured* rather than hoped for: the obstacle
layer is built at the tier's own form and then read back, and a mechanic the belt
took most of away is the conveyor saying it cannot pay. When it says no, the
whole layer is rebuilt a tier gentler, where the mechanic fits instead of being
refused (:func:`relieve_obstacles`). The level keeps every mechanic its tier
bought - a relieved Hard level still carries the wall, the tunnel and the links -
they are just set the way an easier tier would set them. What comes out is
certified as a whole in stage 13, and
:attr:`AutoGenResult.obstacle_belt_cost` says how much of the conveyor the
obstacles ended up spending, measured against the base grid of stage 5, which is
the same play with nothing in the way.

Thirteen stages, and the order they run in is the design. The picture is turned
into a box grid that is **proven beatable with nothing in the way** (stages 1-5),
and only then are obstacles laid on top of that proof (stages 6-12), every one of
them re-certified. Difficulty is therefore never the thing that makes a level
unwinnable: it is spent out of what the picture left over, and a mechanic the
grid cannot carry is dropped rather than shipped.

The last two stages are a different kind of mechanic and come last for a reason.
A ``Frozen`` box and a ``LargeBlock`` slab do not name a box or a partner - they
name a *number*, and the runtime opens them once the picture has lost that many
pixels. So they can only be written once the play order exists, and once it does
they are **read out of it** rather than laid on top of it: the number is capped
by how much of the picture is already gone when that order reaches the box
behind it. Neither can cost the level its proof, and neither spends a single
ball of conveyor - which is why they are budgeted apart from the other five
(:data:`LOCK_KINDS`). What they take is the player's freedom to tap early.

1. **Balance** - a box holds exactly nine balls, so pixels whose color count is
   not a multiple of nine are deleted from the pixel grid (bottom-most,
   edge-most first).
2. **Scan** - :func:`picture_scan.scan_picture` reads the picture in the order
   the runtime eats it (top row down, right to left, holes skipped) and reports
   the cheapest conveyor any play could get away with. That number is a lower
   bound, so a picture over the belt is refused here with an explanation rather
   than after a long search that ends in "no". The colour count is also what the
   tier is read off, in two steps rather than one: :func:`rate_picture` says what
   the artwork *is* on the designer's three-wide scale (dễ, vừa, khó) and then
   which of the four build tiers to aim at, which is what ``auto_difficulty``
   hands the run. That tier is a **target**, not a description of what comes out -
   see stage 12b.
3. **Repair** - :func:`picture_repair.repair_picture`, and only for a picture the
   belt cannot hold: its short runs are merged into the colour beside them and
   paid back against their own kind, so every colour keeps its pixel count and
   the box multiset does not move. What changes is the order the picture asks for
   colours in, which is the thing that jams a level in the first place.
4. **Walkthrough** - the pixel histogram fully determines the box multiset, so
   only the pick order is open; :func:`pixel_gameplay.solve_order` searches for
   an order that wins on the belt.
5. **Base grid** - :func:`build_base_grid`: the boxes laid out with *no mechanic
   on them at all*, whatever does not fit stored in tunnels that hand each box
   over exactly when the picture asks for it, and the whole thing replayed and
   proven to win. This is the floor. Every later stage changes a grid that
   already had a winning line, and when none of those changes turns out to be
   playable, this is what ships.
6. **Layout** - the boxes fill the smallest lattice of 3x3 slots that holds them
   all, no larger than the configured slot limit (8x8 slots = 24x24 cells = 576
   balls). Walkthrough order maps onto the slots front row first, scrambled by
   difficulty. A picture too big for the whole lattice overflows into tunnels,
   and ``tunnel_mode="mechanic"`` asks for tunnels even when everything fits.
   Any slot the boxes do not fill is a **wall**: it blocks the route to the
   boxes around it, so Hard and SuperHard reserve a couple on purpose to pinch a
   box down to a single way in.
7. **Queue** - each tunnel gets a contiguous block of the walkthrough, and the
   block is buried by difficulty: ``dig_window == 1`` releases every box exactly
   at the step it is needed, a wider window reverses that many boxes so the
   wanted color sits at the *back* of the window and the player has to keep
   pulling to reach it. The window is only as wide as the belt survives. Each
   tunnel's ``direction`` is the side it hands its queue out on, so it is aimed
   at a neighbouring slot that really holds a box - never at a wall, another
   tunnel or off the edge of the lattice, all of which would seal the mouth.
8. **Hide** - a difficulty-driven share of the boxes gets the ``Hidden`` effect,
   weighted towards the back rows and never on the front row, so the player can
   always see what is immediately available but not what is coming.
9. **Link** - opt-in ``LinkedContainer`` obstacles tie pairs of neighbouring boxes
   together: tapping one sends both down, so the pick costs two tray slots at
   once. ``linked_mode="sync"`` pairs boxes the board wants within a step or two
   of each other, so the second half drains straight away and the link is a
   freebie; ``"stall"`` deliberately pairs a wanted box with one needed much
   later, so the partner squats on the belt and the conveyor runs full.
   The easy tiers additionally demand the pair clear *clean* - after the tap
   the conveyor is empty again - so an easy link is a freebie by construction
   rather than by luck.
10. **Lock** - opt-in ``ArrowLock`` effects shut a box until a box in the arrow's
   direction has been opened. The arrow only ever points at a real neighbouring
   box that the walkthrough opens *earlier*, never at a wall, a tunnel or off the
   grid, so the lock always has a key and the certified order stays legal.
   ``arrow_reach`` picks the form: the easy tiers point at the box opened
   immediately before, so the arrows read as a route across the grid, while
   Hard and SuperHard reach for the earliest key the order allows.
11. **Slab** - ``LargeBlock`` rectangles over solid blocks of the lattice, each
   opening when the picture has lost a given number of pixels. A slab lifts in
   one piece, so its number is bounded by the *earliest* box under it, which
   makes the regions the play order visits last the ones worth covering. While it
   is shut a slab is treated as a wall, so one that strands a box or a tunnel
   mouth is not laid at all. It runs before Freeze because it is much the more
   constrained of the two: a grid has only a handful of late-wanted rectangles,
   and a Frozen box fits almost anywhere.
12b. **Sum** - :func:`score_layer` reads the difficulty the finished level
   actually adds up to: the boxes buried out of sight *and* every obstacle laid
   on top, weighted into one number on the same 0-3 line the tiers live on. This
   exists because nothing else ever asked it. The tier decides which mechanics,
   relief decides how hard each one bites, and both of those are per-mechanic
   decisions - so a Hard picture whose belt refused the hard forms shipped with a
   Hard label and an Easy level underneath it, and no reading anywhere said so.
   When the sum comes out under the target, :func:`climb_obstacles` takes one
   mechanic at a time back to its tier's own setting - cheapest on the conveyor
   first - rebuilding and re-scoring each time, and keeps a rung only if the
   result is playable *and* the total went up. So a mechanic the picture cannot
   pay for is paid for by one it can, and a level that still cannot reach its
   tier ships saying how far short it came rather than wearing the label anyway.

12. **Freeze** - a difficulty-driven share of the surface boxes gets the
   ``Frozen`` effect on the same counter, each one's ``frozenCount`` written at
   most a box below the pixel count the play order has cleared when it reaches
   that box. A lock only ever goes on a colour that still has another box to
   serve the frontier while it is shut: freezing a colour's last box stops the
   picture, and a stopped picture never advances the very counter that would
   open it.
13. **Certify** - the level is replayed with
   :func:`pixel_gameplay.simulate_order`, both in walkthrough order and in the
   order the tunnels, links and locks actually force, its histograms are checked
   against the pixel grid, :class:`level_validator.LevelValidator` is asked
   whether the file it produced is legal, and
   :func:`pixel_gameplay.measure_difficulty` scores it. Three separate questions
   come out of here and a level can fail them one at a time:
   :attr:`AutoGenResult.winnable` (can it be cleared on its own belt),
   :attr:`AutoGenResult.valid` (does the file load) and
   :attr:`AutoGenResult.difficulty_matched` (is it the difficulty the picture
   asked for). Only the last one is about the design rather than about
   correctness, which is why it is a warning and not an error.

Stages 6-12 are one unit and can run more than once. A finished mechanic layer is
read back rather than trusted, on two separate questions: whether the conveyor
paid for what the tier asked (:attr:`ObstacleLayer.cut`, which steps the *form*
down a tier - see :func:`relieve_obstacles`) and whether the layout is playable at all
(:attr:`ObstacleLayer.faults`, which disqualifies it). Faults are the ones no
replay can catch: the gameplay model taps a queue by index and walks no route
across the grid, so a wall that seals a box in and a tunnel whose mouth faces no
box both replay as wins and are dead in the runtime. A lock that opens after the
play order wants the box behind it is the third of them, and the worst: it wins
in the model and deadlocks in the runtime with no way back. They are read off the
finished layout instead, and a layer that has one never ships.

One case is outside both of those readings, and :data:`BURIAL_GROUPS` is the
answer to it: the picture does not win on the belt the level ships with at all.
The obstacles are then certified against the belt the picture *needs*, so the
belt refuses nothing and neither reading fires - while Hidden, which never costs
a ball, is not something a belt check could cut in the first place. So the
*burial* alone is floored at Easy - laid in solution order, in plain sight,
handed over when asked for - and every obstacle on top keeps its tier's form and
is still climbed, so the level is not stripped. The tier, the theme and the
mechanics the level carries are untouched, and raising ``piece`` to the number in
the warning hands the tier's own burial straight back.
"""

import random
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace

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
    FrozenCellEffectData,
    HiddenCellEffectData,
    LargeBlockObstacleData,
    LinkedContainerObstacleData,
    PixelGridData,
    PixelLevelData,
    TunnelCellData,
)
from pixel_level_tool.services.level_validator import LevelValidator, ValidationMessage
from pixel_level_tool.services.picture_repair import (
    RepairReport,
    belt_summary,
    drop_scattered_colors,
    merge_summary,
    repair_picture,
)
from pixel_level_tool.services.picture_scan import (
    DEFAULT_BELT_SLOTS,
    EASY_MAX_COLORS,
    FRAGMENTED,
    MEDIUM_MAX_COLORS,
    BeltJam,
    PictureScan,
    difficulty_for_colors,
    scan_picture,
)
from pixel_level_tool.services.pixel_gameplay import (
    BoardState,
    lazy_order,
    BoxSpec,
    DifficultyMetrics,
    GameRules,
    GameplayError,
    Solution,
    TrayBox,
    TunnelRelease,
    belt_peak,
    belt_used,
    box_multiset,
    can_tap,
    drain,
    measure_difficulty,
    minimum_belt,
    resolve_link_groups,
    resolve_pick_sequence,
    simulate_groups,
    simulate_order,
    solve_order,
    tap_progress,
)


# A Square_3x3 box covers a 3x3 block of grid cells and holds nine balls, so the
# box grid is a lattice of 3-cell slots: `gridCols = 3 * slot columns`.
SLOT = 3
BALLS_PER_BOX = 9
MAX_BOX_SLOTS = 8
# What the hand-made levels ship as `piece`: the conveyor holds this many
# boxes, so the belt is DEFAULT_PIECE * BALLS_PER_BOX balls wide.
DEFAULT_PIECE = 5
ACTIVE_POLICIES = ("none", "row0", "all")
SCRAMBLE_MODES = ("ordered", "local", "global")
TUNNEL_MODES = ("auto", "overflow", "mechanic")
# Where the tunnels are parked. "back" is the row furthest from the player, which
# is where the hand-made levels put them; "front" is the opposite edge, the row
# the player eats first; "random" is anywhere the lattice still stays walkable.
TUNNEL_PLACEMENTS = ("auto", "back", "front", "random")
LINKED_MODES = ("auto", "sync", "stall")

# How far the correct next box may sit from the front of the grid, in boxes,
# when the layout is only locally scrambled.
LOCAL_SCRAMBLE_WINDOW = 4

# A tunnel is a queue with no visible depth limit, but a very deep one just hides
# most of the level, so overflow spreads over more tunnels instead.
MAX_TUNNEL_DEPTH = 16

# A tunnel eats a surface slot for good - an emptied one stays on the grid as a
# wall - so the automatic ceiling is priced like the other structural knobs: at
# most one tunnel per this many boxes, and never more than this share of the
# lattice. Neither bound can veto a tunnel an overflowing picture cannot be built
# without; they only bound the tunnels the tier asks for of its own accord.
TUNNEL_BOX_BUDGET = 8
TUNNEL_LATTICE_SHARE = 3
# Spreading an overflow the other way, a grid whose tunnels outnumber its boxes
# is not a grid any more, so the spread stops at half the lattice. Only the queue
# depth limit itself can push past this, because past it the level does not exist.
TUNNEL_SPREAD_SHARE = 2

# The grid the difficulty profiles are written for: the hand-made levels lay 30
# boxes out on a 5x6 lattice. A picture twice that size carries twice the tier's
# tunnel dose, which is what keeps a big picture from being run through the same
# one or two queues a small one gets.
REFERENCE_BOXES = 30

# A wall costs a whole slot and narrows the way in to its neighbours, so it is
# the most expensive difficulty knob here: at most one wall per this many boxes.
WALL_BOX_BUDGET = 4

# What a wall is *for*, and it takes two of them: a pinch is a pair flanking one
# box, so that box keeps a single way in - see `_wall_groups`. A tier's wall
# count is therefore a pinch count in disguise, which is what makes the pinches a
# level really got comparable with the number the tier asked for.
WALLS_PER_PINCH = 2

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

# How far an ArrowLock reaches for its key, per tier. "near" points at the box
# opened just before it, so the lock is already open by the time the player gets
# there and the arrows read as a route through the grid rather than as a puzzle;
# "far" points at the earliest legal key, so the box stays shut as long as it can.
ARROW_REACH = ("near", "far")

# At the easy tiers a linked pair has to clear *clean*: after the tap the belt is
# back to empty, so the player is never left holding a partner they cannot spend.
# This is the difference between a link that reads as a freebie and one that
# quietly eats a third of the conveyor for the next twenty picks.
CLEAN_LINK_RESIDUE = 0

# The five mechanics Auto Gen Box can spend. Every one of them is read off the
# level the same way: the tier says how strong a dose it wants, the picture says
# how much of that dose it can actually pay for, and the smaller number wins.
OBSTACLE_KINDS = ("hidden", "wall", "tunnel", "arrow", "linked")

# The two *lock* mechanics, budgeted apart from the five above.
#
# A lock names no box and no partner - it names a number, and the runtime opens
# it once the picture has lost that many pixels. Which makes it the only kind of
# obstacle this generator can derive rather than impose: the count is read out
# of the certified play order in stage 11, so by construction it is already open
# when the winning line wants the box under it. A lock therefore spends no
# conveyor and takes no grid slot away from anything, and charging it against
# OBSTACLE_BUDGET would only let it push a belt-spending mechanic off a level
# that could comfortably afford both.
LOCK_KINDS = ("frozen", "block")
ALL_OBSTACLE_KINDS = OBSTACLE_KINDS + LOCK_KINDS

OBSTACLE_KIND_LABELS: dict[str, str] = {
    "hidden": "Hidden",
    "wall": "Wall",
    "tunnel": "Tunnel",
    "arrow": "ArrowLock",
    "linked": "LinkedContainer",
    "frozen": "Frozen",
    "block": "LargeBlock",
}

# How many *kinds* of mechanic a tier may run at once, as (fewest, most).
#
# This is a separate limit from the dose of each one, and it is the one a player
# feels first: a level carrying two mechanics reads as a level with a rule, and
# one carrying five reads as a level with a syllabus. So an easy level spends one
# or two, a medium one three or four, and a hard one four or five.
#
# It is a *range*, and `obstacle_kind_dose` rolls inside it per level rather than
# filling it to the ceiling - two seeds at the same tier should not both produce
# the same syllabus. The ceiling is clamped to the number of mechanics that exist,
# so the six here reads as five.
#
# The floor is a check rather than a quota: a picture too small to pay for the
# tier's minimum is generated anyway and the report says which mechanics it
# could not afford.
OBSTACLE_BUDGET: dict[int, tuple[int, int]] = {
    int(LevelDifficulty.Easy): (1, 2),
    int(LevelDifficulty.Medium): (3, 4),
    int(LevelDifficulty.Hard): (4, 6),
    int(LevelDifficulty.SuperHard): (4, 6),
}

# The same idea for the locks, on their own budget. Two mechanics, so the ranges
# are small: an easy level may carry one lock or none, and only the hardest tier
# is guaranteed both. Rolled per level exactly like OBSTACLE_BUDGET.
LOCK_BUDGET: dict[int, tuple[int, int]] = {
    int(LevelDifficulty.Easy): (0, 1),
    int(LevelDifficulty.Medium): (1, 2),
    int(LevelDifficulty.Hard): (1, 2),
    int(LevelDifficulty.SuperHard): (2, 2),
}

# How a lock's number is written, once the tier's share and the safety ceiling
# have both had their say.
#
# `LOCK_MARGIN` is the gap kept between a lock opening and the winning line
# wanting the box behind it, in balls. One whole box: the line taps in whole
# boxes, so anything finer is not a margin the runtime can express.
#
# `LOCK_ROUNDING` writes the final number as an odd one - hand-made levels use
# flat 20/30/40/100/150, and an odd count reads as measured rather than typed.
# Always rounded *down*, because the ceiling above it is a safety limit and
# rounding up would step over it.
LOCK_MARGIN = BALLS_PER_BOX
LOCK_ROUNDINGS = ("odd", "five", "ten", "none")

# A slab needs a solid rectangle of boxes to sit on, and locking a quarter of the
# grid behind one number is already a lot, so a level buys one slab per this many
# boxes *per covered slot*: 44 boxes and a 2x2 slab is two slabs, which is what
# the hand-made levels carry.
BLOCK_BOX_BUDGET = 4

# How big a slab gets, and how late it opens: both come off the room the *picture*
# leaves rather than off the tier alone.
#
# `spare_boxes` is whole boxes of conveyor still free at the picture's tightest
# moment, and it is the level's own statement of how much of itself it can afford
# to have shut away. A picture already filling its belt is being asked for enough
# without four extra boxes going dark for half the level, so it gets the small
# slab and an earlier number; a picture with room to spare gets the wide one and
# the tier's number in full.
#
# The slab spends no conveyor itself - it cannot, it is derived from the winning
# line - so this is not a price being paid. It is the one measurement the level
# makes of itself that says how much pressure it is already under.
BLOCK_WIDE_ROOM = 3
BLOCK_WIDE_SPAN = (3, 3)
BLOCK_ROOM_FULL = 3
BLOCK_TIGHT_SHARE = 0.6
# Frozen is per box, so it needs far less room - but a grid too small to have a
# spare box of any colour cannot carry a lock safely at all.
FROZEN_BOX_BUDGET = 4

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

TUNNEL_PLACEMENT_LABELS: dict[str, str] = {
    "back": "hàng sau cùng, cột ngoài rìa trước",
    "front": "hàng trước (slot_y 0), nơi người chơi ăn tới đầu tiên",
    "random": "ngẫu nhiên trong lưới, có thể rơi vào giữa",
}


class AutoGenError(ValueError):
    pass


# --------------------------------------------------------------------------- #
# Difficulty profiles
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DifficultyProfile:
    """How a difficulty label turns into concrete level knobs.

    The conveyor is a fixed thirty balls at every difficulty, so the bite has to
    come from the obstacles rather than from the belt: a hidden box shows no
    color, so the player cannot tell whether tapping it wastes conveyor room,
    and ``scramble`` decides how far from the front row the next needed box may
    sit, i.e. how much searching is required.

    Each obstacle also has an easy *form* and a hard one, which is what keeps an
    easy level easy even when it carries the same mechanic: ``arrow_reach`` says
    whether an ArrowLock points at the box opened just before it or at the
    earliest key it can legally reach, and ``clean_links`` demands that a linked
    pair leaves the conveyor empty instead of parking a partner on it.
    """

    hidden_ratio: float
    scramble: str
    label: str
    # Tunnels, for `tunnel_mode="mechanic"`: how many to plant and how deep.
    tunnels: int = 1
    tunnel_depth: int = 3
    # Where they sit. A tunnel is a permanent hole, so the further it moves from
    # the back edge the more of the grid it forces the player to route around:
    # the back row costs almost nothing, the front row blocks the way in at the
    # very start, and a free slot anywhere can land mid-grid.
    tunnel_placement: str = "back"
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
    # Frozen: how many surface boxes carry a lock, and *where in the level* the
    # locks open, as a share of the whole picture. The two are separate dials on
    # purpose - the share says when the pressure happens, the count says how much
    # of it there is - and `frozen_at` is a band rather than a number so four
    # locks on one level do not all open on the same pixel.
    frozen_ratio: float = 0.0
    frozen_at: tuple[float, float] = (0.0, 0.0)
    # LargeBlock: how many slabs, how big one is in box slots, and the share of
    # the picture each one opens at. One entry per slab, so a tier staggers its
    # slabs down the level instead of lifting them all at once.
    blocks: int = 0
    block_span: tuple[int, int] = (2, 2)
    block_at: tuple[float, ...] = ()
    # The third lock dial, and the one that decides how much a lock actually
    # bites: how far past its opening moment the winning line's own turn for that
    # box may fall, as a share of the picture. A box the line wants right after
    # the lock lifts is a lock the player feels; one it does not want for another
    # half a level is decoration. Small window = tight locks.
    lock_window: float = 1.0
    # Which locks this tier reaches for, best first, cut to LOCK_BUDGET.
    lock_kinds: tuple[str, ...] = LOCK_KINDS
    # The easy/hard *form* of each mechanic, independent of how many are spent.
    arrow_reach: str = "near"
    clean_links: bool = True
    # Which mechanics this tier reaches for, best first. Only the first
    # OBSTACLE_BUDGET[tier] of them that the picture can pay for are spent, so
    # the order is what decides who gets dropped when the budget runs out.
    kinds: tuple[str, ...] = OBSTACLE_KINDS
    # Draw the mix at random instead of taking the order above from the top.
    #
    # The order is a priority list, and a priority list plus a small dose means
    # the same two or three mechanics every single time: every Easy level was
    # Hidden and an arrow, every Medium one Hidden, an arrow and a pair. That is
    # right for the hard tiers, where the order *is* the tier - a Hard level
    # without its wall and its tunnel is not Hard - but at the gentle end any of
    # the seven reads as gentle once it is dosed down, so which ones a level gets
    # should vary. On for Easy and Medium, off above them.
    shuffle_kinds: bool = False

    def budget(self, difficulty: int) -> tuple[int, int]:
        return OBSTACLE_BUDGET[difficulty]


DIFFICULTY_PROFILES: dict[int, DifficultyProfile] = {
    # The two easy tiers reach for the three mechanics that have a genuinely
    # gentle form - a little Hidden, arrows that read as a route, links that
    # clear clean - and leave the two structural ones, which have no gentle
    # form, for last: a wall never opens and an emptied tunnel stays on the
    # grid as one, so neither can be dosed down to "mild".
    int(LevelDifficulty.Easy): DifficultyProfile(
        0.08, "ordered", "Easy", tunnels=1, tunnel_depth=3, dig_window=1, walls=0,
        arrow_ratio=0.08, linked_pairs=2, linked_mode="sync",
        frozen_ratio=0.05, frozen_at=(0.03, 0.06),
        blocks=0, block_at=(), lock_window=0.40,
        lock_kinds=("frozen", "block"),
        arrow_reach="near", clean_links=True,
        kinds=("hidden", "arrow", "linked", "tunnel", "wall"),
        shuffle_kinds=True,
    ),
    int(LevelDifficulty.Medium): DifficultyProfile(
        0.15, "ordered", "Medium", tunnels=1, tunnel_depth=4, dig_window=2, walls=0,
        arrow_ratio=0.15, linked_pairs=3, linked_mode="sync",
        frozen_ratio=0.10, frozen_at=(0.05, 0.10),
        blocks=2, block_span=(2, 2), block_at=(0.25, 0.38), lock_window=0.30,
        lock_kinds=("frozen", "block"),
        arrow_reach="near", clean_links=True,
        kinds=("hidden", "arrow", "linked", "tunnel", "wall"),
        shuffle_kinds=True,
    ),
    # The hard tiers put the structural pair first, because that is the bite the
    # tier is being asked for: Hidden and arrows shrink what the player knows,
    # but a wall and a tunnel shrink what the grid *is*.
    int(LevelDifficulty.Hard): DifficultyProfile(
        0.40, "local", "Hard", tunnels=2, tunnel_depth=4, dig_window=3, walls=2,
        tunnel_placement="front",
        arrow_ratio=0.25, linked_pairs=3, linked_mode="stall",
        frozen_ratio=0.15, frozen_at=(0.10, 0.20),
        blocks=2, block_span=(2, 2), block_at=(0.30, 0.45), lock_window=0.15,
        lock_kinds=("block", "frozen"),
        arrow_reach="far", clean_links=False,
        kinds=("hidden", "wall", "tunnel", "arrow", "linked"),
    ),
    int(LevelDifficulty.SuperHard): DifficultyProfile(
        0.60, "global", "SuperHard", tunnels=2, tunnel_depth=5, dig_window=4, walls=4,
        tunnel_placement="random",
        arrow_ratio=0.33, linked_pairs=4, linked_mode="stall",
        frozen_ratio=0.20, frozen_at=(0.15, 0.30),
        blocks=3, block_span=(2, 2), block_at=(0.35, 0.50, 0.62), lock_window=0.06,
        lock_kinds=("block", "frozen"),
        arrow_reach="far", clean_links=False,
        kinds=("hidden", "wall", "tunnel", "arrow", "linked"),
    ),
}

# Mirrors MainWindow._DIFFICULTY_FORCED_THEME so a generated level lands on the
# theme the rest of the tool would pick for that difficulty.
DIFFICULTY_FORCED_THEME: dict[int, int] = {
    int(LevelDifficulty.Hard): int(ThemeId.Hard),
    int(LevelDifficulty.SuperHard): int(ThemeId.SuperHard),
}


# --------------------------------------------------------------------------- #
# Stage 2b - the difficulty read off the picture
# --------------------------------------------------------------------------- #
# The designer's own scale for a piece of artwork: three words wide, because that
# is what somebody says out loud about a picture. Deliberately shorter than the
# four build tiers - "khó" is one word and covers both Hard and SuperHard.
PICTURE_BANDS = ("dễ", "vừa", "khó")
BAND_EASY, BAND_MEDIUM, BAND_HARD = range(3)


def band_for_colors(colors: int) -> int:
    """Where a picture sits on the designer's three-wide scale.

    The same two thresholds :func:`picture_scan.difficulty_for_colors` uses, read
    one scale shorter: everything past ``MEDIUM_MAX_COLORS`` is simply "khó",
    whether it ends up asking for Hard or for SuperHard.
    """
    if colors <= EASY_MAX_COLORS:
        return BAND_EASY
    if colors <= MEDIUM_MAX_COLORS:
        return BAND_MEDIUM
    return BAND_HARD


@dataclass(frozen=True)
class PictureRating:
    """One picture, read twice: what it *is*, and what tier to build for it.

    These used to be one line - a colour count mapped straight onto a tier - and
    two different questions were riding on it:

    1. **What is this picture?** A three-wide reading of the artwork itself, off
       the thing a designer can see at a glance: how many colours it is painted
       in. That is :attr:`band`, and it is a statement, not a decision.
    2. **Which level should be built for it?** Four wide, because the fourth tier
       exists for pictures past what the designer's scale was drawn for. That is
       :attr:`tier`, and it is the *target* the obstacle layer is then built up
       to - see :class:`DifficultyClimb`.

    They cannot be the same reading, because they are not the same width: a
    twelve-colour picture and a twenty-colour one are both "khó" to look at, and
    only the second one asks for SuperHard.

    What :attr:`tier` is **not** is a description of the level that comes out.
    The tier is what the picture asked for; whether the obstacles actually added
    up to it is measured afterwards, by :func:`score_layer`.
    """

    colors: int = 0
    fragmentation: float = 0.0
    painted: int = 0
    # The three-wide reading of the artwork, before the noise bump.
    band: int = BAND_EASY
    # The four-wide target, after it.
    tier: int = int(LevelDifficulty.Easy)
    # The tier the colour count alone asked for, kept so the bump stays visible.
    color_tier: int = int(LevelDifficulty.Easy)
    fragmented: bool = False

    @property
    def band_label(self) -> str:
        return PICTURE_BANDS[self.band]

    @property
    def tier_label(self) -> str:
        return DIFFICULTY_PROFILES[self.tier].label

    @property
    def bumped(self) -> bool:
        """Did fragmentation move the target above what the colours asked for?"""
        return self.tier > self.color_tier

    @property
    def reason(self) -> str:
        """Why this picture reads as it does, in the terms it was read in."""
        base = f"{self.colors} màu → tranh {self.band_label}"
        if self.bumped:
            return (
                f"{base}, độ vụn {self.fragmentation:.0%} ≥ {FRAGMENTED:.0%} nên nâng"
                f" một nấc → {self.tier_label}"
            )
        return f"{base} → {self.tier_label}, độ vụn {self.fragmentation:.0%} chưa tới ngưỡng nâng nấc"


def rate_picture(scan: PictureScan) -> PictureRating:
    """Read the band first, then choose the tier from it. In that order.

    A picture painted as noise plays harder than its colour count suggests, so a
    heavily fragmented one is pushed up a tier. It is never pushed *down*: a
    twelve-colour picture in neat bands is still twelve colours to read, which is
    the thing the count was measuring in the first place.
    """
    colors = scan.colors
    color_tier = difficulty_for_colors(colors)
    tier = color_tier
    fragmented = scan.fragmentation >= FRAGMENTED
    if fragmented and tier < int(LevelDifficulty.SuperHard):
        tier += 1
    return PictureRating(
        colors=colors,
        fragmentation=scan.fragmentation,
        painted=scan.painted,
        band=band_for_colors(colors),
        tier=tier,
        color_tier=color_tier,
        fragmented=fragmented,
    )


@dataclass
class AutoGenOptions:
    # -1 asks the scanner to read the tier off the picture instead of trusting a
    # number the designer may have set for a different picture entirely.
    difficulty: int = int(LevelDifficulty.Easy)
    auto_difficulty: bool = False
    max_slot_cols: int = MAX_BOX_SLOTS
    max_slot_rows: int = MAX_BOX_SLOTS
    # How much Hidden to spend, either as a share of the surface boxes or as a
    # plain count. The count is what the designer asked for, so it wins; the share
    # is the Auto answer behind it, and the difficulty's share behind that. The
    # same pattern holds for the tunnel and arrow counts below.
    hidden_ratio: float | None = None
    hidden_boxes: int | None = None
    # The conveyor, in balls. 0 keeps the runtime's thirty; it is only a knob so
    # a designer can ask "would this picture work on a bigger belt?".
    belt_slots: int = 0
    active_policy: str = "none"
    allow_tunnels: bool = True
    # The tunnel ceiling. 0 reads it off the picture - the boxes it carries and
    # the lattice they have to fit in - instead of holding every level to the same
    # fixed four, which quietly capped every large picture at the same number.
    max_tunnels: int = 0
    tunnel_count: int | None = None
    tunnel_mode: str = "auto"
    tunnel_placement: str = "auto"
    tunnel_depth: int = 0
    dig_window: int | None = None
    walls: int | None = None
    # None hands the decision to the tier, the way Hidden and Wall have always
    # worked; True asks for the mechanic even when the tier would not have picked
    # it, and False says this level never has it.
    use_arrow_lock: bool | None = None
    arrow_ratio: float | None = None
    arrow_boxes: int | None = None
    use_linked_container: bool | None = None
    linked_pairs: int | None = None
    linked_mode: str = "auto"
    # The two locks, on the same None/count pattern as the mechanics above.
    frozen_boxes: int | None = None
    blocks: int | None = None
    # Draw the gentle tiers' obstacle mix at random instead of taking the tier's
    # priority order from the top - see `DifficultyProfile.shuffle_kinds`, which
    # is what decides whether a tier has anything to draw in the first place.
    # Off pins every level to its tier's canonical mix.
    shuffle_obstacles: bool = True
    # Balls kept between a lock opening and the winning line wanting the box
    # behind it. One box by default. Raise it to a whole belt if the runtime
    # turns out to count balls *poured onto the conveyor* rather than balls
    # cleared off the picture: the two can differ by a full belt.
    lock_margin: int = LOCK_MARGIN
    # How the final number is written: "odd" (default), "five", "ten", "none".
    lock_rounding: str = "odd"
    # Measure what the finished level adds up to and, when it comes out gentler
    # than the tier the picture asked for, harden the mechanics it can still
    # afford until it gets there - see `DifficultyClimb`. Off ships whatever the
    # relief ladder left, which is what the tool used to do: a Hard picture
    # relieved two tiers went out wearing a Hard label and playing like an Easy
    # one, and nothing said so.
    difficulty_climb: bool = True
    # Let a picture that already fills the conveyor pull the *form* of the
    # obstacles down a tier or two - the mechanics stay, they just stop being
    # dosed as if the belt were empty. Off hands every level its tier's own forms
    # whatever the picture costs, which is what the tool used to do.
    obstacle_relief: bool = True
    # The one case `obstacle_relief` above cannot see: a picture that does not win
    # on the level's own belt at all. The obstacles are certified against the belt
    # the picture *needs*, so the belt refuses nothing and the burial ships at the
    # tier's own form on a level nobody can finish. On floors the *burial* at
    # Easy's forms - and only the burial, so the obstacles laid on top stay and
    # keep being climbed - which makes the level readable the moment `piece` is
    # raised to the number in the warning. See `BURIAL_GROUPS`.
    jam_relief: bool = True
    # Recolour the picture until it plays on the belt the level ships with: short
    # runs are merged into the colour beside them and paid back beside their own
    # kind, so every colour keeps its pixel count and the box multiset does not
    # move. Only ever engages on a picture that cannot be won as painted.
    repair_picture: bool = True
    # The last resort for a picture too shredded for `repair_picture` to save:
    # drop the most scattered colour outright and give its pixels to the colours
    # already beside them, one colour at a time, until the picture plays. Off by
    # default because it is the only repair that changes what the artwork is made
    # of - the palette comes back shorter. Engages only when the safe pass has
    # already run and the picture still cannot be won.
    drop_scattered_colors: bool = False
    # Notches to step the difficulty *down* from what the picture reads as, and
    # the same for the obstacle forms. 0 is the scenario the picture asked for;
    # 1 turns a Hard picture into a Medium level, 2 into an Easy one. This is a
    # deliberate choice, unlike `obstacle_relief`, which only reacts to the belt.
    ease_difficulty: int = 0
    ease_obstacles: int = 0
    # Re-roll the whole run this many times on different seeds and keep the best
    # one: winnable first, then the most mechanics, then the most conveyor left
    # over. 1 is a single run on the seed given.
    shuffle_attempts: int = 1
    apply_theme: bool = True
    seed: int | None = None


# --------------------------------------------------------------------------- #
# Which mechanics this level gets
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ObstaclePlan:
    """The mechanics one run spends, and why it left the rest alone.

    Every mechanic used to be gated differently - Hidden and Wall followed the
    tier, ArrowLock and LinkedContainer waited for a tick box, tunnels waited for
    the picture to overflow - so a level's obstacle mix depended on which knobs
    the designer happened to remember.  Now all five are read off the level the
    same way and the answer is this plan: the tier's own order, cut to its
    :data:`OBSTACLE_BUDGET`, minus whatever the picture cannot pay for.
    """

    difficulty: int = int(LevelDifficulty.Easy)
    kinds: tuple[str, ...] = ()
    budget: tuple[int, int] = (0, 0)
    # How many kinds this particular level was asked to run, rolled inside the
    # budget rather than pinned to its ceiling - two Hard levels off two seeds
    # should not both carry the same five mechanics.
    dose: int = 0
    # The same pair for the locks, which roll on their own budget.
    lock_budget: tuple[int, int] = (0, 0)
    lock_dose: int = 0
    # Kinds booked before the budget was opened: a count the designer typed, or a
    # tunnel the picture does not fit without.
    forced: tuple[str, ...] = ()
    # (kind, why) for every mechanic the tier looked at and did not spend.
    skipped: tuple[tuple[str, str], ...] = ()
    # The picture has more boxes than the lattice holds, so tunnels are not the
    # tier's choice here - the level does not exist without them.
    overflow: bool = False

    def has(self, kind: str) -> bool:
        return kind in self.kinds

    @property
    def count(self) -> int:
        return len(self.kinds)

    @property
    def mechanics(self) -> tuple[str, ...]:
        """The kinds charged against OBSTACLE_BUDGET, which is not all of them.

        The locks roll on LOCK_BUDGET instead, so every reading of "is this level
        inside its budget" has to be taken over this rather than over `kinds`.
        """
        return tuple(kind for kind in self.kinds if kind not in LOCK_KINDS)

    @property
    def over_budget(self) -> bool:
        """More kinds than the tier allows, because the designer asked for them."""
        return len(self.mechanics) > self.budget[1] or len(self.locks) > self.lock_budget[1]

    @property
    def under_budget(self) -> bool:
        """Fewer kinds than the tier wants, because the picture cannot pay."""
        return len(self.mechanics) < self.budget[0] or len(self.locks) < self.lock_budget[0]

    @property
    def under_dose(self) -> bool:
        """Fewer kinds than this level rolled, because the picture cannot pay."""
        return len(self.mechanics) < self.dose or len(self.locks) < self.lock_dose

    @property
    def locks(self) -> tuple[str, ...]:
        return tuple(kind for kind in self.kinds if kind in LOCK_KINDS)

    @property
    def labels(self) -> str:
        return ", ".join(OBSTACLE_KIND_LABELS[kind] for kind in self.kinds) or "không có"


def _typed(*values: float | None) -> bool | None:
    """The first number the designer actually typed, read as on/off."""
    for value in values:
        if value is not None:
            return value > 0
    return None


def designer_choice(kind: str, options: AutoGenOptions) -> bool | None:
    """What the designer said about one mechanic: on, off, or no opinion.

    A typed number is an opinion.  A count of zero switches the mechanic off for
    this level; any other count switches it on even when the tier's budget would
    not have reached that far, because a number somebody typed outranks a table.
    Everything still on Auto is the tier's to decide.
    """
    if kind == "hidden":
        return _typed(options.hidden_boxes, options.hidden_ratio)
    if kind == "wall":
        return _typed(options.walls)
    if kind == "tunnel":
        if not options.allow_tunnels:
            return False
        typed = _typed(options.tunnel_count)
        if typed is not None:
            return typed
        if options.tunnel_mode == "mechanic":
            return True
        if options.tunnel_mode == "overflow":
            return False
        return None
    if kind == "arrow":
        if options.use_arrow_lock is not None:
            return options.use_arrow_lock
        return _typed(options.arrow_boxes, options.arrow_ratio)
    if kind == "linked":
        if options.use_linked_container is not None:
            return options.use_linked_container
        return _typed(options.linked_pairs)
    if kind == "frozen":
        return _typed(options.frozen_boxes)
    if kind == "block":
        return _typed(options.blocks)
    raise AutoGenError(f"Unknown obstacle kind {kind!r}.")


def spare_boxes(scan: PictureScan) -> int:
    """Whole boxes the belt can still hold at the picture's tightest moment.

    This is the currency every belt-costing mechanic is priced in: burying a box
    in a tunnel and parking a stalled link partner both put a box on the conveyor
    that the picture is not asking for yet, and this is how many of those the
    level can carry before the tap that loses the game.
    """
    return max(0, scan.belt_headroom) // BALLS_PER_BOX


def resolve_linked_mode(options: AutoGenOptions, profile: DifficultyProfile) -> str:
    """Which link form this run uses, with ``auto`` handed to the difficulty."""
    return profile.linked_mode if options.linked_mode == "auto" else options.linked_mode


def afford_reason(
    kind: str,
    *,
    options: AutoGenOptions,
    profile: DifficultyProfile,
    scan: PictureScan,
    surface_boxes: int,
    capacity: int,
    box_count: int,
) -> str:
    """Why this picture cannot pay for one mechanic, or an empty string when it can."""
    if kind == "hidden":
        ratio = profile.hidden_ratio if options.hidden_ratio is None else options.hidden_ratio
        if options.hidden_boxes is None and round(ratio * surface_boxes) < 1:
            return f"{ratio:.0%} của {surface_boxes} box mặt ngoài làm tròn xuống 0"
        return ""
    if kind == "wall":
        if surface_boxes < WALL_BOX_BUDGET:
            return f"cần từ {WALL_BOX_BUDGET} box mặt ngoài trở lên, lưới chỉ có {surface_boxes}"
        if options.walls is None and profile.walls <= 0:
            return f"mức {profile.label} không dùng wall"
        return ""
    if kind == "tunnel":
        if not options.allow_tunnels:
            return "tunnel bị tắt cho level này"
        if capacity < 2 or box_count < 2:
            return "lưới không đủ slot cho cả box và tunnel"
        return ""
    if kind == "arrow":
        if surface_boxes < ARROW_BOX_BUDGET:
            return f"cần từ {ARROW_BOX_BUDGET} box mặt ngoài trở lên, lưới chỉ có {surface_boxes}"
        return ""
    if kind == "linked":
        if surface_boxes < LINK_BOX_BUDGET:
            return f"cần từ {LINK_BOX_BUDGET} box mặt ngoài trở lên, lưới chỉ có {surface_boxes}"
        return ""
    # The two locks are priced in boxes the winning line can spare, not in belt:
    # a lock only ever goes on a box whose colour has another box to serve the
    # frontier while it is shut, so a grid with no spares cannot carry one.
    if kind == "frozen":
        if surface_boxes < FROZEN_BOX_BUDGET:
            return f"cần từ {FROZEN_BOX_BUDGET} box mặt ngoài trở lên, lưới chỉ có {surface_boxes}"
        if options.frozen_boxes is None and round(profile.frozen_ratio * surface_boxes) < 1:
            return f"{profile.frozen_ratio:.0%} của {surface_boxes} box mặt ngoài làm tròn xuống 0"
        return ""
    if kind == "block":
        span = profile.block_span[0] * profile.block_span[1]
        need = BLOCK_BOX_BUDGET * span
        if surface_boxes < need:
            return f"một slab {profile.block_span[0]}x{profile.block_span[1]} cần từ {need} box mặt ngoài, lưới chỉ có {surface_boxes}"
        if options.blocks is None and profile.blocks <= 0:
            return f"mức {profile.label} không dùng LargeBlock"
        return ""
    raise AutoGenError(f"Unknown obstacle kind {kind!r}.")


def obstacle_kind_dose(budget: tuple[int, int], available: int, rng: random.Random) -> int:
    """How many *kinds* this particular level runs, rolled inside the tier's range.

    The budget is a range and it has to be used as one. Filling it to the ceiling
    instead - which is what happens if nothing rolls - hands every level of a tier
    the same syllabus: there are only five mechanics, so a Hard ceiling of six
    meant every Hard level carried all five, every time, and the range was
    decoration. Rolling it means two seeds give two different levels, which is
    what a range was for.

    Clamped to what actually exists: a tier asking for six of five kinds is asking
    for five, and the floor comes down with it rather than being unreachable.
    """
    high = max(0, min(budget[1], available))
    low = max(0, min(budget[0], high))
    return rng.randint(low, high)


def plan_obstacle_kinds(
    *,
    difficulty: int,
    profile: DifficultyProfile,
    options: AutoGenOptions,
    scan: PictureScan,
    surface_boxes: int,
    capacity: int,
    box_count: int,
    rng: random.Random,
) -> ObstaclePlan:
    """Pick this level's mechanics: the tier's order, cut to this level's dose.

    Three things get booked before the budget is opened, because none of them is
    the budget's to refuse: a count the designer typed, a mechanic they ticked on
    by hand, and a tunnel the picture does not fit in the lattice without.  Those
    can push a level past its ceiling, and the report says so rather than quietly
    dropping what was asked for.
    """
    budget = OBSTACLE_BUDGET[difficulty]
    dose = obstacle_kind_dose(budget, len(profile.kinds), rng)
    # The locks roll on their own budget, so a level that spends four mechanics
    # on the belt and the grid can still carry a lock - see LOCK_KINDS.
    lock_budget = LOCK_BUDGET[difficulty]
    lock_dose = obstacle_kind_dose(lock_budget, len(profile.lock_kinds), rng)
    # A picture bigger than the lattice needs a tunnel whatever the tier thinks,
    # and one tunnel slot always comes out of the lattice, hence `capacity - 1`.
    overflow = options.allow_tunnels and box_count > capacity - 1

    wants: dict[str, bool | None] = {}
    reasons: dict[str, str] = {}
    for kind in profile.kinds + profile.lock_kinds:
        want = designer_choice(kind, options)
        if kind == "tunnel" and overflow and want is not False:
            want = True
        wants[kind] = want
        reasons[kind] = (
            ""
            if want is False
            else afford_reason(
                kind,
                options=options,
                profile=profile,
                scan=scan,
                surface_boxes=surface_boxes,
                capacity=capacity,
                box_count=box_count,
            )
        )

    every = profile.kinds + profile.lock_kinds
    forced = tuple(kind for kind in every if wants[kind] is True and not reasons[kind])
    skipped: list[tuple[str, str]] = []

    def spend(order: tuple[str, ...], roll: int, span: tuple[int, int], noun: str):
        # At the gentle tiers the order is drawn rather than read from the top,
        # so two Easy levels off two seeds carry two different mechanics instead
        # of both carrying whatever sits first in the table.
        if profile.shuffle_kinds and options.shuffle_obstacles:
            drawn = list(order)
            rng.shuffle(drawn)
            order = tuple(drawn)
        picked = [kind for kind in order if kind in forced]
        for kind in order:
            if kind in picked:
                continue
            if wants[kind] is False:
                skipped.append((kind, "đã tắt cho level này"))
            elif reasons[kind]:
                skipped.append((kind, reasons[kind]))
            elif len(picked) >= roll:
                skipped.append(
                    (
                        kind,
                        f"level này rút {roll} {noun} trong khoảng {span[0]}-{span[1]} "
                        f"của mức {profile.label}",
                    )
                )
            else:
                picked.append(kind)
        return picked

    chosen = spend(profile.kinds, dose, budget, "loại obstacle")
    chosen += spend(profile.lock_kinds, lock_dose, lock_budget, "loại khoá")

    rank = {kind: index for index, kind in enumerate(every)}
    return ObstaclePlan(
        difficulty=difficulty,
        kinds=tuple(sorted(chosen, key=rank.__getitem__)),
        budget=budget,
        dose=dose,
        lock_budget=lock_budget,
        lock_dose=lock_dose,
        forced=forced,
        skipped=tuple(skipped),
        overflow=overflow,
    )


def resolve_tunnel_mode(options: AutoGenOptions, plan: ObstaclePlan) -> str:
    """Which tunnel mode this run used, with ``auto`` answered by the plan.

    ``auto`` is the default now: a tier that spends its budget on tunnels wants
    them as a mechanic - planted and filled to its own depth - and a tier that
    does not still gets the ones an overflowing picture forces on it.
    """
    if options.tunnel_mode != "auto":
        return options.tunnel_mode
    return "mechanic" if plan.has("tunnel") else "overflow"


# --------------------------------------------------------------------------- #
# In which form this level gets them
# --------------------------------------------------------------------------- #
# The two mechanics that are paid for in conveyor, and are therefore the two the
# belt can refuse: burying a queue `dig_window` deep pulls boxes out before the
# picture wants them, and a `stall` link drops a partner nothing below is asking
# for. Hidden, Wall and ArrowLock cost the player knowledge, a slot and an
# alternative - never a ball on the belt, so no belt check can ever cut them.
BELT_SPENDING_KINDS = ("tunnel", "linked")

# The half of a level's difficulty that is *burial* - what the player cannot see
# or cannot reach yet - as opposed to the obstacles laid on top of it. The split
# is :data:`DIFFICULTY_DIALS`' own, and the module docstring's: a picture is made
# hard mostly by what is hidden, and the rest by what is in the way.
#
# It is named here because of the line right above. Hidden never costs a ball, so
# no belt check anywhere is able to cut it, and on a picture that cannot be won
# at all that is the worst combination the tool can ship: the player is already
# going to run the conveyor dry, and the tier would additionally hide 60% of the
# surface and scatter the box they need next anywhere on the grid. Relief cannot
# see that case - it only reacts to what the belt *refuses*, and the belt refuses
# nothing here, because the obstacles are certified against `required_belt`
# rather than against the belt the level actually has.
#
# So on a jammed picture these three go to Easy's setting and nothing else does:
# the boxes are laid in solution order, in plain sight, handed over exactly when
# the picture asks for them. Every obstacle *on top* keeps its tier's form and
# the climb still buys more of them back (:func:`climb_obstacles`), so the level
# is not stripped - what it loses is only the part that made it unreadable.
BURIAL_GROUPS = ("hidden", "scramble", "tunnel")


def belt_room(required_belt: int, belt_slots: int) -> int:
    """Whole boxes of conveyor left over once the picture's own play is paid for.

    ``required_belt`` is the narrowest belt the picture can be won on at all, so
    everything above it is what the obstacles have to live in. Counted in whole
    boxes because that is the only unit the belt is ever spent in: a tap pours
    nine balls or nothing.
    """
    return max(0, belt_slots - required_belt) // BALLS_PER_BOX


def soften_profile(
    profile: DifficultyProfile, difficulty: int, form: int
) -> DifficultyProfile:
    """The tier's profile with every dose and form taken from a gentler tier.

    ``kinds`` and ``label`` are deliberately left alone: the level is still the
    tier the picture reads as, and it still carries every mechanic that tier
    bought. What changes is how hard each one bites - a link that clears clean
    instead of squatting, an arrow whose key is the box opened just before,
    a queue handed out in order instead of buried.

    A dose the gentler tier zeroes is kept at one, because a mechanic dropped to
    zero is a mechanic *removed*, and removing one is the budget's job, not this
    one's. One wall still pinches, and one wall is what the picture can pay for.
    """
    if form >= difficulty:
        return profile
    gentle = DIFFICULTY_PROFILES[form]
    return replace(
        profile,
        hidden_ratio=gentle.hidden_ratio,
        scramble=gentle.scramble,
        tunnels=max(1, gentle.tunnels) if profile.tunnels else gentle.tunnels,
        tunnel_depth=gentle.tunnel_depth,
        tunnel_placement=gentle.tunnel_placement,
        dig_window=gentle.dig_window,
        walls=max(1, gentle.walls) if profile.walls else gentle.walls,
        arrow_ratio=gentle.arrow_ratio,
        linked_pairs=max(1, gentle.linked_pairs) if profile.linked_pairs else gentle.linked_pairs,
        linked_mode=gentle.linked_mode,
        # The locks soften the same way: fewer of them, opening earlier in the
        # level, and chosen from boxes the winning line does not want for a good
        # while yet. `shuffle_kinds` comes down too, so a Hard level relieved to
        # Easy draws its mix instead of keeping the hard tier's priority order.
        frozen_ratio=gentle.frozen_ratio,
        frozen_at=gentle.frozen_at,
        blocks=max(1, gentle.blocks) if profile.blocks else gentle.blocks,
        block_span=gentle.block_span,
        block_at=gentle.block_at or profile.block_at[:1],
        lock_window=gentle.lock_window,
        shuffle_kinds=gentle.shuffle_kinds,
        arrow_reach=gentle.arrow_reach,
        clean_links=gentle.clean_links,
    )


@dataclass(frozen=True)
class ObstacleRelief:
    """How hard the obstacles ended up being set, and what the picture said about it.

    A hard picture and hard obstacles are two separate difficulties that used to
    be added together without anybody checking the sum: the tier is read off the
    colour count, and the tier then dosed every mechanic as if the conveyor were
    empty. On a picture that already needs 40 of its 45 balls, what that produces
    is a level where the burial is cut back by the belt check and the stall links
    are dropped one at a time by the belt check - the level still wins, but what
    survives is whatever the checks happened to leave rather than a design.

    So the form is *measured* rather than guessed at. The obstacle layer is built
    at the tier's own form and the result is read: a burial shallower than asked
    for and a pair count short of the request are the belt saying no. When it
    says no the whole layer is rebuilt a tier gentler, where the mechanic fits
    instead of being refused, and so on down to Easy.

    ``tried`` is that conversation, hardest first: the form, and which of
    :data:`BELT_SPENDING_KINDS` the belt cut at it. The mechanics themselves never
    change - see :class:`ObstaclePlan` for those - only how hard each one bites.
    """

    difficulty: int = int(LevelDifficulty.Easy)
    form: int = int(LevelDifficulty.Easy)
    # Where the ladder started. Normally the tier itself; lower when the designer
    # asked for a gentler build with `ease_obstacles`, which is a decision rather
    # than something the belt forced.
    top: int = int(LevelDifficulty.Easy)
    # The burial was floored at Easy's forms - see `unbury_profile` - because the
    # picture reported "KHÔNG THỂ THẮNG" before a single box existed. Deliberately
    # *not* a count of tiers: it moves three dials and leaves the rest of the form
    # exactly where the ladder put them, so it is not a rung on this ladder at all
    # and `form`, `top` and `eased` all read the same with it on as without.
    unburied: bool = False
    # Belt the picture's own cheapest winning play needs, out of what it has, and
    # the whole boxes that leaves over. Reported rather than decided on: it is the
    # reading that explains *why* a form did not fit.
    required_belt: int = 0
    belt_slots: int = 0
    room: int = 0
    # (form, kinds the belt cut at that form), hardest form first.
    tried: tuple[tuple[int, tuple[str, ...]], ...] = ()
    # (form, why it could not ship) for the attempts that were disqualified
    # outright rather than merely trimmed.
    faulted: tuple[tuple[int, tuple[str, ...]], ...] = ()
    # Every form faulted, so the level shipped as the bare base grid.
    base: bool = False
    enabled: bool = True

    @property
    def eased(self) -> int:
        """Tiers the designer asked the obstacle forms down, before any measuring."""
        return self.difficulty - self.top

    @property
    def steps(self) -> int:
        """Tiers the *belt* stepped the obstacle forms down, on top of any easing."""
        return self.top - self.form

    @property
    def relieved(self) -> bool:
        return self.steps > 0

    @property
    def cut(self) -> tuple[str, ...]:
        """Mechanics the belt still refused at the form that was shipped."""
        return next((cut for form, cut in self.tried if form == self.form), ())

    @property
    def refused(self) -> tuple[str, ...]:
        """Mechanics the belt cut at the top of the ladder, i.e. why relief stepped in."""
        return next((cut for form, cut in self.tried if form == self.top), ())

    @property
    def label(self) -> str:
        return DIFFICULTY_PROFILES[self.form].label

    @property
    def top_label(self) -> str:
        return DIFFICULTY_PROFILES[self.top].label

    @property
    def tier_label(self) -> str:
        return DIFFICULTY_PROFILES[self.difficulty].label


@dataclass
class ObstacleLayer:
    """One complete attempt at the obstacle layer, and what the belt made of it.

    Everything in here is decided by the form the attempt was built at, so an
    attempt is the unit relief works in: there is no point softening the links
    without also re-laying the grid the arrows were aimed across.
    """

    form: int
    profile: DifficultyProfile
    cols: int
    rows: int
    placements: list[Placement]
    blocks: list[list[int]]
    tunnel_slots: list[tuple[int, int]]
    facings: list[Direction]
    wall_slots: list[tuple[int, int]]
    pinched: list[tuple[int, int]]
    wanted_window: int
    queues: list[list[int]]
    dig_windows: list[int]
    release: TunnelRelease
    hidden: set[int]
    hidden_count: int
    linked: list[tuple[Placement, Placement, int]]
    play_groups: list[list[int]]
    play_position: dict[int, int]
    link_count: int
    linked_mode: str
    arrows: dict[int, tuple[Direction, Placement]]
    arrow_count: int
    # Where each filled tunnel hands its queue out, and the peak this layer's own
    # play order reaches on the belt. 0 belt means the play does not win at all.
    mouths: list[tuple[tuple[int, int], Direction]]
    played_belt: int
    # Stages 11 and 12. `progress` is the pixel count this layer's own play order
    # has cleared by the time it reaches each box, which is the number both locks
    # are written against and the only reason they are safe.
    progress: dict[int, int]
    frozen: list[BoxLock]
    frozen_count: int
    slabs: list[Slab]
    slab_count: int
    # Whole boxes of conveyor the picture leaves free at its tightest moment,
    # which is what sized the slabs and scaled how late they open.
    lock_room: int
    # Why this layer cannot be shipped at all, empty when it can. A fault is not
    # an error: it disqualifies one candidate, and the run falls back to a form
    # that has none - in the worst case to the base grid, which has none by
    # construction. See `relieve_obstacles`.
    faults: tuple[str, ...] = ()

    @property
    def shippable(self) -> bool:
        return not self.faults

    @property
    def cut(self) -> tuple[str, ...]:
        """Which belt-spending mechanics the conveyor took *most* of away from this form.

        Only the two the conveyor can refuse are read. An ArrowLock that found no
        key and a Hidden that ran out of back-row boxes are the *grid* being too
        small, and no amount of softening buys either of them a slot - relief
        would step down forever chasing them.

        And the reading is "most of", not "any of". Some shortfall is the normal
        working of the belt checks: :func:`plan_queues` widens each tunnel on its
        own, so a block that happens to sit over a tight stretch of the
        walkthrough staying shallow says nothing about the tier. A mechanic that
        mostly landed is the design the tier asked for; one that mostly did not is
        a trim, and a trim is what relief exists to replace with a form that fits.
        """
        cut: list[str] = []
        # Burial is read off the deepest queue, because that is where the tier's
        # digging either happened or did not.
        asked = max(0, self.wanted_window - 1)
        if self.blocks and asked:
            deepest = max(self.dig_windows, default=1) - 1
            if deepest * 2 < asked:
                cut.append("tunnel")
        if self.link_count and len(self.linked) * 2 < self.link_count:
            cut.append("linked")
        return tuple(cut)


@dataclass(frozen=True)
class ChoiceCensus:
    """How many boxes the player can actually tap, step by step.

    This is the number the obstacles move, and until it existed nothing in the
    tool measured them. :func:`pixel_gameplay.measure_difficulty` walks the bare
    *walkthrough* and asks how many picks keep the level winnable - a question
    about the **picture**, which is why its answer came out the same at every
    tier no matter what was laid on the grid. Every mechanic this generator
    spends works by taking a box *off the table*: a tunnel offers only its head,
    an arrow waits for its key, a lock waits for a pixel count, and a full
    conveyor refuses every tap at once. That is what this counts.

    ``fewest == 1`` somewhere means the level has a moment with exactly one legal
    tap. That is not a losing state - the certified line is always among the
    choices - but it is the moment a player has no decision left, and a level
    made of them is a level being led by the nose rather than solved.
    """

    steps: int = 0
    fewest: int = 0
    total: int = 0
    forced: int = 0

    @property
    def mean(self) -> float:
        return self.total / self.steps if self.steps else 0.0

    @property
    def forced_ratio(self) -> float:
        """Share of taps where the level offers exactly one box."""
        return self.forced / self.steps if self.steps else 0.0


def build_obstacle_layer(
    *,
    board: BoardState,
    solution: Solution,
    scan: PictureScan,
    options: AutoGenOptions,
    tier_profile: DifficultyProfile,
    plan: ObstaclePlan,
    difficulty: int,
    form: int,
    rules: GameRules,
    seed: int,
    climb: Sequence[str] = (),
    climb_from: int | None = None,
    bury_easy: bool = False,
) -> ObstacleLayer:
    """Lay out the grid and spend every mechanic in the plan, at one given form.

    The rng is seeded here rather than passed in, so an attempt depends only on
    the form it was built at: stepping down does not shift the grid of the form
    that is finally kept, and the same seed and form always give the same level.

    ``climb`` names the mechanics whose dials are taken back off ``climb_from``
    (the tier itself when it is None) after the form has been softened, which is
    how :func:`climb_obstacles` buys a shortfall back one mechanic at a time. It
    is a per-mechanic override of the form and nothing else: no mechanic is added
    or removed by it, because that is ``plan``'s business.

    ``bury_easy`` floors the burial dials at Easy's whatever the form and the
    climb decided, for a picture that cannot be won on its own belt at all -
    :func:`unbury_profile`.
    """
    profile = soften_profile(tier_profile, difficulty, form)
    if climb:
        profile = harden_profile(
            profile,
            DIFFICULTY_PROFILES[difficulty if climb_from is None else climb_from],
            climb,
        )
    # Last, so it is a floor and not an argument: `bury_easy` is set for a
    # picture that cannot be won on the belt the level ships with, and neither
    # the form nor a climb rung is allowed to put the burial back. See
    # :data:`BURIAL_GROUPS`.
    if bury_easy:
        profile = unbury_profile(profile)
    rng = random.Random(seed)

    cols, rows, placements, blocks, tunnel_slots, facings, wall_slots, pinched = _layout(
        solution, options, profile, plan, rng
    )

    # The picture's reading of the burial depth happens inside plan_queues, which
    # replays each tunnel at every depth down from this one and keeps the deepest
    # that still wins on the real belt. That is exact, so nothing is capped here.
    wanted_window = profile.dig_window if options.dig_window is None else options.dig_window
    queues, dig_windows, release = plan_queues(
        board, solution.order, blocks, wanted_window, rules
    )

    hidden_count = plan_hidden_count(len(placements), options, profile) if plan.has("hidden") else 0
    hidden = choose_hidden(placements, hidden_count, rng)

    # Links come before locks: a linked pair may not carry an ArrowLock, and the
    # links move boxes forward in the pick order, which is exactly what the locks
    # have to be checked against.
    linked_mode = resolve_linked_mode(options, profile)
    link_count = plan_link_count(len(placements), options, profile, scan, plan)
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
        profile.clean_links,
    )
    linked_indices = {
        placement.order_index for left, right, _ in linked for placement in (left, right)
    }
    play_position = {
        index: step for step, group in enumerate(play_groups) for index in group
    }

    arrow_count = plan_arrow_count(len(placements), options, profile, scan, plan)
    arrows = plan_arrow_locks(
        placements, play_position, hidden | linked_indices, arrow_count, rng, profile.arrow_reach
    )

    # The last word on "is there still a way to win": the level replayed exactly
    # as its own obstacles force it - queues buried, pairs dropping two boxes at
    # once - and the peak that play reaches on the belt.
    play_specs = [[solution.order[index] for index in group] for group in play_groups]
    played_belt = belt_peak(board, play_specs, rules)

    # Stages 11 and 12. Both locks are read out of the play order that was just
    # certified, so they come last and they come after the belt has had its say:
    # the number on a lock is bounded by how much of the picture is already gone
    # when this exact order reaches the box behind it.
    steps = tap_progress(board, play_specs, rules) or []
    progress = {
        index: steps[step] for index, step in play_position.items() if step < len(steps)
    }
    total_pixels = len(board.sequence)

    # Read the picture per colour *before* a single lock is placed: where the
    # frontier asks for each colour, and how many balls of it the grid holds.
    # Only the frontier colour can be spent, so this is what says whether a box
    # can clear anything at the moment a lock would be holding it shut - and it
    # is a fact about the picture, true for every order the player might tap in,
    # unlike `progress`, which is true only of the one order just certified.
    supply = read_color_supply(board.sequence, solution.order)

    # Slabs first, then Frozen. A slab needs a solid rectangle of boxes the play
    # order visits late and a grid has only a handful of those; a Frozen box needs
    # one box of a colour with a spare, and almost anything qualifies. Running the
    # loose one first let it eat the late-wanted boxes and left the tight one with
    # nothing - a fifth of SuperHard runs bought `LargeBlock` and shipped none.
    room = spare_boxes(scan)
    slab_span = block_span_for(room, profile)
    slab_count = (
        plan_block_count(len(placements), options, profile, slab_span)
        if plan.has("block")
        else 0
    )
    partners: dict[int, int] = {}
    for left, right, _ in linked:
        partners[left.order_index] = right.order_index
        partners[right.order_index] = left.order_index
    slabs = plan_slabs(
        placements,
        solution.order,
        supply,
        progress,
        cols,
        rows,
        wall_slots,
        tunnel_slots,
        slab_count,
        total_pixels,
        profile,
        options,
        set(),
        partners,
        room,
        rng,
    )
    slab_covered = {index for slab in slabs for index in slab.covered}
    # What the slabs hold back, handed to Frozen so it reads the picture the
    # slabs left rather than the one it started with: a colour whose only spare
    # box went under a slab has no spare any more.
    slab_shut = {index: slab.count for slab in slabs for index in slab.covered}
    frozen_count = (
        plan_frozen_count(len(placements), options, profile) if plan.has("frozen") else 0
    )
    frozen = plan_frozen(
        placements,
        solution.order,
        supply,
        progress,
        slab_shut,
        frozen_count,
        total_pixels,
        profile,
        options,
        # A linked pair has to carry identical effects, so freezing one half would
        # mean freezing the other at a number its own ceiling may not allow. And a
        # box already under a slab has a counter; a second one over it has no
        # defined moment of opening.
        linked_indices | slab_covered,
        rng,
    )
    # A slab hides what is under it, but only until it lifts, and Hidden keeps a
    # box dark for good. So the two stack rather than cancel, and the Hidden the
    # tier bought is left exactly where stage 8 put it: taking it back and
    # re-spending it would push the level past the share its tier asked for, and
    # would land on the bulk colour, which is the one Hidden that hides nothing.

    # Three ways a finished layout can be unplayable, and the replay only sees one
    # of them. The other two are geometry the gameplay model does not carry: it
    # taps a queue by index and walks no route across the grid, so a sealed mouth
    # and a walled-in box both replay as wins. They are asked of the layout here
    # instead, and a layout with any of the three is not shipped.
    box_slots = {(placement.slot_x, placement.slot_y) for placement in placements}
    mouths = [
        (slot, facing)
        for slot, queue, facing in zip(tunnel_slots, queues, facings, strict=True)
        if queue
    ]
    sealed = sealed_tunnel_mouths(mouths, box_slots)
    faults: list[str] = []
    if played_belt is None:
        faults.append(f"thứ tự obstacle bắt buộc thua trên băng {rules.belt_slots} bóng")
    if not layout_is_open(cols, rows, wall_slots, tunnel_slots):
        faults.append("wall bịt kín đường vào một box")
    if sealed:
        faults.append(
            "tunnel không có box thật để nhả queue: "
            + ", ".join(f"({x}, {y}) → {facing.name}" for (x, y), facing in sealed)
        )
    # The fourth way, and the only one a lock can cause: a counter that has not
    # reached its number by the time the winning line needs the box behind it.
    # The replay cannot see this either - it taps by index and counts no pixels -
    # so a level with a late lock wins in the model and deadlocks in the runtime.
    faults.extend(locks_hold(frozen, slabs, progress, options.lock_margin))
    # And the fifth, which `locks_hold` cannot see: a set of counters the
    # certified line clears but no other order can, because between them they
    # starve a colour the picture asks for before any of them opens.
    faults.extend(locks_open(board.sequence, solution.order, frozen, slabs))
    if len(frozen) >= len(placements) and placements:
        faults.append("mọi box mặt ngoài đều Frozen, không có box nào tap được lúc bắt đầu")

    return ObstacleLayer(
        form=form,
        profile=profile,
        cols=cols,
        rows=rows,
        placements=placements,
        blocks=blocks,
        tunnel_slots=tunnel_slots,
        facings=facings,
        wall_slots=wall_slots,
        pinched=pinched,
        wanted_window=wanted_window,
        queues=queues,
        dig_windows=dig_windows,
        release=release,
        hidden=hidden,
        hidden_count=hidden_count,
        linked=linked,
        play_groups=play_groups,
        play_position=play_position,
        link_count=link_count,
        linked_mode=linked_mode,
        arrows=arrows,
        arrow_count=arrow_count,
        mouths=mouths,
        played_belt=played_belt or 0,
        progress=progress,
        frozen=frozen,
        frozen_count=frozen_count,
        slabs=slabs,
        slab_count=slab_count,
        lock_room=room,
        faults=tuple(faults),
    )


def build_base_grid(
    *,
    board: BoardState,
    solution: Solution,
    scan: PictureScan,
    options: AutoGenOptions,
    tier_profile: DifficultyProfile,
    difficulty: int,
    rules: GameRules,
    seed: int,
) -> ObstacleLayer:
    """The box grid with no mechanics on it at all: just the picture, laid out.

    This is stage 5, and it is the floor the whole run stands on. It is the
    picture and nothing else: every box the histogram asks for, placed in
    walkthrough order on the smallest lattice that holds them, whatever does not
    fit stored in tunnels that hand each box out **exactly** when the picture asks
    for it (``dig_window`` 1), and no Hidden, Wall, ArrowLock or LinkedContainer
    anywhere. An empty :class:`ObstaclePlan` says all of that in one object, so
    this is :func:`build_obstacle_layer` with nothing to spend.

    Two things follow from having it as a real, certified artifact rather than as
    an intermediate step:

    * **The level is winnable before a single obstacle exists.** Every mechanic
      added afterwards is a change to a grid that already had a proven winning
      line, which is the only order in which "does this still win" is a question
      with a meaning.
    * **There is always something to ship.** A mechanic layer can turn out
      unplayable in ways the belt check cannot see - a wall that seals a box in, a
      tunnel with no box to hand its queue to - and when every form does, this is
      what goes out instead of an error.
    """
    return build_obstacle_layer(
        board=board,
        solution=solution,
        scan=scan,
        # An empty plan silences the knobs that are read through it - Hidden,
        # Wall, ArrowLock, LinkedContainer - but the tunnel knobs are read
        # straight off the options, and a typed tunnel count is a request for a
        # *mechanic*. The floor gets only the tunnels the picture cannot be laid
        # out without, handing each box over exactly when it is wanted.
        options=replace(
            options,
            tunnel_mode="overflow",
            tunnel_count=None,
            tunnel_depth=0,
            tunnel_placement="auto",
            dig_window=1,
            walls=0,
        ),
        tier_profile=tier_profile,
        # No kinds: the tier decides nothing here, the picture decides everything.
        plan=ObstaclePlan(difficulty=difficulty),
        difficulty=difficulty,
        # The gentlest form, so nothing about the base is a difficulty choice:
        # boxes in walkthrough order, front row first, released when needed.
        form=int(LevelDifficulty.Easy),
        rules=rules,
        seed=seed,
    )


def relieve_obstacles(
    *,
    board: BoardState,
    solution: Solution,
    scan: PictureScan,
    options: AutoGenOptions,
    tier_profile: DifficultyProfile,
    plan: ObstaclePlan,
    difficulty: int,
    rules: GameRules,
    seed: int,
    base: ObstacleLayer,
    bury_easy: bool = False,
) -> tuple[ObstacleLayer, ObstacleRelief]:
    """Lay the mechanics on the certified base, at the hardest form it survives.

    Starts at the tier's own form, because a picture with room to spare should get
    exactly the level its tier describes. Each attempt is then read rather than
    trusted, on two separate questions:

    * **Faults** disqualify an attempt outright - it loses on the belt, a wall
      seals a box in, or a tunnel has no box to hand its queue to. A faulted
      attempt is never shipped, however good its numbers look.
    * **Cuts** are the softer signal: anything in :data:`BELT_SPENDING_KINDS` that
      came out smaller than asked for is the conveyor saying it cannot pay, and
      the answer to that is a gentler form of the same mechanic - not a smaller
      amount of it.

    Easy is the floor of the forms and it is not guaranteed to fit either: a
    picture with no room at all refuses even a clean link. So the attempt kept is
    the fault-free one that lost the fewest mechanics, and the *hardest* of those
    on a tie - stepping down is only ever worth it when it buys back something the
    belt was refusing, and a gentler form that loses just as much has bought
    nothing.

    If every form faults, ``base`` ships: a level with no mechanics beats no
    level, and it is the same grid every attempt was measured against.
    """
    # `ease_obstacles` moves where the ladder *starts*: relief reacts to the belt,
    # this is the designer saying "build the gentler version of this tier" before
    # anything is measured. The tier itself, and so the level's label and theme,
    # is untouched - a Hard level with Easy-form obstacles is still a Hard level.
    top = max(
        int(LevelDifficulty.Easy), difficulty - max(0, options.ease_obstacles)
    )
    tried: list[ObstacleLayer] = []
    for form in range(top, int(LevelDifficulty.Easy) - 1, -1):
        tried.append(
            build_obstacle_layer(
                board=board,
                solution=solution,
                scan=scan,
                options=options,
                tier_profile=tier_profile,
                plan=plan,
                difficulty=difficulty,
                form=form,
                rules=rules,
                seed=seed,
                bury_easy=bury_easy,
            )
        )
        if not options.obstacle_relief:
            break
        # A faulted attempt is not a reason to stop looking, and not a reason to
        # accept it either: keep stepping down and let the pick sort it out.
        if tried[-1].shippable and not tried[-1].cut:
            break
    shippable = [attempt for attempt in tried if attempt.shippable]
    if not options.obstacle_relief:
        layer = tried[0] if tried[0].shippable else base
    elif shippable:
        layer = min(shippable, key=lambda attempt: (len(attempt.cut), -attempt.form))
    else:
        layer = base
    relief = ObstacleRelief(
        difficulty=difficulty,
        form=layer.form,
        top=top,
        unburied=bury_easy,
        required_belt=solution.required_belt,
        belt_slots=rules.belt_slots,
        room=belt_room(solution.required_belt, rules.belt_slots),
        tried=tuple((attempt.form, attempt.cut) for attempt in tried),
        faulted=tuple(
            (attempt.form, attempt.faults) for attempt in tried if attempt.faults
        ),
        base=layer is base,
        enabled=options.obstacle_relief,
    )
    return layer, relief


# --------------------------------------------------------------------------- #
# Stage 12b - what the finished level adds up to, and climbing it to the target
# --------------------------------------------------------------------------- #
# Every reading the score is taken over, grouped by the mechanic it belongs to,
# and what each group is worth.
#
# The point of grouping them is that a level's difficulty is a *sum*, not a list
# of separate verdicts. "This picture is Hard" is a statement about the whole
# level - the boxes buried out of sight plus every obstacle laid on top - so a
# shortfall in one group can be paid for by another, and no single group is
# checked against the tier on its own. The three burial readings come to 4.5 of
# the 10 and the six obstacle ones to the other 5.5, which is the split the
# module docstring describes: a picture is made hard mostly by what the player
# cannot see, and the rest by what is in the way.
#
# The weights are relative and nothing else: the anchors below are summed with
# the same numbers, so what a weight actually decides is how far one mechanic
# moves the total - i.e. how much of a shortfall a climb can buy back with it.
DIFFICULTY_DIALS: dict[str, tuple[str, ...]] = {
    # Boxes the player cannot see or cannot reach yet: "box duoc chon".
    "hidden": ("hidden_ratio",),
    "scramble": ("scramble",),
    "tunnel": ("dig_window", "tunnel_placement"),
    # Obstacles laid on top.
    "wall": ("wall_pinches",),
    "arrow": ("arrow_ratio", "arrow_reach"),
    "linked": ("linked_pairs", "linked_mode", "clean_links"),
    "frozen": ("frozen_ratio",),
    "block": ("blocks",),
    "lock": ("lock_bite",),
}
DIFFICULTY_WEIGHTS: dict[str, float] = {
    "hidden": 2.0,
    "scramble": 1.0,
    "tunnel": 1.5,
    "wall": 1.0,
    "arrow": 1.25,
    "linked": 1.25,
    "frozen": 0.75,
    "block": 0.75,
    "lock": 0.5,
}
# The two groups that are not one of OBSTACLE_KIND_LABELS' mechanics, because no
# budget buys them: the layout is always scrambled somehow, and a lock's timing
# rides on whichever of the two locks the level already carries.
DIFFICULTY_GROUP_LABELS: dict[str, str] = OBSTACLE_KIND_LABELS | {
    "scramble": "xáo trộn lưới",
    "lock": "độ trễ mở khoá",
}

# The readings that are a *choice between forms* rather than a number, easiest
# first, so the index into the tuple is already "harder = larger". Each one is
# the option list the knob itself is validated against, minus the leading "auto"
# where it has one - "auto" is a request to decide, never a form a level is in.
DIAL_ORDERS: dict[str, tuple[str, ...]] = {
    "scramble": SCRAMBLE_MODES,
    "tunnel_placement": TUNNEL_PLACEMENTS[1:],
    "arrow_reach": ARROW_REACH,
    "linked_mode": LINKED_MODES[1:],
}


def _form_notch(dial: str, form: str) -> float:
    order = DIAL_ORDERS[dial]
    return float(order.index(form)) if form in order else 0.0


def layer_dials(layer: ObstacleLayer) -> dict[str, float]:
    """One finished layer as the flat dial table the ladders are read against.

    Counts become shares wherever the profile takes a share (Hidden, ArrowLock,
    Frozen) so that a layer and a profile are comparable dial for dial, and the
    numbers are the ones actually **laid** rather than the ones asked for -
    `hidden` not `hidden_count`, `linked` not `link_count`. What the belt refused
    is exactly what must not be scored.

    The *forms* - how the grid is scrambled, how far an arrow reaches, whether a
    pair clears clean - are read off `layer.profile`, the profile this layer was
    really built at, because for those the profile **is** the level: there is
    nothing else they could be. A mechanic the layer does not carry reads as the
    bottom of its dial rather than as Easy's setting, so an absent
    LinkedContainer is not credited with Easy's "sync, clears clean".
    """
    profile = layer.profile
    surface = len(layer.placements)
    buried = any(layer.queues)
    return {
        "hidden_ratio": len(layer.hidden) / surface if surface else 0.0,
        "scramble": _form_notch("scramble", profile.scramble),
        # A tunnel nobody filled buries nothing, whatever the profile asked for.
        "dig_window": float(max(layer.dig_windows, default=1) if buried else 1),
        "tunnel_placement": (
            _form_notch("tunnel_placement", profile.tunnel_placement) if buried else 0.0
        ),
        # The pinches, not the empty slots. Every slot the boxes do not fill is a
        # wall - see `_layout` - so a picture that simply tiles badly leaves
        # leftovers nobody asked for, and counting those would hand it a wall
        # score it never designed for. A wall that narrows a box down to one
        # approach is the mechanic; a wall sitting in a corner is a gap.
        "wall_pinches": float(len(layer.pinched)),
        "arrow_ratio": len(layer.arrows) / surface if surface else 0.0,
        "arrow_reach": (
            _form_notch("arrow_reach", profile.arrow_reach) if layer.arrows else 0.0
        ),
        "linked_pairs": float(len(layer.linked)),
        "linked_mode": (
            _form_notch("linked_mode", layer.linked_mode) if layer.linked else 0.0
        ),
        "clean_links": 0.0 if profile.clean_links or not layer.linked else 1.0,
        "frozen_ratio": len(layer.frozen) / surface if surface else 0.0,
        "blocks": float(len(layer.slabs)),
        # How late a lock opens, read as a bite rather than as a window, so that
        # a level with no lock at all sits below every tier instead of above
        # them: a *small* window is the hard one, and 0 would read as hardest.
        "lock_bite": (
            (1.0 - profile.lock_window) if (layer.frozen or layer.slabs) else 0.0
        ),
    }


def profile_dials(profile: DifficultyProfile) -> dict[str, float]:
    """The same table for a tier, i.e. that tier's dials spent in full."""
    return {
        "hidden_ratio": profile.hidden_ratio,
        "scramble": _form_notch("scramble", profile.scramble),
        "dig_window": float(profile.dig_window),
        "tunnel_placement": _form_notch("tunnel_placement", profile.tunnel_placement),
        "wall_pinches": float(profile.walls // WALLS_PER_PINCH),
        "arrow_ratio": profile.arrow_ratio,
        "arrow_reach": (
            _form_notch("arrow_reach", profile.arrow_reach) if profile.arrow_ratio else 0.0
        ),
        "linked_pairs": float(profile.linked_pairs),
        "linked_mode": (
            _form_notch("linked_mode", profile.linked_mode) if profile.linked_pairs else 0.0
        ),
        "clean_links": 0.0 if profile.clean_links or not profile.linked_pairs else 1.0,
        "frozen_ratio": profile.frozen_ratio,
        "blocks": float(profile.blocks),
        "lock_bite": (
            (1.0 - profile.lock_window) if (profile.frozen_ratio or profile.blocks) else 0.0
        ),
    }


def ladder_notch(value: float, ladder: Sequence[float]) -> float:
    """Where ``value`` sits on a four-tier ladder, as a notch on the 0-3 line.

    The ladder is a dial as the four canonical profiles write it, so the notch
    that comes back is on exactly the scale the designer already reads - the same
    0/1/2/3 as :class:`LevelDifficulty` - rather than on an invented 0-100.
    Between two tiers the answer is interpolated, so 1.6 means "past Medium, not
    yet Hard" and can be reported as such.

    Anything at or under the easy tier's own setting is 0, because Easy *is* the
    bottom of this scale: there is no gentler level to be short of. Anything past
    the hardest tier's setting is 3 - nothing above SuperHard is ever the target,
    so measuring how far past it a dial went would be measuring nothing.

    A flat rung - ``walls`` is (0, 0, 2, 4), because neither easy tier has one -
    is read from its *bottom*, so a level with no wall scores 0 for walls rather
    than being credited with Medium's wall count of zero as if it were a choice.
    """
    steps = list(ladder)
    if not steps:  # pragma: no cover - every dial has four rungs
        return 0.0
    if value <= steps[0]:
        return 0.0
    for index in range(1, len(steps)):
        if value <= steps[index]:
            low, high = steps[index - 1], steps[index]
            if high <= low:
                return float(index)
            return (index - 1) + (value - low) / (high - low)
    return float(len(steps) - 1)


def dial_ladder(dial: str) -> tuple[float, ...]:
    """One dial as the four canonical profiles write it, Easy first."""
    return tuple(
        profile_dials(DIFFICULTY_PROFILES[tier])[dial] for tier in sorted(DIFFICULTY_PROFILES)
    )


def group_notch(group: str, dials: dict[str, float]) -> float:
    """One mechanic's notch: the mean of the notches of the dials that set it."""
    names = DIFFICULTY_DIALS[group]
    return sum(ladder_notch(dials[name], dial_ladder(name)) for name in names) / len(names)


def raw_difficulty(dials: dict[str, float]) -> float:
    """Every group's notch, weighted and summed. Not yet on the 0-3 line."""
    return sum(
        DIFFICULTY_WEIGHTS[group] * group_notch(group, dials) for group in DIFFICULTY_DIALS
    )


def difficulty_anchors() -> tuple[float, ...]:
    """:func:`raw_difficulty` of each canonical tier, spent in full. Easy first.

    This is what the score is measured against, and it is why there is not a
    single hand-picked threshold in here: the four rows of
    :data:`DIFFICULTY_PROFILES` *are* the scale. Edit a profile and the band
    moves with it, so the score cannot quietly drift away from what a tier means.
    """
    return tuple(
        raw_difficulty(profile_dials(DIFFICULTY_PROFILES[tier]))
        for tier in sorted(DIFFICULTY_PROFILES)
    )


@dataclass(frozen=True)
class LevelDifficultyScore:
    """How hard the level that came out actually is, as one number, and why.

    ``notch`` is that number, on the 0-3 line the tiers themselves live on: 2.0
    is exactly what a Hard profile spent in full comes to, and 1.6 is a level
    that got most of the way from Medium to Hard. ``target`` is what the picture
    asked for, so the two are directly comparable and the gap between them is
    the thing :func:`climb_obstacles` is trying to close.

    ``groups`` is the same reading un-summed, which is what makes a shortfall
    actionable: it says *which* mechanic came out gentler than the tier wanted,
    and therefore which one is worth hardening.
    """

    groups: dict[str, float] = field(default_factory=dict)
    raw: float = 0.0
    anchors: tuple[float, ...] = ()
    notch: float = 0.0
    target: int = int(LevelDifficulty.Easy)

    @property
    def tier(self) -> int:
        """The notch rounded to a tier, which is the label a level would carry."""
        tiers = sorted(DIFFICULTY_PROFILES)
        return min(max(tiers), max(min(tiers), round(self.notch)))

    @property
    def label(self) -> str:
        return DIFFICULTY_PROFILES[self.tier].label

    @property
    def target_label(self) -> str:
        return DIFFICULTY_PROFILES[self.target].label

    @property
    def reached(self) -> bool:
        """Does the level as a whole read as the tier the picture asked for?

        Asked of the rounded tier rather than of the raw notch, because the tier
        is what the level ships as: a Hard target met at 1.62 rounds to Hard and
        is Hard. Half a notch short of that is a level wearing the wrong label.
        """
        return self.tier >= self.target

    @property
    def shortfall(self) -> float:
        return max(0.0, float(self.target) - self.notch)

    @property
    def summary(self) -> str:
        return (
            f"{self.notch:.2f}/3 = {self.label}"
            f" (mục tiêu {self.target}.00 = {self.target_label})"
        )


def score_layer(layer: ObstacleLayer, *, target: int) -> LevelDifficultyScore:
    """Score one finished layer against the tier the picture asked for."""
    dials = layer_dials(layer)
    return LevelDifficultyScore(
        groups={group: group_notch(group, dials) for group in DIFFICULTY_DIALS},
        raw=raw_difficulty(dials),
        anchors=difficulty_anchors(),
        # The same interpolation the dials use, over the anchors instead of over
        # one dial's rungs: the four tiers are the ladder here too.
        notch=ladder_notch(raw_difficulty(dials), difficulty_anchors()),
        target=target,
    )


# Which dials each rung of the climb takes back, and the order the rungs are
# walked in.
#
# The order is the whole design of the climb: what spends no conveyor comes
# first. A level is short of its tier precisely when the belt refused to pay for
# something, so reaching straight for one of :data:`BELT_SPENDING_KINDS` is
# asking the question that already got a no - those two are the last resort.
# Everything above them is free on the belt for a different reason each: the two
# locks are derived from the certified play order, Hidden only hides a colour,
# an arrow's key is always a box the order opens earlier, and a wall and the
# scramble cost slots and distance rather than balls.
CLIMB_ORDER: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("frozen", ("frozen_ratio", "frozen_at")),
    ("block", ("blocks", "block_span", "block_at")),
    ("lock", ("lock_window",)),
    ("hidden", ("hidden_ratio",)),
    ("arrow", ("arrow_ratio", "arrow_reach")),
    ("wall", ("walls",)),
    ("scramble", ("scramble",)),
    ("tunnel", ("dig_window", "tunnel_depth", "tunnels", "tunnel_placement")),
    ("linked", ("linked_pairs", "linked_mode", "clean_links")),
)


def harden_profile(
    profile: DifficultyProfile, source: DifficultyProfile, groups: Sequence[str]
) -> DifficultyProfile:
    """``profile`` with the dials of ``groups`` taken back off ``source``.

    The exact inverse of :func:`soften_profile`, applied one mechanic at a time
    instead of to all of them at once - which is the only way a shortfall can be
    paid for out of the mechanics that still fit. ``source`` is never gentler
    than ``profile`` (it is the tier itself, or a tier above it, against a
    profile relief has already stepped down) and every dial in
    :data:`DIFFICULTY_PROFILES` is monotone across the tiers, so taking the
    source's value is always the harder of the two.

    ``kinds`` and ``label`` are untouched, exactly as in :func:`soften_profile`:
    this changes how hard the mechanics bite, never which ones the level carries.
    """
    dials = {
        dial: getattr(source, dial)
        for group, fields in CLIMB_ORDER
        if group in groups
        for dial in fields
    }
    return replace(profile, **dials) if dials else profile


def unbury_profile(profile: DifficultyProfile) -> DifficultyProfile:
    """``profile`` with the burial dials alone taken down to Easy's settings.

    :data:`BURIAL_GROUPS` says which those are and why. Only the *forms* move -
    how much is hidden, how far from the front row the wanted box may sit, how
    deep a queue is buried - never a count: the tunnels the picture cannot be
    laid out without are still planted, they just hand each box over when it is
    asked for. Which mechanics the level carries stays :class:`ObstaclePlan`'s
    decision here exactly as it is everywhere else.

    Applied last in :func:`build_obstacle_layer`, after the form has been
    softened *and* after any climb rung has been taken back, so this is a floor
    rather than one more voice in the argument: nothing downstream can bury the
    level again.
    """
    easy = DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)]
    return replace(
        profile,
        **{
            dial: getattr(easy, dial)
            for group in BURIAL_GROUPS
            for dial in DIFFICULTY_DIALS[group]
        },
    )


@dataclass(frozen=True)
class DifficultyClimb:
    """Stage 12b: obstacles hardened until the level adds up to the picture's tier.

    Stages 6-12 build the level the tier describes, and :func:`relieve_obstacles`
    steps that build down until the conveyor stops refusing it. Neither ever
    asked the question the picture actually posed: taken *as a whole*, does the
    level come out at the difficulty the picture was read as? A Hard picture
    relieved two tiers carries every mechanic Hard bought, set the way Easy would
    set them, and ships wearing a Hard label.

    So the sum is measured (:func:`score_layer`) and then closed. One mechanic at
    a time is taken back to its tier's own setting, cheapest on the conveyor
    first, and the layer is rebuilt and re-scored. A rung is kept only if the
    rebuild is playable *and* the total actually went up - which is what keeps
    this from simply undoing relief: relief stepped down because the belt was
    refusing something, and a rung the belt still refuses comes back trimmed by
    those same checks, scores no higher and is dropped on the spot. What the
    climb buys back is the difficulty relief overpaid, spent on the mechanics
    the picture can afford.

    If every rung at the tier's own setting is spent and the level is still
    short, the second lap reaches one tier *above* the target for the dials that
    did land. That is the sum being taken seriously: a mechanic the grid could
    not carry gets paid for by one it can, rather than by relabelling the level.

    This is the mirror of :class:`ObstacleRelief` and reads the same way: relief
    is the conversation on the way down, ``tried`` is the one on the way back up.
    """

    target: int = int(LevelDifficulty.Easy)
    # The notch before the first rung and after the last one.
    start: float = 0.0
    final: float = 0.0
    # (group, the tier its dials were taken from, what happened), in order tried.
    tried: tuple[tuple[str, int, str], ...] = ()
    # The groups whose rung was kept, in the order they were added.
    added: tuple[str, ...] = ()
    reached: bool = True
    enabled: bool = True

    @property
    def gained(self) -> float:
        return self.final - self.start

    @property
    def climbed(self) -> bool:
        return bool(self.added)

    @property
    def refused(self) -> tuple[tuple[str, str], ...]:
        """The rungs that were tried and did not stick, with the reason."""
        return tuple((group, why) for group, _, why in self.tried if group not in self.added)


def climb_sources(
    top: int, *, difficulty: int, tier_profile: DifficultyProfile, options: AutoGenOptions
) -> tuple[int, ...]:
    """The tiers a climb takes dials from, gentlest first.

    ``top`` is :attr:`ObstacleRelief.top`, the form the designer asked for, and
    it is the ceiling rather than ``difficulty`` on purpose. Relief steps the
    forms down for two quite different reasons and only one of them is a
    shortfall: :attr:`ObstacleRelief.steps` is the belt refusing to pay, which is
    what the climb exists to buy back, while :attr:`ObstacleRelief.eased` is the
    designer asking for the gentler build of this tier. Climbing past ``top``
    would undo the second one, i.e. overrule the very knob that was set.

    The second lap reaches one tier *above* that, and only when nobody asked for
    the shortfall at all. A mechanic the grid or the belt could not carry is fair
    to pay for out of another one - that is what makes this a sum - but a
    mechanic the designer switched off by hand is not a shortfall to make up.
    Cranking Hidden to SuperHard's share because somebody unticked the wall is
    the tool overruling them, so a run with anything turned off, or with the
    forms deliberately eased, gets one lap and a report saying how far short it
    came. :func:`designer_choice` is the same reading
    :func:`plan_obstacle_kinds` gates on, so the two cannot disagree.

    Two laps is the ceiling either way. A third has little left to offer - by
    then every dial the grid can carry is already set above the target's own -
    and each lap costs one full rebuild per mechanic.
    """
    if top < difficulty or any(
        designer_choice(kind, options) is False
        for kind in tier_profile.kinds + tier_profile.lock_kinds
    ):
        return (top,)
    return tuple(range(top, min(int(LevelDifficulty.SuperHard), top + 1) + 1))


def climb_obstacles(
    *,
    board: BoardState,
    solution: Solution,
    scan: PictureScan,
    options: AutoGenOptions,
    tier_profile: DifficultyProfile,
    plan: ObstaclePlan,
    difficulty: int,
    rules: GameRules,
    seed: int,
    layer: ObstacleLayer,
    top: int,
    bury_easy: bool = False,
) -> tuple[ObstacleLayer, LevelDifficultyScore, DifficultyClimb]:
    """Harden the layer, one mechanic at a time, until it scores its target tier.

    Returns the layer that shipped, its score, and the record of the climb. The
    layer handed in is the floor: a climb that buys nothing returns it unchanged,
    so this can never make a level less playable than relief left it.

    ``top`` is the hardest form the designer asked for - see
    :func:`climb_sources` - and no dial is ever taken past it on the first lap.

    ``bury_easy`` is the picture that cannot be won on its own belt, and this is
    the half of it that *adds*: the burial is floored at Easy and stays there, so
    the shortfall that floor leaves is made up out of the obstacles laid on top -
    a wall, an arrow, a lock - which is how such a level keeps its content
    instead of shipping bare. The three burial rungs are skipped rather than
    tried, because :func:`unbury_profile` runs after the climb and would undo
    them: attempting one costs a full rebuild and can only score the same.
    """
    score = score_layer(layer, target=difficulty)
    if score.reached or not options.difficulty_climb:
        return (
            layer,
            score,
            DifficultyClimb(
                target=difficulty,
                start=score.notch,
                final=score.notch,
                reached=score.reached,
                enabled=options.difficulty_climb,
            ),
        )

    best_layer, best = layer, score
    kept: list[str] = []
    tried: list[tuple[str, int, str]] = []
    for source in climb_sources(
        top, difficulty=difficulty, tier_profile=tier_profile, options=options
    ):
        for group, _ in CLIMB_ORDER:
            if group in kept:
                continue
            if bury_easy and group in BURIAL_GROUPS:
                tried.append(
                    (group, source, "tranh không thắng được nên chôn box giữ ở mức dễ")
                )
                continue
            # A rung for a mechanic the budget never bought cannot help: every
            # dial behind it is read through `plan.has`, so hardening it changes
            # nothing and only costs a rebuild. The two groups that are not
            # mechanics - the scramble and the lock timing - have no plan to ask.
            if group in ALL_OBSTACLE_KINDS and not plan.has(group):
                tried.append((group, source, "level này không mua loại đó"))
                continue
            attempt = build_obstacle_layer(
                board=board,
                solution=solution,
                scan=scan,
                options=options,
                tier_profile=tier_profile,
                plan=plan,
                difficulty=difficulty,
                # The form relief settled on stays the floor: the climb lifts
                # single dials off it, it does not re-run the ladder.
                form=layer.form,
                rules=rules,
                seed=seed,
                climb=tuple(kept + [group]),
                climb_from=source,
                bury_easy=bury_easy,
            )
            if not attempt.shippable:
                tried.append((group, source, "lưới không chơi được: " + "; ".join(attempt.faults)))
                continue
            trial = score_layer(attempt, target=difficulty)
            # The belt gets the last word here too, measured rather than asked: a
            # rung the conveyor cannot pay for comes back trimmed by the same
            # checks `ObstacleLayer.cut` reads, so it scores no higher than what
            # is already kept and is dropped.
            if trial.raw <= best.raw + 1e-9:
                tried.append((group, source, "băng không chịu, điểm không tăng"))
                continue
            gain = trial.notch - best.notch
            kept.append(group)
            best_layer, best = attempt, trial
            tried.append((group, source, f"+{gain:.2f} nấc → {trial.notch:.2f}"))
            if best.reached:
                break
        if best.reached:
            break
    return (
        best_layer,
        best,
        DifficultyClimb(
            target=difficulty,
            start=score.notch,
            final=best.notch,
            tried=tuple(tried),
            added=tuple(kept),
            reached=best.reached,
            enabled=True,
        ),
    )


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
    # The placement and mode this run resolved to, with "auto" already answered.
    tunnel_placement: str = "back"
    tunnel_mode: str = "overflow"
    # What the picture was measured to be worth in tunnels: the tier's dose for a
    # grid this size, and the ceiling that dose was cut to.
    tunnel_dose: int = 0
    tunnel_ceiling: int = 0
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
    # The two locks, as laid. Each one carries the number it was written with,
    # the number its tier asked for, and the ceiling the winning line allowed -
    # so the report can say which locks the grid could not bear in full.
    frozen: list[BoxLock] = field(default_factory=list)
    frozen_dose: int = 0
    slabs: list[Slab] = field(default_factory=list)
    slab_dose: int = 0
    # The measurement the slabs were sized and timed from: whole boxes of belt
    # still free at the picture's tightest moment.
    lock_room: int = 0
    # The per-colour read both locks were placed from, before either was placed:
    # where the frontier asks for each colour and how many balls of it exist.
    color_supply: dict[int, "ColorSupply"] = field(default_factory=dict)
    # How many boxes the level actually offers at each tap. This is the only
    # number here that the *obstacles* move: `metrics` walks the bare walkthrough
    # and so describes the picture, whatever is laid on the grid afterwards.
    choices: ChoiceCensus = field(default_factory=ChoiceCensus)
    play_groups: list[list[int]] = field(default_factory=list)
    removed_pixels: Counter[int] = field(default_factory=Counter)
    # The two cheaper balance moves: pixels painted into empty cells to top a
    # colour up, and pixels recoloured from one colour into another.
    added_pixels: Counter[int] = field(default_factory=Counter)
    moved_pixels: Counter[tuple[int, int]] = field(default_factory=Counter)
    emptied_columns: list[int] = field(default_factory=list)
    dropped_obstacles: int = 0
    # The seed this run actually used, including the one derived from the level
    # number when the caller asked for none. Feeding it back reproduces this grid.
    seed: int = 0
    # What the scanner read off the picture, and the tier this run settled on -
    # which is not options.difficulty when the caller asked for auto.
    scan: PictureScan = field(default_factory=PictureScan)
    # Which mechanics this run was allowed to spend, and what it left out.
    obstacle_plan: ObstaclePlan = field(default_factory=ObstaclePlan)
    # How hard each of them was set, and the profile that came out of it - which
    # is not DIFFICULTY_PROFILES[difficulty] when the picture forced a step down.
    obstacle_relief: ObstacleRelief = field(default_factory=ObstacleRelief)
    # Stage 12b: what the level was measured to add up to, taken over the buried
    # boxes and every obstacle together, and the rungs the climb spent closing
    # the gap to `difficulty`. `score.target` is that target; `score.notch` is
    # what came out, on the same 0-3 line.
    score: LevelDifficultyScore = field(default_factory=LevelDifficultyScore)
    climb: DifficultyClimb = field(default_factory=DifficultyClimb)
    # What the picture itself read as. Read on every run, not only the ones that
    # asked for it: a designer who typed their own tier still wants to know what
    # the picture would have said.
    rating: PictureRating = field(default_factory=PictureRating)
    profile: DifficultyProfile = field(
        default_factory=lambda: DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)]
    )
    difficulty: int = int(LevelDifficulty.Easy)
    belt_slots: int = DEFAULT_BELT_SLOTS
    # The belt the obstacles were verified on. Same as `belt_slots` unless the
    # picture cannot be played on the level's own belt, in which case this is the
    # belt it needs and `jam` says where the level's own one gives out.
    certified_belt: int = 0
    # Fullest the conveyor gets when the level is played the way its obstacles
    # force it to be played - tunnel releases, linked pairs and all. This is the
    # number the obstacles are answerable for; everything else in here is a plan.
    played_belt: int = 0
    # Stage 4: the box grid before a single mechanic was laid on it, which the run
    # certifies on its own. Its play order *is* the walkthrough - a queue that
    # hands each box over exactly when the picture asks for it releases in
    # walkthrough order - so `base_belt` is what the level needs with nothing in
    # the way, and it is what every obstacle is measured against.
    base_belt: int = 0
    base_surface_boxes: int = 0
    base_tunnel_count: int = 0
    base_tunnel_boxes: int = 0
    # What the picture had to be repainted into before it could be played at all,
    # and how many rolls of the whole run this result was picked out of.
    repair: RepairReport = field(default_factory=RepairReport)
    shuffle_attempts: int = 1
    shuffle_rolls: int = 1
    jam: BeltJam | None = None
    # What LevelValidator makes of the level this run produced. The generator's
    # own checks are about the *play* - does it win, do the histograms match - and
    # the validator's are about the *file*: every rule the runtime and the rest of
    # the tool rely on. A generated level has to pass both, so it is asked here
    # rather than left to whichever panel the designer happens to open.
    validation: tuple[ValidationMessage, ...] = ()
    warnings: list[str] = field(default_factory=list)

    @property
    def winnable(self) -> bool:
        """Can this level be cleared on the belt its own ``piece`` buys?"""
        return self.jam is None

    @property
    def validation_errors(self) -> tuple[ValidationMessage, ...]:
        return tuple(message for message in self.validation if message.severity == "error")

    @property
    def validation_warnings(self) -> tuple[ValidationMessage, ...]:
        return tuple(message for message in self.validation if message.severity == "warning")

    @property
    def valid(self) -> bool:
        """Does the generated level pass every rule LevelValidator enforces?"""
        return not self.validation_errors

    @property
    def difficulty_matched(self) -> bool:
        """Does the level add up to the difficulty the picture was read as?

        A third question, beside `winnable` and `valid`, and the only one of the
        three about the *design* rather than about correctness: a level can win,
        pass every file rule, and still play two tiers gentler than the tier it
        ships as.
        """
        return self.score.reached

    @property
    def locked_balls(self) -> int:
        """Balls held behind a lock at the moment it is written, both kinds together.

        The level's own reading of how much of itself is shut away, and the one
        number that makes a Frozen box and a slab comparable: a slab over four
        boxes is four times the Frozen.
        """
        return len(self.frozen) * BALLS_PER_BOX + sum(slab.mass for slab in self.slabs)

    @property
    def lock_pressure(self) -> float:
        """``locked_balls`` as a share of the picture."""
        total = len(self.solution.order) * BALLS_PER_BOX
        return self.locked_balls / total if total else 0.0

    @property
    def trimmed_locks(self) -> int:
        """Locks the grid could not bear at the tier's number, so they open earlier."""
        return sum(lock.trimmed for lock in self.frozen) + sum(
            slab.trimmed for slab in self.slabs
        )

    @property
    def obstacle_free(self) -> bool:
        """Did the level ship as the bare base grid, every mechanic layer faulting?"""
        return self.obstacle_relief.base

    @property
    def walkthrough_belt(self) -> int:
        """Fullest the conveyor gets on the bare walkthrough, with nothing forcing it.

        The obstacles are laid on top of this order, so this is the baseline they
        are measured against - not ``solution.required_belt``, which is the
        narrowest belt *some* play wins on rather than the one this play uses.
        """
        return max((step.belt_used for step in self.solution.steps), default=0)

    @property
    def obstacle_belt_cost(self) -> int:
        """Extra balls the obstacles park on the conveyor, over the bare walkthrough."""
        return max(0, self.played_belt - self.walkthrough_belt)

    @property
    def played_headroom(self) -> int:
        """Balls of conveyor still free at the tightest moment of the real play."""
        return self.certified_belt - self.played_belt

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
# The eight cells touching one pixel. Balancing works on this neighbourhood
# because a pixel with no neighbour of its own color is a speck: it reads as a
# mistake in the artwork and it opens a one-pixel run in the play order.
NEIGHBOUR_STEPS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


@dataclass
class BalanceReport:
    """What balancing did to the picture, one counter per kind of move.

    The three moves are not equally expensive, and the report keeps them apart so
    the dialog can say which one this picture needed: ``added`` cost the picture
    nothing, ``moved`` traded one color for another in place, and ``removed`` is
    the only one that took artwork away.
    """

    added: Counter[int] = field(default_factory=Counter)
    # (from color, to color) -> pixels recolored, i.e. one color paying another.
    moved: Counter[tuple[int, int]] = field(default_factory=Counter)
    removed: Counter[int] = field(default_factory=Counter)
    emptied_columns: list[int] = field(default_factory=list)

    @property
    def added_pixels(self) -> int:
        return sum(self.added.values())

    @property
    def moved_pixels(self) -> int:
        return sum(self.moved.values())

    @property
    def removed_pixels(self) -> int:
        return sum(self.removed.values())

    @property
    def changed(self) -> bool:
        return bool(self.added or self.moved or self.removed)


def balance_pixel_grid(grid: PixelGridData, unit: int = BALLS_PER_BOX) -> BalanceReport:
    """Make every color count a multiple of ``unit`` while keeping the artwork.

    A box holds exactly nine balls, so a color with a leftover cannot be poured
    into whole boxes. There are three ways to spend that leftover and deleting is
    the worst of them, so it is the last one tried rather than the first:

    1. **Paint** the color up to its next multiple, into empty cells that touch
       that color. Nothing is lost - the picture only grows - so this runs first,
       and it is all-or-nothing per color: stopping halfway leaves the color just
       as unbalanced, having changed the picture for nothing. Colors needing the
       fewest pixels go first, so a picture with little room left still balances
       as many colors as that room can pay for.
    2. **Recolor** a neighbouring color's pixel into it, which is what a full
       picture has left. The pixel stays where it is and only changes color, so
       the silhouette survives untouched; two colors whose leftovers add up to
       nine settle each other exactly this way, and a receiver short of more than
       one donor's leftover collects from several.
    3. **Borrow**, for a color walled in by its neighbours: it has no empty cell
       to grow into, but another color does, so that one is grown by exactly what
       the receiver is short of and hands those pixels straight over. The donor
       ends the trade on the multiple it started on and nothing is deleted, which
       is why this is tried before the last move and not after it.
    4. **Delete**, the only move that takes artwork away. What reaches it is the
       residue none of the others could: a full picture whose colors cannot even
       settle each other, and never more than ``unit - 1`` pixels in total.
    """
    grid.ensure_dense()
    report = BalanceReport()
    if not grid.histogram():
        return report

    pending = _leftovers(grid, unit)

    # 1. Paint. Cheapest color first, so when the empty cells run out the colors
    #    left over are the ones that would have cost the most room.
    for color_id in sorted(pending, key=lambda color: (unit - pending[color], color)):
        need = unit - pending[color_id]
        if len(_grow_color(grid, color_id, need)) == need:
            report.added[color_id] += need
            del pending[color_id]

    # 2. Recolor. Every transfer balances both ends: the receiver takes exactly
    #    what it is short of, and a donor handing over its whole leftover lands on
    #    a multiple itself.
    while pending:
        receiver = max(pending, key=lambda color: (pending[color], -color))
        need = unit - pending[receiver]
        donors = sorted(
            (color for color in pending if color != receiver),
            key=lambda color: (pending[color], color),
        )
        if sum(pending[donor] for donor in donors) < need:
            break
        for donor in donors:
            if not need:
                break
            for _ in range(min(need, pending[donor])):
                target = _transfer_pixel(grid, donor, receiver)
                if target is None:  # pragma: no cover - the leftover guarantees a pixel
                    break
                grid.set_color_id(target[0], target[1], receiver)
                report.moved[(donor, receiver)] += 1
                pending[donor] -= 1
                need -= 1
            if not pending[donor]:
                del pending[donor]
        del pending[receiver]

    # 3. Borrow. A colour with no empty cell of its own is still balanced for
    #    free as long as *some* colour has room: that one grows by what the
    #    receiver is short of and passes it on, ending where it began.
    for receiver in sorted(pending):
        need = unit - pending[receiver]
        for donor in sorted(color for color in grid.histogram() if color != receiver):
            if len(_grow_color(grid, donor, need)) < need:
                continue
            handed = 0
            for _ in range(need):
                target = _transfer_pixel(grid, donor, receiver)
                if target is None:  # pragma: no cover - the donor was just grown
                    break
                grid.set_color_id(target[0], target[1], receiver)
                handed += 1
            report.added[donor] += need
            report.moved[(donor, receiver)] += handed
            del pending[receiver]
            break

    # 4. Delete the residue, bottom-most and edge-most first: pixels are eaten
    #    top-down, so the bottom of the picture is what the player reaches last.
    for color_id in sorted(pending):
        for _ in range(pending[color_id]):
            target = _least_valuable_pixel(grid, color_id)
            if target is None:  # pragma: no cover - histogram guarantees a pixel exists
                break
            grid.set_color_id(target[0], target[1], EMPTY_COLOR_ID)
            report.removed[color_id] += 1

    report.emptied_columns = [
        column
        for column in range(grid.width)
        if all(grid.get_color_id(row, column) == EMPTY_COLOR_ID for row in range(grid.height))
    ]
    return report


def _leftovers(grid: PixelGridData, unit: int) -> dict[int, int]:
    """Pixels past the last whole box, per color, for the colors that have any."""
    return {
        color_id: count % unit
        for color_id, count in sorted(grid.histogram().items())
        if count % unit
    }


def _grow_color(grid: PixelGridData, color_id: int, need: int) -> list[tuple[int, int]]:
    """Paint ``need`` empty cells in ``color_id``, or paint none at all.

    Half a color's need is worth nothing - the count is still not a multiple - so
    a run that cannot finish puts every cell it took back, leaving the picture
    exactly as it found it for the recolor pass to work on.
    """
    painted: list[tuple[int, int]] = []
    for _ in range(need):
        cell = _best_growth_cell(grid, color_id)
        if cell is None:
            for row, column in painted:
                grid.set_color_id(row, column, EMPTY_COLOR_ID)
            return []
        grid.set_color_id(cell[0], cell[1], color_id)
        painted.append(cell)
    return painted


def _best_growth_cell(grid: PixelGridData, color_id: int) -> tuple[int, int] | None:
    """The empty cell that extends ``color_id`` while disturbing the picture least.

    A ball only stops at a painted pixel and the runtime eats each row from the
    right, so a cell with the same color beside it *in its own row* falls inside
    an existing run and costs the conveyor nothing at all. After that it is about
    the artwork: hug the color's own blob, stay inside the picture's bounding box
    rather than growing its outline, and prefer the bottom rows, which are eaten
    last. A cell touching no pixel of that color is never taken - a speck away
    from its color is both a blemish and a fresh one-pixel run.
    """
    bounds = _painted_bounds(grid)
    centre = (grid.width - 1) / 2
    best: tuple[int, int] | None = None
    best_key: tuple[int, int, int, int, float] | None = None
    for row in range(grid.height):
        for column in range(grid.width):
            if grid.get_color_id(row, column) != EMPTY_COLOR_ID:
                continue
            same = _neighbours_of(grid, row, column, color_id)
            if not same:
                continue
            in_run = any(
                0 <= column + step < grid.width
                and grid.get_color_id(row, column + step) == color_id
                for step in (-1, 1)
            )
            inside = bounds is not None and (
                bounds[0] <= row <= bounds[2] and bounds[1] <= column <= bounds[3]
            )
            key = (0 if in_run else 1, -same, 0 if inside else 1, -row, abs(column - centre))
            if best_key is None or key < best_key:
                best, best_key = (row, column), key
    return best


def _transfer_pixel(grid: PixelGridData, donor_id: int, receiver_id: int) -> tuple[int, int] | None:
    """The donor pixel that already reads most like the receiver: their border.

    Recoloring on the border grows the receiver's blob by one cell and shaves the
    donor's edge, which is the least a swap can show. A pixel taken from the
    middle of the donor would punch a hole in it, so the count of the donor's own
    neighbours breaks the tie the other way.

    Preferring a pixel that joins a run of the receiver *in its own row* was
    tried and measured: it does cut the run count on every picture, but it
    consistently raised the belt the picture needs. The peak is set by how many
    colours are live at once, not by how many runs there are, and moving the
    receiver's pixels around inside the play order moves that peak the wrong way
    as often as not. So the choice stays about the artwork.
    """
    best: tuple[int, int] | None = None
    best_key: tuple[int, int, int, float] | None = None
    centre = (grid.width - 1) / 2
    for row in range(grid.height):
        for column in range(grid.width):
            if grid.get_color_id(row, column) != donor_id:
                continue
            key = (
                -_neighbours_of(grid, row, column, receiver_id),
                _neighbours_of(grid, row, column, donor_id),
                -row,
                abs(column - centre),
            )
            if best_key is None or key < best_key:
                best, best_key = (row, column), key
    return best


def _neighbours_of(grid: PixelGridData, row: int, column: int, color_id: int) -> int:
    """How many of the eight cells around this one carry ``color_id``."""
    return sum(
        1
        for row_step, column_step in NEIGHBOUR_STEPS
        if 0 <= row + row_step < grid.height
        and 0 <= column + column_step < grid.width
        and grid.get_color_id(row + row_step, column + column_step) == color_id
    )


def _painted_bounds(grid: PixelGridData) -> tuple[int, int, int, int] | None:
    """``(top, left, bottom, right)`` of everything painted, or None on a blank grid."""
    painted = [
        (row, column)
        for row in range(grid.height)
        for column in range(grid.width)
        if grid.get_color_id(row, column) != EMPTY_COLOR_ID
    ]
    if not painted:
        return None
    return (
        min(row for row, _ in painted),
        min(column for _, column in painted),
        max(row for row, _ in painted),
        max(column for _, column in painted),
    )


def balance_summary(
    added: Counter[int], moved: Counter[tuple[int, int]], removed: Counter[int]
) -> str:
    """The three balance moves in one Vietnamese line, for the dialog and report."""
    parts: list[str] = []
    if added:
        parts.append(f"thêm {sum(added.values())} pixel vào chỗ trống ({_color_counts(added)})")
    if moved:
        parts.append(
            f"đổi màu {sum(moved.values())} pixel ("
            + ", ".join(
                f"{COLOR_NAMES.get(source, source)}→{COLOR_NAMES.get(target, target)} {count}"
                for (source, target), count in sorted(moved.items())
            )
            + ")"
        )
    if removed:
        parts.append(f"xoá {sum(removed.values())} pixel dư ({_color_counts(removed)})")
    return ", ".join(parts) if parts else "mọi màu đã chia hết, không phải sửa gì"


def _color_counts(counts: Counter[int]) -> str:
    return ", ".join(
        f"{COLOR_NAMES.get(color, color)} {count}" for color, count in sorted(counts.items())
    )


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


def snug_store(
    box_count: int, stored: int, tunnels: int, max_cols: int, max_rows: int
) -> int:
    """Nudge a tunnel load until the surface fills its rectangle exactly.

    The box grid is a rectangle, so a surface that does not fill one leaves slots
    over - and an empty slot is a wall to the player, whatever the tier called it.
    A level that never bought the wall mechanic should not sprout one by accident,
    and the tunnels are the elastic part of the layout: they can swallow a box
    more or a box less without changing anything the player counts. So the load
    moves to the nearest size that packs, and stays put only if none does.
    """
    capacity = max_cols * max_rows
    # Never below what the picture forces into tunnels, and never so deep that a
    # tunnel is left holding nothing.
    floor = max(tunnels, box_count - (capacity - tunnels))
    for candidate in sorted(
        range(floor, box_count), key=lambda value: (abs(value - stored), value)
    ):
        wanted = box_count - candidate + tunnels
        if wanted > capacity:
            continue
        cols, rows = choose_lattice(wanted, max_cols, max_rows)
        if cols * rows == wanted:
            return candidate
    return stored


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


def tunnel_depth_for(options: AutoGenOptions, profile: DifficultyProfile) -> int:
    """Boxes one tunnel is meant to hold at this tier, never below a real queue."""
    return max(2, options.tunnel_depth or profile.tunnel_depth)


def tunnels_for_overflow(box_count: int, capacity: int, depth: int) -> int:
    """Fewest tunnels whose queues, ``depth`` boxes deep, swallow the overflow.

    A tunnel is not free storage: it takes a surface slot of its own, so ``t``
    tunnels leave ``capacity - t`` slots and have to hold ``box_count -
    (capacity - t)`` boxes. Solving that for ``t`` is where the ``depth - 1``
    comes from - each tunnel only buys ``depth - 1`` boxes of headroom.
    """
    overflow = box_count - capacity
    if overflow <= 0:
        return 0
    return -(-overflow // max(1, depth - 1))


def tunnel_ceiling(
    box_count: int, capacity: int, options: AutoGenOptions, profile: DifficultyProfile
) -> int:
    """Most tunnels this level may carry, read off the picture when left on Auto.

    A typed ``max_tunnels`` is an instruction and stands. Auto measures instead:
    a tunnel is a permanent hole in the surface, so it is rationed like a wall -
    one per :data:`TUNNEL_BOX_BUDGET` boxes, and never more than
    :data:`TUNNEL_LATTICE_SHARE` of the lattice.

    Whatever comes out of that, the ceiling is then lifted to whatever an
    overflowing picture cannot be built without: a ceiling is there to stop a
    tier from spending tunnels it does not need, never to refuse the ones that
    are the only reason the picture fits at all.
    """
    if options.max_tunnels > 0:
        ceiling = max(1, options.max_tunnels)
    else:
        ceiling = max(
            profile.tunnels,
            min(box_count // TUNNEL_BOX_BUDGET, max(1, capacity // TUNNEL_LATTICE_SHARE)),
        )
    return max(ceiling, tunnels_for_overflow(box_count, capacity, MAX_TUNNEL_DEPTH))


def tunnel_dose(box_count: int, profile: DifficultyProfile) -> int:
    """How many tunnels the tier wants on a grid of this many boxes.

    ``profile.tunnels`` is the dose for a hand-made grid of
    :data:`REFERENCE_BOXES` boxes; a picture carrying twice that carries twice
    the dose, so a big picture is not run through the same pair of queues a small
    one gets. It never drops below the tier's own number: that is the floor the
    tier was written with.
    """
    return max(profile.tunnels, round(profile.tunnels * box_count / REFERENCE_BOXES))


def plan_tunnels(
    box_count: int,
    capacity: int,
    options: AutoGenOptions,
    profile: DifficultyProfile,
    *,
    mechanic: bool,
) -> tuple[int, int]:
    """How many tunnels to build and how many boxes they swallow.

    A tunnel pays for itself twice: it stores boxes, but it also eats a surface
    slot forever, because an emptied tunnel stays on the grid as a wall. So an
    overflowing picture needs tunnels for ``box_count - (capacity - tunnels)``
    boxes, not just for ``box_count - capacity``.

    When ``mechanic`` is set the tunnels are wanted for their own sake - the
    obstacle plan spent budget on them - so the tier's dose and depth apply even
    when everything would have fit in the lattice; :func:`tunnel_dose` reads that
    dose off the picture rather than handing every level the same one or two. An
    explicit ``tunnel_count`` says the same thing in plain numbers, so it also
    lifts the ceiling — a bound that only exists to keep the automatic answer
    sensible should not veto a number the designer typed. Tunnels switched off
    still win over it: there is no such thing as a disabled tunnel that exists
    anyway.

    An overflowing picture then gets as many tunnels as it takes to keep every
    queue down to the tier's own depth, so the boxes the lattice cannot hold
    spread across several shallow tunnels instead of being stacked into one deep
    one. Either way this is a floor, not a cap.
    """
    depth = tunnel_depth_for(options, profile)
    max_tunnels = tunnel_ceiling(box_count, capacity, options, profile)
    if options.tunnel_count is not None and options.allow_tunnels:
        wanted = max(0, options.tunnel_count)
        max_tunnels = max(max_tunnels, wanted)
    else:
        wanted = min(tunnel_dose(box_count, profile), max_tunnels) if mechanic else 0
    tunnels = wanted
    if box_count > capacity - tunnels:
        # Spread the overflow at the tier's depth where the ceiling allows it, and
        # never leave it under what the deepest legal queue could hold.
        tunnels = max(
            tunnels,
            1,
            min(
                max_tunnels,
                max(1, capacity // TUNNEL_SPREAD_SHARE),
                tunnels_for_overflow(box_count, capacity, depth),
            ),
            tunnels_for_overflow(box_count, capacity, MAX_TUNNEL_DEPTH),
        )
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
    # Asking for a number of tunnels means wanting them as a mechanic, so they are
    # filled to the difficulty's depth rather than left holding one box each.
    as_mechanic = mechanic or options.tunnel_count is not None
    fill = options.tunnel_depth or (profile.tunnel_depth if as_mechanic else 1)
    stored = max(forced, min(tunnels * fill, box_count - 1))
    return tunnels, stored


def resolve_tunnel_placement(options: AutoGenOptions, profile: DifficultyProfile) -> str:
    """Which placement this run uses, with ``auto`` handed to the difficulty."""
    if options.tunnel_placement == "auto":
        return profile.tunnel_placement
    return options.tunnel_placement


def _tunnel_order(
    slots: list[tuple[int, int]], placement: str, rng: random.Random
) -> list[tuple[int, int]]:
    """Slots to try for a tunnel, best first, for one placement.

    ``back`` is what the hand-made levels do: the row furthest from the player,
    outermost column first, because a permanent hole hurts least on an edge and
    the outer columns keep the middle of the grid readable.

    ``front`` is the same shape mirrored onto ``slot_y == 0``, the row the player
    eats first - the tunnel then stands in the way from the opening tap rather
    than at the end. ``random`` gives up the edge preference entirely, so a
    tunnel can land mid-grid and force the player to route around it.
    """
    centre = max(slot_x for slot_x, _ in slots) / 2
    if placement == "random":
        shuffled = list(slots)
        rng.shuffle(shuffled)
        return shuffled
    if placement == "front":
        return sorted(slots, key=lambda slot: (slot[1], -abs(slot[0] - centre), slot[0]))
    return sorted(slots, key=lambda slot: (-slot[1], -abs(slot[0] - centre), slot[0]))


def tunnels_can_release(
    chosen: list[tuple[int, int]], cols: int, rows: int
) -> bool:
    """Does every tunnel here still have a neighbour that could hold a box?

    A tunnel hands its queue out through one side, and that side has to be a real
    box: a wall never opens and an emptied tunnel stays on the grid as one, so a
    mouth aimed at either is sealed for the whole level. :func:`tunnel_directions`
    keeps the best side a tunnel has and :func:`sealed_tunnel_mouths` then fails
    the layout - but that is a fault the layout can *avoid* rather than discover,
    by simply not parking a tunnel where it walls another one in.

    Which is exactly what used to happen to an overflowing picture. The back row
    fills with tunnels, the next tunnel goes in the row in front of it, and the
    tunnel behind that slot now has nothing but tunnels on every side: a picture
    of 81 boxes on a 64-slot lattice laid nine tunnels, sealed the corner one and
    refused the whole level. Skipping the candidate instead sends the search on
    to the next row but one, where the row between them is still boxes and every
    mouth opens.
    """
    taken = set(chosen)
    return all(
        any(
            neighbour not in taken for neighbour in slot_neighbours(slot, cols, rows)
        )
        for slot in chosen
    )


def _tunnel_slots(
    slots: list[tuple[int, int]],
    count: int,
    cols: int,
    rows: int,
    placement: str,
    rng: random.Random,
) -> list[tuple[int, int]]:
    """Park ``count`` tunnels, in the order ``placement`` prefers.

    Every pick is checked twice, against the two ways a tunnel can break a
    layout that no replay would notice:

    * :func:`layout_is_open` - a tunnel is a permanent hole, so once it moves off
      the back edge it can seal a *box* away from every approach, and a level
      with an unreachable box is not a harder level, it is an unplayable one.
    * :func:`tunnels_can_release` - a tunnel walled in by other tunnels has no
      box to hand its own queue to, so the boxes inside it never come out.

    Candidates failing either are skipped, which is what makes the back rows fill
    in alternating order once one of them is full: a solid row of tunnels needs
    the row in front of it to stay boxes, so the next tunnel goes one row further
    in.

    Both checks are **preferences, not vetoes**. A placement that cannot seat
    them all falls back to the back rows, and then to seating them anywhere at
    all, rather than failing the run: the position is a flavour of the level and
    a free mouth is a property of a good one, but neither is worth losing the
    level over. A lattice too cramped to give every tunnel a box - three slots
    asked for two tunnels, say - then lands a sealed mouth, which
    :func:`sealed_tunnel_mouths` reports as a fault and the relief ladder answers
    by stepping the form down or shipping the bare base grid. That is the path
    that already existed for it, and it degrades where raising here would not.
    """
    if count <= 0:
        return []
    chosen: list[tuple[int, int]] = []
    orders = (_tunnel_order(slots, placement, rng), _tunnel_order(slots, "back", rng))
    # Strict first, so a lattice with room to keep every mouth free does. Only a
    # lattice that cannot is allowed to seat a tunnel that walls another one in.
    for free_mouths in (True, False):
        for order in orders:
            for slot in order:
                if len(chosen) >= count:
                    break
                if slot in chosen:
                    continue
                if not layout_is_open(cols, rows, [], chosen + [slot]):
                    continue
                if free_mouths and not tunnels_can_release(chosen + [slot], cols, rows):
                    continue
                chosen.append(slot)
            if len(chosen) >= count:
                break
        if len(chosen) >= count:
            break
    if len(chosen) < count:  # pragma: no cover - plan_tunnels keeps a slot per tunnel
        raise AutoGenError("The box grid lattice has fewer slots than the level needs tunnels.")
    return sorted(chosen, key=lambda slot: (slot[1], slot[0]))


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


def sealed_tunnel_mouths(
    mouths: list[tuple[tuple[int, int], Direction]], box_slots: set[tuple[int, int]]
) -> list[tuple[tuple[int, int], Direction]]:
    """Tunnels whose mouth faces no box, so their queue can never be handed out.

    :func:`tunnel_directions` keeps the best side a tunnel has even when no side
    holds a box, because on a small lattice there is nothing better to point at.
    That leaves the one failure the gameplay model cannot see: the simulation taps
    a queue by index and never asks where the mouth points, so a level with a
    sealed tunnel replays as a win and is unplayable in the runtime.

    So it is checked here instead, against the finished layout, and a layout that
    has one is not shipped - see :attr:`ObstacleLayer.faults`.
    """
    return [
        (slot, facing)
        for slot, facing in mouths
        if (slot[0] + DIRECTION_STEPS[facing][0], slot[1] + DIRECTION_STEPS[facing][1])
        not in box_slots
    ]


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
    profile: DifficultyProfile,
    plan: ObstaclePlan,
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

    tunnel_count, stored = plan_tunnels(
        len(specs), capacity, options, profile, mechanic=plan.has("tunnel")
    )

    if not plan.has("wall") and tunnel_count:
        stored = snug_store(len(specs), stored, tunnel_count, max_cols, max_rows)

    # Walls need slots of their own, so the lattice is sized for them up front -
    # asking for them afterwards would only steal room the boxes already claimed.
    walls = plan_walls(len(specs) - stored, options, profile) if plan.has("wall") else 0
    walls = min(walls, max(0, capacity - (len(specs) - stored) - tunnel_count))
    cols, rows = choose_lattice(
        min(len(specs) - stored + tunnel_count + walls, capacity), max_cols, max_rows
    )
    slots = _slot_sequence(cols, rows)
    tunnel_slots = _tunnel_slots(
        slots, tunnel_count, cols, rows, resolve_tunnel_placement(options, profile), rng
    )
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
def plan_hidden_count(
    surface_boxes: int, options: AutoGenOptions, profile: DifficultyProfile
) -> int:
    """How many surface boxes to hide, before knowing which ones can take it.

    A plain count is what the designer asked for, so it beats the share; the share
    is the Auto answer behind it, and the difficulty's own share behind that.
    """
    if options.hidden_boxes is not None:
        return max(0, min(options.hidden_boxes, surface_boxes))
    ratio = profile.hidden_ratio if options.hidden_ratio is None else options.hidden_ratio
    if not 0.0 <= ratio <= 1.0:
        raise AutoGenError(f"Hidden ratio must be between 0 and 1, got {ratio}.")
    return max(0, min(round(ratio * surface_boxes), surface_boxes))


def choose_hidden(
    placements: list[Placement],
    wanted: int,
    rng: random.Random,
) -> set[int]:
    """Pick which ``wanted`` surface boxes carry ``Hidden``, rarest color first.

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
    if wanted <= 0:
        return set()
    candidates = [placement for placement in placements if placement.slot_y > 0]
    wanted = min(len(candidates), wanted)
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
def plan_link_count(
    surface_boxes: int,
    options: AutoGenOptions,
    profile: DifficultyProfile,
    scan: PictureScan,
    plan: ObstaclePlan,
) -> int:
    """How many LinkedContainer pairs to tie, before knowing which boxes can take one.

    The picture's own reading of a link is exact and happens later, in
    :func:`plan_links`: every candidate pair is replayed against the real belt and
    dropped if it loses, and at the easy tiers it is dropped unless the conveyor is
    back to empty afterwards. So this only sizes the request; the picture gets the
    last word on which pairs survive it.
    """
    if not plan.has("linked"):
        return 0
    wanted = profile.linked_pairs if options.linked_pairs is None else options.linked_pairs
    if wanted <= 0:
        return 0
    # Two boxes per pair, and a pair spends two tray slots on one tap, so a small
    # grid cannot carry the same number of links a large one shrugs off.
    wanted = min(wanted, surface_boxes // LINK_BOX_BUDGET)
    return max(0, wanted)


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


def belt_residues(
    board: BoardState, groups: list[list[BoxSpec]], rules: GameRules
) -> list[int] | None:
    """Balls still on the conveyor after each pick drains, or ``None`` if it loses.

    :func:`simulate_groups` only answers "does this win", but an easy tier needs
    the stronger question: does this pick leave the player *clean*? A pair that
    wins while parking eight balls on the belt for the next twenty picks is a
    perfectly legal level and a miserable easy one, and the residue is the only
    thing that tells the two apart.
    """
    board = board.clone()
    tray: list[TrayBox] = []
    residues: list[int] = []
    for group in groups:
        drain(board, tray)
        tray = [box for box in tray if box.remaining > 0]
        if not can_tap(tray, rules, len(group)):
            return None
        for spec in group:
            tray.append(TrayBox(spec.color, spec.size, spec.size))
        drain(board, tray)
        tray = [box for box in tray if box.remaining > 0]
        residues.append(belt_used(tray))
    drain(board, tray)
    tray = [box for box in tray if box.remaining > 0]
    if not board.done() or tray:
        return None
    return residues


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
    clean: bool = False,
) -> tuple[list[tuple[Placement, Placement, int]], list[list[int]]]:
    """Tie up to ``count`` pairs, keeping only the ones the conveyor survives.

    A link is never fair by construction: dropping two boxes on one tap needs
    room for both at that instant, and a ``stall`` partner then squats on the
    belt for the next ``gap`` picks. So each candidate is tried against a full
    replay and kept only if the run still wins - the level stays beatable no
    matter how mean the pairing looks.

    ``clean`` adds the easy-tier promise on top: the pair must also drain to
    nothing the moment it lands, so both halves clear straight onto the picture
    and the player is never left holding a partner with nowhere to put it.
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
        specs = [[order[index] for index in group] for group in trial]
        if clean:
            residues = belt_residues(board, specs, rules)
            if residues is None:
                continue
            spot = next(
                slot for slot, group in enumerate(trial) if left.order_index in group
            )
            if residues[spot] > CLEAN_LINK_RESIDUE:
                continue
        elif not simulate_groups(board, specs, rules):
            continue
        chosen.append((left, right, gap))
        used.update({left.order_index, right.order_index})
        groups = trial
    return chosen, groups


# --------------------------------------------------------------------------- #
# Stage 7 - lock boxes behind an arrow
# --------------------------------------------------------------------------- #
def plan_arrow_count(
    surface_boxes: int,
    options: AutoGenOptions,
    profile: DifficultyProfile,
    scan: PictureScan,
    plan: ObstaclePlan,
) -> int:
    """How many boxes to lock behind an arrow, before knowing which ones can take one.

    An arrow never costs conveyor: the key is always a box the certified order
    opens *earlier*, so a player following that order is never held up by a lock.
    What a lock costs is an alternative - one fewer box the player could have
    tapped instead - and a fragmented picture hardly has any, because the colour
    it needs next all but dictates the pick. So the dose shrinks with the
    fragmentation the scanner measured, on the same reading that raised the tier.
    """
    if not plan.has("arrow"):
        return 0
    if options.arrow_boxes is not None:
        wanted = options.arrow_boxes
    else:
        ratio = profile.arrow_ratio if options.arrow_ratio is None else options.arrow_ratio
        dose = ratio * surface_boxes
        fragmentation = min(1.0, max(0.0, scan.fragmentation))
        # A tier that wants locks at all keeps one: reading the picture is meant to
        # thin the dose, not to cancel the mechanic the budget just paid for.
        wanted = max(1, round(dose * (1.0 - fragmentation))) if round(dose) >= 1 else 0
    if wanted <= 0:
        return 0
    # A locked box is unavailable until its key goes, so locking too many at once
    # leaves the player staring at a grid with nothing tappable on it.
    return min(wanted, surface_boxes // ARROW_BOX_BUDGET)


def arrow_candidates(
    placements: list[Placement],
    position: dict[int, int],
    blocked: set[int],
    reach: str = "far",
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

    ``reach`` picks between the two forms of the mechanic, which is what keeps an
    easy level easy even though it carries the same obstacle:

    * ``"far"`` aims at the *earliest* legal key, so the wait is as long as the
      order allows and the box stays shut for most of the level.
    * ``"near"`` aims at the box opened immediately before, so the lock is
      already open by the time the player reaches it. The arrows then read as a
      route drawn across the grid - "this one, then this one" - rather than as a
      puzzle to solve, which is what an easy tier wants from them.
    """
    if reach not in ARROW_REACH:
        raise AutoGenError(f"Unsupported arrow reach {reach!r}.")
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
            wait = position[placement.order_index] - position[key.order_index]
            # "near" wants the smallest wait, so the same comparison works on a
            # negated key rather than needing a second branch below.
            option = (
                -wait if reach == "near" else wait,
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
    reach: str = "far",
) -> dict[int, tuple[Direction, Placement]]:
    """Pick which boxes get an ArrowLock, scattered over the grid.

    ``blocked`` holds the boxes that must stay plain: the hidden ones, because a
    box that shows neither its color nor an open state is unreadable, and the
    linked ones, because the validator forbids a LinkedContainer from targeting an
    ArrowLock box.
    """
    if count <= 0:
        return {}
    candidates = arrow_candidates(placements, position, blocked, reach)
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
# --------------------------------------------------------------------------- #
# Stages 11 and 12 - freeze boxes, slab over regions
# --------------------------------------------------------------------------- #
# Both locks open on the same number: pixels the picture has already lost. So
# both are laid *after* the play order is fixed, and both are read out of it
# rather than imposed on it - `tap_progress` says how much of the picture is
# gone by the time the winning line reaches a box, and a lock on that box may
# not ask for more than that. Which is why neither can cost the level its proof,
# and why neither needs the relief ladder the other five go through.
#
# What a lock costs is the player's *freedom*: the box behind it cannot be
# tapped early to clear the conveyor, cannot be tapped out of curiosity, and in
# a slab's case four of them go at once. The tier decides where in the level
# that happens (`frozen_at`, `block_at`) and how tight it is (`lock_window`).
def round_lock(value: int, rounding: str) -> int:
    """Write a lock's number the way the designer asked, always rounding *down*.

    Down, never to the nearest: the value handed in is a safety ceiling, and
    rounding up would step over it and hand the level a lock that opens after
    the winning line needed the box behind it.
    """
    if value < 1:
        return 0
    if rounding == "none":
        return value
    if rounding == "odd":
        return value if value % 2 else value - 1
    if rounding == "five":
        return value - value % 5
    if rounding == "ten":
        return value - value % 10
    raise AutoGenError(f"Unknown lock rounding {rounding!r}.")


def lock_target(band: tuple[float, float] | float, total: int, rng: random.Random) -> int:
    """Where in the picture one lock opens, in pixels, rolled inside the tier's band."""
    if isinstance(band, tuple):
        low, high = band
        share = rng.uniform(low, high) if high > low else low
    else:
        share = band
    return max(0, round(share * total))


def lock_count(target: int, ceiling: int, window: int, rounding: str) -> int:
    """The number to write: as late as the tier asked, as tight as it demands.

    ``target`` is where in the picture the tier wants this lock to open, and
    ``ceiling`` is the latest it may open at all and still be safe. Honouring
    the target alone is right when the two are close, and decoration when they
    are not: a lock that lifts at 29 on a box the winning line does not want
    until 126 has already been cleared by the time it could have cost anybody
    anything. The obstacle is on the grid and does nothing.

    ``lock_window`` is the tier's statement of how close is close enough, so
    when the gap is wider than that the count is lifted toward the ceiling until
    the gap *is* the window. The tier's share then reads as a floor - "no earlier
    than this" - rather than as an exact mark, which is the reading that keeps
    the mechanic honest on a grid whose boxes do not happen to fall where the
    band wanted them.

    ``ceiling`` is still never crossed, and the value is still rounded *down*,
    so nothing about the safety of the number changes - only the point of it.
    """
    if ceiling < 1:
        return 0
    return round_lock(min(ceiling, max(target, ceiling - max(0, window))), rounding)


def plan_frozen_count(
    surface_boxes: int, options: AutoGenOptions, profile: DifficultyProfile
) -> int:
    """How many surface boxes carry a Frozen lock, before knowing which ones can."""
    if options.frozen_boxes is not None:
        return max(0, min(options.frozen_boxes, surface_boxes))
    ratio = profile.frozen_ratio
    if not 0.0 <= ratio <= 1.0:
        raise AutoGenError(f"Frozen ratio must be between 0 and 1, got {ratio}.")
    return max(0, min(round(ratio * surface_boxes), surface_boxes))


def block_span_for(room: int, profile: DifficultyProfile) -> tuple[int, int]:
    """How big one slab is, in box slots, read off the room the picture leaves."""
    return BLOCK_WIDE_SPAN if room >= BLOCK_WIDE_ROOM else profile.block_span


def block_span_ladder(room: int, profile: DifficultyProfile) -> list[tuple[int, int]]:
    """The slab sizes to try, biggest first, down to a pair.

    A slab needs a *solid* rectangle of the lattice, and walls and tunnel mouths
    cut the lattice into pieces. On a fragmented grid there is no 2x2 of real
    boxes anywhere - measured on a 24x24 picture, SuperHard found none at all in
    13 of 15 seeds - and the run then bought ``LargeBlock`` and shipped nothing.
    That is a mechanic *removed*, not a mechanic dosed down, and removing one is
    the budget's job rather than the geometry's.

    So the size steps down until one fits, the way every other dose in here is
    relieved rather than dropped. The last rung is a pair, either way up, which
    is still the thing a slab is and the thing a Frozen box is not: two boxes
    behind one counter, opaque until it lifts, lifting together.
    """
    ladder = [block_span_for(room, profile)]
    for span in (profile.block_span, (2, 2), (2, 1), (1, 2)):
        if span not in ladder:
            ladder.append(span)
    return ladder


def block_room_scale(room: int) -> float:
    """How much of the tier's opening share a picture with this much room pays.

    A tight picture opens its slabs earlier than the tier asks - the level is
    already under pressure and does not need a quarter of its grid dark for as
    long. Full room pays the tier's number as written.
    """
    ease = min(1.0, max(0, room) / BLOCK_ROOM_FULL)
    return BLOCK_TIGHT_SHARE + (1.0 - BLOCK_TIGHT_SHARE) * ease


def plan_block_count(
    surface_boxes: int,
    options: AutoGenOptions,
    profile: DifficultyProfile,
    span: tuple[int, int] | None = None,
) -> int:
    """How many slabs to try to fit, before knowing whether the grid has room."""
    span_x, span_y = span or profile.block_span
    slots = max(1, span_x * span_y)
    afford = surface_boxes // (BLOCK_BOX_BUDGET * slots)
    wanted = profile.blocks if options.blocks is None else options.blocks
    return max(0, min(wanted, afford, len(profile.block_at) if options.blocks is None else wanted))


@dataclass(frozen=True)
class BoxLock:
    """One Frozen box: which box, what number, and how much room was left over."""

    order_index: int
    slot: tuple[int, int]
    color: int
    count: int
    target: int
    ceiling: int

    @property
    def trimmed(self) -> bool:
        """The grid could not bear the tier's number, so the lock opens earlier."""
        return self.count < self.target

    @property
    def slack(self) -> int:
        """Pixels between the lock opening and the winning line wanting the box."""
        return max(0, self.ceiling - self.count)


@dataclass(frozen=True)
class Slab:
    """One LargeBlock: the rectangle, the boxes under it, and its number."""

    slot_x: int
    slot_y: int
    span_x: int
    span_y: int
    covered: tuple[int, ...]
    count: int
    target: int
    ceiling: int

    @property
    def slots(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (self.slot_x + dx, self.slot_y + dy)
            for dy in range(self.span_y)
            for dx in range(self.span_x)
        )

    @property
    def rect(self) -> tuple[int, int, int, int]:
        """The slab in box-grid cells, which is what the level file stores."""
        return (
            self.slot_x * SLOT,
            self.slot_y * SLOT,
            self.span_x * SLOT,
            self.span_y * SLOT,
        )

    @property
    def mass(self) -> int:
        """Balls held behind this slab."""
        return len(self.covered) * BALLS_PER_BOX

    @property
    def trimmed(self) -> bool:
        return self.count < self.target

    @property
    def slack(self) -> int:
        return max(0, self.ceiling - self.count)


@dataclass(frozen=True)
class ColorSupply:
    """What one colour can pay for, read off the *picture* rather than a play order.

    ``wanted`` is every pixel number at which the frontier asks for this colour,
    in order, and ``balls`` is how many balls of it the whole grid holds. Those
    two facts answer the only question a progress lock has to settle before it
    is written: shut this many balls of this colour away, and the picture stops
    dead at *which* pixel.
    """

    color: int
    wanted: tuple[int, ...]
    balls: int

    @property
    def pixels(self) -> int:
        return len(self.wanted)


def read_color_supply(
    sequence: Sequence[int], order: list[BoxSpec]
) -> dict[int, ColorSupply]:
    """Where the picture asks for each colour, and how many balls of it exist.

    This is the read the two progress locks are placed from, and it is done
    before any lock is chosen. Only the frontier colour can be spent, so a box
    clears pixels at the moments its own colour comes up and at no others - and
    that list of moments is a property of the picture alone, the same for every
    order the player might tap in.
    """
    wanted: dict[int, list[int]] = {}
    for pixel, color in enumerate(sequence):
        wanted.setdefault(color, []).append(pixel)
    balls: Counter[int] = Counter()
    for spec in order:
        balls[spec.color] += spec.size
    return {
        color: ColorSupply(color, tuple(spots), balls.get(color, 0))
        for color, spots in wanted.items()
    }


def lock_reach(
    supply: dict[int, ColorSupply],
    order: list[BoxSpec],
    shut: dict[int, int],
    candidate: Iterable[int],
    total: int,
) -> int:
    """Highest number a lock over ``candidate`` can carry and still be opened.

    ``progress`` bounds a lock by the one order the run certified. This bounds
    it by the *picture*, which is a far stronger statement: the picture is paid
    for in one direction, so the ``n``-th pixel of a colour cannot clear until
    ``n`` balls of that colour have been poured. Hold some of them back behind a
    counter and the picture stops at the first pixel it can no longer pay for -
    and because both locks open on progress, a picture that stops there never
    opens anything again, whatever order the player tapped in.

    So for each colour under the lock: walk the pixels the picture asks that
    colour for, subtract the balls already shut away by locks written earlier,
    subtract the balls this lock would shut, and the first pixel left unpayable
    is the ceiling. ``total`` - the whole picture - means nothing constrains it.
    """
    adding: Counter[int] = Counter()
    for index in candidate:
        adding[order[index].color] += order[index].size
    held: dict[int, list[tuple[int, int]]] = {}
    for index, count in shut.items():
        if count > 0:
            held.setdefault(order[index].color, []).append((count, order[index].size))

    reach = total
    for color, balls in adding.items():
        info = supply.get(color)
        if info is None:
            continue
        earlier = held.get(color, ())
        for position, pixel in enumerate(info.wanted):
            # Locks written earlier are only in the way while they are still
            # shut, which is why the comparison is against this pixel and not
            # against the lock being written.
            already = sum(size for count, size in earlier if count > pixel)
            if info.balls - already - balls < position + 1:
                reach = min(reach, pixel)
                break
    return reach


def locks_open(
    sequence: Sequence[int],
    order: list[BoxSpec],
    frozen: list["BoxLock"],
    slabs: list["Slab"],
) -> list[str]:
    """Every pixel a locked picture cannot pay for in *any* tap order. Empty passes.

    :func:`locks_hold` proves the certified line never waits on a lock. This
    proves nobody else can either: a box pours nothing until its own counter has
    opened, so the balls that can pay pixel ``q`` are the ones on boxes numbered
    at most ``q``. Walk the picture once, compare what it has asked of each
    colour against what has been let out, and the first place demand passes
    supply is a pixel no order gets past.

    Derived from the same numbers the planners are bounded by, so like
    ``locks_hold`` this can only fail on a bug - which is why it runs.
    """
    shut: dict[int, int] = {}
    for lock in frozen:
        shut[lock.order_index] = max(shut.get(lock.order_index, 0), lock.count)
    for slab in slabs:
        for index in slab.covered:
            shut[index] = max(shut.get(index, 0), slab.count)
    if not shut:
        return []

    opened: dict[int, list[tuple[int, int]]] = {}
    for index, spec in enumerate(order):
        opened.setdefault(spec.color, []).append((shut.get(index, 0), spec.size))

    asked: Counter[int] = Counter()
    for pixel, color in enumerate(sequence):
        asked[color] += 1
        poured = sum(size for count, size in opened.get(color, ()) if count <= pixel)
        if asked[color] > poured:
            names = sorted(
                count for count, _ in opened.get(color, ()) if count > pixel
            )
            return [
                f"tranh dừng ở pixel {pixel} (màu {color}): cần {asked[color]} bóng, "
                f"chỉ có {poured} bóng đã mở khoá — khoá còn đóng: {names}"
            ]
    return []


def _pick_lock(
    available: list[tuple[int, int]], target: int, window: int
) -> tuple[int, int] | None:
    """The (ceiling, key) whose ceiling sits closest *above* ``target``.

    Closest above is what makes a lock bite: the winning line reaching the box
    right after the lock lifts means the player spent the whole stretch before
    it unable to touch that box. A ceiling far above ``target`` is a lock that
    opened long before anyone wanted the box - legal, and decoration. So the
    tier's ``lock_window`` is tried first and the search widens only if nothing
    in the grid falls inside it.

    Nothing at or above ``target`` at all means the tier's number does not fit
    this grid; the highest ceiling is returned instead and the caller writes a
    smaller number than the tier asked for.
    """
    if not available:
        return None
    inside = [item for item in available if 0 <= item[0] - target <= window]
    above = [item for item in available if item[0] >= target]
    if inside:
        return min(inside, key=lambda item: (item[0] - target, item[1]))
    if above:
        return min(above, key=lambda item: (item[0] - target, item[1]))
    return max(available, key=lambda item: (item[0], -item[1]))


def plan_frozen(
    placements: list[Placement],
    order: list[BoxSpec],
    supply: dict[int, ColorSupply],
    progress: dict[int, int],
    shut: dict[int, int],
    wanted: int,
    total: int,
    profile: DifficultyProfile,
    options: AutoGenOptions,
    banned: set[int],
    rng: random.Random,
) -> list[BoxLock]:
    """Pick which surface boxes freeze, and at what number.

    Three rules keep a Frozen box from being a dead level rather than a hard
    one, and they are applied in that order: what the *picture* can pay for
    decides which boxes are even eligible, then which of them is picked, and
    only then the number written on it.

    **The colour first.** The picture is cleared by a single frontier, so a box
    clears pixels at the moments its own colour comes up and at no others. If
    the colour the frontier wants has only one box left and that box is frozen,
    nothing can advance - and because the lock opens on *progress*, nothing
    advancing means the lock never opens either. That is not difficulty, it is
    an unwinnable file. So a lock only ever goes on a colour that still has an
    unlocked box to serve the frontier while it is shut, and ``shut`` is what
    makes that count honest: a spare already sitting under a slab, or frozen by
    an earlier round of this loop, is not a spare.

    **Then the ceiling**, which is two bounds at once and the tighter wins:

    * ``progress`` - how much of the picture is gone when the winning line
      reaches this box. Below it, the certified line never waits on a lock.
    * :func:`lock_reach` - how far the picture can be paid for *at all* with
      this box's balls held back. Below it, no tap order can stall, not just
      the certified one.

    Boxes already tied into a LinkedContainer are left out entirely: the
    validator makes both halves of a pair carry identical effects, so freezing
    one would mean freezing its partner at the same number, and the partner's
    own ceiling is a different number.
    """
    if wanted <= 0:
        return []
    margin = max(0, options.lock_margin)
    window = round(profile.lock_window * total)
    # Boxes of each colour that nothing has shut away yet. Decremented as this
    # loop writes locks, so the "another box of its colour" rule is measured
    # against what is actually still tappable rather than against a head count.
    free_boxes = Counter(
        spec.color for index, spec in enumerate(order) if not shut.get(index, 0)
    )
    shut = dict(shut)

    def ceiling_for(index: int) -> int:
        reach = lock_reach(supply, order, shut, (index,), total)
        return min(progress.get(index, 0), reach) - margin

    pool: dict[int, Placement] = {}
    for placement in placements:
        index = placement.order_index
        if index in banned or free_boxes[placement.spec.color] < 2:
            continue
        if ceiling_for(index) < 1:
            continue
        pool[index] = placement

    locks: list[BoxLock] = []
    for _ in range(min(wanted, len(pool))):
        target = lock_target(profile.frozen_at, total, rng)
        # Recomputed every round: the lock written last round holds balls back
        # too, so the colour it sat on may no longer have a spare and the boxes
        # sharing that colour may no longer reach as far as they did.
        available = [
            (ceiling, index)
            for index, placement in pool.items()
            if free_boxes[placement.spec.color] >= 2
            and (ceiling := ceiling_for(index)) >= 1
        ]
        chosen = _pick_lock(available, target, window)
        if chosen is None:
            break
        ceiling, index = chosen
        count = lock_count(target, ceiling, window, options.lock_rounding)
        placement = pool.pop(index)
        if count < 1:
            continue
        shut[index] = count
        free_boxes[placement.spec.color] -= 1
        locks.append(
            BoxLock(
                order_index=index,
                slot=(placement.slot_x, placement.slot_y),
                color=placement.spec.color,
                count=count,
                target=target,
                ceiling=ceiling,
            )
        )
    return sorted(locks, key=lambda lock: (lock.count, lock.order_index))


def slab_rectangles(
    placements: list[Placement], span_x: int, span_y: int
) -> list[tuple[int, int, tuple[int, ...]]]:
    """Every ``span_x`` x ``span_y`` rectangle of the lattice that is solid boxes.

    A slab covers whole slots, so a rectangle straddling a wall, a tunnel or an
    empty corner is not one - the runtime would be drawing a slab over nothing.
    """
    at: dict[tuple[int, int], int] = {
        (placement.slot_x, placement.slot_y): placement.order_index
        for placement in placements
    }
    found: list[tuple[int, int, tuple[int, ...]]] = []
    for slot_x, slot_y in sorted(at):
        cells = [
            (slot_x + dx, slot_y + dy) for dy in range(span_y) for dx in range(span_x)
        ]
        if any(cell not in at for cell in cells):
            continue
        found.append((slot_x, slot_y, tuple(at[cell] for cell in cells)))
    return found


def plan_slabs(
    placements: list[Placement],
    order: list[BoxSpec],
    supply: dict[int, ColorSupply],
    progress: dict[int, int],
    cols: int,
    rows: int,
    wall_slots: list[tuple[int, int]],
    tunnel_slots: list[tuple[int, int]],
    wanted: int,
    total: int,
    profile: DifficultyProfile,
    options: AutoGenOptions,
    banned: set[int],
    partners: dict[int, int],
    room: int,
    rng: random.Random,
) -> list[Slab]:
    """Lay the slabs, latest-wanted region first.

    A slab lifts in one piece, so its number is bounded by the *earliest* of the
    boxes under it - all four have to be tappable by the time the winning line
    wants the first of them. Which makes the good rectangles the ones the line
    does not visit for a while: the further back a region is wanted, the bigger
    the number it can carry and the longer the player spends locked out of it.

    A slab is **opaque**: the colours under it cannot be read until it lifts, so
    it is a Hidden over its whole rectangle for as long as it is shut. A
    temporary one, which is why it stacks with the real ``Hidden`` rather than
    replacing it - a box carrying both is dark while the slab is up and dark
    afterwards too.

    A LinkedContainer goes under a slab **whole or not at all**, which is what
    ``partners`` is for: tapping either half takes both, so a pair split across
    the edge of a shut slab cannot be tapped until it lifts, and that delay is
    invisible to the replay. Both halves under one slab has none of that problem.

    This runs *before* :func:`plan_frozen`, and the order is deliberate. A slab
    needs a solid rectangle of boxes the play order visits late, and a grid only
    has a handful of those; a Frozen box needs one box of a colour with a spare,
    and almost anything qualifies. Letting the loose mechanic pick first left the
    tight one with nothing on small grids - a fifth of SuperHard runs bought
    ``LargeBlock`` and shipped none. The constrained mechanic picks first.

    While it is shut a slab is also a wall over its own rectangle, so the layout
    is re-checked with it blocked: a slab that strands a box or a tunnel mouth on
    the far side of the grid is not laid at all. That check is deliberately the
    strict reading - if the runtime turns out to let the player route straight
    across a closed slab, this only ever refused a rectangle it could have kept.
    """
    if wanted <= 0:
        return []
    # Size and number both come off the room the picture leaves - see
    # BLOCK_WIDE_ROOM. A slab is opaque, so a wide one on a tight picture is a
    # ninth of the grid the player cannot even read the colour of.
    scale = block_room_scale(room)
    margin = max(0, options.lock_margin)
    window = round(profile.lock_window * total)
    shares = profile.block_at or ((0.3,) * wanted)

    def rectangles(span: tuple[int, int]) -> list[tuple[int, int, tuple[int, ...]]]:
        """Rectangles of this size a slab could actually be laid on, filters and all."""
        wide, tall = span
        keep: list[tuple[int, int, tuple[int, ...]]] = []
        for slot_x, slot_y, covered in slab_rectangles(placements, wide, tall):
            cells = [(slot_x + dx, slot_y + dy) for dy in range(tall) for dx in range(wide)]
            if any(index in banned for index in covered):
                continue
            inside = set(covered)
            if any(partners[index] not in inside for index in covered if index in partners):
                continue
            if not layout_is_open(cols, rows, list(wall_slots) + cells, tunnel_slots):
                continue
            wanted_at = min(progress.get(index, 0) for index in covered)
            reach = lock_reach(supply, order, {}, covered, total)
            if min(wanted_at, reach) - margin < 1:
                continue
            keep.append((slot_x, slot_y, covered))
        return keep

    # Biggest size that this grid has anywhere to put one. Stepping down beats
    # shipping nothing: see `block_span_ladder`.
    span_x, span_y = 0, 0
    candidates: list[tuple[int, int, tuple[int, ...]]] = []
    for span in block_span_ladder(room, profile):
        candidates = rectangles(span)
        if candidates:
            span_x, span_y = span
            break
    if not candidates:
        return []

    taken: set[tuple[int, int]] = set()
    slabs: list[Slab] = []
    # What each slab already laid holds back, so the next one is measured
    # against a picture that is already short of those balls.
    shut: dict[int, int] = {}
    for round_index in range(wanted):
        share = shares[min(round_index, len(shares) - 1)] * scale
        target = lock_target(share, total, rng)
        available: list[tuple[int, int]] = []
        lookup: dict[int, tuple[int, int, tuple[int, ...]]] = {}
        for slot_x, slot_y, covered in candidates:
            cells = [
                (slot_x + dx, slot_y + dy) for dy in range(span_y) for dx in range(span_x)
            ]
            if any(cell in taken for cell in cells):
                continue
            if any(index in banned for index in covered):
                continue
            # A LinkedContainer goes under a slab whole or not at all. Tapping
            # either half takes both, so a pair split across the edge of a shut
            # slab cannot be tapped at all until it lifts - and that delay is
            # invisible to the replay, which taps by index and counts no pixels.
            # Both halves under the same slab keeps the pair coherent: dark
            # together, locked together, open together.
            inside = set(covered)
            if any(
                partners[index] not in inside for index in covered if index in partners
            ):
                continue
            if not layout_is_open(cols, rows, list(wall_slots) + cells, tunnel_slots):
                continue
            # Two bounds, tighter wins. The winning line has to be able to tap
            # the *earliest* box under the slab by the time it wants it, and the
            # picture has to be payable up to the number with every colour under
            # the slab held back - the second bound holds for any tap order, not
            # only the certified one, which is what a slab needs: it takes four
            # boxes out at once, so it is the lock most able to starve a colour.
            wanted_at = min(progress.get(index, 0) for index in covered)
            reach = lock_reach(supply, order, shut, covered, total)
            ceiling = min(wanted_at, reach) - margin
            if ceiling < 1:
                continue
            key = slot_y * cols + slot_x
            available.append((ceiling, key))
            lookup[key] = (slot_x, slot_y, covered)
        chosen = _pick_lock(available, target, window)
        if chosen is None:
            break
        ceiling, key = chosen
        slot_x, slot_y, covered = lookup[key]
        count = lock_count(target, ceiling, window, options.lock_rounding)
        if count < 1:
            continue
        taken.update(
            (slot_x + dx, slot_y + dy) for dy in range(span_y) for dx in range(span_x)
        )
        for index in covered:
            shut[index] = count
        slabs.append(
            Slab(
                slot_x=slot_x,
                slot_y=slot_y,
                span_x=span_x,
                span_y=span_y,
                covered=covered,
                count=count,
                target=target,
                ceiling=ceiling,
            )
        )
    return sorted(slabs, key=lambda slab: (slab.count, slab.slot_y, slab.slot_x))


def locks_hold(
    frozen: list[BoxLock], slabs: list[Slab], progress: dict[int, int], margin: int
) -> list[str]:
    """Every lock the winning line would still be waiting on. Empty is the only pass.

    The counts are derived from ``progress``, so this can only fail on a bug -
    which is exactly why it runs: a lock that opens late is not a level the belt
    check can catch, because the gameplay model taps boxes by index and knows
    nothing about counters. It replays as a win and ships as a dead file.
    """
    late: list[str] = []
    for lock in frozen:
        wanted_at = progress.get(lock.order_index, 0)
        if lock.count > wanted_at:
            late.append(
                f"Frozen {lock.count} trên box {lock.order_index} mở sau khi "
                f"đường thắng cần nó ({wanted_at} pixel)"
            )
    for slab in slabs:
        wanted_at = min((progress.get(index, 0) for index in slab.covered), default=0)
        if slab.count > wanted_at:
            late.append(
                f"LargeBlock {slab.count} tại ({slab.slot_x}, {slab.slot_y}) mở sau khi "
                f"đường thắng cần box dưới nó ({wanted_at} pixel)"
            )
    return late


def count_open_choices(
    board: BoardState,
    order: list[BoxSpec],
    layer: "ObstacleLayer",
    rules: GameRules,
) -> ChoiceCensus:
    """Replay the level's own play order and count the legal taps at each step.

    Exact rather than sampled, because every constraint here is a lookup: a
    tunnel hands out one box, an arrow names one key, a lock names one number,
    and the conveyor either has nine slots free or it does not.
    """
    frozen_at = {lock.order_index: lock.count for lock in layer.frozen}
    slab_at = {
        index: slab.count for slab in layer.slabs for index in slab.covered
    }
    arrow_key = {
        index: key.order_index for index, (_, key) in layer.arrows.items()
    }
    partners: dict[int, int] = {}
    for left, right, _ in layer.linked:
        partners[left.order_index] = right.order_index
        partners[right.order_index] = left.order_index

    in_tunnel: dict[int, tuple[int, int]] = {}
    for tunnel, queue in enumerate(layer.queues):
        for position, index in enumerate(queue):
            in_tunnel[index] = (tunnel, position)
    heads = [0] * len(layer.queues)
    surface = [placement.order_index for placement in layer.placements]

    board = board.clone()
    tray: list[TrayBox] = []
    taken: set[int] = set()
    census = ChoiceCensus()
    steps = fewest = total = forced = 0

    for group in layer.play_groups:
        drain(board, tray)
        # Emptied boxes are left in the tray rather than pruned: `belt_used` sums
        # what is still on the conveyor, and a drained box contributes nothing.
        tray = [box for box in tray if box.remaining > 0]
        cleared = board.cursor
        free = rules.belt_slots - belt_used(tray)

        offered = [index for index in surface if index not in taken]
        for tunnel, queue in enumerate(layer.queues):
            if heads[tunnel] < len(queue):
                head = queue[heads[tunnel]]
                if head not in taken:
                    offered.append(head)

        open_now = 0
        for index in offered:
            if frozen_at.get(index, 0) > cleared or slab_at.get(index, 0) > cleared:
                continue
            key = arrow_key.get(index)
            if key is not None and key not in taken:
                continue
            # A pair drops both boxes at once, so it needs room for both.
            if free < rules.box_size * (2 if index in partners else 1):
                continue
            open_now += 1

        steps += 1
        total += open_now
        fewest = open_now if steps == 1 else min(fewest, open_now)
        forced += open_now <= 1

        for index in group:
            taken.add(index)
            spot = in_tunnel.get(index)
            if spot is not None:
                tunnel, position = spot
                heads[tunnel] = max(heads[tunnel], position + 1)
            tray.append(TrayBox(order[index].color, order[index].size, order[index].size))

    return replace(census, steps=steps, fewest=fewest, total=total, forced=forced)


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
    frozen: int = 0,
) -> BoxCellData:
    effects: list[CellEffectData] = []
    if hidden:
        effects.append(HiddenCellEffectData())
    if arrow is not None:
        effects.append(ArrowLockCellEffectData(required_direction=arrow))
    if frozen > 0:
        effects.append(FrozenCellEffectData(frozen_count=frozen))
    return BoxCellData(
        grid_x=grid_x,
        grid_y=grid_y,
        shape=CellShape.Square_3x3,
        direction=Direction.Up,
        color=ItemColor(spec.color),
        is_active=is_active,
        effects=effects or None,
    )


def belt_for_level(level: PixelLevelData) -> int:
    """The conveyor this level ships with, in balls.

    ``piece`` is how many boxes the belt holds, so the belt is ``piece`` boxes of
    balls. The hand-made levels ship ``piece: 5`` and both of the ones on hand
    need it: level 10 peaks at 40 balls and level 5 at 43, and neither is winnable
    on anything smaller. A level with no ``piece`` falls back to the same five.
    """
    return max(1, level.piece or DEFAULT_PIECE) * BALLS_PER_BOX


def scan_level(level: PixelLevelData, *, belt_slots: int = 0) -> PictureScan:
    """What Auto Gen Box would read off this level's picture, without generating.

    Balancing runs first for the same reason it does inside
    :func:`auto_generate_boxes`: the pixels it removes are the ones that would
    otherwise be balls nothing on the picture ever asks for again, so scanning
    the raw picture reports a conveyor demand the real level never has. A seven-colour picture can read as unplayable before balancing and
    comfortable after it.

    The level is never touched - the balance happens on a clone.
    """
    slots = belt_slots or belt_for_level(level)
    working = level.clone()
    grid = working.pixel_grid
    if grid.width <= 0 or grid.height <= 0:
        return PictureScan(belt_slots=slots)
    grid.ensure_dense()
    balance = BalanceReport()
    if grid.histogram():
        balance = balance_pixel_grid(grid, BALLS_PER_BOX)
    scan = scan_picture(grid, belt_slots=slots, box_size=BALLS_PER_BOX)
    scan.deleted = balance.removed
    scan.added = balance.added
    scan.moved = balance.moved
    return scan


def _at_cell(scan: PictureScan, step: int) -> str:
    """Where a step of the play order sits on the canvas, as the editor shows it.

    A jam reported only as "pixel thứ 175" is a number nobody can find on a
    picture; the cell it happened on is a place a designer can go and repaint.
    """
    cell = scan.cell_at(step)
    return f" (ô hàng {cell[0]}, cột {cell[1]})" if cell else ""


def jam_headline(result: "AutoGenResult") -> str:
    """The one line that goes in a banner: what is wrong, where, and what fixes it.

    The full trace is several lines and belongs in the report body. This is what
    goes where there is room for a sentence - a banner over the report, a status
    bar - and it has to carry the cell, because that is the part a designer acts
    on.

    A validator error outranks a jam, and a jam outranks the level coming out
    gentler than its tier. That is the order the three of them can be acted on
    in: a validator error is a broken file and never the quieter of the three, a
    jam is the picture asking for a wider conveyor, and a level short of its tier
    still works - it is just not the level that was asked for.
    """
    if result.validation_errors:
        first = result.validation_errors[0].message
        more = len(result.validation_errors) - 1
        return (
            f"LỖI VALIDATE trên lưới vừa sinh: {first}"
            + (f" (và {more} lỗi nữa)" if more else "")
            + " — đây là lỗi của Auto Gen Box, xem phần dưới."
        )
    if result.jam is None:
        if result.score.reached:
            return ""
        return (
            f"CHỈ ĐẠT {result.score.label} ({result.score.notch:.2f}/3) so với mức "
            f"{result.score.target_label} mà tranh đọc ra — thiếu"
            f" {result.score.shortfall:.2f} nấc"
            + (
                f", đã siết {len(result.climb.added)} loại obstacle mà vẫn không tới"
                if result.climb.climbed
                else ", tranh không còn chỗ cho obstacle nào nữa"
                if result.climb.enabled
                else ", tự tăng độ khó đang tắt"
            )
            + ". Level vẫn chơi được — xem phần dưới."
        )
    cell = result.scan.cell_at(result.jam.at)
    return (
        f"CHƯA THẮNG ĐƯỢC với piece={result.belt_slots // BALLS_PER_BOX}: người chơi kẹt tại"
        + (f" ô hàng {cell[0]}, cột {cell[1]}" if cell else f" pixel thứ {result.jam.at}")
        + f" (pixel thứ {result.jam.at}/{result.scan.painted}), băng đầy"
        f" {result.jam.used}/{result.jam.belt_slots} bóng."
        f" Cần piece={result.scan.required_piece} — box grid bên dưới vẫn đầy đủ và đúng."
    )


def format_jam(scan: PictureScan, jam: BeltJam) -> str:
    """The jam as a table: who is squatting on the belt, and how long they stay.

    This is the question a designer actually asks - *why* does it stick here -
    and the answer is always the same shape: a color whose run was shorter than a
    box left the rest of that box behind, and it cannot be spent until the
    picture asks for that color again.
    """
    lines = [
        f"KẸT tại pixel thứ {jam.at}/{scan.painted}{_at_cell(scan, jam.at)}: tranh đang đòi màu "
        f"{COLOR_NAMES.get(jam.wanted, jam.wanted)}, trên băng không còn bóng màu đó.",
        f"Tap thêm 1 box cần 9 ô trống, mà băng đang giữ {jam.used}/{jam.belt_slots} bóng"
        f" — chỉ còn {jam.free} ô. Không tap được, không rót được: thua ở đây.",
        "  Bóng thừa đang nằm trên băng (màu — số bóng — còn bao nhiêu pixel nữa mới dùng tới):",
    ]
    lines += [
        f"    {COLOR_NAMES.get(color, color)}: {balls} bóng, "
        + (
            f"chờ {ahead} pixel nữa{_at_cell(scan, jam.at + ahead)}"
            if ahead >= 0
            else "tranh không đòi lại nữa"
        )
        for color, balls, ahead in jam.stuck
    ]
    lines.append(
        f"  Vì sao thừa: {scan.short_runs}/{scan.run_count} mảng màu ngắn hơn 9 pixel,"
        f" mảng dài trung bình {scan.mean_run:.1f} — mỗi lần tap đổ nguyên 9 bóng nên"
        f" trung bình {scan.wasted_per_tap:.1f} bóng bị bỏ lại nằm chờ."
    )
    return "\n".join(lines)


def format_scan(scan: PictureScan) -> str:
    """What the picture costs, in the few lines a dialog can hold.

    This sits above every knob in the Auto Gen Box dialog, so it has to stay
    short enough to read at a glance and short enough not to push the knobs off
    the screen. It answers four questions and stops: how big is this picture,
    what did balancing have to do to it, how does it play, and does the belt
    carry it.

    Everything longer - where exactly the belt jams, which colours are squatting
    on it, the empty columns, the obstacle budget - belongs to the Auto Gen
    Report, which is written after generating and is a panel rather than a
    dialog. :func:`format_jam` is the piece that moved there.
    """
    if not scan.painted:
        return "Chưa có pixel nào được tô — hãy vẽ hoặc import ảnh trước."
    tier = rate_picture(scan).tier_label
    lines = [
        f"{scan.colors} màu, {scan.painted} pixel = {scan.boxes} box x 9 bóng"
        f"   ·   độ khó đọc được: {tier}",
        f"Chia hết cho 9: " + balance_summary(scan.added, scan.moved, scan.deleted),
        f"Thứ tự ăn: {scan.run_count} mảng màu, dài nhất {scan.longest_run},"
        f" trung bình {scan.mean_run:.1f} — độ vụn {scan.fragmentation:.0%}",
        f"Băng truyền: cần {scan.demand.peak_balls}/{scan.belt_slots} bóng"
        f" ({scan.demand.peak_boxes} màu chờ cùng lúc)"
        + (
            f", còn dư {scan.belt_headroom} = chỗ trống để làm khó"
            f" {spare_boxes(scan)} box — piece={scan.piece} ĐỦ"
            if scan.demand.wins(scan.belt_slots)
            else f" — piece={scan.piece} THIẾU, cần piece={scan.required_piece}"
            f" (băng {scan.required_belt} bóng)"
        ),
    ]
    jam = scan.jam()
    if jam is not None:
        cell = scan.cell_at(jam.at)
        lines.append(
            "KHÔNG THỂ THẮNG với piece hiện tại: kẹt tại pixel thứ"
            f" {jam.at}/{scan.painted}"
            + (f" (ô hàng {cell[0]}, cột {cell[1]})" if cell else "")
            + f", băng đầy {jam.used}/{jam.belt_slots} bóng vì"
            f" {len(jam.stuck)} màu đang giữ bóng thừa."
        )
        lines.append(
            "Box grid vẫn sinh đầy đủ — xem tab Auto Gen Report để biết màu nào kẹt,"
            " kẹt bao lâu và ở ô nào."
        )
    return "\n".join(lines)


def shuffle_score(result: AutoGenResult) -> tuple:
    """How good one roll of a level is, best last, for :func:`auto_generate_boxes`.

    Read in the order a designer would argue for it:

    1. **Winnable** on the belt the level ships with. Nothing else is worth
       comparing until this is true.
    2. **Not stripped bare** - a roll that had to fall back to the base grid
       carries no mechanic at all.
    3. **More mechanics on the grid**, because that is what the tier was asking
       for in the first place.
    4. **A harder obstacle form**, so a roll that kept the tier's own shape beats
       one the belt talked down.
    5. **More conveyor left over** at the tightest moment of the real play, which
       is the player's room to be wrong.
    """
    return (
        result.winnable,
        not result.obstacle_free,
        result.obstacle_plan.count,
        result.obstacle_relief.form,
        result.played_headroom,
    )


def auto_generate_boxes(level: PixelLevelData, options: AutoGenOptions) -> AutoGenResult:
    """Build a full Box Ball Grid for ``level``'s pixel grid at a given difficulty.

    With ``shuffle_attempts`` above one this rolls the whole run that many times
    on consecutive seeds and keeps the best by :func:`shuffle_score`. Every roll
    is a complete, certified level - the shuffle only picks between them, so the
    one that ships is exactly the one that seed produces on its own.
    """
    if options.shuffle_attempts > 1:
        rolls = max(1, options.shuffle_attempts)
        first = options.seed if options.seed is not None else level.level * 1000
        best: AutoGenResult | None = None
        failure: AutoGenError | None = None
        failed = 0
        for attempt in range(rolls):
            try:
                result = auto_generate_boxes(
                    level, replace(options, seed=first + attempt, shuffle_attempts=1)
                )
            except AutoGenError as exc:
                # One bad seed is not a bad picture: a layout that cannot be built
                # is exactly what the next roll is for. Only every roll failing is
                # an error, and then it is the first one's message that explains it.
                failure = failure or exc
                failed += 1
                continue
            if best is None or shuffle_score(result) > shuffle_score(best):
                best = result
        if best is None:
            raise failure or AutoGenError("No seed produced a usable box grid.")
        best.shuffle_attempts = rolls
        best.shuffle_rolls = rolls - failed
        # Said here rather than inside the roll, because a roll knows nothing about
        # the others - and the seed is the one thing a designer needs off this line
        # to get the same grid back without shuffling again.
        best.warnings.append(
            f"Đã xóc {rolls} lần, dựng được {best.shuffle_rolls} bản rồi giữ bản tốt nhất "
            "(ưu tiên: thắng được → còn obstacle → nhiều loại obstacle hơn → dạng obstacle cứng "
            f"hơn → còn nhiều băng dư hơn). Bản này là seed {best.seed} — điền seed đó và đặt số "
            "lần xóc về 1 nếu muốn dựng lại đúng lưới này."
        )
        return best

    if not options.auto_difficulty and options.difficulty not in DIFFICULTY_PROFILES:
        raise AutoGenError(f"Unsupported difficulty {options.difficulty}.")
    if options.active_policy not in ACTIVE_POLICIES:
        raise AutoGenError(f"Unsupported isActive policy {options.active_policy!r}.")
    if options.tunnel_mode not in TUNNEL_MODES:
        raise AutoGenError(f"Unsupported tunnel mode {options.tunnel_mode!r}.")
    if options.tunnel_placement not in TUNNEL_PLACEMENTS:
        raise AutoGenError(f"Unsupported tunnel placement {options.tunnel_placement!r}.")
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
    if options.frozen_boxes is not None and options.frozen_boxes < 0:
        raise AutoGenError(f"Frozen box count cannot be negative, got {options.frozen_boxes}.")
    if options.blocks is not None and options.blocks < 0:
        raise AutoGenError(f"LargeBlock count cannot be negative, got {options.blocks}.")
    if options.lock_margin < 0:
        raise AutoGenError(f"Lock margin cannot be negative, got {options.lock_margin}.")
    if options.lock_rounding not in LOCK_ROUNDINGS:
        raise AutoGenError(f"Unsupported lock rounding {options.lock_rounding!r}.")

    working = level.clone()
    grid = working.pixel_grid
    if grid.width <= 0 or grid.height <= 0:
        raise AutoGenError("Pixel grid must have a positive width and height.")
    grid.ensure_dense()
    if not grid.histogram():
        raise AutoGenError("Paint the pixel grid before generating boxes.")

    balance = balance_pixel_grid(grid, BALLS_PER_BOX)
    removed, emptied = balance.removed, balance.emptied_columns
    if not grid.histogram():
        raise AutoGenError(
            f"Every color has fewer than {BALLS_PER_BOX} pixels, so not a single box can be "
            "built. Paint at least nine pixels of one color."
        )

    # Scanned after balancing, never before: the leftovers balancing deletes are
    # exactly the balls that would otherwise sit on the conveyor forever, so an
    # unbalanced picture reads far harder than the one that actually gets played.
    belt_slots = options.belt_slots or belt_for_level(level)
    scan = scan_picture(grid, belt_slots=belt_slots, box_size=BALLS_PER_BOX)

    # A picture the belt cannot hold is scattered, not oversized: its contents fit
    # in whole boxes and it is the *order* they are wanted in that jams. Merging
    # the specks into their own kind fixes that without touching what any colour
    # owns, so it is worth trying before the level is written off as needing a
    # wider piece. Nothing happens to a picture that already plays.
    repair = RepairReport(belt_slots=belt_slots)
    if options.repair_picture and not scan.demand.wins(belt_slots):
        repair = repair_picture(grid, belt_slots=belt_slots, box_size=BALLS_PER_BOX)
        if repair.changed:
            scan = scan_picture(grid, belt_slots=belt_slots, box_size=BALLS_PER_BOX)

    # Second pass, and only if the designer asked for it: a picture so shredded
    # that merging every speck into its own kind was not enough. What is left is
    # scattered *colour* - a colour spread over thirty three-pixel specks has no
    # large region of its own to be consolidated beside - so the only move that
    # helps is giving that colour up. It changes the palette, which is why it is
    # opt-in and why it runs last.
    if options.drop_scattered_colors and not scan.demand.wins(belt_slots):
        repair = drop_scattered_colors(
            grid,
            belt_slots=belt_slots,
            box_size=BALLS_PER_BOX,
            report=repair if repair.changed else None,
        )
        if repair.drops:
            scan = scan_picture(grid, belt_slots=belt_slots, box_size=BALLS_PER_BOX)
            if not grid.histogram():  # pragma: no cover - min_colors keeps three
                raise AutoGenError(
                    "Dropping the scattered colours left nothing painted."
                )

    scan.deleted = removed
    scan.added = balance.added
    scan.moved = balance.moved
    # "Lấy độ khó từ ảnh", in the two steps it always was: rate the picture, then
    # choose the tier its rating asks for. The rating is kept whole rather than
    # collapsed into the one number, so the report can say *why* this picture
    # reads as it does - and it is read either way, because a designer who typed
    # their own tier still wants to know what the picture would have said.
    rating = rate_picture(scan)
    difficulty = rating.tier if options.auto_difficulty else options.difficulty
    # Stepping the scenario down is a decision, not a reaction: the picture says
    # what it reads as and this says how much of that to actually build. Easy is
    # the floor - there is no gentler level to ask for.
    if options.ease_difficulty:
        difficulty = max(int(LevelDifficulty.Easy), difficulty - max(0, options.ease_difficulty))
    # From here `difficulty` is the **target**: the tier the obstacles are built
    # up to, and the number the finished level is scored against in stage 12b.
    # Whether it came off the picture or out of the dialog makes no difference to
    # anything downstream.
    if difficulty not in DIFFICULTY_PROFILES:  # pragma: no cover - suggest_difficulty is in range
        raise AutoGenError(f"Unsupported difficulty {difficulty}.")
    profile = DIFFICULTY_PROFILES[difficulty]
    rules = GameRules(belt_slots=belt_slots, box_size=BALLS_PER_BOX)

    board = BoardState.from_pixel_grid(grid)
    try:
        boxes = box_multiset(board, BALLS_PER_BOX)
    except GameplayError as exc:  # pragma: no cover - balancing guarantees multiples of nine
        raise AutoGenError(str(exc)) from exc

    # The belt is what the burial and the links get measured against, not a veto
    # on the picture: a level is *made* hard by forcing spare boxes onto the
    # conveyor, so the walkthrough is solved on the belt the level ships with and
    # the pressure the obstacles add is what has to stay inside it.
    #
    # A picture the shipped belt cannot hold is **not** refused, and `piece` is
    # not moved on the designer's behalf either. Both would throw away work: the
    # box grid a picture wants is fully determined by its histogram, and it is
    # correct whether or not the conveyor is wide enough to play it. So the grid
    # is built, and what the belt cannot do is reported as a warning that says
    # exactly where the play stops - see `format_jam`.
    #
    # The obstacles are then certified against the belt the picture actually needs
    # rather than the one it has. Certifying against a belt nothing wins on would
    # only strip the level bare - no burial, no links, every check failing for the
    # same single reason - and the moment `piece` is set to the number in the
    # warning the level is correct, obstacles and all.
    solution = solve_order(board, boxes, rules)
    jam = None
    certified_belt = belt_slots
    if solution is None:
        jam = scan.jam()
        certified_belt = max(belt_slots, scan.required_belt)
        rules = GameRules(belt_slots=certified_belt, box_size=BALLS_PER_BOX)
        # The late-tapping play always exists and always wins on `required_belt`,
        # so this cannot fail even when the search gives up on the wider belt too.
        solution = solve_order(board, boxes, rules) or lazy_order(board, boxes, BALLS_PER_BOX)
    solution.required_belt = (
        minimum_belt(board, boxes, max_slots=certified_belt, min_slots=scan.demand.peak_balls)
        or certified_belt
    )

    # `jam` is set only when `solve_order` lost on the belt the level *ships* with,
    # which is the same reading `format_scan` prints as "KHÔNG THỂ THẮNG" above
    # every knob in the dialog - and it is taken after the repairs, so a picture
    # the repair pass saved arrives here with no jam and keeps its tier's burial.
    # Decided once and handed to both stages 12 and 12b, so relief and the climb
    # cannot disagree about it. See `BURIAL_GROUPS` for why it is worth doing.
    bury_easy = options.jam_relief and jam is not None

    # The picture and the obstacles are two difficulties, and the conveyor is
    # where they add up. `difficulty` was read off the picture, so a hard picture
    # asks for the hardest obstacle forms on exactly the level with no belt left
    # to pay for them. The tier therefore keeps deciding *which* mechanics the
    # level carries, and the belt gets the last word on how hard each one is set:
    # `tier_profile` stays behind for the first decision, `profile` becomes
    # whatever form the picture turned out to accept.
    tier_profile = profile

    seed = options.seed if options.seed is not None else working.level * 1000 + difficulty
    # This one only rolls how many *kinds* the level runs. Everything the layout
    # rolls is drawn from a generator each obstacle attempt seeds for itself, so
    # walking the relief ladder cannot shift the grid of the attempt that is kept.
    rng = random.Random(seed)

    # Which mechanics this level gets, decided once and for all five of them from
    # the same two readings: what the tier wants, and what the picture can pay.
    # It has to happen before the lattice is laid out, because two of the answers
    # (walls, tunnels) need slots of their own.
    capacity = max(1, min(options.max_slot_cols, MAX_BOX_SLOTS)) * max(
        1, min(options.max_slot_rows, MAX_BOX_SLOTS)
    )
    box_count = len(solution.order)
    # Boxes that will end up on the surface, near enough to tell a grid that can
    # carry a wall from one that cannot. The exact count is measured again on the
    # finished lattice, where every dose is actually sized.
    surface_estimate = min(box_count, max(1, capacity - 1))
    # The tier's own profile, not the relieved one: relief sets how hard each
    # mechanic bites, never which ones the level carries.
    plan = plan_obstacle_kinds(
        difficulty=difficulty,
        profile=tier_profile,
        options=options,
        scan=scan,
        surface_boxes=surface_estimate,
        capacity=capacity,
        box_count=box_count,
        rng=rng,
    )

    # The box grid on its own first, with no mechanic anywhere on it: the picture
    # laid out, the overflow in tunnels that hand a box over exactly when it is
    # wanted, and a winning line replayed on it. Everything after this is a change
    # to a grid that is already known to be beatable, and if none of those changes
    # turns out to be playable, this is what ships.
    base = build_base_grid(
        board=board,
        solution=solution,
        scan=scan,
        options=options,
        tier_profile=tier_profile,
        difficulty=difficulty,
        rules=rules,
        seed=seed,
    )
    if base.faults:
        raise AutoGenError(
            "The picture cannot be laid out as a playable box grid before any obstacle is "
            "added: " + "; ".join(base.faults) + ". Raise the slot limit or use a smaller "
            "picture."
        )

    # Then every mechanic in the plan, laid on that base at the hardest form the
    # picture does not refuse. What comes back has been replayed as its own
    # obstacles force it to be played, so it too is a level with a winning line.
    layer, relief = relieve_obstacles(
        board=board,
        solution=solution,
        scan=scan,
        options=options,
        tier_profile=tier_profile,
        plan=plan,
        difficulty=difficulty,
        rules=rules,
        seed=seed,
        base=base,
        bury_easy=bury_easy,
    )
    # Stage 12b. Two things have decided this level so far and neither of them
    # ever looked at the sum: the tier said which mechanics, relief said how hard
    # each one is set. So the sum is read off the finished layer and, when it
    # comes out under the tier the picture asked for, the mechanics the picture
    # can still afford are hardened until it gets there. A level that already
    # scores its target is handed straight back - see `DifficultyClimb`.
    #
    # Skipped for a base ship, where there is nothing to harden: every form
    # faulted, so the level has no mechanic on it to set harder.
    if relief.base:
        score = score_layer(layer, target=difficulty)
        climb = DifficultyClimb(
            target=difficulty,
            start=score.notch,
            final=score.notch,
            reached=score.reached,
            enabled=options.difficulty_climb,
        )
    else:
        layer, score, climb = climb_obstacles(
            board=board,
            solution=solution,
            scan=scan,
            options=options,
            tier_profile=tier_profile,
            plan=plan,
            difficulty=difficulty,
            rules=rules,
            seed=seed,
            layer=layer,
            top=relief.top,
            bury_easy=bury_easy,
        )
    if relief.base:
        # The level went out with no mechanics on it, so the plan has to say that
        # rather than list what the tier bought and never got onto the grid.
        plan = ObstaclePlan(
            difficulty=difficulty,
            budget=plan.budget,
            dose=plan.dose,
            skipped=tuple(
                (kind, "mọi dạng obstacle đều làm lưới không chơi được")
                for kind in plan.kinds
            )
            + plan.skipped,
            overflow=plan.overflow,
        )
    # What the base came to, kept for the report: this is the level's floor, and
    # the number every obstacle is answerable to.
    result_base_belt = base.played_belt
    result_base_surface = len(base.placements)
    result_base_tunnel_boxes = sum(len(queue) for queue in base.queues)
    result_base_tunnels = sum(1 for queue in base.queues if queue)

    profile = layer.profile
    cols, rows = layer.cols, layer.rows
    placements = layer.placements
    blocks, tunnel_slots, facings = layer.blocks, layer.tunnel_slots, layer.facings
    wall_slots, pinched = layer.wall_slots, layer.pinched
    wanted_window, queues, dig_windows = layer.wanted_window, layer.queues, layer.dig_windows
    release = layer.release
    hidden, hidden_count = layer.hidden, layer.hidden_count
    linked, link_count, linked_mode = layer.linked, layer.link_count, layer.linked_mode
    play_groups, play_position = layer.play_groups, layer.play_position
    arrows, arrow_count = layer.arrows, layer.arrow_count
    played_belt = layer.played_belt
    frozen_locks, frozen_count = layer.frozen, layer.frozen_count
    slabs, slab_count = layer.slabs, layer.slab_count
    frozen_by_index = {lock.order_index: lock.count for lock in frozen_locks}
    slab_covered = {index for slab in slabs for index in slab.covered}

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
            _is_active(
                placement.slot_y,
                options.active_policy,
                # A locked box is not openable yet whichever kind of lock it is,
                # and the validator refuses an active Hidden box outright. A slab
                # counts: the box under it cannot be tapped and cannot be read.
                is_hidden
                or arrow is not None
                or placement.order_index in frozen_by_index
                or placement.order_index in slab_covered,
            ),
            is_hidden,
            arrow[0] if arrow else None,
            frozen_by_index.get(placement.order_index, 0),
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
    ] + [
        LargeBlockObstacleData(
            grid_x=slab.rect[0],
            grid_y=slab.rect[1],
            width=slab.rect[2],
            height=slab.rect[3],
            count=slab.count,
        )
        for slab in slabs
    ]
    # piece is left exactly as the level shipped it, because the belt was sized
    # *from* it: writing back the peak the walkthrough reached would change the
    # belt the next run is generated against, and the two would chase each other.
    # What the walkthrough actually peaked at goes in the report instead.
    working.piece = belt_slots // BALLS_PER_BOX
    working.difficulty = difficulty
    if options.apply_theme and difficulty in DIFFICULTY_FORCED_THEME:
        working.theme_id = DIFFICULTY_FORCED_THEME[difficulty]

    expected_boxes = len(solution.order)
    if len(placements) + tunnel_boxes != expected_boxes:
        raise AutoGenError("Internal error: some generated boxes were dropped during layout.")
    if working.source_histogram() != working.target_histogram():
        raise AutoGenError("Internal error: generated boxes do not match the pixel grid.")
    if not layout_is_open(cols, rows, wall_slots, tunnel_slots):
        raise AutoGenError("Internal error: a wall seals a box off from every side.")
    if not simulate_order(board, solution.order, rules):
        raise AutoGenError(
            f"Internal error: the generated walkthrough does not win on a "
            f"{certified_belt}-ball belt."
        )
    play_order = [solution.order[index] for index in release.sequence]
    if not simulate_order(board, play_order, rules):
        raise AutoGenError(
            f"Internal error: the tunnel queues force a pick order that loses on a "
            f"{certified_belt}-ball belt."
        )
    if not arrow_order_holds(arrows, play_position):
        raise AutoGenError(
            "Internal error: an ArrowLock box is opened before the box its arrow points at."
        )
    # The locks, asked of the level that is actually being handed back rather
    # than of the layer that planned them. A late lock is the one unwinnable
    # state no replay above can reach: the model taps by index and counts no
    # pixels, so the level wins in the simulator and deadlocks in the runtime.
    late_locks = locks_hold(frozen_locks, slabs, layer.progress, options.lock_margin)
    if late_locks:
        raise AutoGenError("Internal error: " + "; ".join(late_locks))
    # Same question asked of the picture instead of the certified line: is there
    # a pixel these counters make unpayable in *every* tap order? A level that
    # fails this wins in the simulator and stalls for the player.
    starved = locks_open(board.sequence, solution.order, frozen_locks, slabs)
    if starved:
        raise AutoGenError("Internal error: " + "; ".join(starved))
    slab_slots = {slot for slab in slabs for slot in slab.slots}
    if len(slab_slots) != sum(len(slab.slots) for slab in slabs):
        raise AutoGenError("Internal error: two LargeBlock slabs overlap.")
    if slab_slots & set(tunnel_slots) or slab_slots & set(wall_slots):
        raise AutoGenError("Internal error: a LargeBlock slab covers a tunnel or a wall.")
    # A pair may sit under a slab, but only as a pair: covering one half leaves a
    # LinkedContainer that cannot be tapped until the slab lifts, and no replay
    # above can see that.
    if any(
        (left.order_index in slab_covered) != (right.order_index in slab_covered)
        for left, right, _ in linked
    ):
        raise AutoGenError("Internal error: a LargeBlock slab covers half of a LinkedContainer.")
    # Every rule the file has to satisfy, asked of the level that is about to be
    # handed back. The checks above prove the level can be *played*; these prove
    # it can be *loaded* - an arrow with no blocker, a tunnel pointing nowhere, a
    # LinkedContainer whose halves disagree. On the ids the level will be saved
    # with, because several of those rules are about ids referring to each other.
    validated = working.clone()
    validated.assign_deterministic_ids()
    validation = tuple(LevelValidator().validate(validated).messages)

    metrics = measure_difficulty(board, solution, rules)
    choices = count_open_choices(board, solution.order, layer, rules)

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
    # A generated level that breaks a validator rule is a bug in here, not a note
    # for the designer, so it goes above everything - including the jam, which is
    # a property of the picture rather than a fault in the grid.
    errors = [message for message in validation if message.severity == "error"]
    if errors:
        warnings.append(
            f"LỖI VALIDATE trên lưới vừa sinh ({len(errors)} lỗi) — đây là lỗi của Auto Gen Box, "
            "không phải của bức tranh: "
            + "; ".join(message.message for message in errors)
            + ". Hãy báo lại kèm seed và ảnh để sửa."
        )
    # The validator's *warnings* are not echoed here on purpose. They are listed
    # in the report body and in the Validation tab, and the one every generated
    # level gets - "histogram balance is not a solvability proof" - is a caution
    # this run has already answered by replaying the level. Repeating it beside
    # the certified walkthrough would read as a contradiction of it.
    #
    # Nothing else in this list matters if the level cannot be finished, so the
    # jam goes first, with the place on the canvas where the play stops.
    if jam is not None:
        warnings.append(
            f"LEVEL NÀY CHƯA THẮNG ĐƯỢC với piece={belt_slots // BALLS_PER_BOX} "
            f"(băng {belt_slots} bóng). Box grid vẫn được sinh đầy đủ và đúng theo pixel grid, "
            f"nhưng người chơi sẽ kẹt lại giữa chừng.\n"
            + format_jam(scan, jam)
            + f"\n  Obstacle đã được kiểm chứng trên băng {certified_belt} bóng "
            f"(piece={certified_belt // BALLS_PER_BOX}): đặt piece={scan.required_piece} "
            f"cho level là chạy đúng ngay, không phải sinh lại. "
            "Hoặc gom các đốm cùng màu thành mảng dài từ 9 pixel theo thứ tự ăn "
            "(trên xuống, phải qua trái) để bỏ hẳn phần bóng thừa."
        )

    # The one thing the validator cannot check, because it is about the design
    # rather than about the file: the level wins, it loads, and it still does not
    # add up to the tier it ships as. Said here rather than left in the report
    # body, because a level wearing the wrong label is the kind of thing that
    # goes unnoticed for a whole batch of levels.
    if not score.reached:
        gentlest = sorted(
            (notch, group) for group, notch in score.groups.items() if notch > 0.0
        )[:3]
        warnings.append(
            f"LEVEL NÀY CHỈ ĐẠT {score.label} ({score.notch:.2f}/3) so với mức "
            f"{score.target_label} mà tranh đọc ra — thiếu {score.shortfall:.2f} nấc. "
            + (
                "Đã thử tăng "
                + "/".join(
                    DIFFICULTY_GROUP_LABELS[group] for group, _, _ in climb.tried
                )
                + " nhưng "
                + (
                    "chỉ kéo lên được đến đây"
                    if climb.climbed
                    else "không loại nào tăng được điểm"
                )
                + ". "
                if climb.tried
                else "Tự tăng độ khó đang tắt. "
                if not climb.enabled
                else ""
            )
            + "Nhẹ nhất đang là "
            + ", ".join(
                f"{DIFFICULTY_GROUP_LABELS[group]} {notch:.2f}" for notch, group in gentlest
            )
            + ". Muốn đúng mức thì nới piece cho băng rộng hơn, hoặc gom màu lại "
            "để tranh chừa chỗ cho obstacle."
        )

    # The plan itself heads the report, so only the two ways it can go wrong are
    # worth a warning: more mechanics than the tier allows, or fewer than it wants.
    if plan.over_budget:
        warnings.append(
            f"Đang dùng {plan.count} loại obstacle, vượt ngân sách {plan.budget[1]} loại của mức "
            f"{profile.label}: "
            + ", ".join(OBSTACLE_KIND_LABELS[kind] for kind in plan.forced)
            + " được giữ lại vì đã bị chỉ định bằng con số cụ thể hoặc do ảnh tràn slot. "
            "Trả các ô đó về Auto nếu muốn đúng ngân sách."
        )
    elif plan.under_budget:
        warnings.append(
            f"Chỉ dùng được {plan.count}/{plan.budget[0]} loại obstacle tối thiểu của mức "
            f"{profile.label}, nên level sẽ nhẹ hơn mức này thường có — xem phần Không dùng ở trên."
        )
    elif plan.under_dose:
        warnings.append(
            f"Level này rút {plan.dose} loại obstacle nhưng lưới chỉ nhận được {plan.count} — "
            "vẫn nằm trong khoảng của mức, xem phần Không dùng ở trên để biết loại nào không đủ chỗ."
        )
    # Every mechanic layer turned out unplayable, so the level went out as the
    # bare base grid. That is a real answer - the picture is beatable and the
    # grid is correct - but it is not the level the tier describes, so it is said
    # first and with the reasons each form failed on.
    if relief.base:
        warnings.append(
            f"Level này ra không có obstacle nào: lưới box gốc thắng được (băng đỉnh "
            f"{result_base_belt}/{certified_belt} bóng), nhưng mọi dạng obstacle đều làm lưới "
            "không chơi được — "
            + "; ".join(
                f"dạng {DIFFICULTY_PROFILES[form].label}: " + ", ".join(faults)
                for form, faults in relief.faulted
            )
            + ". Nâng giới hạn slot hoặc hạ số wall để lưới có chỗ cho obstacle."
        )
    elif relief.faulted and not relief.relieved:
        # When relief stepped down, the step-down warning below already names the
        # faults; this is for the forms that faulted without changing the answer.
        warnings.append(
            "Đã bỏ "
            + ", ".join(
                f"dạng {DIFFICULTY_PROFILES[form].label} ({', '.join(faults)})"
                for form, faults in relief.faulted
            )
            + f" vì lưới dựng ra không chơi được, nên chốt ở dạng {relief.label}."
        )
    # Relief is the answer to "tranh khó cộng obstacle khó thì level còn thắng
    # được không": the mechanics all stayed, they are just set gentler, and the
    # designer has to be told which ones changed shape and why.
    if relief.relieved:
        softened = [
            change
            for change in (
                f"box ẩn {profile.hidden_ratio:.0%} thay vì {tier_profile.hidden_ratio:.0%}"
                if profile.hidden_ratio != tier_profile.hidden_ratio
                else "",
                f"độ chôn tunnel {profile.dig_window} thay vì {tier_profile.dig_window}"
                if profile.dig_window != tier_profile.dig_window
                else "",
                f"link {profile.linked_mode} thay vì {tier_profile.linked_mode}"
                if profile.linked_mode != tier_profile.linked_mode
                else "",
                "link phải rút cạn băng ngay sau khi thả"
                if profile.clean_links and not tier_profile.clean_links
                else "",
                "mũi tên chỉ vào box vừa mở ngay trước đó"
                if profile.arrow_reach != tier_profile.arrow_reach
                else "",
                f"{profile.walls} wall thay vì {tier_profile.walls}"
                if profile.walls != tier_profile.walls
                else "",
                f"xếp box kiểu {profile.scramble} thay vì {tier_profile.scramble}"
                if profile.scramble != tier_profile.scramble
                else "",
            )
            if change
        ]
        # Two different things can force a step down, and saying the wrong one is
        # worse than saying nothing: the belt refusing a mechanic is the picture
        # being expensive, a faulted layout is the lattice being too small.
        faulted_at_top = dict(relief.faulted).get(relief.top, ())
        because = []
        if relief.refused:
            because.append(
                "băng không chịu "
                + "/".join(OBSTACLE_KIND_LABELS[kind] for kind in relief.refused)
                + f" (lời giải đã cần {relief.required_belt}/{relief.belt_slots} bóng, chỉ chừa "
                f"{relief.room} box trống)"
            )
        if faulted_at_top:
            because.append("lưới dựng ra không chơi được: " + ", ".join(faulted_at_top))
        warnings.append(
            f"Đã hạ độ khó obstacle từ {relief.top_label} xuống {relief.label} "
            f"({relief.steps} nấc) vì ở dạng {relief.top_label} thì "
            + " và ".join(because)
            + ". Đã dựng thử từng dạng: "
            + " → ".join(
                f"{DIFFICULTY_PROFILES[form].label} ("
                + (
                    "băng cắt " + "/".join(OBSTACLE_KIND_LABELS[kind] for kind in cut)
                    if cut
                    else "băng nhận đủ"
                )
                + (
                    ", lưới hỏng"
                    if dict(relief.faulted).get(form)
                    else ""
                )
                + ")"
                for form, cut in relief.tried
            )
            + f", nên chốt ở dạng {relief.label}. Vẫn giữ nguyên {plan.count} loại obstacle "
            f"({plan.labels}), chỉ nhẹ tay hơn: "
            + "; ".join(softened)
            + ". Bỏ tick 'Tự hạ độ khó obstacle' nếu muốn đúng dạng của mức "
            f"{relief.top_label}."
        )
    elif relief.cut:
        warnings.append(
            "Băng chuyền không trả nổi dạng obstacle của mức "
            f"{relief.label}: "
            + ", ".join(OBSTACLE_KIND_LABELS[kind] for kind in relief.cut)
            + " bị cắt bớt lúc kiểm chứng"
            + (
                ", mà đây đã là dạng nhẹ nhất — tranh này chỉ chừa "
                f"{relief.room} box trống trên băng."
                if relief.form == int(LevelDifficulty.Easy)
                else "."
            )
            + (
                " Bật 'Tự hạ độ khó obstacle' để nó tự tìm dạng nhẹ hơn mà băng chịu được."
                if not relief.enabled
                else ""
            )
        )
    # A mechanic the designer asked for by name and did not get is the one thing
    # the plan must never let pass in silence.
    denied = [
        (kind, why) for kind, why in plan.skipped if designer_choice(kind, options) is True
    ]
    if denied:
        warnings.append(
            "Đã xin nhưng lưới không nhận được: "
            + "; ".join(f"{OBSTACLE_KIND_LABELS[kind]} ({why})" for kind, why in denied)
            + "."
        )
    # Repainting somebody's artwork is the most intrusive thing in here, so it is
    # spelled out whether it worked or not.
    if repair.moves:
        warnings.append(
            "Đã sửa tranh để level chơi được: "
            + merge_summary(repair)
            + ", "
            + belt_summary(repair)
            + ". Mỗi đốm lẻ được nhập vào màu bên cạnh và trả lại đúng số pixel đó ngay cạnh "
            "mảng lớn của chính nó — riêng bước gom này không bỏ màu nào: số pixel từng màu "
            "không đổi và số box sinh ra vẫn y nguyên, chỉ thứ tự tranh đòi màu là đổi. "
            "Các nước đã sửa: "
            + "; ".join(
                f"{move.pixels} pixel {COLOR_NAMES[ItemColor(move.color)]} ở ô hàng "
                f"{move.at[0]}, cột {move.at[1]} → {COLOR_NAMES[ItemColor(move.into)]}, "
                f"trả lại ở ô hàng {move.paid_at[0]}, cột {move.paid_at[1]}"
                for move in repair.moves
            )
            + ". Bỏ tick 'Sửa tranh cho chơi được' nếu muốn giữ nguyên từng pixel."
        )
    # Said apart from the merges, and in stronger terms, because this is the one
    # repair that changes what the artwork is *made of*: the palette comes back
    # shorter and no amount of reading the merge list would reveal that.
    if repair.drops:
        gone = [drop for drop in repair.drops if drop.gone]
        painted = sum(grid.histogram().values())
        warnings.append(
            f"Đã bỏ bớt màu vụn để level qua được: {len(repair.drops)} box đốm màu "
            f"({repair.dropped_pixels}/{painted} pixel = "
            f"{repair.dropped_pixels / painted:.1%} bức tranh) đã đổi màu. Các nước: "
            + "; ".join(
                f"{drop.pixels} pixel {COLOR_NAMES[ItemColor(drop.color)]} ở ô hàng "
                f"{drop.at[0]}, cột {drop.at[1]} → {COLOR_NAMES[ItemColor(drop.into)]} "
                f"(mất {drop.runs_removed} mảng vụn"
                + (", màu này rời khỏi bảng màu" if drop.gone else "")
                + ")"
                for drop in repair.drops
            )
            + f". Bảng màu còn {len(grid.histogram())} màu"
            + (
                " (không mất màu nào — chỉ các đốm vụn bị gom đi, mảng lớn của mọi màu "
                "giữ nguyên)"
                if not gone
                else ": mất "
                + ", ".join(COLOR_NAMES[ItemColor(drop.color)] for drop in gone)
                + " vì cả màu đó chỉ có đúng số pixel vừa bị gom"
            )
            + ". Mỗi nước bỏ đúng 1 box (9 pixel) — mức nhỏ nhất mà histogram cho phép vì mọi "
            "màu phải chia hết cho 9 — và chọn box nào hạ băng nhiều nhất, rồi dừng ngay khi "
            "tranh thắng được. Bỏ tick 'Bỏ màu quá vụn nếu vẫn không qua được' nếu muốn giữ "
            "nguyên từng pixel và chấp nhận level KẸT."
        )
    if repair.changed and not repair.wins:
        warnings.append(
            f"Sửa tranh vẫn chưa đủ: băng còn cần {repair.belt_after}/{repair.belt_slots} "
            "bóng"
            + (
                " và đã hết nước gom (mọi đốm lẻ còn lại đều là mảng cuối của màu đó)"
                if repair.exhausted
                else " và nước gom tiếp theo không giúp giảm thêm"
            )
            + ". Tranh này rắc quá đều — "
            + (
                "nâng piece hoặc tự gom màu thành mảng dài từ "
                f"{BALLS_PER_BOX} pixel theo thứ tự ăn."
                if options.drop_scattered_colors
                else "tick 'Bỏ màu quá vụn nếu vẫn không qua được' để tool bỏ bớt màu vụn, "
                f"hoặc nâng piece, hoặc tự gom màu thành mảng dài từ {BALLS_PER_BOX} pixel "
                "theo thứ tự ăn."
            )
        )
    elif not repair.changed and options.repair_picture and jam is not None:
        warnings.append(
            "Không sửa được tranh cho chơi được: không có đốm màu lẻ nào gom được mà giảm được "
            "băng. "
            + (
                "Tranh này cần piece lớn hơn, hoặc phải gom màu bằng tay."
                if options.drop_scattered_colors
                else "Tick 'Bỏ màu quá vụn nếu vẫn không qua được' để tool bỏ bớt màu vụn, "
                "hoặc nâng piece, hoặc gom màu bằng tay."
            )
        )
    if relief.eased:
        warnings.append(
            f"Đã hạ sẵn dạng obstacle {relief.eased} nấc theo yêu cầu, từ {relief.tier_label} "
            f"xuống {relief.top_label}: level vẫn là mức {relief.tier_label} (theme và difficulty "
            f"không đổi) nhưng obstacle được dựng ở dạng của mức {relief.top_label}."
        )
    if relief.unburied:
        gentle, asked = DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)], DIFFICULTY_PROFILES[relief.difficulty]
        warnings.append(
            f"Tranh KHÔNG THẮNG ĐƯỢC trên băng của level (piece={scan.piece}, cần"
            f" piece={scan.required_piece}), nên phần CHÔN BOX đã hạ xuống mức Easy:"
            f" box ẩn {gentle.hidden_ratio:.0%} thay vì {asked.hidden_ratio:.0%},"
            f" xếp box kiểu {gentle.scramble} thay vì {asked.scramble}, độ chôn trong"
            f" tunnel {gentle.dig_window} thay vì {asked.dig_window}."
            " Băng không cắt được box ẩn (nó không tốn bóng nào) nên không hạ ở đây thì"
            " level đã kẹt lại còn bị chôn ở mức khó nhất, không ai đọc được."
            f" Obstacle đặt lên trên vẫn giữ dạng mức {relief.label} và vẫn được thêm vào"
            " cho tới khi lưới không chơi được nữa, nên level không bị dựng trơ."
            f" Level vẫn là mức {relief.tier_label} — nâng piece lên"
            f" {scan.required_piece} rồi gen lại là chôn box trở về đúng mức đó."
        )
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
        # A mouth with no box in front of it used to be a warning on a level that
        # went out anyway - and it is the one fault the replay cannot catch, since
        # the gameplay model taps a queue by index and never asks where the mouth
        # points. It is a layout fault now, so a layout that has one is not
        # shipped and this list can only ever be empty; it stays as an assertion
        # rather than a warning.
        box_slots = {(placement.slot_x, placement.slot_y) for placement in placements}
        if sealed_tunnel_mouths(tunnel_mouths, box_slots):
            raise AutoGenError(
                "Internal error: a tunnel mouth faces no box, so its queue can never be "
                "handed out."
            )
    if blocks and any(window < wanted_window for window in dig_windows):
        warnings.append(
            f"Độ chôn của tunnel bị thu hẹp từ {wanted_window} xuống "
            + "/".join(str(window) for window in dig_windows)
            + f": chôn sâu hơn sẽ dồn nhiều bóng lên băng cùng lúc hơn mức {belt_slots} "
            "bóng chứa được. Muốn đào sâu hơn thì rút ngắn tunnel hoặc gom màu lại."
        )
    if wall_slots and not plan.has("wall"):
        warnings.append(
            f"{len(wall_slots)} slot trống không phải wall của mức {profile.label} (mức này không "
            f"dùng wall): lưới box phải là hình chữ nhật, và {len(placements)} box mặt ngoài cộng "
            f"{used_tunnels} tunnel không lấp kín {cols}x{rows} slot. Người chơi vẫn thấy nó như "
            "một wall, nên hãy chỉnh giới hạn slot nếu muốn lưới kín."
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
    if plan.has("linked") and not linked:
        warnings.append(
            f"Không nối được cặp LinkedContainer nào ở chế độ {linked_mode!r}: cần hai box nằm sát "
            "nhau, cùng trạng thái ẩn, và khoảng cách trong thứ tự giải phải phù hợp — mà thả hai "
            f"box cùng lúc vẫn không được vượt {belt_slots} bóng trên băng."
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
            f"tràn băng {belt_slots} bóng nên đã bị bỏ. Muốn nhiều link hơn thì "
            "chuyển sang chế độ sync."
        )
    if plan.has("arrow") and not arrows:
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
    if scan.belt_headroom <= BALLS_PER_BOX:
        warnings.append(
            f"Băng truyền gần như hết chỗ: đoạn chật nhất của ảnh cần {scan.demand.peak_balls}/"
            f"{belt_slots} bóng, chỉ còn dư {scan.belt_headroom}. Level vẫn thắng được nhưng "
            "người chơi hầu như không có quyền sai — thêm bất kỳ obstacle nào cũng nên cân nhắc."
        )
    warnings.append(
        f"Băng truyền: lời giải cần {solution.required_belt}/{belt_slots} bóng, đỉnh "
        f"{solution.peak_boxes} box nằm trên băng cùng lúc (box đã rót vơi chỉ chiếm phần "
        f"bóng còn lại, nên số box có thể vượt piece={working.piece}). Còn dư "
        f"{belt_slots - solution.required_belt} bóng cho việc chôn box và nối link."
    )
    # The straight answer to "obstacle có làm level khó thêm không": the same play
    # measured twice, once on the bare base grid and once as the obstacles force
    # it. The two are the same walk when nothing spends belt, which is why the
    # base's own peak and the walkthrough's are one number.
    walkthrough_belt = max((step.belt_used for step in solution.steps), default=0)
    obstacle_cost = max(0, played_belt - walkthrough_belt)
    headroom = certified_belt - played_belt
    if not obstacle_cost:
        verdict = (
            "obstacle không làm băng đầy thêm chút nào — chúng chỉ chặn tầm nhìn và đường đi, "
            "không chiếm thêm chỗ trên băng"
        )
    elif headroom >= BALLS_PER_BOX:
        verdict = (
            f"obstacle làm băng đầy thêm {obstacle_cost} bóng, vẫn còn dư {headroom} bóng "
            f"({headroom // BALLS_PER_BOX} box) để người chơi sai"
        )
    else:
        verdict = (
            f"obstacle làm băng đầy thêm {obstacle_cost} bóng và chỉ còn dư {headroom} bóng — "
            "dưới một box, nghĩa là gần như không được phép lấy sai box nào"
        )
    warnings.append(
        f"Có obstacle rồi thì khó thêm bao nhiêu: chơi đúng thứ tự obstacle bắt buộc, băng "
        f"đầy nhất {played_belt}/{certified_belt} bóng, so với {walkthrough_belt} bóng của "
        f"lưới box gốc chưa có obstacle — {verdict}. Lưới gốc ({result_base_surface} box mặt "
        f"ngoài + {result_base_tunnel_boxes} box trong {result_base_tunnels} tunnel) đã được "
        "chạy thử thắng trước khi thêm bất kỳ obstacle nào, và đường thắng sau khi thêm cũng "
        "đã được chạy thử lại nguyên vẹn với đủ tunnel, link và arrow."
    )
    if hidden_count > 0 and not hidden:
        warnings.append(
            "Không ẩn được box nào: mọi box đều nằm ở hàng trước, vốn luôn hiển thị."
        )
    elif hidden_count and len(hidden) < hidden_count:
        warnings.append(
            f"Chỉ ẩn được {len(hidden)}/{hidden_count} box: hàng slot trước luôn hiển thị nên "
            "không nhận Hidden, và lưới không còn box nào ở hàng sau để ẩn thêm."
        )
    # A mechanic the plan bought and the grid then shipped none of. Every one of
    # these has a local warning above saying *why*, but only when the mechanic got
    # far enough to have a reason - a slab that found no legal rectangle simply
    # produced an empty list. Without this the level quietly runs one mechanic
    # fewer than its tier bought and the report reads as if nothing happened,
    # which is the one thing a difficulty tool must not do.
    built_counts = {
        "hidden": len(hidden),
        "wall": len(wall_slots),
        "tunnel": used_tunnels,
        "arrow": len(arrows),
        "linked": len(linked),
        "frozen": len(frozen_locks),
        "block": len(slabs),
    }
    hollow = [kind for kind in plan.kinds if not built_counts.get(kind, 0)]
    if hollow:
        warnings.append(
            "Mức "
            + profile.label
            + " có mua "
            + ", ".join(OBSTACLE_KIND_LABELS[kind] for kind in hollow)
            + " nhưng lưới này không đặt được cái nào, nên level chạy ít hơn "
            + f"{len(hollow)} loại obstacle so với mức của nó."
        )

    if options.tunnel_count is not None and used_tunnels != options.tunnel_count:
        warnings.append(
            f"Dựng {used_tunnels} tunnel thay vì {options.tunnel_count} như đã xin: "
            + (
                "bức ảnh tràn slot nên cần thêm tunnel để chứa box."
                if used_tunnels > options.tunnel_count
                else "lưới không đủ slot cho chừng đó tunnel, hoặc không còn box nào để cất vào."
            )
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
        tunnel_placement=resolve_tunnel_placement(options, profile),
        tunnel_mode=resolve_tunnel_mode(options, plan),
        tunnel_dose=tunnel_dose(box_count, profile),
        tunnel_ceiling=tunnel_ceiling(box_count, capacity, options, profile),
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
        frozen=frozen_locks,
        frozen_dose=frozen_count,
        slabs=slabs,
        slab_dose=slab_count,
        lock_room=layer.lock_room,
        color_supply=read_color_supply(board.sequence, solution.order),
        choices=choices,
        play_groups=play_groups,
        removed_pixels=removed,
        added_pixels=balance.added,
        moved_pixels=balance.moved,
        emptied_columns=emptied,
        dropped_obstacles=dropped_obstacles,
        seed=seed,
        scan=scan,
        obstacle_plan=plan,
        obstacle_relief=relief,
        profile=profile,
        difficulty=difficulty,
        belt_slots=belt_slots,
        certified_belt=certified_belt,
        played_belt=played_belt,
        base_belt=result_base_belt,
        base_surface_boxes=result_base_surface,
        base_tunnel_count=result_base_tunnels,
        base_tunnel_boxes=result_base_tunnel_boxes,
        repair=repair,
        jam=jam,
        validation=validation,
        score=score,
        climb=climb,
        rating=rating,
        warnings=warnings,
    )


def format_report(result: AutoGenResult, options: AutoGenOptions) -> str:
    # The profile the run actually used, which is the tier's own only when the
    # picture left room for it - every "mục tiêu" below has to be the number the
    # generator was aiming at, not the one the table would have wanted.
    profile = result.profile
    tier = DIFFICULTY_PROFILES[result.difficulty]
    relief = result.obstacle_relief
    metrics = result.metrics
    scan = result.scan
    plan = result.obstacle_plan
    rating = result.rating
    score = result.score
    climb = result.climb
    chosen = " (tự đọc từ ảnh)" if options.auto_difficulty else ""
    lines = []
    if result.jam is not None:
        lines += [
            f"!! CHƯA THẮNG ĐƯỢC với piece={result.belt_slots // BALLS_PER_BOX} — "
            f"cần piece={scan.required_piece} (băng {scan.required_belt} bóng)",
            format_jam(scan, result.jam),
            f"  Box grid dưới đây vẫn đầy đủ và đúng, đã kiểm chứng trên băng "
            f"{result.certified_belt} bóng.",
            "",
        ]
    lines += [
        f"Độ khó: {tier.label}{chosen}   seed: {result.seed}"
        + (
            f"   (đã hạ {options.ease_difficulty} nấc so với tranh)"
            if options.ease_difficulty and options.auto_difficulty
            else ""
        )
        + (
            f"   xóc {result.shuffle_rolls}/{result.shuffle_attempts} bản"
            if result.shuffle_attempts > 1
            else ""
        ),
        f"  đọc từ ảnh: {rating.reason}"
        + (
            ""
            if options.auto_difficulty
            else f" — không dùng, độ khó lấy từ ô đã chọn ({tier.label})"
        ),
        f"Độ khó tổng hợp của level dựng ra: {score.summary}"
        + ("" if score.reached else f" — THIẾU {score.shortfall:.2f} nấc"),
        "  cộng từ: "
        + ", ".join(
            f"{DIFFICULTY_GROUP_LABELS[group]} {score.groups[group]:.2f}"
            for group in DIFFICULTY_DIALS
        ),
        f"  thang điểm neo vào chính 4 dòng độ khó: "
        + " < ".join(
            f"{DIFFICULTY_PROFILES[step].label} {anchor:.1f}"
            for step, anchor in enumerate(score.anchors)
        )
        + f" — level này {score.raw:.1f}",
        "  tự tăng độ khó: "
        + (
            "đã đủ mức ngay từ đầu, không cần thêm"
            if not climb.tried and climb.reached
            else "đang tắt"
            if not climb.enabled
            else (
                f"{climb.start:.2f} → {climb.final:.2f} nấc bằng cách siết "
                + "/".join(DIFFICULTY_GROUP_LABELS[group] for group in climb.added)
                if climb.climbed
                else "không loại nào siết thêm được"
            )
            + (
                "; không siết được: "
                + ", ".join(
                    f"{DIFFICULTY_GROUP_LABELS[group]} ({why})"
                    for group, why in climb.refused
                )
                if climb.refused
                else ""
            )
        ),
        f"Lưới box gốc (chưa obstacle): THẮNG ĐƯỢC, băng đỉnh {result.base_belt}/"
        f"{result.certified_belt} bóng — {result.base_surface_boxes} box mặt ngoài"
        + (
            f" + {result.base_tunnel_boxes} box tràn vào {result.base_tunnel_count} tunnel"
            f" (nhả đúng lúc tranh cần)"
            if result.base_tunnel_boxes
            else ", không cần tunnel"
        ),
        f"Obstacle: {plan.count} loại — level này rút {plan.dose} loại trong khoảng"
        f" {plan.budget[0]}-{plan.budget[1]} của mức {tier.label} — {plan.labels}",
        "  không dùng: "
        + (
            "; ".join(f"{OBSTACLE_KIND_LABELS[kind]} ({why})" for kind, why in plan.skipped)
            if plan.skipped
            else "không có, mức này dùng hết"
        ),
        f"  dạng obstacle: mức {relief.label}"
        + (
            f" — đã hạ sẵn {relief.eased} nấc theo yêu cầu (từ {relief.tier_label})"
            if relief.eased
            else ""
        )
        + (
            f" — riêng chôn box hạ về Easy vì tranh không thắng được trên piece"
            f"={result.scan.piece} (cần piece={result.scan.required_piece}); obstacle đặt lên"
            " trên vẫn ở dạng trên"
            if relief.unburied
            else ""
        )
        + (
            f" — hạ thêm {relief.steps} nấc từ {relief.top_label}: băng không chịu "
            + "/".join(OBSTACLE_KIND_LABELS[kind] for kind in relief.refused)
            + f" ở dạng {relief.top_label}, tranh chỉ chừa {relief.room} box trống"
            if relief.relieved
            else f" — đúng dạng đã đặt, tranh chừa {relief.room} box trống trên băng"
            + ("" if relief.enabled else " (tự hạ đang tắt)")
        )
        + (
            "; băng vẫn cắt bớt "
            + "/".join(OBSTACLE_KIND_LABELS[kind] for kind in relief.cut)
            if relief.cut
            else ""
        ),
        f"  obstacle làm băng đầy thêm: {result.obstacle_belt_cost} bóng"
        f" ({result.walkthrough_belt} → {result.played_belt}/{result.certified_belt}),"
        f" còn dư {result.played_headroom} bóng khi chơi đúng thứ tự obstacle bắt buộc",
        f"Quét ảnh: {scan.colors} màu, {scan.painted} pixel, {scan.run_count} mảng màu"
        f" (dài nhất {scan.longest_run}, trung bình {scan.mean_run:.1f})"
        f"   độ vụn {scan.fragmentation:.0%}",
        f"Băng truyền: đoạn chật nhất cần {scan.demand.peak_balls}/{result.belt_slots} bóng"
        f" = {scan.demand.peak_boxes} màu chờ cùng lúc, còn dư {scan.belt_headroom}",
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
        f"piece (đỉnh số box cùng lúc): {metrics.peak_boxes}"
        f"   lời giải cần tối đa {metrics.required_belt}/{metrics.belt_slots} bóng trên băng",
        "",
        "Lời giải đã kiểm chứng:",
        f"  validate lưới vừa sinh: {len(result.validation_errors)} lỗi,"
        f" {len(result.validation_warnings)} cảnh báo"
        + "".join(
            f"\n    [{message.severity}] {message.message}" for message in result.validation
        ),
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
            f" (chế độ {result.tunnel_mode}"
            + (", ảnh tràn slot nên buộc phải có" if plan.overflow else "")
            + ")"
            + f"   độ chôn (dig window): "
            + "/".join(str(window) for window in result.dig_windows)
            + f" (mục tiêu {profile.dig_window})",
            f"  đo từ ảnh: mức {profile.label} muốn {result.tunnel_dose} tunnel cho"
            f" {result.total_boxes} box, trần "
            + (
                f"{result.tunnel_ceiling} tunnel (tự đo theo ảnh)"
                if options.max_tunnels <= 0
                else f"{options.max_tunnels} tunnel (đặt tay)"
            ),
            f"  phải đào: tối đa {result.release.max_dig} box thừa trước khi tới box cần,"
            f" trung bình {result.release.mean_dig:.2f}",
        ]
        lines.append(f"  vị trí: {TUNNEL_PLACEMENT_LABELS[result.tunnel_placement]}")
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
    census = result.choices
    if census.steps:
        lines += [
            "",
            f"Số box tap được ở mỗi lượt: ít nhất {census.fewest}, trung bình "
            f"{census.mean:.1f} — {census.forced} / {census.steps} lượt "
            f"({census.forced_ratio:.0%}) chỉ còn đúng một box hợp lệ",
            "  đây là con số duy nhất ở đây phản ánh obstacle: tunnel chỉ mời đầu hàng,"
            " arrow chờ chìa, khoá chờ đủ pixel, băng đầy thì từ chối tất.",
        ]
    if result.frozen or result.slabs:
        total = len(result.solution.order) * BALLS_PER_BOX
        lines += [
            "",
            f"Khoá theo tiến độ: giữ {result.locked_balls}/{total} bóng "
            f"({result.lock_pressure:.0%} bức tranh), mở khi tranh đã tan "
            f"đủ số pixel ghi bên dưới",
        ]
        if result.frozen:
            lines.append(
                f"  Frozen: {len(result.frozen)}/{result.frozen_dose} box "
                f"(mục tiêu {profile.frozen_ratio:.0%} box mặt ngoài, mở ở "
                f"{profile.frozen_at[0]:.0%}-{profile.frozen_at[1]:.0%} bức tranh)"
            )
            lines.append(
                "  slot (x, y) → count, còn dư trước lúc cần: "
                + ", ".join(
                    f"({lock.slot[0]}, {lock.slot[1]}) → {lock.count} dư {lock.slack}"
                    for lock in result.frozen
                )
            )
        if result.slabs:
            span = result.slabs[0]
            scale = block_room_scale(result.lock_room)
            lines.append(
                f"  LargeBlock: {len(result.slabs)}/{result.slab_dose} slab "
                f"{span.span_x}x{span.span_y} box, che luôn màu bên dưới "
                f"(băng còn dư {result.lock_room} box → mở ở "
                + ", ".join(f"{share * scale:.0%}" for share in profile.block_at)
                + " bức tranh)"
            )
            lines.append(
                "  ô lưới (x, y, w, h) → count, che, còn dư: "
                + ", ".join(
                    f"({slab.rect[0]}, {slab.rect[1]}, {slab.rect[2]}, {slab.rect[3]}) → "
                    f"{slab.count} che {len(slab.covered)} box dư {slab.slack}"
                    for slab in result.slabs
                )
            )
        if result.trimmed_locks:
            lines.append(
                f"  {result.trimmed_locks} khoá phải hạ số xuống dưới mức của tier: "
                "đường thắng cần box đằng sau chúng sớm hơn mốc tier đặt ra"
            )
        locked_colors = {lock.color for lock in result.frozen} | {
            spec.color
            for slab in result.slabs
            for spec in (result.solution.order[index] for index in slab.covered)
        }
        if locked_colors and result.color_supply:
            lines.append(
                "  màu bị khoá → pixel tranh cần / bóng trên lưới, box còn tap được: "
                + ", ".join(
                    f"{color}: {info.pixels}/{info.balls}, {free} box"
                    for color in sorted(locked_colors)
                    if (info := result.color_supply.get(color)) is not None
                    for free in (
                        sum(
                            1
                            for index, spec in enumerate(result.solution.order)
                            if spec.color == color
                            and not any(
                                lock.order_index == index for lock in result.frozen
                            )
                            and not any(index in slab.covered for slab in result.slabs)
                        ),
                    )
                )
            )
    if result.removed_pixels or result.added_pixels or result.moved_pixels:
        lines += [
            "",
            "Cân bằng màu (mỗi màu chia hết cho 9): "
            + balance_summary(result.added_pixels, result.moved_pixels, result.removed_pixels),
        ]
    if result.warnings:
        lines += [""] + [f"- {warning}" for warning in result.warnings]
    return "\n".join(lines)
