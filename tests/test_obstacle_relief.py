from __future__ import annotations

"""How hard the obstacles are allowed to bite, once the picture has been paid for.

The tier is read off the picture, and it then doses every mechanic as if the
conveyor were empty. Those are two difficulties adding up in the same place, and
the hardest pictures are exactly the ones with no belt left to pay for the
hardest obstacle forms - so a hard picture used to get a level where the burial
was cut back by the belt check and the stall links were dropped one at a time by
the belt check. It still won; what survived was just not designed.

Relief is the answer to that, and these tests pin down what it may and may not
do. It may soften: a link that clears clean instead of squatting, an arrow whose
key is the box opened just before, a shallower queue, fewer walls. It may not
*remove*: which mechanics a level carries stays the obstacle budget's decision
(``test_obstacle_budget``), and every mechanic that survives the budget is still
on the grid afterwards. And whatever comes out has a winning line that has been
replayed with the obstacles in place.
"""

import pytest

from pixel_level_tool.domain.enums import LevelDifficulty
from pixel_level_tool.services.box_autogen import (
    BALLS_PER_BOX,
    BELT_SPENDING_KINDS,
    DIFFICULTY_PROFILES,
    OBSTACLE_BUDGET,
    OBSTACLE_KINDS,
    AutoGenOptions,
    auto_generate_boxes,
    belt_room,
    format_report,
    shuffle_score,
    soften_profile,
)
from pixel_level_tool.services.pixel_gameplay import (
    BoardState,
    GameRules,
    belt_peak,
    box_multiset,
    simulate_groups,
    solve_order,
)
from tests.test_box_autogen import ALL_DIFFICULTIES, assert_valid, banded_level, level_10


HARD_TIERS = [int(LevelDifficulty.Hard), int(LevelDifficulty.SuperHard)]


def generated(level, **knobs):
    options = AutoGenOptions(**knobs)
    return auto_generate_boxes(level, options), options


def roomy_level():
    """A picture with room to spare in both senses: belt and lattice.

    Ten colours in solid bands, three boxes each. Each band is one contiguous run
    in play order, so the conveyor never holds more than one colour and the belt
    is almost entirely free - and thirty boxes on a sixty-four slot lattice leave
    plenty of slots for the walls and tunnels a hard tier wants. Both matter: a
    six-box picture has belt to spare too, and still cannot carry a tunnel,
    because there is nowhere on the grid to point its mouth.
    """
    return banded_level([0, 2, 3, 4, 5, 6, 7, 8, 11, 13], width=9, band_height=3)


# --------------------------------------------------------------------------- #
# The reading
# --------------------------------------------------------------------------- #
def test_belt_room_is_counted_in_whole_boxes_because_that_is_how_it_is_spent():
    assert belt_room(45, 45) == 0
    assert belt_room(36, 45) == 1
    # Eight balls free is no room at all: a tap pours nine or nothing.
    assert belt_room(37, 45) == 0
    assert belt_room(9, 45) == 4


def test_a_picture_that_fills_its_belt_leaves_no_room_and_one_that_does_not_does():
    tight, _ = generated(level_10(), difficulty=int(LevelDifficulty.Hard))
    roomy, _ = generated(roomy_level(), difficulty=int(LevelDifficulty.Hard))
    assert tight.obstacle_relief.room == 0
    assert roomy.obstacle_relief.room > 0


# --------------------------------------------------------------------------- #
# Softening, and the line it may not cross
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("difficulty", HARD_TIERS)
def test_softening_never_zeroes_a_dose_the_tier_was_spending(difficulty):
    """A mechanic dosed to nothing is a mechanic removed, which is not relief's call."""
    tier = DIFFICULTY_PROFILES[difficulty]
    for form in range(int(LevelDifficulty.Easy), difficulty):
        soft = soften_profile(tier, difficulty, form)
        assert soft.walls >= 1, "the tier pinches, so the relieved level still pinches"
        assert soft.tunnels >= 1
        assert soft.linked_pairs >= 1
        assert soft.hidden_ratio > 0
        assert soft.arrow_ratio > 0
        assert soft.dig_window >= 1


@pytest.mark.parametrize("difficulty", HARD_TIERS)
def test_softening_only_ever_moves_a_knob_towards_the_gentle_end(difficulty):
    tier = DIFFICULTY_PROFILES[difficulty]
    soft = soften_profile(tier, difficulty, int(LevelDifficulty.Easy))
    assert soft.hidden_ratio < tier.hidden_ratio
    assert soft.arrow_ratio < tier.arrow_ratio
    assert soft.dig_window <= tier.dig_window
    assert soft.walls <= tier.walls
    assert soft.linked_mode == "sync" and tier.linked_mode == "stall"
    assert soft.clean_links and not tier.clean_links
    assert soft.arrow_reach == "near" and tier.arrow_reach == "far"


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_softening_keeps_the_tier_priority_order_it_was_handed(difficulty):
    """Relief sets how hard each mechanic bites, never which ones are picked."""
    tier = DIFFICULTY_PROFILES[difficulty]
    soft = soften_profile(tier, difficulty, int(LevelDifficulty.Easy))
    assert soft.kinds == tier.kinds
    assert soft.label == tier.label


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_a_form_at_or_above_the_tier_is_the_tier_itself(difficulty):
    tier = DIFFICULTY_PROFILES[difficulty]
    assert soften_profile(tier, difficulty, difficulty) is tier
    assert soften_profile(tier, difficulty, int(LevelDifficulty.SuperHard)) is tier


def test_a_typed_number_outranks_the_relieved_form_the_way_it_outranks_the_tier():
    """Relief swaps the table, and a number the designer typed still beats a table."""
    result, _ = generated(
        level_10(), difficulty=int(LevelDifficulty.SuperHard), hidden_boxes=4, seed=7
    )
    assert result.obstacle_relief.relieved, "the fixture is only useful if relief fires"
    assert result.hidden_boxes == 4


# --------------------------------------------------------------------------- #
# What the belt says, and what relief does about it
# --------------------------------------------------------------------------- #
def test_a_roomy_picture_keeps_its_tier_untouched():
    """Relief is a reaction, not a policy: nothing refused means nothing softened."""
    for difficulty in ALL_DIFFICULTIES:
        result, _ = generated(roomy_level(), difficulty=difficulty, seed=5)
        relief = result.obstacle_relief
        assert not relief.relieved
        assert relief.form == difficulty
        assert result.profile is DIFFICULTY_PROFILES[difficulty]


def test_a_belt_tight_picture_steps_the_hardest_tier_down_a_notch():
    result, _ = generated(level_10(), difficulty=int(LevelDifficulty.SuperHard), seed=7)
    relief = result.obstacle_relief

    assert relief.relieved
    assert relief.form < relief.difficulty
    # And it stepped down *for a reason*: the belt refused a mechanic at the
    # tier's own form, and the report can name which one.
    assert set(relief.refused) <= set(BELT_SPENDING_KINDS)
    assert relief.refused


def test_stepping_down_buys_back_the_mechanic_the_belt_was_refusing():
    """The whole point: a link the picture can pay for beats a link it drops."""
    tier = int(LevelDifficulty.SuperHard)
    relieved, _ = generated(level_10(), difficulty=tier, seed=7)
    raw, _ = generated(level_10(), difficulty=tier, obstacle_relief=False, seed=7)

    assert "linked" in raw.obstacle_relief.refused
    assert raw.link_count == 0, "the tier's stall pairs were all refused by the belt"
    assert relieved.link_count > 0
    assert relieved.linked_mode == "stall", "one step down, not all the way to sync"


def test_a_queue_left_shallow_beside_a_deep_one_is_not_the_belt_refusing():
    """Some shortfall is the belt checks working, not the tier being unaffordable.

    `plan_queues` widens each tunnel on its own so that one block sitting over a
    tight stretch of the walkthrough does not flatten the others. Reading that as
    a refusal would step a Hard level down to Easy forms - gutting its hidden
    share and its walls - over a single queue that stayed shallow.
    """
    result, _ = generated(level_10(), difficulty=int(LevelDifficulty.Hard), seed=7)
    windows = result.dig_windows

    assert len(windows) > 1 and min(windows) < max(windows), "fixture needs an uneven pair"
    assert max(windows) == DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)].dig_window
    assert "tunnel" not in result.obstacle_relief.cut
    assert not result.obstacle_relief.relieved


def test_relief_never_drops_a_mechanic_the_budget_bought():
    """Softening a level must not quietly cost it an obstacle *kind*."""
    for difficulty in HARD_TIERS:
        relieved, _ = generated(level_10(), difficulty=difficulty, seed=7)
        raw, _ = generated(
            level_10(), difficulty=difficulty, obstacle_relief=False, seed=7
        )
        plan = relieved.obstacle_plan
        assert plan.kinds == raw.obstacle_plan.kinds
        # Which kinds the level runs is the plan's answer; every one it bought has
        # to still be on the grid after softening, in some amount.
        built = {
            "hidden": relieved.hidden_boxes,
            "wall": relieved.wall_count,
            "tunnel": relieved.tunnel_count,
            "arrow": relieved.arrow_count,
            "linked": relieved.link_count,
            "frozen": len(relieved.frozen),
            "block": len(relieved.slabs),
        }
        for kind in plan.kinds:
            assert built[kind] > 0, f"{kind} was bought and then softened away"


def test_a_step_down_only_happens_when_it_loses_less_than_staying_put():
    """A gentler form that is refused just as much has bought nothing."""
    result, _ = generated(level_10(), difficulty=int(LevelDifficulty.Hard), seed=7)
    relief = result.obstacle_relief
    kept = next(cut for form, cut in relief.tried if form == relief.form)
    for form, cut in relief.tried:
        if form == relief.form:
            continue
        # Every other rung either lost more, or lost the same and was gentler.
        assert len(cut) > len(kept) or (len(cut) == len(kept) and form < relief.form)


def test_switching_relief_off_hands_the_level_its_tier_form_and_says_so():
    result, options = generated(
        level_10(), difficulty=int(LevelDifficulty.SuperHard), obstacle_relief=False, seed=7
    )
    relief = result.obstacle_relief

    assert not relief.enabled
    assert relief.form == int(LevelDifficulty.SuperHard)
    assert not relief.relieved
    assert len(relief.tried) == 1, "no ladder is walked when relief is off"
    assert result.profile is DIFFICULTY_PROFILES[int(LevelDifficulty.SuperHard)]
    assert any("Tự hạ độ khó obstacle" in warning for warning in result.warnings)


def test_relief_reads_only_the_two_mechanics_the_belt_can_actually_refuse():
    """A lock with no key and a hidden with no back row are the grid, not the belt.

    Chasing those down the ladder would step a level to Easy over something no
    amount of softening can buy, so only the conveyor-spending pair is read.
    """
    assert set(BELT_SPENDING_KINDS) <= set(OBSTACLE_KINDS)
    for difficulty in ALL_DIFFICULTIES:
        result, _ = generated(level_10(), difficulty=difficulty, seed=7)
        for _, cut in result.obstacle_relief.tried:
            assert set(cut) <= set(BELT_SPENDING_KINDS)


# --------------------------------------------------------------------------- #
# The winning line, and what the obstacles cost it
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_the_level_that_ships_is_replayable_with_every_obstacle_on_it(difficulty):
    result, _ = generated(level_10(), difficulty=difficulty, seed=7)
    board = BoardState.from_pixel_grid(result.level.pixel_grid)
    rules = GameRules(result.certified_belt, BALLS_PER_BOX)

    # The order the tunnels, links and locks force - not the ideal walkthrough.
    assert simulate_groups(board, result.play_groups_specs, rules)
    assert result.played_belt == belt_peak(board, result.play_groups_specs, rules)
    assert result.played_belt <= result.certified_belt
    assert_valid(result.level)


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_the_obstacle_belt_cost_is_the_two_plays_measured_the_same_way(difficulty):
    result, _ = generated(level_10(), difficulty=difficulty, seed=7)
    board = BoardState.from_pixel_grid(result.level.pixel_grid)
    rules = GameRules(result.certified_belt, BALLS_PER_BOX)
    bare = belt_peak(board, [[spec] for spec in result.solution.order], rules)

    assert bare == result.walkthrough_belt
    assert result.obstacle_belt_cost == max(0, result.played_belt - bare)
    assert result.played_headroom == result.certified_belt - result.played_belt


def test_a_level_whose_obstacles_spend_no_belt_says_the_cost_is_zero():
    """Hidden, Wall and ArrowLock cost knowledge, a slot and an alternative - not balls."""
    result, options = generated(
        roomy_level(),
        difficulty=int(LevelDifficulty.Easy),
        allow_tunnels=False,
        use_linked_container=False,
        seed=5,
    )
    assert result.obstacle_belt_cost == 0
    assert result.played_belt == result.walkthrough_belt
    assert "obstacle làm băng đầy thêm: 0 bóng" in format_report(result, options)


def test_belt_peak_refuses_a_play_that_loses_rather_than_reporting_a_number():
    board = BoardState.from_pixel_grid(roomy_level().pixel_grid)
    boxes = box_multiset(board, BALLS_PER_BOX)
    rules = GameRules(BALLS_PER_BOX, BALLS_PER_BOX)
    solution = solve_order(board, boxes, rules)
    assert solution is not None

    # One box of belt is enough one at a time and never enough for two at once.
    assert belt_peak(board, [[spec] for spec in solution.order], rules) == BALLS_PER_BOX
    both = [solution.order[:2]] + [[spec] for spec in solution.order[2:]]
    assert belt_peak(board, both, rules) is None


# --------------------------------------------------------------------------- #
# Reproducibility and reporting
# --------------------------------------------------------------------------- #
def test_the_form_that_ships_is_the_one_that_seed_would_have_built_on_its_own():
    """Walking the ladder must not shift the grid of the rung that is kept.

    Every attempt re-seeds from the run's own seed, so the level a relieved run
    ships is exactly the level asking for that form directly would have given -
    otherwise a designer could not reproduce their own grid.
    """
    relieved, _ = generated(level_10(), difficulty=int(LevelDifficulty.SuperHard), seed=7)
    form = relieved.obstacle_relief.form
    assert form != int(LevelDifficulty.SuperHard)

    again, _ = generated(level_10(), difficulty=int(LevelDifficulty.SuperHard), seed=7)
    assert again.hidden_boxes == relieved.hidden_boxes
    assert again.wall_slots == relieved.wall_slots
    assert again.linked_pairs == relieved.linked_pairs
    assert again.arrow_locks == relieved.arrow_locks
    assert again.play_groups == relieved.play_groups


def test_the_report_states_the_form_the_obstacles_ran_in_and_the_targets_match_it():
    result, options = generated(
        level_10(), difficulty=int(LevelDifficulty.SuperHard), seed=7
    )
    relief = result.obstacle_relief
    report = format_report(result, options)

    # The tier is still the level's, and the form is stated beside it.
    assert "Độ khó: SuperHard" in report
    assert f"dạng obstacle: mức {relief.label}" in report
    # Every "mục tiêu" in the report has to be what the run was aiming at, or a
    # designer reads a miss where the generator hit exactly what it went for.
    assert f"mục tiêu {result.profile.hidden_ratio:.0%}" in report
    assert f"mục tiêu {result.profile.dig_window}" in report
    assert any("hạ độ khó obstacle" in warning for warning in result.warnings)


def test_the_report_answers_whether_the_obstacles_made_the_level_harder():
    result, options = generated(level_10(), difficulty=int(LevelDifficulty.Hard), seed=7)
    report = format_report(result, options)

    assert f"{result.walkthrough_belt} → {result.played_belt}/{result.certified_belt}" in report
    assert any("khó thêm bao nhiêu" in warning for warning in result.warnings)


def test_relief_survives_a_run_on_a_picture_the_belt_cannot_even_hold():
    """A jammed picture is the extreme case, and it must still produce a level.

    The obstacles are certified on the belt the picture *needs* rather than the
    one it has, so relief measures its room against that same belt - anything
    else would price the forms against a conveyor nothing wins on.
    """
    from tests.test_box_autogen import noisy_level

    level = noisy_level(12, 12, colors=8, seed=1)
    # Left as painted: repairing it is exactly what would remove the jam this
    # test is about, and that path has its own tests.
    result, _ = generated(
        level, difficulty=int(LevelDifficulty.SuperHard), repair_picture=False, seed=7
    )

    assert result.jam is not None
    assert result.obstacle_relief.belt_slots == result.certified_belt
    assert result.played_belt <= result.certified_belt
    assert_valid(result.level)


# --------------------------------------------------------------------------- #
# Asking for a gentler scenario, and rolling for a better one
# --------------------------------------------------------------------------- #
def test_easing_the_difficulty_builds_the_gentler_level_the_picture_did_not_ask_for():
    """`auto_difficulty` reads the tier off the picture and never steps it down."""
    picture = AutoGenOptions(auto_difficulty=True, seed=7)
    read, _ = generated(level_10(), auto_difficulty=True, seed=7)
    eased, _ = generated(level_10(), auto_difficulty=True, ease_difficulty=1, seed=7)

    assert eased.difficulty == read.difficulty - 1
    assert eased.level.difficulty == eased.difficulty, "the file carries the eased tier"
    assert eased.obstacle_plan.budget == OBSTACLE_BUDGET[eased.difficulty]
    assert picture.ease_difficulty == 0, "and nothing is eased unless it is asked for"


def test_easing_is_floored_at_easy_rather_than_running_off_the_scale():
    result, _ = generated(level_10(), difficulty=int(LevelDifficulty.Medium), ease_difficulty=3)

    assert result.difficulty == int(LevelDifficulty.Easy)


def test_easing_the_obstacles_leaves_the_level_at_its_own_tier():
    """The point of the separate knob: gentler mechanics, same level on the shelf."""
    result, _ = generated(
        level_10(), difficulty=int(LevelDifficulty.SuperHard), ease_obstacles=2, seed=7
    )
    relief = result.obstacle_relief

    assert result.difficulty == int(LevelDifficulty.SuperHard), "the tier is untouched"
    assert result.level.difficulty == int(LevelDifficulty.SuperHard)
    assert relief.eased == 2
    assert relief.top == int(LevelDifficulty.Medium)
    assert relief.form <= relief.top
    assert any("hạ sẵn dạng obstacle" in warning for warning in result.warnings)


def test_easing_the_obstacles_actually_softens_them():
    tier = int(LevelDifficulty.SuperHard)
    strict, _ = generated(level_10(), difficulty=tier, seed=7)
    eased, _ = generated(level_10(), difficulty=tier, ease_obstacles=3, seed=7)

    assert eased.profile.hidden_ratio < strict.profile.hidden_ratio
    assert eased.linked_mode == "sync" and strict.linked_mode == "stall"
    assert eased.obstacle_plan.kinds == strict.obstacle_plan.kinds, "same mechanics"


def test_shuffling_keeps_the_best_roll_and_says_which_seed_it_was():
    rolls = 6
    shuffled, options = generated(
        level_10(), difficulty=int(LevelDifficulty.Hard), shuffle_attempts=rolls, seed=100
    )

    assert shuffled.shuffle_attempts == rolls
    assert 1 <= shuffled.shuffle_rolls <= rolls
    assert 100 <= shuffled.seed < 100 + rolls, "the winning roll's own seed"
    assert any("Đã xóc" in warning for warning in shuffled.warnings)
    # And that seed on its own rebuilds exactly the level that was kept.
    again, _ = generated(
        level_10(), difficulty=int(LevelDifficulty.Hard), seed=shuffled.seed
    )
    assert again.obstacle_plan.kinds == shuffled.obstacle_plan.kinds
    assert again.hidden_boxes == shuffled.hidden_boxes
    assert again.wall_slots == shuffled.wall_slots


def test_shuffling_never_keeps_a_roll_that_a_plain_run_would_have_beaten():
    """The score is the whole contract: the kept roll is the best of what it saw."""
    rolls = 5
    shuffled, _ = generated(
        level_10(), difficulty=int(LevelDifficulty.Hard), shuffle_attempts=rolls, seed=200
    )
    best = max(
        (generated(level_10(), difficulty=int(LevelDifficulty.Hard), seed=200 + roll)[0]
         for roll in range(rolls)),
        key=shuffle_score,
    )

    assert shuffle_score(shuffled) == shuffle_score(best)


def test_a_single_roll_is_the_default_and_costs_nothing_extra():
    result, _ = generated(level_10(), difficulty=int(LevelDifficulty.Hard), seed=7)

    assert result.shuffle_attempts == 1 and result.shuffle_rolls == 1
    assert not any("Đã xóc" in warning for warning in result.warnings)
