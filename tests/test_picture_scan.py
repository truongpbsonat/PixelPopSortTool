from __future__ import annotations

"""The picture scanner: play order, conveyor demand, and the tier it reads."""

import random
from collections import Counter

import pytest

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID, LevelDifficulty
from pixel_level_tool.domain.level_models import PixelGridData, PixelLevelData
from pixel_level_tool.services.box_autogen import (
    AutoGenError,
    AutoGenOptions,
    auto_generate_boxes,
    balance_pixel_grid,
    format_scan,
    scan_level,
)
from pixel_level_tool.services.picture_scan import (
    BALLS_PER_BOX,
    DEFAULT_BELT_SLOTS,
    belt_demand,
    belt_jam,
    colour_runs,
    difficulty_for_colors,
    play_sequence,
    scan_picture,
    suggest_difficulty,
)
from pixel_level_tool.services.pixel_gameplay import (
    GameRules,
    lazy_order,
    simulate_order,
    BoardState,
    GameRules,
    box_multiset,
    solve_order,
)


def grid(color_ids: list[int], width: int, height: int) -> PixelGridData:
    return PixelGridData(width, height, list(color_ids))


def banded(colors: list[int], width: int = 3, band_height: int = 3) -> PixelGridData:
    return grid([color for color in colors for _ in range(band_height * width)], width, band_height * len(colors))


def scattered(width: int, height: int, colors: int, seed: int) -> PixelGridData:
    rnd = random.Random(seed)
    return grid([rnd.randrange(colors) for _ in range(width * height)], width, height)


# --------------------------------------------------------------------------- #
# Play order
# --------------------------------------------------------------------------- #
def test_play_order_is_top_down_then_right_to_left():
    # rows are [0, 1, 2] / [3, 4, 5], so each row is read from its right edge.
    assert play_sequence(grid([0, 1, 2, 3, 4, 5], 3, 2)) == [2, 1, 0, 5, 4, 3]


def test_empty_cells_are_skipped_not_stopped_at():
    """A ball jumps a hole, so a picture with a gap is still one continuous run."""
    holed = grid([0, EMPTY_COLOR_ID, 0, EMPTY_COLOR_ID, 1, EMPTY_COLOR_ID], 3, 2)
    assert play_sequence(holed) == [0, 0, 1]


def test_a_hole_inside_the_outline_is_reported_but_does_not_block():
    scan = scan_picture(grid([0, 0, 0, 0, EMPTY_COLOR_ID, 0, 0, 0, 0], 3, 3))
    assert scan.holes == 1
    assert scan.painted == 8
    assert scan.playable


def test_colour_runs_group_the_sequence():
    assert colour_runs([1, 1, 0, 0, 0, 2]) == [(1, 2), (0, 3), (2, 1)]


# --------------------------------------------------------------------------- #
# Conveyor demand
# --------------------------------------------------------------------------- #
def test_one_colour_never_needs_more_than_a_single_box():
    assert belt_demand([0] * 90).peak_balls == BALLS_PER_BOX - 1


def test_two_colours_alternating_need_a_box_of_each():
    """Both boxes have already paid a ball by the time both are live."""
    demand = belt_demand([0, 1] * 27)
    assert demand.peak_boxes == 2
    assert demand.peak_balls == 2 * (BALLS_PER_BOX - 1)


def test_demand_is_a_lower_bound_no_solver_can_beat():
    """The gate is only worth having if a picture it refuses truly cannot be won.

    The bound says "no play holds less than this"; this checks the other
    direction empirically, that the solver never wins below it either.
    """
    for seed in range(1, 8):
        picture = scattered(9, 9, 4, seed)
        balance_pixel_grid(picture)
        scan = scan_picture(picture)
        board = BoardState.from_pixel_grid(picture)
        boxes = box_multiset(board)
        below = scan.demand.peak_balls - 1
        if below >= BALLS_PER_BOX:
            rules = GameRules(belt_slots=below, box_size=BALLS_PER_BOX)
            assert solve_order(board, boxes, rules) is None, f"seed {seed} won under its own bound"


# --------------------------------------------------------------------------- #
# The belt the picture needs, which is the number a refusal has to hand over
# --------------------------------------------------------------------------- #
def test_the_tap_peak_is_what_the_late_tapping_play_really_needs():
    """A tap pours nine balls at once, so holding the peak is not the same as tapping it."""
    demand = belt_demand([0, 1] * 27)

    assert demand.peak_balls == 2 * (BALLS_PER_BOX - 1), "two colours waiting, drained by one"
    assert demand.peak_tap == demand.peak_balls + 1, "the tap needed a whole box of room"
    assert demand.wins(demand.peak_tap) and not demand.wins(demand.peak_tap - 1)


def test_the_belt_a_picture_asks_for_is_the_one_the_lazy_play_wins_on():
    """The number the tool prints is the number a real play is legal at."""
    for seed in range(1, 8):
        picture = scattered(12, 12, 5, seed)
        balance_pixel_grid(picture)
        scan = scan_picture(picture)
        board = BoardState.from_pixel_grid(picture)
        boxes = box_multiset(board)

        play = lazy_order(board, boxes)

        assert play.required_belt == scan.demand.peak_tap, f"seed {seed} disagrees with the scan"
        assert simulate_order(board, play.order, GameRules(belt_slots=scan.demand.peak_tap))
        assert not simulate_order(
            board, play.order, GameRules(belt_slots=scan.demand.peak_tap - 1)
        ), "one ball under, and the play the number promised is illegal"


def test_the_piece_a_picture_asks_for_is_its_belt_in_whole_boxes():
    """`piece` is the only knob a level has, and it is counted in boxes."""
    picture = scattered(12, 12, 5, seed=3)
    balance_pixel_grid(picture)
    scan = scan_picture(picture)

    assert scan.required_piece == -(-scan.demand.peak_tap // BALLS_PER_BOX)
    assert scan.required_belt == scan.required_piece * BALLS_PER_BOX
    assert scan.required_belt >= scan.demand.peak_tap, "rounding a piece down would lose the play"


def test_the_jam_names_the_colours_squatting_on_the_belt():
    """The question a designer asks is *why here*, and leftovers are the answer."""
    picture = scattered(12, 12, 10, seed=1)
    balance_pixel_grid(picture)
    sequence = play_sequence(picture)

    jam = belt_jam(sequence, 45)

    assert jam is not None
    assert jam.used + BALLS_PER_BOX > jam.belt_slots, "a whole box no longer fits"
    assert jam.free < BALLS_PER_BOX
    assert sequence[jam.at] == jam.wanted, "the picture is asking for the colour it cannot tap"
    assert jam.wanted not in {colour for colour, _, _ in jam.stuck}, "the wanted colour is gone"
    assert sum(balls for _, balls, _ in jam.stuck) == jam.used
    for colour, balls, ahead in jam.stuck:
        assert 0 < balls < BALLS_PER_BOX, "a leftover is part of a box, never a whole one"
        assert ahead != 0, "a colour wanted right now would be draining, not stuck"


def test_a_belt_that_carries_the_picture_never_jams():
    sequence = play_sequence(banded([0, 1, 2]))
    assert belt_jam(sequence, belt_demand(sequence).peak_tap) is None
    assert belt_jam(sequence, belt_demand(sequence).peak_tap - 1) is not None


def test_the_jam_table_says_how_long_each_colour_is_stuck_for():
    """A leftover is only dead weight until the picture asks for that colour again."""
    # Red once, then a long stretch of other colours before Red comes back.
    sequence = [0] + [1] * 20 + [2] * 20 + [0] * 8
    jam = belt_jam(sequence, 18)

    assert jam is not None
    stuck = {colour: (balls, ahead) for colour, balls, ahead in jam.stuck}
    assert stuck[0][0] == BALLS_PER_BOX - 1, "one Red pixel spent one ball of the box"
    assert stuck[0][1] == 41 - jam.at, "and the rest waits for the Red at the end"


def test_a_picture_the_belt_cannot_hold_is_built_anyway_and_names_the_piece():
    """Nothing is refused; what the belt cannot do comes back as a warning."""
    level = PixelLevelData(pixel_grid=scattered(12, 12, 8, seed=1), piece=5)
    scan = scan_level(level)
    assert scan.required_piece > level.piece

    result = auto_generate_boxes(level, AutoGenOptions(repair_picture=False))

    assert result.jam is not None
    warning = next(w for w in result.warnings if "CHƯA THẮNG ĐƯỢC" in w)
    assert f"đặt piece={scan.required_piece}" in warning
    assert result.certified_belt == scan.required_belt


def test_the_piece_the_refusal_names_is_one_that_actually_generates():
    """The number is only worth printing if setting it makes the level build."""
    picture = scattered(12, 12, 8, seed=1)
    needed = scan_level(PixelLevelData(pixel_grid=picture, piece=5)).required_piece

    result = auto_generate_boxes(
        PixelLevelData(pixel_grid=picture, piece=needed), AutoGenOptions()
    )

    assert result.level.piece == needed
    assert result.solution.required_belt <= needed * BALLS_PER_BOX


def test_the_scan_names_the_piece_before_anything_is_generated():
    """The dialog reads the number out up front, not only in a failure."""
    level = PixelLevelData(pixel_grid=scattered(12, 12, 8, seed=1), piece=5)
    scan = scan_level(level)

    text = format_scan(scan)
    assert "THIẾU" in text
    assert f"cần piece={scan.required_piece}" in text
    assert f"băng {scan.required_belt} bóng" in text


def test_a_picture_its_belt_holds_says_the_piece_is_enough():
    scan = scan_level(PixelLevelData(pixel_grid=banded([0, 1, 2]), piece=5))
    assert scan.demand.wins(scan.belt_slots)
    assert "ĐỦ" in format_scan(scan)
    assert "KHÔNG THỂ THẮNG" not in format_scan(scan)


def test_a_banded_picture_of_many_colours_still_fits_the_belt():
    """Layout beats colour count: twelve colours in bands are easier than six as noise."""
    scan = scan_picture(banded(list(range(12))))
    assert scan.colors == 12
    assert scan.playable and scan.demand.peak_boxes == 1


def test_scattered_colours_overflow_the_belt():
    picture = scattered(15, 15, 6, seed=1)
    balance_pixel_grid(picture)
    scan = scan_picture(picture)
    assert not scan.playable
    assert scan.demand.peak_balls > DEFAULT_BELT_SLOTS


def test_fragmentation_separates_bands_from_noise():
    assert scan_picture(banded([0, 1, 2])).fragmentation == 0.0
    assert scan_picture(scattered(15, 15, 6, seed=2)).fragmentation > 0.5


# --------------------------------------------------------------------------- #
# The difficulty the picture reads as
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "colors, expected",
    [
        (1, LevelDifficulty.Easy),
        (3, LevelDifficulty.Easy),
        (4, LevelDifficulty.Medium),
        (8, LevelDifficulty.Medium),
        (9, LevelDifficulty.Hard),
        (12, LevelDifficulty.Hard),
        (13, LevelDifficulty.SuperHard),
    ],
)
def test_the_colour_scale_matches_the_designers_bands(colors, expected):
    assert difficulty_for_colors(colors) == int(expected)


def test_a_fragmented_picture_is_pushed_up_one_tier():
    """Noise plays harder than its colour count, so the tier follows the play order."""
    bands = scan_picture(banded([0, 1, 2]))
    noise = scan_picture(scattered(15, 15, 3, seed=3))
    assert bands.colors == noise.colors == 3
    assert suggest_difficulty(bands) == int(LevelDifficulty.Easy)
    assert suggest_difficulty(noise) == int(LevelDifficulty.Medium)


def test_the_tier_is_never_pushed_past_super_hard():
    scan = scan_picture(scattered(15, 15, 14, seed=4))
    assert scan.colors > 12
    assert suggest_difficulty(scan) == int(LevelDifficulty.SuperHard)


# --------------------------------------------------------------------------- #
# Scanning a level, which is what the dialog does
# --------------------------------------------------------------------------- #
def test_scan_level_balances_first_so_it_reports_the_picture_that_gets_played():
    """Leftover pixels read as balls nothing ever asks for, and inflate the demand."""
    # 10 of one colour and 10 of another: one pixel of each is left over per box.
    picture = grid([0] * 10 + [1] * 10, 5, 4)
    raw = scan_picture(picture)
    balanced = scan_level(PixelLevelData(pixel_grid=picture))
    assert raw.trimmed_pixels == 2
    assert balanced.demand.peak_balls < raw.demand.peak_balls


def test_scan_level_reports_the_pixels_the_divisible_by_nine_rule_deletes():
    """The trim is invisible after the fact, so the scan has to carry it."""
    picture = grid([0] * 10 + [1] * 10, 5, 4)
    scan = scan_level(PixelLevelData(pixel_grid=picture))

    assert scan.deleted == Counter({0: 1, 1: 1})
    assert scan.trimmed_pixels == 2, "still reported once balancing has done it"
    assert scan.painted == 18 and scan.boxes == 2
    assert "xoá 2 pixel dư" in format_scan(scan)


def test_scan_text_says_so_when_nothing_has_to_be_balanced():
    scan = scan_level(PixelLevelData(pixel_grid=banded([0, 1, 2])))
    assert scan.trimmed_pixels == 0
    assert not scan.balanced
    assert "không phải sửa gì" in format_scan(scan)


def test_scan_level_never_touches_the_level_it_reads():
    level = PixelLevelData(pixel_grid=banded([0, 1, 2]))
    before = list(level.pixel_grid.color_ids)
    scan_level(level)
    assert list(level.pixel_grid.color_ids) == before


def test_scan_of_an_unpainted_grid_says_so_instead_of_failing():
    scan = scan_level(PixelLevelData(pixel_grid=grid([EMPTY_COLOR_ID] * 9, 3, 3)))
    assert scan.painted == 0
    assert "Chưa có pixel" in format_scan(scan)


def test_the_scan_text_names_the_jam_when_the_picture_cannot_be_won():
    """The dialog says where it jams in one line and points at the report for the rest."""
    level = PixelLevelData(pixel_grid=scattered(15, 15, 10, seed=1))
    text = format_scan(scan_level(level))
    assert "KHÔNG THỂ THẮNG" in text
    assert "kẹt tại pixel thứ" in text and "ô hàng" in text
    assert "Auto Gen Report" in text, "the detail lives there, not in the dialog"


# --------------------------------------------------------------------------- #
# Auto difficulty end to end
# --------------------------------------------------------------------------- #
def test_auto_difficulty_reads_the_tier_off_the_picture():
    level = PixelLevelData(pixel_grid=banded(list(range(10))), level=1)
    result = auto_generate_boxes(level, AutoGenOptions(auto_difficulty=True))
    assert result.scan.colors == 10
    assert result.difficulty == int(LevelDifficulty.Hard)
    assert result.level.difficulty == int(LevelDifficulty.Hard)


def test_auto_difficulty_overrides_the_number_the_caller_passed():
    level = PixelLevelData(pixel_grid=banded([0, 1, 2]), level=1)
    options = AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), auto_difficulty=True)
    result = auto_generate_boxes(level, options)
    assert result.difficulty == int(LevelDifficulty.Easy)


def test_a_picture_over_the_belt_is_built_with_the_jam_it_found():
    """The belt never vetoes: it warns, and the grid it warns about is still whole."""
    level = PixelLevelData(pixel_grid=scattered(15, 15, 10, seed=5), level=1)

    result = auto_generate_boxes(level, AutoGenOptions(auto_difficulty=True))

    assert result.jam is not None
    assert result.total_boxes == result.scan.boxes, "every box the picture wants is there"
    assert result.level.source_histogram() == result.level.target_histogram()
