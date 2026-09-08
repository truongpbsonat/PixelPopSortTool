from __future__ import annotations

"""What a level nobody can finish is allowed to bury.

`test_obstacle_relief` covers the belt saying no. This covers the one case the
belt never says anything about: the picture does not win on the conveyor the
level ships with at all - the "KHÔNG THỂ THẮNG với piece hiện tại" line the
dialog prints before a single box is generated.

Two facts about the run put that case outside everything else's reach. Hidden
costs no ball, so it is not in ``BELT_SPENDING_KINDS`` and no belt check
anywhere can cut it; and the obstacles are certified against the belt the
picture *needs* rather than the one it has, so on a jammed picture the belt
refuses nothing and relief has nothing to react to. The result used to be the
worst combination the tool could ship: a level the player runs dry, with 60% of
the surface hidden and the box they need next scattered anywhere on the grid.

The answer splits the level the way ``DIFFICULTY_DIALS`` already splits it -
what the player cannot see, against what is in the way. The **burial** goes to
Easy and stays there: boxes in solution order, in plain sight, handed over when
the picture asks. Every **obstacle on top** keeps its tier's form and is still
climbed, so what the level loses is only the part that made it unreadable, not
its content. Nothing here is a difficulty change: the tier, the theme and the
mechanics the level carries all stand, and raising ``piece`` to the number in
the warning hands the tier's own burial straight back.

What this cannot do, and no knob in the tool can, is make such a picture
winnable: ``winnable`` is ``jam is None``, read off the picture against its own
belt before a box exists. `test_no_amount_of_easing_wins_a_picture_that_jams`
pins that down so the promise is never mistaken for a stronger one.
"""

import pytest

from pixel_level_tool.domain.enums import LevelDifficulty
from pixel_level_tool.services.box_autogen import (
    BALLS_PER_BOX,
    BURIAL_GROUPS,
    CLIMB_ORDER,
    DIFFICULTY_DIALS,
    DIFFICULTY_PROFILES,
    AutoGenOptions,
    auto_generate_boxes,
    format_report,
    unbury_profile,
)
from tests.test_box_autogen import (
    ALL_DIFFICULTIES,
    assert_valid,
    level_10,
    noisy_level,
    unrepaired,
)
from tests.test_picture_repair import broken_up


HARD_TIERS = [int(LevelDifficulty.Hard), int(LevelDifficulty.SuperHard)]
EASY = DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)]
# The dials the burial is made of, and the ones it is not allowed to touch.
BURIAL_DIALS = tuple(dial for group in BURIAL_GROUPS for dial in DIFFICULTY_DIALS[group])


def stranded(tier: int, **knobs):
    """Level 10 on a belt one box short of what its own play needs.

    36 balls against the 40 the bare picture wants, so the jam is the picture
    rather than anything the obstacles did - which is the whole point. The
    picture is left as painted (`unrepaired`) because the repair's job is to stop
    a picture jamming, and a repaired picture is not what this file is about.
    """
    options = unrepaired(difficulty=tier, belt_slots=4 * BALLS_PER_BOX, **knobs)
    return auto_generate_boxes(level_10(), options), options


# --------------------------------------------------------------------------- #
# The promise, and the promise it is not
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier", ALL_DIFFICULTIES)
@pytest.mark.parametrize("ease", ALL_DIFFICULTIES)
def test_no_amount_of_easing_wins_a_picture_that_jams(tier, ease):
    """The honest limit of all of this, pinned so it cannot be oversold.

    `winnable` is `jam is None`: the picture against the belt its own `piece`
    buys, read before a single box exists. Level 10's bare walkthrough needs 40
    balls and this belt is 36, so no tier, no form and no obstacle count can
    flip it - only raising `piece`, or repainting. What the burial floor buys is
    a level a designer can *read*, not one that suddenly wins.
    """
    result, _ = stranded(tier, ease_obstacles=ease)

    assert result.base_belt > result.belt_slots, "the bare picture already loses"
    assert not result.winnable and result.jam is not None


@pytest.mark.parametrize("tier", HARD_TIERS)
def test_a_jam_floors_the_burial_at_easy(tier):
    result, _ = stranded(tier)
    shipped, asked = result.profile, DIFFICULTY_PROFILES[tier]

    assert result.obstacle_relief.unburied
    assert shipped.hidden_ratio == EASY.hidden_ratio < asked.hidden_ratio
    assert shipped.scramble == EASY.scramble != asked.scramble
    assert shipped.dig_window == EASY.dig_window < asked.dig_window


@pytest.mark.parametrize("tier", HARD_TIERS)
def test_the_obstacles_laid_on_top_keep_the_tiers_own_form(tier):
    """The half that is *not* touched, and the reason this is not `ease_obstacles`.

    A level stripped of its walls, arrows and links would be a different level.
    Only what the player cannot see comes down; what is in the way stays exactly
    where the relief ladder put it.
    """
    result, _ = stranded(tier)
    relief = result.obstacle_relief
    shipped, form = result.profile, DIFFICULTY_PROFILES[relief.form]
    # A dial the climb bought back is allowed to end up *harder* than the form -
    # that is stage 12b paying for the floored burial out of the top half, and
    # `test_the_climb_makes_the_shortfall_up_out_of_the_obstacles_instead` is
    # where it is asserted. Everything else has to be the form's own value.
    climbed = {
        dial for group, dials in CLIMB_ORDER if group in result.climb.added for dial in dials
    }

    assert relief.form == relief.top == tier, "the form ladder is untouched by this"
    assert relief.eased == 0, "and it is not the designer's easing knob either"
    for dial, value in vars(form).items():
        if dial in BURIAL_DIALS or dial in climbed or dial.startswith("_"):
            continue
        assert getattr(shipped, dial) == value, f"{dial} is not the burial's business"


@pytest.mark.parametrize("tier", HARD_TIERS)
def test_the_level_still_carries_every_mechanic_the_budget_bought(tier):
    """"thêm các obs vào" - the level is not shipped bare because of this."""
    result, floored = stranded(tier)
    kept, _ = stranded(tier, jam_relief=False)

    assert result.obstacle_plan.count == kept.obstacle_plan.count
    assert result.obstacle_plan.kinds == kept.obstacle_plan.kinds
    assert not result.obstacle_relief.base, "and it never falls back to the base grid"
    assert result.obstacle_free is False


@pytest.mark.parametrize("tier", HARD_TIERS)
def test_the_climb_makes_the_shortfall_up_out_of_the_obstacles_instead(tier):
    """The floor leaves a hole in the score, and stage 12b fills it from the top half.

    On level 10 at Hard this buys back the lock timing and an extra arrow - the
    burial is gone, so the level pays for its tier with what is in the way.
    """
    result, _ = stranded(tier)
    climb = result.climb

    assert all(group not in BURIAL_GROUPS for group in climb.added), (
        "a burial rung would be undone by the floor, so it is never even tried"
    )
    refused = dict(climb.refused)
    for group in BURIAL_GROUPS:
        if group in refused:
            assert "chôn box giữ ở mức dễ" in refused[group], "and the report says why"


def test_the_burial_floor_cannot_be_climbed_back_off():
    """The floor runs last in `build_obstacle_layer`, after every climb rung."""
    hard = DIFFICULTY_PROFILES[int(LevelDifficulty.SuperHard)]

    floored = unbury_profile(hard)

    for dial in BURIAL_DIALS:
        assert getattr(floored, dial) == getattr(EASY, dial)
    assert floored.walls == hard.walls, "and it touches nothing outside the burial"
    assert floored.kinds == hard.kinds, "least of all which mechanics the level has"
    assert floored.tunnels == hard.tunnels, "a count is the budget's, never a form's"


# --------------------------------------------------------------------------- #
# When it may not fire
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier", HARD_TIERS)
def test_the_level_is_still_the_tier_that_was_asked_for(tier):
    result, _ = stranded(tier)

    assert result.difficulty == tier
    assert result.level.difficulty == tier
    assert result.obstacle_relief.difficulty == tier
    assert result.valid
    assert_valid(result.level)


@pytest.mark.parametrize("tier", HARD_TIERS)
def test_switching_it_off_buries_a_stuck_level_the_way_the_tool_used_to(tier):
    result, _ = stranded(tier, jam_relief=False)

    assert result.jam is not None
    assert not result.obstacle_relief.unburied
    assert result.profile.hidden_ratio == DIFFICULTY_PROFILES[tier].hidden_ratio
    assert result.hidden_boxes > 0


@pytest.mark.parametrize("tier", HARD_TIERS)
def test_a_picture_that_wins_on_its_own_belt_keeps_its_tiers_burial(tier):
    """The overwhelming majority of runs, which this must not touch at all."""
    options = AutoGenOptions(difficulty=tier)

    result = auto_generate_boxes(level_10(), options)

    assert result.jam is None
    assert not result.obstacle_relief.unburied
    assert result.profile.hidden_ratio == DIFFICULTY_PROFILES[result.obstacle_relief.form].hidden_ratio


def test_a_picture_the_repair_saves_keeps_its_tiers_burial():
    """The reading is taken after the repairs, so this never fires on a fixed picture.

    Level 15's shredded shape cannot be won as painted - `test_picture_repair`
    turns exactly this fixture into a jam with the repair switched off - and the
    repair merges it back into a picture that plays. Once it does there is no jam
    left to react to, and the level is entitled to its tier's burial.
    """
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), seed=3)

    result = auto_generate_boxes(broken_up(15), options)

    assert result.repair.changed and result.jam is None
    assert not result.obstacle_relief.unburied


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_a_floored_run_still_ships_a_playable_certified_level(difficulty):
    options = unrepaired(difficulty=difficulty)

    result = auto_generate_boxes(noisy_level(12, 12, 10, seed=7), options)

    assert result.jam is not None and result.obstacle_relief.unburied
    assert result.valid
    assert_valid(result.level)
    assert result.solution is not None, "the winning line is replayed either way"


# --------------------------------------------------------------------------- #
# Saying so
# --------------------------------------------------------------------------- #
def test_the_warning_says_what_came_down_what_stayed_and_how_to_undo_it():
    tier = int(LevelDifficulty.SuperHard)
    result, options = stranded(tier)

    warning = next(w for w in result.warnings if "CHÔN BOX" in w)
    assert "KHÔNG THẮNG ĐƯỢC" in warning
    assert f"piece={result.scan.required_piece}" in warning, "the fix is a number"
    assert "không tốn bóng nào" in warning, "why the belt could not do this itself"
    assert "vẫn giữ dạng mức" in warning, "and that the obstacles on top stayed"
    assert "không bị dựng trơ" in warning
    assert "riêng chôn box hạ về Easy" in format_report(result, options)


def test_a_run_with_no_jam_says_nothing_about_any_of_this():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard))

    result = auto_generate_boxes(level_10(), options)

    assert not [w for w in result.warnings if "CHÔN BOX" in w]
    assert "riêng chôn box hạ về Easy" not in format_report(result, options)
