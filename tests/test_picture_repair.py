from __future__ import annotations

"""Repainting a picture the conveyor cannot hold until it can be played.

A tap pours nine balls and the frontier is one cell, so a colour that comes in
short runs is what jams a level: a run of four spends four and leaves five on the
belt until that colour is wanted again. Level 15 is the case - ten colours, 72
whole boxes, nothing wrong with its *contents*, but 127 of its 148 runs are
shorter than a box, so it needs a 54-ball belt while shipping ``piece: 5``.

The one invariant everything here rests on: a repair is a **recolour, never a
deletion**. A speck is merged into the colour beside it and exactly as many
pixels are handed back against that colour's own run, so every colour keeps its
pixel count to the pixel. That is what makes it safe to run at all - the box
multiset comes straight off the histogram, so a repaired picture builds the same
boxes as the original and only the order they are wanted in changes.
"""

from collections import Counter

import pytest

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID, ItemColor, LevelDifficulty
from pixel_level_tool.services.box_autogen import (
    BALLS_PER_BOX,
    AutoGenOptions,
    auto_generate_boxes,
    format_report,
)
from pixel_level_tool.services.picture_repair import (
    MAX_MOVES,
    WHOLE_RUN,
    belt_for_play,
    consolidate_once,
    repair_picture,
    repair_summary,
)
from pixel_level_tool.services.picture_scan import play_cells, play_sequence, scan_picture
from tests.test_box_autogen import assert_valid, make_level


def broken_up(pieces: int, level: int = 15):
    """Level 15's own histogram with every colour chopped into ``pieces`` and interleaved.

    This is the shape that jams, and it is the shape level 15 really has: not a
    solid picture with a few specks on it, but every colour cut into a dozen
    pieces that take turns in play order. ``pieces`` is the dial - at 1 every
    colour is one run and the picture plays on almost no belt at all; at 15 it
    needs eight boxes of conveyor and cannot be played on the five it ships.

    Nothing about the *contents* changes with the dial: 72 boxes over ten colours
    at every setting, which is the point.
    """
    from tests.test_base_grid import LEVEL_15_BALLS, LEVEL_15_HEIGHT, LEVEL_15_WIDTH

    by_colour: dict[int, list[int]] = {}
    for colour, balls in LEVEL_15_BALLS.items():
        cut = max(1, min(pieces, balls))
        size, extra = divmod(balls, cut)
        by_colour[colour] = [size + (1 if index < extra else 0) for index in range(cut)]
    # Round-robin, so no two pieces of one colour ever end up next to each other.
    cells: list[int] = []
    while any(by_colour.values()):
        for colour in list(by_colour):
            if by_colour[colour]:
                cells.extend([colour] * by_colour[colour].pop(0))
    cells += [EMPTY_COLOR_ID] * (LEVEL_15_WIDTH * LEVEL_15_HEIGHT - len(cells))
    grid = make_level(cells, LEVEL_15_WIDTH, LEVEL_15_HEIGHT, level=level)
    grid.piece = 5
    return grid


def solid(level: int = 15):
    """The same histogram with every colour in one piece: the state repair walks to."""
    return broken_up(1, level=level)


def runs_of(grid) -> list[tuple[int, int]]:
    sequence = play_sequence(grid)
    runs: list[tuple[int, int]] = []
    for color in sequence:
        if runs and runs[-1][0] == color:
            runs[-1] = (color, runs[-1][1] + 1)
        else:
            runs.append((color, 1))
    return runs


# --------------------------------------------------------------------------- #
# The invariant
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pieces", [4, 8, 15])
def test_a_repair_never_changes_what_any_colour_owns(pieces):
    """The whole safety of this: same histogram in, same histogram out."""
    level = broken_up(pieces)
    grid = level.pixel_grid
    before = Counter(grid.histogram())

    repair_picture(grid, belt_slots=level.piece * BALLS_PER_BOX)

    assert Counter(grid.histogram()) == before
    assert scan_picture(grid).boxes == 72, "so the same boxes are built either way"


@pytest.mark.parametrize("pieces", [4, 8, 15])
def test_a_repair_never_paints_over_an_empty_cell_or_leaves_one_behind(pieces):
    level = broken_up(pieces)
    grid = level.pixel_grid
    empties = {
        (row, column)
        for row in range(grid.height)
        for column in range(grid.width)
        if grid.get_color_id(row, column) == EMPTY_COLOR_ID
    }

    repair_picture(grid, belt_slots=level.piece * BALLS_PER_BOX)

    assert {
        (row, column)
        for row in range(grid.height)
        for column in range(grid.width)
        if grid.get_color_id(row, column) == EMPTY_COLOR_ID
    } == empties


def test_a_picture_that_already_plays_is_left_completely_alone():
    """A level that works does not get its art rewritten for tidiness."""
    level = solid()
    grid = level.pixel_grid
    before = list(grid.color_ids)

    report = repair_picture(grid, belt_slots=level.piece * BALLS_PER_BOX)

    assert not report.changed and not report.moves
    assert grid.color_ids == before
    assert repair_summary(report) == "không phải sửa gì"


# --------------------------------------------------------------------------- #
# What a move is, and why it always makes progress
# --------------------------------------------------------------------------- #
def test_one_move_merges_a_speck_away_and_leaves_fewer_runs_than_it_found():
    """Every move lowers the run count, which is what makes the loop terminate."""
    level = broken_up(15)
    grid = level.pixel_grid
    sequence, cells = play_sequence(grid), play_cells(grid)
    before = len(runs_of(grid))

    move = consolidate_once(grid, sequence, cells)

    assert move is not None
    assert move.pixels < WHOLE_RUN, "only a speck is ever merged, never a whole box"
    assert move.color != move.into
    assert len(runs_of(grid)) < before


def test_the_pixels_handed_back_land_against_the_colours_own_run():
    """Paying the colour back somewhere random would leave the picture more broken."""
    level = broken_up(15)
    grid = level.pixel_grid
    sequence, cells = play_sequence(grid), play_cells(grid)

    move = consolidate_once(grid, sequence, cells)
    assert move is not None

    after = play_sequence(grid)
    step = play_cells(grid).index(move.paid_at)
    neighbours = [
        after[index] for index in (step - move.pixels - 1, step + move.pixels)
        if 0 <= index < len(after)
    ]
    assert move.color in neighbours, "the pay-back has to touch the colour it pays"


def test_a_picture_of_whole_bands_has_nothing_left_to_merge():
    """Every colour in one run of whole rows is the state the repair walks towards.

    Whole rows matter: the runtime reads a row right to left, so a region that
    ends mid-row is two runs in play order however solid it looks on the canvas.
    """
    from tests.test_box_autogen import banded_level

    grid = banded_level([0, 1, 2], width=9, band_height=3).pixel_grid
    grid.ensure_dense()

    assert consolidate_once(grid, play_sequence(grid), play_cells(grid)) is None


# --------------------------------------------------------------------------- #
# Level 15, which is what this is for
# --------------------------------------------------------------------------- #
def test_a_scattered_picture_is_repaired_into_one_the_belt_can_hold():
    level = broken_up(15)
    grid = level.pixel_grid
    belt = level.piece * BALLS_PER_BOX
    before = scan_picture(grid, belt_slots=belt)
    assert not before.demand.wins(belt), "the fixture has to start out unplayable"

    report = repair_picture(grid, belt_slots=belt)
    after = scan_picture(grid, belt_slots=belt)

    assert report.changed and report.wins
    assert after.demand.wins(belt)
    assert after.run_count < before.run_count
    assert after.short_runs < before.short_runs
    assert report.belt_after < report.belt_before
    assert report.gained == report.belt_before - report.belt_after


def test_the_repair_aims_past_merely_winning_so_the_player_has_room():
    """Winning with nothing to spare is a level that has to be played perfectly."""
    level = broken_up(15)
    belt = level.piece * BALLS_PER_BOX

    report = repair_picture(level.pixel_grid, belt_slots=belt)

    assert report.belt_after <= belt - BALLS_PER_BOX, "a whole box of conveyor left over"


def test_a_repair_that_cannot_finish_the_job_says_so_and_keeps_its_best_try():
    """Uniform noise is not scattered art, and the honest answer is a wider piece."""
    import random

    rng = random.Random(4)
    cells = [rng.randrange(12) for _ in range(18 * 18)]
    level = make_level(cells, 18, 18, level=1)
    grid = level.pixel_grid
    belt = 45
    before = scan_picture(grid, belt_slots=belt)
    assert not before.demand.wins(belt)

    report = repair_picture(grid, belt_slots=belt, max_moves=12)

    assert not report.wins
    assert len(report.moves) <= 12
    # It still kept whatever it did manage, and never made the picture worse.
    assert report.belt_after <= report.belt_before
    assert Counter(grid.histogram()) == Counter(before.histogram)


def test_the_summary_reads_as_a_sentence_a_designer_can_act_on():
    level = broken_up(15)
    report = repair_picture(level.pixel_grid, belt_slots=level.piece * BALLS_PER_BOX)

    text = repair_summary(report)
    assert "gom" in text and "số pixel mỗi màu không đổi" in text
    assert f"{report.belt_after}/{report.belt_slots}" in text


# --------------------------------------------------------------------------- #
# Through the generator
# --------------------------------------------------------------------------- #
def test_a_picture_that_needed_a_wider_piece_generates_a_winnable_level_instead():
    """The end of the chain: level 15's shape ships beatable on the piece it has."""
    level = broken_up(15)
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), seed=3)

    result = auto_generate_boxes(level, options)

    assert result.repair.changed
    assert result.winnable and result.jam is None
    assert result.total_boxes == 72
    assert result.valid
    assert_valid(result.level)
    report = format_report(result, options)
    assert "Đã sửa tranh để level chơi được" in " ".join(result.warnings)
    assert "THẮNG ĐƯỢC" in report


def test_switching_the_repair_off_leaves_the_picture_and_reports_the_jam():
    """A designer who wants their pixels untouched keeps them, and is told the cost."""
    level = broken_up(15)
    untouched = list(level.pixel_grid.color_ids)
    options = AutoGenOptions(
        difficulty=int(LevelDifficulty.Hard), repair_picture=False, seed=3
    )

    result = auto_generate_boxes(level, options)

    assert not result.repair.changed
    assert result.jam is not None, "the picture still cannot be won as painted"
    assert result.level.pixel_grid.color_ids == untouched
    assert result.total_boxes == 72, "and the grid is still correct and complete"


def test_the_generator_lists_every_pixel_it_moved():
    """Repainting somebody's artwork is never allowed to be silent."""
    level = broken_up(15)
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), seed=3)

    result = auto_generate_boxes(level, options)
    told = " ".join(result.warnings)

    for move in result.repair.moves:
        assert f"ô hàng {move.at[0]}, cột {move.at[1]}" in told
    assert "số pixel từng màu không đổi" in told
