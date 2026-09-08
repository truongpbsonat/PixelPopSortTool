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
    MAX_THIN_SHARE,
    MIN_COLORS_KEPT,
    WHOLE_RUN,
    RepairReport,
    belt_for_play,
    belt_summary,
    best_thin,
    color_scatter,
    consolidate_once,
    drop_scattered_colors,
    drop_summary,
    most_scattered_color,
    repair_picture,
    repair_summary,
    thin_once,
    thinnable_colors,
)
from pixel_level_tool.domain.level_models import PixelGridData, PixelLevelData
from pixel_level_tool.services.picture_scan import play_cells, play_sequence, scan_picture
from tests.test_box_autogen import assert_valid, make_level


def _shredded_grid(*, size: int = 24, colors: int = 10, seed: int = 3) -> PixelGridData:
    """Uniform per-pixel noise: the shape no merge can consolidate.

    Every colour is a whole number of boxes - the leftovers are folded into
    colour 1 - so the picture is *buildable* and only unplayable, which is the
    case the drop pass exists for. There is no large region of any colour to pay
    a speck back beside, so `repair_picture` runs out with the belt still short.
    """
    import random

    rng = random.Random(seed)
    ids = [rng.randrange(1, colors + 1) for _ in range(size * size)]
    return PixelGridData(size, size, _whole_boxes(ids))


def _shredded_level(level: int = 1, **knobs) -> PixelLevelData:
    return PixelLevelData(level=level, piece=5, pixel_grid=_shredded_grid(**knobs))


def _mixed_grid(
    *, size: int = 24, share: float = 0.6, bands: int = 4, colors: int = 10, seed: int = 2
) -> PixelGridData:
    """Painted bands over part of the picture, per-pixel dust over the rest.

    The case the thinning pass exists for, and the one `_shredded_grid` is not:
    a picture with real regions in it that the safe pass gets *close* on and
    cannot finish - it leaves the belt at 49 against 45. A few boxes of dust are
    the difference, so thinning it is a repair rather than a repaint.
    """
    import random

    rng = random.Random(seed)
    ids: list[int] = []
    split = int(size * (1.0 - share))
    for row in range(size):
        if row < split:
            ids.extend([1 + (row * bands) // max(1, split)] * size)
        else:
            ids.extend(rng.randrange(1, colors + 1) for _ in range(size))
    return PixelGridData(size, size, _whole_boxes(ids))


def _mixed_level(level: int = 1, **knobs) -> PixelLevelData:
    return PixelLevelData(level=level, piece=5, pixel_grid=_mixed_grid(**knobs))


def _whole_boxes(ids: list[int], filler: int = 1) -> list[int]:
    """Fold every colour's leftover pixels into ``filler`` so all are whole boxes.

    Colour balancing would do this inside the generator, but a fixture handed
    straight to `repair_picture` has to arrive already buildable - the point of
    these fixtures is a picture that is *unplayable*, not one that is invalid.
    """
    histogram = Counter(ids)
    for color, count in list(histogram.items()):
        if color == filler:
            continue
        for index in [i for i, value in enumerate(ids) if value == color][
            : count % BALLS_PER_BOX
        ]:
            ids[index] = filler
    remainder = Counter(ids)[filler] % BALLS_PER_BOX
    if remainder:
        spare = next(color for color in Counter(ids) if color != filler)
        for index in [i for i, value in enumerate(ids) if value == filler][:remainder]:
            ids[index] = spare
    return ids


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


# --------------------------------------------------------------------------- #
# The second pass: thinning the dust a colour cannot be paid back for
# --------------------------------------------------------------------------- #
# Everything above rests on "a repair is a recolour, never a deletion", and that
# is exactly why it runs out: the merge is a *swap*, and a colour with no large
# region has nowhere to be paid back from. The one-way merge is what is left, and
# it does change what a colour owns - so the whole design of this pass is about
# changing as little as possible:
#
#   * one box (nine pixels) per step, the smallest edit a histogram of whole
#     boxes permits;
#   * the box that lowers the *belt* most, not the dustiest colour - thinning by
#     dustiness can widen the belt and did, badly;
#   * stop the instant the picture wins;
#   * and if it cannot win cheaply, put the artwork back untouched.
#
# A colour only leaves the palette when the box given up was all it had.
def test_thinnable_colours_need_a_whole_box_of_dust_to_give_up():
    """Nine pixels is the floor: below it there is no edit the histogram allows."""
    # Colour 2 has three one-pixel specks - dust, but not a box of it.
    sequence = [1] * 9 + [2, 1, 2, 1, 2] + [1] * 9
    assert thinnable_colors(sequence) == []
    # Nine specks of colour 2 is a box, so now it can be thinned.
    sequence = [1] * 9 + [item for _ in range(9) for item in (2, 1)] + [1] * 9
    assert thinnable_colors(sequence) == [2]
    # A colour in whole runs is never offered, however many runs it has.
    assert thinnable_colors([1] * 9 + [2] * 9 + [1] * 9) == []


def test_the_dustiest_colour_is_ranked_by_run_length_not_run_count():
    """The colour with the most short runs is the biggest one - thinning it repaints the subject."""
    # Colour 1: eighteen two-pixel specks (many short runs, lots of pixels).
    # Colour 2: nine one-pixel specks (fewer runs, but dustier and minor).
    sequence: list[int] = []
    for _ in range(9):
        sequence += [1, 1, 3, 3, 3, 3, 3, 3, 3, 3, 3, 1, 1, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3]
    scatter = color_scatter(sequence)
    assert scatter[1][1] > scatter[2][1], "colour 1 really does have more short runs"
    assert most_scattered_color(sequence) == 2, "the dustier, smaller colour is picked"


def test_thinning_gives_up_exactly_one_box_to_exactly_one_colour():
    """Nine pixels cannot be split into two whole boxes, so the receiver is forced."""
    grid = _mixed_grid()
    sequence = play_sequence(grid)
    color = most_scattered_color(sequence)
    assert color is not None

    drop = thin_once(grid, sequence, play_cells(grid), color)

    assert drop is not None
    assert drop.pixels == BALLS_PER_BOX
    assert isinstance(drop.into, int) and drop.into != color
    assert drop.runs_removed >= 1
    after = grid.histogram()
    assert all(count % BALLS_PER_BOX == 0 for count in after.values()), after


def test_thinning_leaves_every_colour_a_whole_number_of_boxes():
    """The box multiset comes off the histogram, so a remainder is an unbuildable level."""
    grid = _mixed_grid()
    before = Counter(grid.color_ids)
    assert all(count % BALLS_PER_BOX == 0 for count in before.values())

    report = drop_scattered_colors(grid, belt_slots=45)

    after = grid.histogram()
    assert report.drops, "the fixture is only useful if thinning engages"
    assert all(count % BALLS_PER_BOX == 0 for count in after.values()), after
    assert sum(after.values()) == sum(before.values()), "no pixel was deleted"


def test_thinning_changes_only_a_sliver_of_the_picture():
    """The complaint this pass was rewritten for: it used to repaint the artwork."""
    grid = _mixed_grid()
    before = list(grid.color_ids)
    painted = len(play_sequence(grid))

    report = drop_scattered_colors(grid, belt_slots=45)

    changed = sum(1 for old, new in zip(before, grid.color_ids, strict=True) if old != new)
    assert report.wins
    assert changed == report.dropped_pixels == len(report.drops) * BALLS_PER_BOX
    assert changed / painted <= MAX_THIN_SHARE, f"{changed}/{painted} recoloured"


def test_the_palette_keeps_the_colours_the_picture_is_made_of():
    """Only a colour whose whole holding was dust leaves; the rest lose specks."""
    grid = _mixed_grid()
    before = Counter(grid.color_ids)

    report = drop_scattered_colors(grid, belt_slots=45)

    after = grid.histogram()
    gone = set(before) - set(after)
    # A colour leaves only because thinning took the last of it, never because
    # the pass decided to be rid of it.
    assert gone == {drop.color for drop in report.drops if drop.gone}
    # And what leaves is dust, not subject: the picture's major colours all
    # survive, which is the property the old whole-colour drop broke.
    major = {color for color, _ in before.most_common(len(before) // 2)}
    assert not (gone & major), f"a major colour was dropped: {gone & major}"
    for color in gone:
        assert before[color] <= min(before[other] for other in major)


def test_a_picture_it_cannot_save_cheaply_is_put_back_untouched():
    """Better a jam than a different picture: pure noise is not artwork with dust on it."""
    grid = _shredded_grid()
    before = list(grid.color_ids)

    report = drop_scattered_colors(grid, belt_slots=45)

    assert not report.wins
    assert report.drops == []
    assert grid.color_ids == before, "the artwork was not left half-repainted"


def test_thinning_never_goes_below_the_floor_of_three_colours():
    """Under three colours the honest answer is a wider piece, not a barer picture."""
    grid = _shredded_grid(colors=4, size=18)
    drop_scattered_colors(grid, belt_slots=9, margin=0)
    assert len(grid.histogram()) >= MIN_COLORS_KEPT


def test_a_picture_that_already_plays_is_not_touched():
    """A level that works does not get its dust swept for tidiness."""
    grid = _mixed_grid()
    grid.color_ids = [1] * 9 + [2] * 9 + [3] * 9 + [EMPTY_COLOR_ID] * (
        grid.width * grid.height - 27
    )
    before = list(grid.color_ids)
    report = drop_scattered_colors(grid, belt_slots=45)
    assert report.drops == [] and grid.color_ids == before


def test_picking_by_belt_beats_picking_by_dustiness():
    """The bug this replaced: thinning the dustiest colour can make the belt *worse*."""
    grid = _mixed_grid()
    sequence = play_sequence(grid)
    start = belt_for_play(sequence)

    dusty = most_scattered_color(sequence)
    by_dust = PixelGridData(grid.width, grid.height, list(grid.color_ids))
    thin_once(by_dust, sequence, play_cells(by_dust), dusty)
    dust_belt = belt_for_play(play_sequence(by_dust))

    chosen = best_thin(grid, sequence)
    assert chosen is not None
    belt, _ = chosen
    assert belt <= dust_belt, "the belt-greedy pick is never worse than the dust pick"
    assert belt < start, "and on this fixture it actually buys something"


# --------------------------------------------------------------------------- #
# Through the generator
# --------------------------------------------------------------------------- #
def test_the_generator_leaves_the_picture_alone_unless_the_tick_is_on():
    """Off by default, because it is the one repair that changes what a colour owns."""
    level = _mixed_level()
    before = Counter(level.pixel_grid.color_ids)

    kept = auto_generate_boxes(level, AutoGenOptions(difficulty=2, seed=7))

    assert kept.repair.drops == []
    assert kept.jam is not None, "the fixture has to be a picture that cannot be won"
    assert set(kept.level.pixel_grid.histogram()) == set(before)
    # And the warning points at the tick rather than leaving the designer stuck.
    assert any("Bỏ màu quá vụn" in warning for warning in kept.warnings)


def test_the_tick_turns_an_unwinnable_picture_into_a_winnable_level():
    """The whole point: playable instead of KẸT, and the artwork still recognisable."""
    level = _mixed_level()
    painted = sum(Counter(level.pixel_grid.color_ids).values())
    colors_before = len(level.pixel_grid.histogram())

    result = auto_generate_boxes(
        _mixed_level(), AutoGenOptions(difficulty=2, seed=7, drop_scattered_colors=True)
    )

    assert result.repair.drops, "the picture needed dust thinned"
    assert result.winnable and result.jam is None
    assert result.valid
    assert_valid(result.level)
    assert result.repair.dropped_pixels / painted <= MAX_THIN_SHARE
    assert len(result.level.pixel_grid.histogram()) >= colors_before - 1
    # Said out loud, with each move placed on the canvas.
    told = " ".join(result.warnings)
    assert "Đã bỏ bớt màu vụn" in told
    for drop in result.repair.drops:
        assert f"ô hàng {drop.at[0]}, cột {drop.at[1]}" in told


def test_the_report_separates_merging_specks_from_thinning_dust():
    """One keeps every colour's pixel count, the other does not - never one sentence."""
    report = drop_scattered_colors(_mixed_grid(), belt_slots=45)
    text = repair_summary(report)
    assert "box đốm màu vụn" in drop_summary(report)
    assert drop_summary(report) in text
    assert belt_summary(report) in text
    # A report with no thinning says nothing about it.
    assert drop_summary(RepairReport()) == ""
