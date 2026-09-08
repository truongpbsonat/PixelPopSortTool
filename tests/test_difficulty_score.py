from __future__ import annotations

"""Reading a difficulty off the picture, and measuring the one that came out.

Two separate things used to be missing, and they are the two halves of the same
question a designer asks about a generated level: *is this the level the picture
asked for?*

The first half is the reading. "Lấy độ khó từ ảnh" was one line that mapped a
colour count onto a tier, and two questions were riding on it: what the artwork
is (dễ / vừa / khó, three wide, what somebody says out loud) and which tier to
build for it (Easy / Medium / Hard / SuperHard, four wide, because the fourth
exists for pictures past what the three-wide scale was drawn for). These pin the
two apart and pin down that the tier is a *target*, not a description.

The second half is the sum. The tier decided which mechanics a level carries and
relief decided how hard each one bites, and nothing ever asked what they came to
*together*. So a Hard picture whose belt refused the hard forms shipped with a
Hard label and an Easy level under it. The score is that sum on the same 0-3
line the tiers live on, and the climb is what closes the gap - under rules these
tests hold it to: it may harden what the picture can still pay for, it may never
overrule a knob the designer set, and whatever comes out still has to win and
still has to validate.
"""

import pytest

from pixel_level_tool.domain.enums import LevelDifficulty
from pixel_level_tool.services.box_autogen import (
    DIFFICULTY_DIALS,
    DIFFICULTY_PROFILES,
    PICTURE_BANDS,
    AutoGenOptions,
    auto_generate_boxes,
    climb_sources,
    dial_ladder,
    difficulty_anchors,
    format_report,
    group_notch,
    harden_profile,
    jam_headline,
    ladder_notch,
    profile_dials,
    rate_picture,
    raw_difficulty,
)
from pixel_level_tool.services.picture_scan import scan_picture
from tests.test_box_autogen import (
    ALL_DIFFICULTIES,
    assert_valid,
    banded_level,
    level_10,
    noisy_level,
)

TIERS = sorted(DIFFICULTY_PROFILES)


def generated(level, **knobs):
    options = AutoGenOptions(seed=7, **knobs)
    return auto_generate_boxes(level, options), options


def roomy_level():
    """Ten colours in solid bands: belt to spare, and slots to spare.

    The same picture ``test_obstacle_relief`` uses for the same reason - a
    picture with room is the only place a hard tier's own forms actually fit, so
    it is where "the climb had nothing to buy" can be told apart from "the climb
    could not buy anything".
    """
    return banded_level([0, 2, 3, 4, 5, 6, 7, 8, 11, 13], width=9, band_height=3)


def rating_of(level):
    return rate_picture(scan_picture(level.pixel_grid))


# --------------------------------------------------------------------------- #
# Reading the picture: two scales, not one
# --------------------------------------------------------------------------- #
def test_the_band_is_three_wide_and_the_tier_is_four_so_they_cannot_be_one_reading():
    """A ten-colour picture and a twenty-colour one look equally hard; only one is SuperHard."""
    ten = rating_of(banded_level(list(range(10)), width=9, band_height=3))
    twenty = rating_of(banded_level(list(range(20)), width=9, band_height=3))

    assert ten.band == twenty.band, "both are simply khó to look at"
    assert ten.band_label == "khó"
    assert ten.tier == int(LevelDifficulty.Hard)
    assert twenty.tier == int(LevelDifficulty.SuperHard), (
        "past what the three-wide scale was drawn for, so it does not get clamped into Hard"
    )


@pytest.mark.parametrize(
    "colors, band, tier",
    [
        (2, "dễ", LevelDifficulty.Easy),
        (3, "dễ", LevelDifficulty.Easy),
        (4, "vừa", LevelDifficulty.Medium),
        (8, "vừa", LevelDifficulty.Medium),
        (9, "khó", LevelDifficulty.Hard),
    ],
)
def test_the_colour_count_sets_both_readings_at_their_own_width(colors, band, tier):
    rating = rating_of(banded_level(list(range(colors)), width=9, band_height=3))
    assert rating.band_label == band
    assert rating.tier == int(tier)
    assert not rating.bumped, "solid bands are not fragmented, so nothing is added"


def test_a_fragmented_picture_moves_the_target_without_moving_what_it_looks_like():
    """The bump is about how the picture *plays*, so it lands on the tier only."""
    bands = rating_of(banded_level([0, 2, 3, 4, 5], width=9, band_height=3))
    noise = rating_of(noisy_level(width=9, height=15, colors=5, seed=3))

    assert bands.band == noise.band, "same colour count, so the same thing to look at"
    assert noise.fragmented and noise.bumped
    assert noise.tier == bands.tier + 1
    assert "nâng" in noise.reason and f"{noise.fragmentation:.0%}" in noise.reason


def test_the_reading_is_a_target_and_says_so_rather_than_describing_the_level():
    """`rating.tier` is what to aim at; `score.target` is that same number aimed at."""
    result, _ = generated(level_10(), auto_difficulty=True)
    assert result.rating.tier == result.difficulty == result.score.target


def test_the_picture_is_read_even_when_the_designer_typed_their_own_tier():
    """A designer overruling the picture still wants to know what it would have said."""
    typed, options = generated(level_10(), difficulty=int(LevelDifficulty.SuperHard))
    assert typed.difficulty == int(LevelDifficulty.SuperHard)
    assert typed.rating.tier == rating_of(level_10()).tier
    assert "không dùng" in format_report(typed, options), (
        "the report has to say the reading was not the thing that decided the tier"
    )


# --------------------------------------------------------------------------- #
# The ladder every dial is read on
# --------------------------------------------------------------------------- #
def test_a_dial_at_a_tiers_own_setting_reads_as_that_tier_or_the_one_that_set_it():
    """A dial two tiers share reads as the *first* of them, which is the point.

    ``clean_links`` is (0, 0, 1, 1): Hard and SuperHard both let a pair squat, so
    "a pair that squats" is a Hard reading and SuperHard has to earn its extra
    notch somewhere else. Reading it as 3 instead would hand every Hard level a
    SuperHard credit for a dial it shares.
    """
    for dial in {name for names in DIFFICULTY_DIALS.values() for name in names}:
        ladder = dial_ladder(dial)
        for tier in TIERS:
            notch = ladder_notch(profile_dials(DIFFICULTY_PROFILES[tier])[dial], ladder)
            first = ladder.index(ladder[tier])
            assert notch == pytest.approx(float(first)), f"{dial} at tier {tier}"


def test_easy_is_the_floor_of_the_scale_rather_than_a_step_above_nothing():
    """There is no gentler level to be short of, so Easy's own setting is 0."""
    ladder = (0.08, 0.15, 0.40, 0.60)
    assert ladder_notch(0.08, ladder) == 0.0
    assert ladder_notch(0.04, ladder) == 0.0
    assert ladder_notch(0.0, ladder) == 0.0


def test_between_two_tiers_the_answer_is_the_distance_between_them():
    ladder = (0.08, 0.15, 0.40, 0.60)
    assert ladder_notch(0.275, ladder) == pytest.approx(1.5)
    assert ladder_notch(0.50, ladder) == pytest.approx(2.5)


def test_a_flat_rung_is_read_from_its_bottom_so_absence_is_not_credited_as_a_choice():
    """Medium has no wall; a level with no wall must not score Medium's zero as one."""
    walls = dial_ladder("wall_pinches")
    assert walls == (0.0, 0.0, 1.0, 2.0), "two walls make one pinch, so 0/0/2/4 halves"
    assert ladder_notch(0.0, walls) == 0.0
    assert ladder_notch(0.5, walls) == pytest.approx(1.5)
    assert ladder_notch(1.0, walls) == pytest.approx(2.0)


def test_walls_are_scored_by_what_they_pinch_not_by_how_many_slots_are_empty():
    """Every unfilled slot is a wall, so a picture that tiles badly leaves leftovers.

    Counting those would hand a badly-packing picture a wall score it never
    designed for - and on a roomy ten-colour picture at Hard that was the whole
    difference between the level reaching its tier and not.
    """
    result, _ = generated(roomy_level(), difficulty=int(LevelDifficulty.Hard))
    pinches = len(result.pinched_slots)
    assert result.wall_count >= pinches, "there are leftovers beyond the pinches"
    assert result.score.groups["wall"] == pytest.approx(
        ladder_notch(float(pinches), dial_ladder("wall_pinches"))
    )


def test_nothing_is_measured_past_the_hardest_tier_because_nothing_aims_there():
    ladder = (0.08, 0.15, 0.40, 0.60)
    assert ladder_notch(0.60, ladder) == 3.0
    assert ladder_notch(0.95, ladder) == 3.0


# --------------------------------------------------------------------------- #
# The bands, which are the four difficulty rows themselves
# --------------------------------------------------------------------------- #
def test_the_scale_is_anchored_on_the_four_difficulty_rows_and_nothing_else():
    anchors = difficulty_anchors()
    assert len(anchors) == len(TIERS)
    assert anchors[0] == 0.0, "Easy's dials are the bottom of every ladder"
    assert all(
        low < high for low, high in zip(anchors, anchors[1:])
    ), f"the anchors have to be orderable to interpolate on: {anchors}"


def test_a_tier_spent_in_full_scores_exactly_that_tier():
    """The calibration in one line: the profiles are the scale, so they land on it."""
    anchors = difficulty_anchors()
    for tier in TIERS:
        raw = raw_difficulty(profile_dials(DIFFICULTY_PROFILES[tier]))
        assert ladder_notch(raw, anchors) == pytest.approx(float(tier))


def test_the_sum_is_a_sum_so_one_mechanic_alone_does_not_decide_it():
    """A level at Hard's burial and nothing else is not a Hard level.

    This is the thing the score exists to say. Every dial was being checked
    against the tier on its own, so a level with Hard's Hidden share read as
    "Hard, burial as asked" and the four missing mechanics went unnamed.
    """
    hard = profile_dials(DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)])
    burial_only = dict.fromkeys(hard, 0.0)
    for dial in DIFFICULTY_DIALS["hidden"] + DIFFICULTY_DIALS["scramble"]:
        burial_only[dial] = hard[dial]

    anchors = difficulty_anchors()
    assert group_notch("hidden", burial_only) == pytest.approx(float(LevelDifficulty.Hard))
    assert ladder_notch(raw_difficulty(burial_only), anchors) < float(LevelDifficulty.Hard)
    assert ladder_notch(raw_difficulty(hard), anchors) == pytest.approx(
        float(LevelDifficulty.Hard)
    )


def test_the_bands_a_picture_is_reported_in_are_the_three_a_designer_says():
    assert PICTURE_BANDS == ("dễ", "vừa", "khó")


# --------------------------------------------------------------------------- #
# Scoring a level that was actually built
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_every_generated_level_carries_the_sum_it_was_measured_at(difficulty):
    result, _ = generated(level_10(), difficulty=difficulty)
    assert result.score.target == difficulty
    assert 0.0 <= result.score.notch <= 3.0
    assert result.difficulty_matched is result.score.reached
    assert result.score.tier == round(result.score.notch)


def test_a_level_with_every_mechanic_switched_off_scores_next_to_nothing():
    """Turn all seven off and what is left is the scramble, which has no off switch.

    The layout is always ordered *somehow* - see ``_layout`` - so the sum cannot
    reach zero on a hard tier. What matters is that the seven mechanics all read
    as absent and the total lands nowhere near the tier: this is the level that
    used to ship as "Hard" with nothing on it.
    """
    result, _ = generated(
        level_10(),
        difficulty=int(LevelDifficulty.Hard),
        hidden_boxes=0,
        walls=0,
        arrow_boxes=0,
        linked_pairs=0,
        frozen_boxes=0,
        blocks=0,
        tunnel_mode="overflow",
        difficulty_climb=False,
    )
    assert not result.obstacle_plan.mechanics, "nothing was bought, so nothing is on it"
    assert all(
        result.score.groups[group] == 0.0
        for group in DIFFICULTY_DIALS
        if group != "scramble"
    ), result.score.groups
    assert result.score.tier == int(LevelDifficulty.Easy)
    assert not result.score.reached


def test_a_roomy_picture_at_its_own_tier_reaches_it_without_being_pushed():
    result, _ = generated(roomy_level(), difficulty=int(LevelDifficulty.Hard))
    assert result.score.reached
    assert not result.climb.climbed, "nothing was short, so nothing was hardened"


# --------------------------------------------------------------------------- #
# The climb
# --------------------------------------------------------------------------- #
def test_the_climb_is_what_stops_a_relieved_level_shipping_under_the_wrong_label():
    """The whole bug, in one comparison: same picture, same seed, one knob."""
    without, _ = generated(
        level_10(), difficulty=int(LevelDifficulty.Medium), difficulty_climb=False
    )
    with_climb, _ = generated(
        level_10(), difficulty=int(LevelDifficulty.Medium), difficulty_climb=True
    )

    assert not without.score.reached, "relief left it under its own tier"
    assert with_climb.score.reached
    assert with_climb.score.notch > without.score.notch
    assert with_climb.climb.added, "and it says which mechanics it spent getting there"


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_the_climb_never_leaves_a_level_gentler_than_it_found_it(difficulty):
    """The relieved layer is the floor: a climb that buys nothing changes nothing."""
    without, _ = generated(level_10(), difficulty=difficulty, difficulty_climb=False)
    with_climb, _ = generated(level_10(), difficulty=difficulty, difficulty_climb=True)
    assert with_climb.score.notch >= without.score.notch


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_a_climbed_level_still_wins_and_still_validates(difficulty):
    """Every rung is a full rebuild, so every rung is re-certified like any other."""
    result, _ = generated(roomy_level(), difficulty=difficulty)
    assert_valid(result.level)
    assert result.valid
    assert result.winnable


def test_the_climb_does_not_overrule_a_mechanic_the_designer_switched_off():
    """A shortfall somebody asked for is not a shortfall to be made up."""
    result, _ = generated(
        level_10(), difficulty=int(LevelDifficulty.Hard), walls=0, tunnel_mode="overflow"
    )
    assert result.wall_count == 0
    assert result.tunnel_count == 0
    # And nothing else is cranked past the tier to compensate for them.
    hard = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    assert result.profile.hidden_ratio <= hard.hidden_ratio
    assert result.profile.arrow_ratio <= hard.arrow_ratio


def test_the_climb_does_not_undo_the_easing_a_designer_asked_for():
    """`ease_obstacles` is a decision; only what the *belt* took is bought back."""
    tier = int(LevelDifficulty.SuperHard)
    strict, _ = generated(level_10(), difficulty=tier)
    eased, _ = generated(level_10(), difficulty=tier, ease_obstacles=3)
    assert eased.profile.hidden_ratio < strict.profile.hidden_ratio
    assert eased.score.notch <= strict.score.notch


def test_the_ceiling_the_climb_may_reach_is_the_form_that_was_asked_for():
    hard = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    plain = AutoGenOptions()
    # Nothing set by hand and nothing eased: one lap at the tier, one above it.
    assert climb_sources(
        int(LevelDifficulty.Hard),
        difficulty=int(LevelDifficulty.Hard),
        tier_profile=hard,
        options=plain,
    ) == (int(LevelDifficulty.Hard), int(LevelDifficulty.SuperHard))
    # A mechanic switched off, so no lap above the tier.
    assert climb_sources(
        int(LevelDifficulty.Hard),
        difficulty=int(LevelDifficulty.Hard),
        tier_profile=hard,
        options=AutoGenOptions(walls=0),
    ) == (int(LevelDifficulty.Hard),)
    # Eased on purpose, so the climb stops at the eased form rather than the tier.
    assert climb_sources(
        int(LevelDifficulty.Easy),
        difficulty=int(LevelDifficulty.Hard),
        tier_profile=hard,
        options=AutoGenOptions(ease_obstacles=2),
    ) == (int(LevelDifficulty.Easy),)
    # Never past the hardest tier there is.
    assert climb_sources(
        int(LevelDifficulty.SuperHard),
        difficulty=int(LevelDifficulty.SuperHard),
        tier_profile=DIFFICULTY_PROFILES[int(LevelDifficulty.SuperHard)],
        options=plain,
    ) == (int(LevelDifficulty.SuperHard),)


def test_hardening_takes_one_mechanic_back_and_leaves_the_others_alone():
    easy = DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)]
    hard = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    hardened = harden_profile(easy, hard, ["hidden"])

    assert hardened.hidden_ratio == hard.hidden_ratio
    assert hardened.arrow_ratio == easy.arrow_ratio
    assert hardened.walls == easy.walls
    # Which mechanics the level carries is the budget's business, not this one's.
    assert hardened.kinds == easy.kinds
    assert hardened.label == easy.label


def test_hardening_nothing_is_the_profile_unchanged():
    easy = DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)]
    assert harden_profile(easy, DIFFICULTY_PROFILES[3], []) is easy


# --------------------------------------------------------------------------- #
# Saying so when it could not be closed
# --------------------------------------------------------------------------- #
def test_a_level_that_cannot_reach_its_tier_says_so_where_it_will_be_seen():
    """It still ships - it wins and it loads - but not under a label nobody checked."""
    result, options = generated(level_10(), difficulty=int(LevelDifficulty.SuperHard))
    assert not result.score.reached

    assert "CHỈ ĐẠT" in jam_headline(result), "the banner over the report has to carry it"
    assert any("CHỈ ĐẠT" in warning for warning in result.warnings)
    report = format_report(result, options)
    assert "Độ khó tổng hợp" in report and "THIẾU" in report
    assert "cộng từ" in report, "and it has to say which mechanic came out gentle"


def test_the_shortfall_is_reported_below_a_jam_and_below_a_validator_error():
    """Three things can be wrong at once; this is the only one the level survives."""
    result, _ = generated(level_10(), difficulty=int(LevelDifficulty.SuperHard))
    assert result.winnable and result.valid and not result.difficulty_matched
    assert jam_headline(result).startswith("CHỈ ĐẠT")


def test_turning_the_climb_off_is_visible_in_the_report_rather_than_silent():
    result, options = generated(
        level_10(), difficulty=int(LevelDifficulty.Medium), difficulty_climb=False
    )
    assert not result.climb.enabled
    assert "đang tắt" in format_report(result, options)
