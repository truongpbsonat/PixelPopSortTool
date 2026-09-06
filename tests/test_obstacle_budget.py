from __future__ import annotations

"""How many *kinds* of obstacle a level may run, and who decides.

Every mechanic used to be gated its own way - Hidden and Wall followed the tier,
ArrowLock and LinkedContainer waited for a tick box, tunnels waited for the
picture to overflow - so what a level ended up carrying depended on which knobs
the designer happened to remember. All five are read off the level the same way
now, and two separate limits shape the answer:

* the **dose** of each mechanic, which is what the existing per-obstacle tests
  cover, and
* the **budget**, tested here: how many mechanics a tier runs at once. Two for an
  easy level, three or four for a medium one, four to six for a hard one - and
  there are only five, so the hard tiers effectively run the lot.

The budget is a ceiling on what the *tier* buys, never on what a designer types:
a count somebody entered by hand and a tunnel an oversized picture forces are
both booked before the budget opens, and can push a level past it on purpose.
"""

import random

import pytest

from pixel_level_tool.domain.enums import LevelDifficulty
from pixel_level_tool.services.box_autogen import (
    ALL_OBSTACLE_KINDS,
    DIFFICULTY_PROFILES,
    LOCK_BUDGET,
    LOCK_KINDS,
    OBSTACLE_BUDGET,
    OBSTACLE_KIND_LABELS,
    OBSTACLE_KINDS,
    AutoGenOptions,
    auto_generate_boxes,
    designer_choice,
    format_report,
    format_scan,
    obstacle_kind_dose,
    plan_obstacle_kinds,
    scan_level,
)
from pixel_level_tool.services.picture_scan import PictureScan
from tests.test_box_autogen import ALL_DIFFICULTIES, assert_valid, banded_level, level_10


def plan_for(difficulty: int, options: AutoGenOptions | None = None, **layout):
    """The plan a real picture produces, without generating the whole grid.

    The kind count is rolled inside the tier's range, so a plan needs an rng like
    a generation does. ``seed`` picks which roll: a test about the ceiling wants a
    seed that rolls high, and one about the floor a seed that rolls low.
    """
    profile = DIFFICULTY_PROFILES[difficulty]
    return plan_obstacle_kinds(
        difficulty=difficulty,
        profile=profile,
        options=options or AutoGenOptions(difficulty=difficulty),
        scan=layout.pop("scan", PictureScan()),
        surface_boxes=layout.pop("surface_boxes", 30),
        capacity=layout.pop("capacity", 64),
        box_count=layout.pop("box_count", 30),
        rng=random.Random(layout.pop("seed", 0)),
    )


def plans_for(difficulty: int, options: AutoGenOptions | None = None, seeds=range(24), **layout):
    """The same plan over many rolls, for the statements that are about the range."""
    return [plan_for(difficulty, options, seed=seed, **layout) for seed in seeds]


# --------------------------------------------------------------------------- #
# The table itself
# --------------------------------------------------------------------------- #
def test_every_tier_ranks_all_five_mechanics_exactly_once():
    """The order decides who gets dropped, so a missing name is a silent bug."""
    for difficulty in ALL_DIFFICULTIES:
        kinds = DIFFICULTY_PROFILES[difficulty].kinds
        assert sorted(kinds) == sorted(OBSTACLE_KINDS)
        assert len(set(kinds)) == len(kinds)


def test_every_kind_has_a_label_to_show_the_designer():
    assert set(OBSTACLE_KIND_LABELS) == set(ALL_OBSTACLE_KINDS)


def test_the_locks_are_budgeted_apart_from_the_mechanics():
    """A lock costs no belt and no slot, so it must not push a mechanic off a level."""
    for difficulty in ALL_DIFFICULTIES:
        for plan in plans_for(difficulty):
            assert set(plan.mechanics) <= set(OBSTACLE_KINDS)
            assert set(plan.locks) <= set(LOCK_KINDS)
            assert set(plan.mechanics) | set(plan.locks) == set(plan.kinds)
            low, high = LOCK_BUDGET[difficulty]
            assert low <= plan.lock_dose <= high
            assert len(plan.locks) <= high


def test_the_hardest_tier_always_carries_both_locks_and_easy_may_carry_none():
    hardest = plans_for(int(LevelDifficulty.SuperHard))
    assert all(len(plan.locks) == 2 for plan in hardest)
    easy = {len(plan.locks) for plan in plans_for(int(LevelDifficulty.Easy))}
    assert easy == {0, 1}


def test_the_budget_widens_with_the_difficulty_and_never_goes_backwards():
    budgets = [OBSTACLE_BUDGET[difficulty] for difficulty in ALL_DIFFICULTIES]
    for (low, high), (next_low, next_high) in zip(budgets, budgets[1:]):
        assert low <= next_low and high <= next_high
    assert OBSTACLE_BUDGET[int(LevelDifficulty.Easy)] == (1, 2)
    assert OBSTACLE_BUDGET[int(LevelDifficulty.Medium)] == (3, 4)
    assert OBSTACLE_BUDGET[int(LevelDifficulty.Hard)] == (4, 6)


# --------------------------------------------------------------------------- #
# What a tier spends on a picture that can pay for anything
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_no_roll_of_a_tier_ever_spends_more_kinds_than_its_budget(difficulty):
    low, high = OBSTACLE_BUDGET[difficulty]
    for plan in plans_for(difficulty):
        assert plan.budget == (low, high)
        assert low <= plan.dose <= high
        assert len(plan.mechanics) <= high
        assert not plan.over_budget


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_the_dose_is_rolled_inside_the_range_rather_than_pinned_to_the_ceiling(difficulty):
    """A range used as a constant is decoration: two seeds must give two levels."""
    low, high = OBSTACLE_BUDGET[difficulty]
    reachable = {min(high, len(OBSTACLE_KINDS)), min(low, len(OBSTACLE_KINDS))}
    rolled = {plan.dose for plan in plans_for(difficulty)}
    assert rolled == reachable, "every rung of the tier's range has to come up"


def test_the_dose_never_asks_for_more_kinds_than_exist():
    """Hard's ceiling of six is five, and its floor comes down with it, not past it."""
    rng = random.Random(0)
    assert obstacle_kind_dose((4, 6), 5, rng) <= 5
    assert obstacle_kind_dose((4, 6), 3, rng) == 3, "a floor above what exists is what exists"
    assert obstacle_kind_dose((0, 0), 5, rng) == 0


def test_easy_runs_one_or_two_mechanics_drawn_from_the_whole_pool():
    """Easy draws its mix rather than reading the tier's order from the top.

    The point of drawing is variety, so what is asserted here is the *range*: one
    or two mechanics, any of them, and more than one mix across the seeds. What
    keeps an easy level easy is no longer which mechanics it picked but the dose
    and the form it picked them at, which is what the per-obstacle tests cover.

    Wall is the one that still cannot land, and not because of the order: Easy's
    profile spends no walls at all, so `afford_reason` turns it down whichever
    position it is drawn in.
    """
    plans = plans_for(int(LevelDifficulty.Easy))
    for plan in plans:
        assert 1 <= len(plan.mechanics) <= 2
        assert set(plan.mechanics) <= set(OBSTACLE_KINDS)
        assert not plan.has("wall")
    assert len({plan.mechanics for plan in plans}) > 1, "a drawn mix has to vary"
    assert any(plan.has("hidden") for plan in plans)


def test_medium_runs_three_or_four_and_hard_four_or_all_five():
    for plan in plans_for(int(LevelDifficulty.Medium)):
        assert 3 <= len(plan.mechanics) <= 4

    hard = plans_for(int(LevelDifficulty.Hard))
    assert {len(plan.mechanics) for plan in hard} == {4, len(OBSTACLE_KINDS)}
    assert any(not plan.skipped for plan in hard), "a full roll of Hard runs the lot"
    assert any(plan.skipped for plan in hard), "and a low roll leaves one out, by name"


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_the_budget_holds_all_the_way_through_a_real_generation(difficulty):
    result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
    plan = result.obstacle_plan
    assert len(plan.mechanics) <= OBSTACLE_BUDGET[difficulty][1]
    assert len(plan.locks) <= LOCK_BUDGET[difficulty][1]
    # Nothing may show up that the plan did not buy.
    assert plan.has("hidden") or result.hidden_boxes == 0
    assert plan.has("arrow") or result.arrow_count == 0
    assert plan.has("linked") or result.link_count == 0
    assert plan.has("tunnel") or result.tunnel_count == 0
    assert plan.has("frozen") or result.frozen == []
    assert plan.has("block") or result.slabs == []
    assert_valid(result.level)


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_a_level_still_wins_with_everything_its_tier_bought(difficulty):
    """The budget adds mechanics, so the winnability proof has to survive it."""
    result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
    assert result.solution.required_belt <= result.belt_slots
    assert result.total_boxes == 30
    assert result.level.source_histogram() == result.level.target_histogram()


def test_the_harder_the_tier_the_more_mechanics_it_carries():
    """A statement about the tiers, so it is read over the whole range of rolls.

    One seed per tier cannot say this any more: Hard rolling five and SuperHard
    rolling four is a legal pair of levels, and it is the point of rolling.
    """
    spans = [
        [plan.count for plan in plans_for(difficulty)] for difficulty in ALL_DIFFICULTIES
    ]
    fewest = [min(counts) for counts in spans]
    most = [max(counts) for counts in spans]
    assert fewest == sorted(fewest) and most == sorted(most)
    assert most[0] < most[-1]


def test_two_seeds_at_the_same_tier_can_carry_different_mechanics():
    """The fix for every Hard level shipping the same five-mechanic syllabus."""
    mixes = {
        auto_generate_boxes(
            level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Hard), seed=seed)
        ).obstacle_plan.kinds
        for seed in range(8)
    }
    assert len(mixes) > 1


# --------------------------------------------------------------------------- #
# What the designer says outranks the table
# --------------------------------------------------------------------------- #
def test_a_typed_count_is_kept_even_when_it_breaks_the_ceiling():
    """Easy buys two mechanics; four typed counts are still four mechanics."""
    asked = AutoGenOptions(
        difficulty=int(LevelDifficulty.Easy),
        hidden_boxes=2,
        walls=2,
        arrow_boxes=2,
        linked_pairs=1,
    )
    plan = plan_for(int(LevelDifficulty.Easy), asked)

    assert len(plan.mechanics) == 4 and plan.over_budget
    assert set(plan.forced) == {"hidden", "wall", "arrow", "linked"}


def test_a_typed_zero_switches_a_mechanic_off_for_the_level():
    asked = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), walls=0, hidden_boxes=0)
    plan = plan_for(int(LevelDifficulty.Hard), asked)

    assert not plan.has("wall") and not plan.has("hidden")
    assert dict(plan.skipped)["wall"] == "đã tắt cho level này"


def test_unticking_an_obstacle_beats_the_tier_that_wanted_it():
    asked = AutoGenOptions(
        difficulty=int(LevelDifficulty.SuperHard),
        use_arrow_lock=False,
        use_linked_container=False,
    )
    plan = plan_for(int(LevelDifficulty.SuperHard), asked)

    assert not plan.has("arrow") and not plan.has("linked")
    assert len(plan.mechanics) == 3


def test_ticking_an_obstacle_gets_it_even_at_the_gentlest_tier():
    asked = AutoGenOptions(difficulty=int(LevelDifficulty.Easy), use_linked_container=True)
    plan = plan_for(int(LevelDifficulty.Easy), asked)

    assert plan.has("linked")
    assert "linked" in plan.forced
    assert len(plan.mechanics) <= OBSTACLE_BUDGET[int(LevelDifficulty.Easy)][1]


@pytest.mark.parametrize(
    "kind, options, expected",
    [
        ("hidden", AutoGenOptions(), None),
        ("hidden", AutoGenOptions(hidden_boxes=0), False),
        ("hidden", AutoGenOptions(hidden_ratio=0.2), True),
        ("wall", AutoGenOptions(walls=3), True),
        ("tunnel", AutoGenOptions(), None),
        ("tunnel", AutoGenOptions(tunnel_mode="mechanic"), True),
        ("tunnel", AutoGenOptions(tunnel_mode="overflow"), False),
        ("tunnel", AutoGenOptions(allow_tunnels=False, tunnel_count=3), False),
        ("arrow", AutoGenOptions(), None),
        ("arrow", AutoGenOptions(use_arrow_lock=True), True),
        ("arrow", AutoGenOptions(arrow_boxes=4), True),
        ("linked", AutoGenOptions(use_linked_container=False, linked_pairs=9), False),
        ("frozen", AutoGenOptions(), None),
        ("frozen", AutoGenOptions(frozen_boxes=0), False),
        ("frozen", AutoGenOptions(frozen_boxes=3), True),
        ("block", AutoGenOptions(), None),
        ("block", AutoGenOptions(blocks=0), False),
        ("block", AutoGenOptions(blocks=2), True),
    ],
)
def test_the_designer_is_read_the_same_way_for_all_five(kind, options, expected):
    """A tick, a typed count, or nothing at all - one rule, every mechanic."""
    assert designer_choice(kind, options) is expected


# --------------------------------------------------------------------------- #
# What the picture can pay for
# --------------------------------------------------------------------------- #
def test_a_picture_too_small_to_pay_falls_short_of_its_tier_and_says_why():
    plan = plan_for(int(LevelDifficulty.Hard), surface_boxes=2, capacity=4, box_count=2)

    assert plan.under_budget
    reasons = dict(plan.skipped)
    assert "wall" in reasons and "arrow" in reasons and "linked" in reasons
    assert all("box mặt ngoài" in why for why in reasons.values() if "tắt" not in why)


def test_an_overflowing_picture_gets_its_tunnels_even_at_easy():
    """Geometry is not the budget's to refuse: the level does not exist without them."""
    plan = plan_for(int(LevelDifficulty.Easy), surface_boxes=8, capacity=9, box_count=30)

    assert plan.has("tunnel") and plan.overflow
    assert "tunnel" in plan.forced


def test_a_tier_that_uses_no_wall_says_so_rather_than_blaming_the_grid():
    plan = plan_for(int(LevelDifficulty.Easy))
    assert dict(plan.skipped)["wall"] == "mức Easy không dùng wall"


# --------------------------------------------------------------------------- #
# Telling the designer
# --------------------------------------------------------------------------- #
def test_the_scan_panel_states_the_tier_and_the_room_before_anything_is_generated():
    """The panel is four lines above a long form, so it carries what only it knows.

    The tier it read off the picture and the belt room left for burying boxes are
    both here; the obstacle budget is not, because the dialog's own Obstacle
    column already spells it out beside the knobs it governs.
    """
    text = format_scan(scan_level(level_10()))
    # Named after the tier the *scanner* read, not the one the combo is showing:
    # the panel describes the picture, and the two can disagree.
    assert "độ khó đọc được:" in text
    assert "chỗ trống để làm khó" in text
    assert len(text.splitlines()) <= 6, "the panel must not push the knobs off screen"


def test_the_report_names_the_mechanics_it_spent_and_the_ones_it_did_not():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Easy))
    report = format_report(auto_generate_boxes(level_10(), options), options)

    assert "Obstacle:" in report
    assert "trong khoảng 1-2 của mức Easy" in report
    assert "không dùng:" in report
    assert "Wall" in report, "the mechanics it skipped are named, not just counted"


def test_a_mechanic_asked_for_by_name_and_not_built_is_never_silent():
    """Two boxes leave no room for a lock, and a designer who ticked one must hear so."""
    options = AutoGenOptions(
        difficulty=int(LevelDifficulty.Easy), use_arrow_lock=True, use_linked_container=True
    )
    result = auto_generate_boxes(banded_level([0, 1]), options)

    assert not result.obstacle_plan.has("arrow")
    denied = [w for w in result.warnings if "Đã xin nhưng" in w]
    assert len(denied) == 1
    assert "ArrowLock" in denied[0] and "LinkedContainer" in denied[0]
