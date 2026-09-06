from __future__ import annotations

"""Auto Gen Box: the two locks that open on progress - Frozen and LargeBlock.

Neither of these names a box or a partner the way an ArrowLock does. Each names
a *number*, and the runtime opens it once the picture has lost that many pixels.
That single fact drives everything tested here:

* a lock is **derived, not imposed**. Its number is read out of the play order
  the run already certified, so the certified line never waits on one - and the
  belt, which every other mechanic is priced in, is not touched at all;
* the failure it can cause is **invisible to the replay**. The gameplay model
  taps boxes by index and counts no pixels, so a lock that opens too late wins
  in the simulator and deadlocks in the runtime. Nothing above catches it, which
  is why `locks_hold` runs as a fault and again as an internal check;
* the worst version of that failure is a **colour with no spare box**. If the
  frontier wants a colour whose last box is frozen, no pixel can clear, so the
  counter never moves and the lock never opens. That is not a hard level, it is
  a dead file, and it is the one thing a Frozen box may never be.

The dose, the tier bands and the rounding are the designer-facing half and are
tested against the shape of the hand-made level 59, which carries four Frozen
boxes and two 2x2 slabs on a Medium picture.
"""

import random
from dataclasses import replace

import pytest

from pixel_level_tool.domain.enums import LevelDifficulty
from pixel_level_tool.domain.level_models import (
    FrozenCellEffectData,
    LargeBlockObstacleData,
)
from pixel_level_tool.services.box_autogen import (
    BALLS_PER_BOX,
    BLOCK_BOX_BUDGET,
    BLOCK_ROOM_FULL,
    BLOCK_TIGHT_SHARE,
    BLOCK_WIDE_ROOM,
    BLOCK_WIDE_SPAN,
    DIFFICULTY_PROFILES,
    LOCK_BUDGET,
    LOCK_KINDS,
    LOCK_MARGIN,
    SLOT,
    AutoGenError,
    AutoGenOptions,
    Placement,
    auto_generate_boxes,
    block_room_scale,
    block_span_for,
    format_report,
    locks_hold,
    plan_block_count,
    plan_frozen_count,
    round_lock,
    slab_rectangles,
)
from pixel_level_tool.services.level_serializer import level_from_dict, level_to_dict
from pixel_level_tool.services.mechanics_scanner import MechanicsScanner
from pixel_level_tool.services.pixel_gameplay import (
    BoardState,
    BoxSpec,
    GameRules,
    tap_progress,
)
from tests.test_box_autogen import (
    ALL_DIFFICULTIES,
    assert_valid,
    banded_level,
    level_10,
)

# Locks only ever land when the tier bought them, so the tests that are about
# the mechanic ask for it by hand rather than hoping the roll goes their way.
FROZEN_ON = {"frozen_boxes": 3, "blocks": 0}
BLOCKS_ON = {"blocks": 2, "frozen_boxes": 0}
BOTH_LOCKS = {"frozen_boxes": 3, "blocks": 2}


def generated(difficulty: int = int(LevelDifficulty.Hard), **knobs):
    return auto_generate_boxes(
        level_10(), AutoGenOptions(difficulty=difficulty, seed=7, **knobs)
    )


def frozen_cells(level):
    return [
        cell for cell in level.grid_cells if cell.has_effect(FrozenCellEffectData)
    ]


def frozen_count_of(cell) -> int:
    return next(
        effect.frozen_count
        for effect in cell.effects
        if isinstance(effect, FrozenCellEffectData)
    )


def slab_obstacles(level):
    return [
        obstacle
        for obstacle in level.obstacles
        if isinstance(obstacle, LargeBlockObstacleData)
    ]


# --------------------------------------------------------------------------- #
# The counter itself
# --------------------------------------------------------------------------- #
def test_tap_progress_reports_the_pixels_gone_before_each_tap():
    """Three one-colour boxes cleared in order: 0, 9 and 18 pixels gone."""
    board = BoardState(tuple([1] * 9 + [2] * 9 + [3] * 9))
    groups = [[BoxSpec(1, 9)], [BoxSpec(2, 9)], [BoxSpec(3, 9)]]
    assert tap_progress(board, groups, GameRules(45, 9)) == [0, 9, 18]


def test_tap_progress_starts_at_zero_so_the_first_tap_can_never_be_locked():
    """Nothing has cleared before the first tap, so its ceiling is below one."""
    board = BoardState(tuple([1] * 9 + [2] * 9))
    steps = tap_progress(board, [[BoxSpec(1, 9)], [BoxSpec(2, 9)]], GameRules(45, 9))
    assert steps[0] == 0


def test_tap_progress_refuses_an_order_that_loses():
    """It is the same walk as the belt check, so a losing order has no timeline."""
    board = BoardState(tuple([1] * 9 + [2] * 9))
    losing = [[BoxSpec(2, 9)], [BoxSpec(1, 9)]]
    assert tap_progress(board, losing, GameRules(9, 9)) is None


def test_tap_progress_reads_a_linked_group_at_one_moment():
    """A pair drops together, so both halves see the same number."""
    board = BoardState(tuple([1] * 9 + [2] * 9 + [3] * 9))
    groups = [[BoxSpec(1, 9), BoxSpec(2, 9)], [BoxSpec(3, 9)]]
    assert tap_progress(board, groups, GameRules(45, 9)) == [0, 18]


# --------------------------------------------------------------------------- #
# Writing the number
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value, rounding, expected",
    [
        (33, "odd", 33),
        (34, "odd", 33),
        (34, "five", 30),
        (34, "ten", 30),
        (34, "none", 34),
        (1, "odd", 1),
        (0, "odd", 0),
        (-5, "odd", 0),
    ],
)
def test_a_lock_number_is_written_the_way_the_designer_asked(value, rounding, expected):
    assert round_lock(value, rounding) == expected


def test_rounding_never_goes_up_because_the_value_is_a_safety_ceiling():
    """Rounding up would step over the limit the number was clamped to."""
    for rounding in ("odd", "five", "ten", "none"):
        for value in range(1, 60):
            assert round_lock(value, rounding) <= value


def test_an_unknown_rounding_is_refused_rather_than_guessed():
    with pytest.raises(AutoGenError):
        round_lock(20, "nearest")
    with pytest.raises(AutoGenError):
        generated(lock_rounding="nearest")


def test_the_default_rounding_writes_odd_numbers_on_a_real_level():
    result = generated(**BOTH_LOCKS)
    numbers = [lock.count for lock in result.frozen] + [
        slab.count for slab in result.slabs
    ]
    assert numbers, "this picture has to carry at least one lock for the test to say anything"
    assert all(number % 2 for number in numbers)


# --------------------------------------------------------------------------- #
# The safety property, which is the whole design
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_no_lock_ever_opens_after_the_winning_line_wants_the_box(difficulty):
    """The one invariant. A lock that opens late is an unwinnable file.

    Checked against the run's own progress timeline rather than against a fresh
    reading of it, because that timeline is what the counts were written from -
    the point is that the two cannot drift apart.
    """
    result = generated(difficulty, **BOTH_LOCKS)
    assert locks_hold(result.frozen, result.slabs, _progress_of(result), LOCK_MARGIN) == []


def _progress_of(result) -> dict[int, int]:
    """Rebuild the play order's pixel timeline from the shipped result."""
    board = BoardState.from_pixel_grid(result.level.pixel_grid)
    rules = GameRules(result.certified_belt, BALLS_PER_BOX)
    specs = [
        [result.solution.order[index] for index in group] for group in result.play_groups
    ]
    steps = tap_progress(board, specs, rules)
    assert steps is not None, "the shipped level has to win the way it is played"
    return {
        index: steps[step]
        for step, group in enumerate(result.play_groups)
        for index in group
    }


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_every_lock_keeps_the_margin_it_was_given(difficulty):
    result = generated(difficulty, **BOTH_LOCKS)
    progress = _progress_of(result)
    for lock in result.frozen:
        assert lock.count <= progress[lock.order_index] - LOCK_MARGIN
    for slab in result.slabs:
        earliest = min(progress[index] for index in slab.covered)
        assert slab.count <= earliest - LOCK_MARGIN


def test_a_bigger_margin_pushes_every_lock_earlier():
    """The knob for the case where the runtime counts balls poured, not cleared."""
    tight = generated(**BOTH_LOCKS, lock_margin=0)
    loose = generated(**BOTH_LOCKS, lock_margin=45)
    assert loose.locked_balls <= tight.locked_balls or sum(
        lock.count for lock in loose.frozen
    ) < sum(lock.count for lock in tight.frozen)


def test_locks_hold_catches_a_late_lock_that_the_replay_cannot_see():
    """The fault exists because no belt check can reach this state."""
    result = generated(**FROZEN_ON)
    assert result.frozen, "the fixture has to carry a Frozen box"
    late = [replace(lock, count=lock.ceiling + 999) for lock in result.frozen]
    complaints = locks_hold(late, [], _progress_of(result), LOCK_MARGIN)
    assert len(complaints) == len(late)
    assert "mở sau khi" in complaints[0]


def test_a_frozen_box_always_has_another_box_of_its_colour_to_stand_in():
    """The deadlock rule: a frozen last-of-its-colour never opens, because nothing clears."""
    for difficulty in ALL_DIFFICULTIES:
        result = generated(difficulty, **FROZEN_ON)
        per_color = {}
        for spec in result.solution.order:
            per_color[spec.color] = per_color.get(spec.color, 0) + 1
        for lock in result.frozen:
            assert per_color[lock.color] >= 2, (
                f"colour {lock.color} has one box and it was frozen"
            )


def test_no_slab_covers_a_box_that_is_also_frozen():
    """Two counters over one box is a lock with no defined opening moment."""
    result = generated(**BOTH_LOCKS)
    frozen = {lock.order_index for lock in result.frozen}
    for slab in result.slabs:
        assert not frozen & set(slab.covered)


def test_slabs_never_overlap_each_other():
    result = generated(int(LevelDifficulty.SuperHard), blocks=4, frozen_boxes=0)
    slots = [slot for slab in result.slabs for slot in slab.slots]
    assert len(slots) == len(set(slots))


# --------------------------------------------------------------------------- #
# What a lock costs, which is nothing the belt can feel
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_adding_the_locks_does_not_move_the_conveyor_at_all(difficulty):
    """A lock is derived from the play order, so it cannot change what that order costs."""
    without = generated(difficulty, frozen_boxes=0, blocks=0)
    with_locks = generated(difficulty, **BOTH_LOCKS)
    assert with_locks.played_belt == without.played_belt
    assert with_locks.play_groups == without.play_groups
    assert with_locks.solution.order == without.solution.order


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_a_level_carrying_both_locks_still_wins_and_still_validates(difficulty):
    result = generated(difficulty, **BOTH_LOCKS)
    assert result.winnable
    assert result.valid, [message.text for message in result.validation_errors]
    assert result.level.source_histogram() == result.level.target_histogram()
    assert_valid(result.level)


def test_a_frozen_box_never_ships_active():
    """The box cannot be opened yet, so it must not start open either."""
    result = generated(**FROZEN_ON)
    assert frozen_cells(result.level)
    for cell in frozen_cells(result.level):
        assert not cell.is_active


def test_a_frozen_box_is_never_half_of_a_linked_pair():
    """The validator makes both halves carry identical effects; two ceilings cannot."""
    result = generated(**BOTH_LOCKS, use_linked_container=True)
    linked_uids = {
        uid
        for obstacle in result.level.obstacles
        if hasattr(obstacle, "target_uids")
        for uid in obstacle.target_uids
    }
    for cell in frozen_cells(result.level):
        assert cell.internal_uid not in linked_uids


# --------------------------------------------------------------------------- #
# The dose, and what the tier asks for
# --------------------------------------------------------------------------- #
def test_the_tier_decides_the_frozen_share_and_a_typed_count_beats_it():
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    auto = AutoGenOptions()
    assert plan_frozen_count(40, auto, profile) == round(profile.frozen_ratio * 40)
    assert plan_frozen_count(40, AutoGenOptions(frozen_boxes=2), profile) == 2
    # Never more locks than there are boxes to put them on.
    assert plan_frozen_count(3, AutoGenOptions(frozen_boxes=99), profile) == 3


def test_a_slab_needs_a_grid_big_enough_to_be_worth_locking_a_quarter_of():
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Medium)]
    span = profile.block_span[0] * profile.block_span[1]
    assert plan_block_count(span * BLOCK_BOX_BUDGET - 1, AutoGenOptions(), profile) == 0
    # 44 boxes and a 2x2 slab is two slabs, which is what level 59 carries.
    assert plan_block_count(44, AutoGenOptions(), profile) == 2


def test_the_frozen_bands_and_the_slab_bands_climb_with_the_tier():
    """A harder tier locks later in the level, which is a longer lockout."""
    bands = [DIFFICULTY_PROFILES[tier].frozen_at for tier in ALL_DIFFICULTIES]
    assert [low for low, _ in bands] == sorted(low for low, _ in bands)
    assert [high for _, high in bands] == sorted(high for _, high in bands)
    windows = [DIFFICULTY_PROFILES[tier].lock_window for tier in ALL_DIFFICULTIES]
    assert windows == sorted(windows, reverse=True), "harder tiers pick tighter locks"


def test_every_tier_ranks_both_locks_exactly_once():
    for difficulty in ALL_DIFFICULTIES:
        kinds = DIFFICULTY_PROFILES[difficulty].lock_kinds
        assert sorted(kinds) == sorted(LOCK_KINDS)
        assert len(set(kinds)) == len(kinds)
        assert LOCK_BUDGET[difficulty][1] <= len(LOCK_KINDS)


def test_easy_lays_no_slab_because_its_profile_spends_none():
    result = generated(int(LevelDifficulty.Easy), frozen_boxes=0)
    assert result.slabs == []
    assert slab_obstacles(result.level) == []


def test_a_typed_zero_switches_a_lock_off_for_the_level():
    result = generated(int(LevelDifficulty.SuperHard), frozen_boxes=0, blocks=0)
    assert result.frozen == [] and result.slabs == []
    assert frozen_cells(result.level) == []
    assert slab_obstacles(result.level) == []
    assert not result.obstacle_plan.has("frozen")
    assert not result.obstacle_plan.has("block")


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
def test_a_slab_only_sits_on_a_solid_rectangle_of_boxes():
    """A rectangle with a hole in it would be a slab drawn over nothing."""
    placements = [
        Placement(BoxSpec(1, 9), index, x, y)
        for index, (x, y) in enumerate([(0, 0), (1, 0), (0, 1)])
    ]
    assert slab_rectangles(placements, 2, 2) == []
    placements.append(Placement(BoxSpec(1, 9), 3, 1, 1))
    found = slab_rectangles(placements, 2, 2)
    assert len(found) == 1
    assert found[0][:2] == (0, 0)
    assert sorted(found[0][2]) == [0, 1, 2, 3]


def test_a_slab_is_written_in_grid_cells_not_slots():
    """The level file stores box-grid cells, and one slot is three of them."""
    result = generated(**BLOCKS_ON)
    assert result.slabs
    for slab, obstacle in zip(result.slabs, slab_obstacles(result.level), strict=True):
        assert obstacle.grid_x == slab.slot_x * SLOT
        assert obstacle.grid_y == slab.slot_y * SLOT
        assert obstacle.width == slab.span_x * SLOT
        assert obstacle.height == slab.span_y * SLOT
        assert obstacle.count == slab.count > 0


def test_a_slab_never_covers_a_tunnel_or_a_wall_slot():
    result = generated(int(LevelDifficulty.SuperHard), **BOTH_LOCKS)
    covered = {slot for slab in result.slabs for slot in slab.slots}
    assert not covered & set(result.wall_slots)
    assert not covered & {slot for slot, _ in result.tunnel_mouths}


def test_the_locks_are_deterministic_for_one_seed():
    first = generated(**BOTH_LOCKS)
    second = generated(**BOTH_LOCKS)
    assert [(lock.slot, lock.count) for lock in first.frozen] == [
        (lock.slot, lock.count) for lock in second.frozen
    ]
    assert [(slab.rect, slab.count) for slab in first.slabs] == [
        (slab.rect, slab.count) for slab in second.slabs
    ]


# --------------------------------------------------------------------------- #
# The file, and telling the designer
# --------------------------------------------------------------------------- #
def test_both_locks_survive_a_round_trip_through_json():
    result = generated(**BOTH_LOCKS)
    restored = level_from_dict(level_to_dict(result.level))
    assert len(frozen_cells(restored)) == len(result.frozen)
    assert [
        (obstacle.grid_x, obstacle.grid_y, obstacle.width, obstacle.height, obstacle.count)
        for obstacle in slab_obstacles(restored)
    ] == [
        (slab.rect[0], slab.rect[1], slab.rect[2], slab.rect[3], slab.count)
        for slab in result.slabs
    ]


def test_the_mechanics_list_discovers_both_locks_without_being_told():
    result = generated(**BOTH_LOCKS)
    found = MechanicsScanner().scan(result.level)
    assert "Frozen" in found and "LargeBlock" in found


def test_the_report_states_what_is_locked_and_for_how_long():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), seed=7, **BOTH_LOCKS)
    result = auto_generate_boxes(level_10(), options)
    text = format_report(result, options)
    assert "Khoá theo tiến độ" in text
    assert f"{result.locked_balls}" in text
    if result.frozen:
        assert "Frozen:" in text
    if result.slabs:
        assert "LargeBlock:" in text


def test_lock_pressure_measures_both_kinds_in_the_same_currency():
    """A slab over four boxes is four Frozen boxes' worth of the picture shut away."""
    result = generated(**BOTH_LOCKS)
    expected = len(result.frozen) * BALLS_PER_BOX + sum(
        len(slab.covered) * BALLS_PER_BOX for slab in result.slabs
    )
    assert result.locked_balls == expected
    assert 0.0 <= result.lock_pressure <= 1.0


# --------------------------------------------------------------------------- #
# A picture with no room for a lock
# --------------------------------------------------------------------------- #
def test_a_picture_with_one_box_per_colour_gets_no_frozen_and_still_ships():
    """Every colour is its own last box, so nothing can safely freeze."""
    level = banded_level([1, 2, 3, 4, 5, 6])
    result = auto_generate_boxes(
        level, AutoGenOptions(difficulty=int(LevelDifficulty.Hard), frozen_boxes=4, seed=3)
    )
    assert result.frozen == []
    assert result.winnable and result.valid


def test_a_grid_too_small_for_a_slab_says_so_rather_than_laying_a_broken_one():
    level = banded_level([1, 2, 3, 4])
    result = auto_generate_boxes(
        level, AutoGenOptions(difficulty=int(LevelDifficulty.Hard), blocks=2, seed=3)
    )
    assert result.slabs == []
    reasons = dict(result.obstacle_plan.skipped)
    assert "block" in reasons and "box mặt ngoài" in reasons["block"]


# --------------------------------------------------------------------------- #
# A slab is opaque, and its size comes off the level's own margin
# --------------------------------------------------------------------------- #
def test_a_box_under_a_slab_never_ships_active():
    """It cannot be tapped and its colour cannot be read, so it is not on offer."""
    result = generated(**BLOCKS_ON)
    assert result.slabs
    covered = {index for slab in result.slabs for index in slab.covered}
    by_slot = {
        (placement_x // SLOT, placement_y // SLOT): cell
        for cell in result.level.grid_cells
        for placement_x, placement_y in [(cell.grid_x, cell.grid_y)]
    }
    for slab in result.slabs:
        for slot in slab.slots:
            assert not by_slot[slot].is_active
    assert covered


def test_a_slab_never_covers_half_of_a_linked_pair():
    """Tapping either half takes both, so a covered half would freeze the pair."""
    result = generated(**BLOCKS_ON, use_linked_container=True)
    assert result.linked_pairs, "the fixture has to carry a pair"
    covered = {slot for slab in result.slabs for slot in slab.slots}
    for left, right, _ in result.linked_pairs:
        assert left not in covered and right not in covered


def test_a_slab_and_a_hidden_box_stack_rather_than_cancel():
    """A slab lifts; Hidden does not. A box carrying both stays dark afterwards.

    So the Hidden the tier bought is left where stage 8 put it - the check here
    is that laying slabs does not quietly move the Hidden share around.
    """
    without = generated(frozen_boxes=0, blocks=0)
    with_slabs = generated(**BLOCKS_ON)
    assert with_slabs.hidden_boxes == without.hidden_boxes


def test_a_slab_grows_from_two_by_two_to_three_by_three_on_a_roomy_picture():
    """`spare_boxes` is the level's own statement of how much it can afford to lock."""
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    assert block_span_for(0, profile) == profile.block_span
    assert block_span_for(BLOCK_WIDE_ROOM - 1, profile) == profile.block_span
    assert block_span_for(BLOCK_WIDE_ROOM, profile) == BLOCK_WIDE_SPAN
    # A wide slab covers more, so a grid buys fewer of them. Read at the one tier
    # that asks for three, because a tier ceiling of two hides the difference.
    hardest = DIFFICULTY_PROFILES[int(LevelDifficulty.SuperHard)]
    assert plan_block_count(72, AutoGenOptions(), hardest, (3, 3)) < plan_block_count(
        72, AutoGenOptions(), hardest, (2, 2)
    )


def test_a_tight_picture_opens_its_slabs_earlier_than_the_tier_asks():
    """The level is already under pressure; a quarter of it going dark can be shorter."""
    scales = [block_room_scale(room) for room in range(BLOCK_ROOM_FULL + 2)]
    assert scales[0] == pytest.approx(BLOCK_TIGHT_SHARE)
    assert scales == sorted(scales), "more room never opens the slab earlier"
    assert scales[-1] == pytest.approx(1.0), "full room pays the tier's number as written"
    assert all(BLOCK_TIGHT_SHARE <= scale <= 1.0 for scale in scales)


def test_the_measured_room_is_reported_so_the_designer_can_see_what_sized_the_slab():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), seed=7, **BLOCKS_ON)
    result = auto_generate_boxes(level_10(), options)
    assert result.lock_room >= 0
    text = format_report(result, options)
    assert "che luôn màu bên dưới" in text
    assert f"băng còn dư {result.lock_room} box" in text


def test_a_roomy_picture_really_does_lay_a_three_by_three_slab():
    """End to end, not just the sizing helper: nine boxes under one counter.

    Long contiguous runs are what leave the conveyor room, so this is a picture
    of whole bands. Walls are off because a slab is a wall while it is shut, and
    a nine-slot rectangle on top of the hard tier's own walls is what
    `layout_is_open` exists to refuse - that refusal is tested elsewhere.
    """
    level = banded_level([color for color in range(1, 17)] * 4)
    result = auto_generate_boxes(
        level,
        AutoGenOptions(
            difficulty=int(LevelDifficulty.Hard),
            seed=1,
            blocks=1,
            walls=0,
            tunnel_mode="overflow",
        ),
    )
    assert result.lock_room >= BLOCK_WIDE_ROOM
    assert len(result.slabs) == 1
    slab = result.slabs[0]
    assert (slab.span_x, slab.span_y) == BLOCK_WIDE_SPAN
    assert len(slab.covered) == BLOCK_WIDE_SPAN[0] * BLOCK_WIDE_SPAN[1]
    assert slab.mass == len(slab.covered) * BALLS_PER_BOX
    assert result.winnable and result.valid
    assert locks_hold(result.frozen, result.slabs, _progress_of(result), LOCK_MARGIN) == []


# --------------------------------------------------------------------------- #
# Does the level actually get harder, and does it ever get stuck?
# --------------------------------------------------------------------------- #
def test_the_open_choice_count_falls_as_the_tier_rises():
    """The measure that the obstacles actually move.

    `measure_difficulty` walks the bare walkthrough, so it describes the picture
    and reads the same at every tier however much is laid on the grid. This one
    replays the level's own play order and counts the boxes it really offers, so
    a tier that spends more mechanics has to come out lower.
    """
    means = []
    for difficulty in ALL_DIFFICULTIES:
        runs = [
            auto_generate_boxes(
                level_10(), AutoGenOptions(difficulty=difficulty, seed=seed)
            ).choices
            for seed in range(6)
        ]
        assert all(census.steps for census in runs)
        means.append(sum(census.mean for census in runs) / len(runs))
    assert means == sorted(means, reverse=True), (
        f"a harder tier has to offer fewer taps, got {means}"
    )
    assert means[0] > means[-1]


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_a_level_always_offers_at_least_one_tap_at_every_step(difficulty):
    """The stuck check. One legal tap is tight; zero is a dead level.

    It cannot be zero by construction - the certified line's own next box is
    always among the choices - so this is a guard on that construction rather
    than on the picture.
    """
    for seed in range(6):
        result = auto_generate_boxes(
            level_10(), AutoGenOptions(difficulty=difficulty, seed=seed)
        )
        assert result.choices.fewest >= 1
        assert result.choices.steps == len(result.play_groups)


def test_locks_take_choices_away_rather_than_leaving_the_level_alone():
    """If a lock changed nothing the player can do, it would not be a mechanic."""
    without = generated(frozen_boxes=0, blocks=0)
    with_locks = generated(**BOTH_LOCKS)
    assert with_locks.choices.mean < without.choices.mean
    # ...but never down to nothing: the winning line stays playable throughout.
    assert with_locks.choices.fewest >= 1


def test_a_slab_takes_a_linked_pair_whole_or_leaves_it_alone():
    """Half a pair under a shut slab freezes the pair, and no replay sees that."""
    for seed in range(8):
        result = auto_generate_boxes(
            level_10(),
            AutoGenOptions(
                difficulty=int(LevelDifficulty.SuperHard),
                seed=seed,
                blocks=2,
                use_linked_container=True,
            ),
        )
        covered = {slot for slab in result.slabs for slot in slab.slots}
        for left, right, _ in result.linked_pairs:
            assert (left in covered) == (right in covered)


def test_a_bought_mechanic_that_ships_nothing_says_so_in_the_report():
    """A silently missing mechanic is a level quietly easier than its tier."""
    result = generated(int(LevelDifficulty.SuperHard), **BOTH_LOCKS)
    built = {
        "hidden": result.hidden_boxes,
        "wall": result.wall_count,
        "tunnel": result.tunnel_count,
        "arrow": result.arrow_count,
        "linked": result.link_count,
        "frozen": len(result.frozen),
        "block": len(result.slabs),
    }
    hollow = [kind for kind in result.obstacle_plan.kinds if not built[kind]]
    warned = any("không đặt được cái nào" in warning for warning in result.warnings)
    assert warned == bool(hollow), (
        f"hollow mechanics {hollow} but warning present = {warned}"
    )


def test_the_report_separates_what_measures_the_picture_from_what_measures_the_level():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), seed=7, **BOTH_LOCKS)
    result = auto_generate_boxes(level_10(), options)
    text = format_report(result, options)
    assert "Số box tap được ở mỗi lượt" in text
    assert f"ít nhất {result.choices.fewest}" in text
