from __future__ import annotations

import random
from collections import Counter
from dataclasses import replace

import pytest

from pixel_level_tool.domain.enums import (
    EMPTY_COLOR_ID,
    CellShape,
    Direction,
    ItemColor,
    LevelDifficulty,
    ThemeId,
)
from pixel_level_tool.domain.level_models import (
    HiddenCellEffectData,
    LargeBlockObstacleData,
    PixelGridData,
    PixelLevelData,
    TunnelCellData,
)
from pixel_level_tool.services.box_autogen import (
    BALLS_PER_BOX,
    DIFFICULTY_PROFILES,
    MAX_BOX_SLOTS,
    SLOT,
    AutoGenError,
    AutoGenOptions,
    auto_generate_boxes,
    balance_pixel_grid,
    belt_residues,
    bury_queue,
    choose_lattice,
    format_report,
    jam_headline,
    layout_is_open,
    plan_hidden_count,
    MAX_TUNNEL_DEPTH,
    plan_tunnels,
    tunnel_ceiling,
    tunnel_dose,
    tunnels_for_overflow,
    plan_walls,
    reachable_slots,
    tunnel_blocks,
    tunnel_directions,
)
from pixel_level_tool.services.level_serializer import dumps_level, level_from_dict, level_to_dict
from pixel_level_tool.services.level_validator import LevelValidator, ValidationMessage
from pixel_level_tool.services.mechanics_scanner import MechanicsScanner
from pixel_level_tool.services.picture_scan import DEFAULT_BELT_SLOTS, scan_picture
from pixel_level_tool.services.pixel_gameplay import (
    BoardState,
    BoxSpec,
    GameRules,
    GameplayError,
    box_multiset,
    minimum_belt,
    resolve_pick_sequence,
    simulate_order,
    solve_order,
)


ALL_DIFFICULTIES = [int(member) for member in LevelDifficulty]

# The Pixel Grid of the hand-made level 10, one row of the picture per line. Its
# per-color counts are 108/81/18/18/18/18/9, all multiples of nine, which is what
# lets a level be built purely from Square_3x3 boxes.
LEVEL_10_ROWS = """
-1 -1 -1  7  0  7  7  7  7  7  7  7  7  0  7 -1 -1 -1
-1  7  7  0  7  3  3  3  3  3  3  3  3  7  0  7  7 -1
-1  5  0  7  3 16  7  3  3  3  7 16  3  3  7  0  5  7
 3  0  7  3  3  7  7  3  3  3  7  7  3  3  3  7  0  3
 3  7  3  3 11 11  3  3  3  3  3 11 11  3  3  3  7  3
 3  7  3  3  3  3  3  7  7  7  3  3  3  3  3  3  7  3
12  7  3  3  3  3  3  3  3  3  3  3  3  3  3  3  7 12
 7  7  7  7  7  7  7  7  7  7  7  7  7  7  7  7  7  7
 7  5  5  5  5  5  5  5  5  5  5  5  5  5  5  5  5  7
11  7  7  7  7  7  7  7  7  7  7  7  7  7  7  7  7 11
 7 12 12 12 12 12 12 12 12 12 12 12 12 12 12 12 12  7
16  7  7  0  0  0  7  0  0  0  0  7  0  0  0  7  7 16
16  7  3  7  7  7  3  7  7  7  7  3  7  7  7  3  7 16
16  7  3  3  3  3  3  3  3  3  3  3  3  3  3  3  7 16
16 16  7  7  7  7  7  7  7  7  7  7  7  7  7  7 16 16
16 16 16 -1 -1 -1 -1 11 11 11 -1 -1 -1 -1 -1 16 16 16
"""


def make_level(color_ids: list[int], width: int, height: int, level: int = 1) -> PixelLevelData:
    return PixelLevelData(pixel_grid=PixelGridData(width, height, list(color_ids)), level=level)


def level_10() -> PixelLevelData:
    """The hand-made level 10 exactly as it is painted.

    It ships ``piece: 5``, so its conveyor is 45 balls, and its worst moment
    needs 40 of them. That is what makes it generatable at all: the belt is
    sized from the level's own piece rather than from a constant.
    """
    rows = [
        [int(value) for value in line.split()]
        for line in LEVEL_10_ROWS.splitlines()
        if line.strip()
    ]
    return make_level(
        [value for row in rows for value in row], len(rows[0]), len(rows), level=10
    )


def unrepaired(**knobs) -> AutoGenOptions:
    """Options that leave the picture exactly as painted.

    A test about the *jam* has to switch the repair off. Repairing is on by
    default and its whole job is to merge the short runs that jam a picture, so a
    fixture painted to jam quietly stops jamming - which is the feature working,
    and is covered in ``test_picture_repair``, but it leaves these tests with
    nothing to report on.
    """
    return AutoGenOptions(repair_picture=False, **knobs)


def tier_options(**knobs) -> AutoGenOptions:
    """Options that hold the obstacles to their own tier's form.

    A test about what a *tier* does has to switch obstacle relief off. Level 10
    leaves under a box of conveyor free at its tightest moment, so relief reads
    the belt refusing the hard forms and hands the level a gentler one instead -
    which is exactly what it is for, and is covered in ``test_obstacle_relief``,
    but it means the tier's own numbers are not what comes out of a default run
    on this picture.

    It also pins the mix. The gentle tiers draw their mechanics at random rather
    than reading the tier's priority order from the top, so "does Easy hit its
    Hidden ratio" is not even a question about a default Easy run - the level may
    not have bought Hidden at all. That draw is covered in its own tests; here
    the tier's canonical mix is what is under test.
    """
    return AutoGenOptions(obstacle_relief=False, shuffle_obstacles=False, **knobs)


def banded_level(band_colors: list[int], width: int = 3, band_height: int = 3) -> PixelLevelData:
    """Full-width horizontal bands of one box worth of pixels each."""
    color_ids = [color for color in band_colors for _ in range(band_height * width)]
    return make_level(color_ids, width, band_height * len(band_colors))


def noisy_level(width: int, height: int, colors: int, seed: int) -> PixelLevelData:
    """Uniform per-pixel noise - a picture the conveyor cannot hold, on purpose."""
    rnd = random.Random(seed)
    return make_level([rnd.randrange(colors) for _ in range(width * height)], width, height)


def varied_level(width: int, height: int, colors: int, seed: int) -> PixelLevelData:
    """A random picture that still fits the conveyor.

    Uniform noise stopped being a usable fixture when the belt started counting
    balls: five colors shuffled per pixel push the picture's own lower bound past
    forty, so the generator refuses it before the layout is ever reached, which
    is what :func:`noisy_level` now exists to pin.

    The layout, wall and tunnel properties still want many different pictures, so
    this varies what a picture is made of - how long each colour runs and in what
    order the colours come - rather than varying every single pixel. Runs are
    whole boxes so nothing is left stranded on the belt, and the tail is whatever
    the last run does not fill, which keeps the colour-balancing path exercised.
    """
    rnd = random.Random(seed)
    color_ids = [EMPTY_COLOR_ID] * (width * height)
    order = [(row, column) for row in range(height) for column in range(width - 1, -1, -1)]
    spot = 0
    while spot < len(order):
        run = min(len(order) - spot, BALLS_PER_BOX * rnd.randint(1, 3))
        color = rnd.randrange(colors)
        for _ in range(run):
            row, column = order[spot]
            color_ids[row * width + column] = color
            spot += 1
    return make_level(color_ids, width, height)


def surface_boxes(level: PixelLevelData) -> list:
    return [cell for cell in level.grid_cells if not isinstance(cell, TunnelCellData)]


def box_colors(level: PixelLevelData) -> Counter[int]:
    counts: Counter[int] = Counter()
    for cell in level.grid_cells:
        if isinstance(cell, TunnelCellData):
            counts.update(int(stored.color) for stored in cell.stored_cells)
        else:
            counts[int(cell.color)] += 1
    return counts


def assert_valid(level: PixelLevelData) -> None:
    snapshot = level.clone()
    snapshot.assign_deterministic_ids()
    assert LevelValidator().validate(snapshot).errors == []


# --------------------------------------------------------------------------- #
# Regression against the hand-made level 10
# --------------------------------------------------------------------------- #
def test_level_10_pixel_grid_is_already_box_aligned():
    histogram = level_10().pixel_grid.histogram()
    assert sum(histogram.values()) == 270
    assert all(count % BALLS_PER_BOX == 0 for count in histogram.values())


LIKE_THE_HAND_MADE_LEVEL = {
    # The two structural mechanics Hard now spends its obstacle budget on. Level
    # 10 was authored as a solid 5x6 rectangle of plain boxes, so both have to be
    # switched off to compare like for like - a wall would take a slot the hand
    # made level gives to a box, and a tunnel would take one *and* swallow boxes.
    "walls": 0,
    "tunnel_mode": "overflow",
}


def test_regenerating_level_10_reproduces_its_structure():
    """Auto Gen Box must land on the same shape a designer authored by hand."""
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.Hard), **LIKE_THE_HAND_MADE_LEVEL),
    )
    generated = result.level

    assert (result.slot_cols, result.slot_rows) == (5, 6)
    assert result.wall_count == 0
    assert (generated.grid_cols, generated.grid_rows) == (15, 18)
    assert result.total_boxes == 30
    assert result.tunnel_count == 0
    assert sum(result.removed_pixels.values()) == 0, "an aligned picture loses no pixels"
    assert result.hidden_boxes == 12
    assert generated.piece == 5, "the level's own piece is left alone"
    assert generated.difficulty == int(LevelDifficulty.Hard)
    assert generated.theme_id == int(ThemeId.Hard)
    assert not any(cell.is_active for cell in generated.grid_cells)
    assert box_colors(generated) == Counter(
        {
            int(ItemColor.Black): 12,
            int(ItemColor.Yellow): 9,
            int(ItemColor.Orange): 2,
            int(ItemColor.LightPink): 1,
            int(ItemColor.Lime): 2,
            int(ItemColor.Red): 2,
            int(ItemColor.White): 2,
        }
    )
    assert "Hidden" in MechanicsScanner().scan(generated)
    assert_valid(generated)


def test_level_10_needs_less_belt_than_the_runtime_gives_it():
    """The solver must not inflate the belt the way a greedy walkthrough does."""
    board = BoardState.from_pixel_grid(level_10().pixel_grid)
    boxes = box_multiset(board)
    belt = level_10().piece * BALLS_PER_BOX
    needed = minimum_belt(board, boxes, max_slots=belt)
    assert needed is not None and needed <= belt
    assert solve_order(board, boxes, GameRules(belt_slots=belt)) is not None


# --------------------------------------------------------------------------- #
# Lattice layout
# --------------------------------------------------------------------------- #
def test_lattice_prefers_an_exact_fit_then_the_squarest_shape():
    assert choose_lattice(30, 8, 8) == (5, 6)
    assert choose_lattice(16, 8, 8) == (4, 4)
    assert choose_lattice(9, 8, 8) == (3, 3)
    assert choose_lattice(1, 8, 8) == (1, 1)


def test_lattice_leaves_slots_empty_when_the_count_cannot_form_a_rectangle():
    cols, rows = choose_lattice(29, 8, 8)  # 29 is prime
    assert cols * rows >= 29
    assert cols <= 8 and rows <= 8


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_every_box_is_a_square_on_the_three_cell_lattice(difficulty):
    result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
    for cell in result.level.grid_cells:
        assert cell.shape == CellShape.Square_3x3
        # Square_3x3 is symmetric, so a plain box has no reason to turn; only a
        # tunnel's direction means something, and that is its release side.
        if not isinstance(cell, TunnelCellData):
            assert cell.direction == Direction.Up
        assert cell.grid_x % SLOT == 0 and cell.grid_y % SLOT == 0
        assert cell.grid_x < result.level.grid_cols and cell.grid_y < result.level.grid_rows
    assert result.level.grid_cols == result.slot_cols * SLOT
    assert result.level.grid_rows == result.slot_rows * SLOT


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_generated_level_is_valid_and_complete(difficulty):
    result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
    generated = result.level
    assert generated.source_histogram() == generated.target_histogram()
    assert result.total_boxes == generated.target_histogram().total() // BALLS_PER_BOX
    assert_valid(generated)


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_generation_validates_its_own_output_instead_of_leaving_it_to_a_panel(difficulty):
    """The generator's checks are about the play; the validator's are about the file.

    A generated level has to pass both, so the run asks the validator itself and
    carries the verdict - a designer reading the Auto Gen Report must not have to
    click over to the Validation tab to find out the grid is broken.
    """
    result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
    snapshot = result.level.clone()
    snapshot.assign_deterministic_ids()

    assert result.validation == tuple(LevelValidator().validate(snapshot).messages)
    assert result.valid and not result.validation_errors
    report = format_report(result, AutoGenOptions(difficulty=difficulty))
    assert "validate lưới vừa sinh: 0 lỗi" in report
    for message in result.validation:
        assert message.message in report, "a validator note has to be readable in the report"


def test_a_validator_error_would_lead_the_banner_ahead_of_a_jam():
    """A jam is the picture asking for a wider belt; a broken grid is a bug in here."""
    result = auto_generate_boxes(
        noisy_level(12, 12, colors=8, seed=1),
        unrepaired(difficulty=int(LevelDifficulty.Hard)),
    )
    assert result.jam is not None and "CHƯA THẮNG" in jam_headline(result)

    result.validation = (ValidationMessage("error", "gridCells overlap"),)
    assert not result.valid
    headline = jam_headline(result)
    assert headline.startswith("LỖI VALIDATE")
    assert "gridCells overlap" in headline


def test_slot_limit_is_respected_and_capacity_is_far_larger_than_a_cell_limit():
    result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Easy)))
    assert result.slot_cols <= MAX_BOX_SLOTS and result.slot_rows <= MAX_BOX_SLOTS
    assert result.level.grid_cols <= MAX_BOX_SLOTS * SLOT
    assert result.level.grid_rows <= MAX_BOX_SLOTS * SLOT
    # 8x8 slots holds 64 boxes, i.e. 576 balls, so a normal picture needs no tunnel.
    assert MAX_BOX_SLOTS * MAX_BOX_SLOTS * BALLS_PER_BOX == 576


def test_custom_slot_limit_forces_tunnels():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Easy), max_slot_cols=2, max_slot_rows=2)
    result = auto_generate_boxes(level_10(), options)
    assert result.slot_cols <= 2 and result.slot_rows <= 2
    assert result.tunnel_boxes > 0
    assert result.total_boxes == 30
    assert_valid(result.level)


def test_tunnels_can_be_refused():
    options = AutoGenOptions(
        difficulty=int(LevelDifficulty.Easy),
        max_slot_cols=2,
        max_slot_rows=2,
        allow_tunnels=False,
    )
    with pytest.raises(AutoGenError, match="tunnels are disabled"):
        auto_generate_boxes(level_10(), options)


def test_tunnel_stored_boxes_keep_the_walkthrough_order():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Easy), max_slot_cols=2, max_slot_rows=2)
    result = auto_generate_boxes(level_10(), options)
    tunnels = [cell for cell in result.level.grid_cells if isinstance(cell, TunnelCellData)]
    assert tunnels
    for tunnel in tunnels:
        assert tunnel.stored_cells, "the validator rejects an empty tunnel"
        assert tunnel.effects is None
        assert all(stored.shape == CellShape.Square_3x3 for stored in tunnel.stored_cells)


# --------------------------------------------------------------------------- #
# Tunnels
# --------------------------------------------------------------------------- #
def tunnels_of(level: PixelLevelData) -> list[TunnelCellData]:
    return [cell for cell in level.grid_cells if isinstance(cell, TunnelCellData)]


def test_a_tunnel_pays_for_itself_twice_because_it_also_eats_a_slot():
    """Storing 30 boxes in a 4 slot grid needs room for 28, not 26: tunnels are walls."""
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Easy), max_tunnels=4)
    tunnels, stored = plan_tunnels(
        30, 4, options, DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)], mechanic=False
    )
    assert (tunnels, stored) == (2, 28)
    assert 30 - stored == 4 - tunnels, "every surviving surface slot carries a box"


def test_the_tunnel_ceiling_is_measured_off_the_picture_when_left_on_auto():
    """One tunnel per eight boxes, so a big picture is not capped where a small one is."""
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    auto = AutoGenOptions(difficulty=int(LevelDifficulty.Hard))
    assert tunnel_ceiling(30, 64, auto, profile) == 3
    assert tunnel_ceiling(96, 64, auto, profile) >= 8, "a picture twice the grid needs more"
    assert tunnel_ceiling(8, 64, auto, profile) == profile.tunnels, "never under the tier's own"


def test_a_typed_tunnel_ceiling_still_stands():
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    assert tunnel_ceiling(64, 64, AutoGenOptions(max_tunnels=2), profile) == 2


def test_the_ceiling_never_refuses_the_tunnels_an_overflow_cannot_do_without():
    """A ceiling bounds what a tier spends by choice, not what the picture forces."""
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)]
    tight = AutoGenOptions(max_tunnels=1)
    assert tunnel_ceiling(200, 16, tight, profile) > 1
    tunnels, stored = plan_tunnels(200, 16, tight, profile, mechanic=False)
    assert stored == 200 - (16 - tunnels), "every surface slot left over carries a box"
    assert stored <= tunnels * MAX_TUNNEL_DEPTH, "no queue is deeper than a queue may be"


def test_the_tier_dose_grows_with_the_picture():
    """profile.tunnels is the dose for a hand-made 30 box grid, not for every grid."""
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    assert tunnel_dose(30, profile) == profile.tunnels
    assert tunnel_dose(60, profile) == 2 * profile.tunnels
    assert tunnel_dose(6, profile) == profile.tunnels, "the tier's number is the floor"


def test_an_overflow_spreads_over_more_tunnels_instead_of_one_deep_one():
    """More, shallower queues keep the grid inside its slot limit without stacking."""
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard))
    tunnels, stored = plan_tunnels(100, 64, options, profile, mechanic=False)

    assert tunnels >= tunnels_for_overflow(100, 64, profile.tunnel_depth)
    assert stored == 100 - (64 - tunnels), "the tunnels hold exactly what the surface cannot"
    per_tunnel = stored / tunnels
    assert per_tunnel <= profile.tunnel_depth + 1, f"{per_tunnel:.1f} boxes deep per tunnel"


def test_a_picture_far_past_the_lattice_still_fits_inside_the_slot_limit():
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard))
    for box_count in (70, 100, 150, 200, 300):
        tunnels, stored = plan_tunnels(box_count, 64, options, profile, mechanic=False)
        assert 0 < tunnels < 64, f"{box_count} boxes asked for {tunnels} tunnels"
        assert box_count - stored == 64 - tunnels
        assert stored <= tunnels * MAX_TUNNEL_DEPTH


def test_overflow_mode_leaves_a_picture_that_fits_alone():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard))
    assert plan_tunnels(
        30, 64, options, DIFFICULTY_PROFILES[int(LevelDifficulty.SuperHard)], mechanic=False
    ) == (0, 0)


def test_an_exact_tunnel_count_is_planted_even_when_the_picture_fits():
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)]
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Easy), tunnel_count=3)

    tunnels, stored = plan_tunnels(30, 64, options, profile, mechanic=False)

    assert tunnels == 3
    assert stored == 3 * profile.tunnel_depth, "asking for tunnels means wanting them filled"


def test_an_exact_tunnel_count_lifts_the_ceiling_that_only_bounds_the_auto_answer():
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)]
    asked = AutoGenOptions(tunnel_count=6, max_tunnels=2)
    assert plan_tunnels(30, 64, asked, profile, mechanic=False)[0] == 6


def test_an_exact_tunnel_count_is_a_floor_not_a_cap():
    """An overflowing picture still gets the extra tunnels its boxes need."""
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)]
    assert plan_tunnels(30, 4, AutoGenOptions(tunnel_count=1), profile, mechanic=False) == (2, 28)


def test_tunnels_switched_off_win_over_an_exact_count():
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)]
    options = AutoGenOptions(tunnel_count=3, allow_tunnels=False)
    assert plan_tunnels(30, 64, options, profile, mechanic=False) == (0, 0)


def test_mechanic_mode_plants_the_difficultys_tunnels_even_when_everything_fits():
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), tunnel_mode="mechanic")
    assert plan_tunnels(30, 64, options, profile, mechanic=True) == (
        profile.tunnels,
        profile.tunnels * profile.tunnel_depth,
    )


def test_tunnel_blocks_are_contiguous_disjoint_and_spread_over_the_walkthrough():
    blocks = tunnel_blocks(30, [4, 4])
    assert [len(block) for block in blocks] == [4, 4]
    for block in blocks:
        assert block == list(range(block[0], block[0] + len(block))), "a block must be contiguous"
        assert block[0] > 0, "the walkthrough must be able to start from the surface"
    assert set(blocks[0]).isdisjoint(blocks[1])
    assert blocks[0][-1] < blocks[1][0]
    assert blocks[1][-1] < 29, "the last box must not be locked behind a tunnel alone"


def test_burying_reverses_the_window_so_the_wanted_box_sits_at_the_back():
    block = [0, 1, 2, 3, 4, 5]
    assert bury_queue(block, 1) == block, "window 1 releases boxes exactly when needed"
    assert bury_queue(block, 3) == [2, 1, 0, 5, 4, 3]
    assert sorted(bury_queue(block, 4)) == block, "burying only reorders"


def test_a_buried_box_forces_the_player_to_pull_the_ones_in_front_of_it():
    # Box 2 is wanted third but sits last in the tunnel, behind 4 and 3.
    release = resolve_pick_sequence(5, [[4, 3, 2]])
    assert release.sequence == [0, 1, 4, 3, 2]
    assert release.digs == [2], "two unwanted boxes came out before the wanted one"
    assert release.max_dig == 2
    # Boxes 3 and 4 are already in the tray when their own turn comes, so they
    # cost nothing extra and record no dig of their own.
    assert release.mean_dig == 2.0


def test_an_unburied_queue_is_played_in_plain_walkthrough_order():
    release = resolve_pick_sequence(5, [[1, 3], [2, 4]])
    assert release.sequence == list(range(5))
    assert release.max_dig == 0


def test_a_box_cannot_be_stored_in_two_tunnels():
    with pytest.raises(GameplayError, match="more than one tunnel"):
        resolve_pick_sequence(4, [[1, 2], [2, 3]])


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_a_mechanic_tunnel_level_is_valid_complete_and_winnable(difficulty):
    options = tier_options(difficulty=difficulty, tunnel_mode="mechanic")
    result = auto_generate_boxes(level_10(), options)

    assert result.tunnel_count == DIFFICULTY_PROFILES[difficulty].tunnels
    assert result.tunnel_boxes > 0
    assert result.total_boxes == 30
    assert result.level.source_histogram() == result.level.target_histogram()
    assert "Hidden" in MechanicsScanner().scan(result.level) or result.hidden_boxes == 0
    assert "Tunnel" in MechanicsScanner().scan(result.level)
    assert_valid(result.level)

    # The order the tunnels force on the player, not just the ideal walkthrough.
    board = BoardState.from_pixel_grid(result.level.pixel_grid)
    assert simulate_order(board, result.play_order, GameRules(result.belt_slots))
    assert Counter(result.play_order) == Counter(result.solution.order)


def test_easy_hands_a_stored_box_over_exactly_when_the_pixel_grid_needs_it():
    result = auto_generate_boxes(
        level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Easy), tunnel_mode="mechanic")
    )
    assert result.tunnel_boxes > 0
    assert result.dig_window == 1
    assert result.release.max_dig == 0
    assert result.play_order == result.solution.order, "the tunnel never gets in the way"


def test_digging_deepens_with_the_difficulty():
    depths = []
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(
            level_10(), tier_options(difficulty=difficulty, tunnel_mode="mechanic")
        )
        depths.append(result.release.max_dig)
    assert depths[0] == 0, "Easy must never make the player dig"
    assert depths == sorted(depths)
    assert depths[-1] >= 2, "SuperHard must bury the wanted color behind several boxes"


def test_a_tunnel_shows_the_color_of_its_head_and_stores_the_rest_in_queue_order():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), tunnel_mode="mechanic")
    result = auto_generate_boxes(level_10(), options)
    order = result.solution.order
    for tunnel, queue in zip(tunnels_of(result.level), result.tunnel_queues):
        assert int(tunnel.color) == order[queue[0]].color
        assert [int(stored.color) for stored in tunnel.stored_cells] == [
            order[index].color for index in queue
        ]
        assert all(stored.is_active is False for stored in tunnel.stored_cells)


def test_tunnels_sit_on_the_back_row_edges_and_never_overlap_a_box():
    options = tier_options(
        difficulty=int(LevelDifficulty.Hard), tunnel_mode="mechanic", tunnel_placement="back"
    )
    result = auto_generate_boxes(level_10(), options)
    tunnels = tunnels_of(result.level)
    assert len(tunnels) == 2
    back_row = (result.slot_rows - 1) * SLOT
    assert all(tunnel.grid_y == back_row for tunnel in tunnels)
    assert {tunnel.grid_x for tunnel in tunnels} == {0, (result.slot_cols - 1) * SLOT}
    occupied = [cell for box in result.level.grid_cells for cell in box.occupied_cells()]
    assert len(occupied) == len(set(occupied)), "an emptied tunnel keeps its slot to itself"


def test_front_placement_puts_the_tunnels_on_the_row_the_player_eats_first():
    options = AutoGenOptions(
        difficulty=int(LevelDifficulty.Easy), tunnel_count=2, tunnel_placement="front"
    )
    result = auto_generate_boxes(level_10(), options)

    tunnels = tunnels_of(result.level)
    assert len(tunnels) == 2
    assert all(tunnel.grid_y == 0 for tunnel in tunnels), "slot_y 0 is the front row"
    assert {tunnel.grid_x for tunnel in tunnels} == {0, (result.slot_cols - 1) * SLOT}
    assert_valid(result.level)


def test_random_placement_can_move_a_tunnel_off_the_edge_rows():
    """The point of the mode: a tunnel the player has to route around, not one on the rim."""
    options = AutoGenOptions(
        difficulty=int(LevelDifficulty.Easy), tunnel_count=3, tunnel_placement="random"
    )
    rows_used = set()
    for seed in range(8):
        result = auto_generate_boxes(level_10(), replace(options, seed=seed))
        rows_used.update(tunnel.grid_y // SLOT for tunnel in tunnels_of(result.level))
        assert_valid(result.level)
    assert rows_used - {0, max(rows_used)}, "random must reach rows other than the two edges"


@pytest.mark.parametrize("placement", ["back", "front", "random"])
def test_every_placement_leaves_a_playable_grid(placement):
    """A tunnel is a permanent hole; a placement that strands a box is not harder, it is broken."""
    for seed in range(6):
        result = auto_generate_boxes(
            level_10(),
            AutoGenOptions(
                difficulty=int(LevelDifficulty.Easy),
                tunnel_count=3,
                tunnel_placement=placement,
                seed=seed,
            ),
        )
        tunnel_slots = [(x, y) for (x, y), _ in result.tunnel_mouths]
        assert layout_is_open(result.slot_cols, result.slot_rows, result.wall_slots, tunnel_slots)
        assert_valid(result.level)


def test_auto_placement_follows_the_difficulty():
    for difficulty, expected in (
        (int(LevelDifficulty.Easy), "back"),
        (int(LevelDifficulty.Medium), "back"),
        (int(LevelDifficulty.Hard), "front"),
        (int(LevelDifficulty.SuperHard), "random"),
    ):
        options = tier_options(difficulty=difficulty, tunnel_count=1)
        assert auto_generate_boxes(level_10(), options).tunnel_placement == expected


def test_an_explicit_placement_outranks_the_difficulty():
    options = AutoGenOptions(
        difficulty=int(LevelDifficulty.SuperHard), tunnel_count=1, tunnel_placement="back"
    )
    assert auto_generate_boxes(level_10(), options).tunnel_placement == "back"


def test_an_unknown_tunnel_placement_is_rejected():
    with pytest.raises(AutoGenError, match="Unsupported tunnel placement"):
        auto_generate_boxes(level_10(), AutoGenOptions(tunnel_placement="sideways"))


def test_a_tunnel_mouth_faces_a_box_never_a_wall_a_tunnel_or_the_outside():
    """``direction`` is the release side, so it has to point at something that clears."""
    boxes = [(1, 0), (0, 1)]
    tunnels = [(0, 0), (2, 2)]
    walls = [(1, 1), (2, 1), (0, 2), (1, 2)]
    facings = tunnel_directions(tunnels, boxes, walls, 3, 3)
    # (0, 0) is a corner: Down and Left leave the lattice, so the mouth turns to
    # one of the two boxes beside it - Right, the earlier of them.
    assert facings[0] is Direction.Right
    # (2, 2) has only walls and the outside around it, so no side is usable; it
    # still keeps one that stays inside the lattice instead of facing outwards.
    assert facings[1] is Direction.Down


def test_a_tunnel_mouth_prefers_the_front_row_when_several_sides_hold_a_box():
    boxes = [(1, 1), (0, 2), (2, 2)]
    facings = tunnel_directions([(1, 2)], boxes, [], 3, 3)
    assert facings == [Direction.Down]


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_generated_tunnels_release_into_a_real_box(difficulty):
    options = AutoGenOptions(difficulty=difficulty, tunnel_mode="mechanic")
    result = auto_generate_boxes(level_10(), options)
    box_slots = {
        (cell.grid_x // SLOT, cell.grid_y // SLOT)
        for cell in result.level.grid_cells
        if not isinstance(cell, TunnelCellData)
    }
    assert result.tunnel_mouths
    for tunnel, (slot, facing) in zip(tunnels_of(result.level), result.tunnel_mouths):
        assert tunnel.direction is facing
        assert (tunnel.grid_x // SLOT, tunnel.grid_y // SLOT) == slot
        step = {
            Direction.Up: (0, 1),
            Direction.Down: (0, -1),
            Direction.Left: (-1, 0),
            Direction.Right: (1, 0),
        }[facing]
        front = (slot[0] + step[0], slot[1] + step[1])
        assert 0 <= front[0] < result.slot_cols and 0 <= front[1] < result.slot_rows
        assert front in box_slots
    assert not any("hướng nhả box hợp lệ" in warning for warning in result.warnings)


def test_digging_is_narrowed_until_the_belt_survives_it():
    """Burying costs conveyor room, so a tight belt has to flatten the queue.

    The picture has to alternate colours box by box for this to bite: reversing a
    run of boxes that are all the same colour changes nothing, so a banded
    picture would swallow any dig window for free.
    """
    options = AutoGenOptions(
        difficulty=int(LevelDifficulty.SuperHard),
        tunnel_mode="mechanic",
        dig_window=8,
        belt_slots=BALLS_PER_BOX,
    )
    result = auto_generate_boxes(banded_level([0, 1, 2] * 4), options)
    assert result.dig_window < 8
    assert any("Độ chôn của tunnel bị thu hẹp" in warning for warning in result.warnings)
    board = BoardState.from_pixel_grid(result.level.pixel_grid)
    assert simulate_order(board, result.play_order, GameRules(result.belt_slots))


def test_overflow_tunnels_are_buried_by_difficulty_too():
    """The mechanic is the same whether the tunnel was asked for or forced."""
    easy = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.Easy), max_slot_cols=3, max_slot_rows=3),
    )
    hard = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), max_slot_cols=3, max_slot_rows=3),
    )
    assert easy.release.max_dig == 0
    assert hard.release.max_dig > 0
    for result in (easy, hard):
        assert result.total_boxes == 30
        assert_valid(result.level)


def test_tunnel_depth_and_count_can_be_overridden():
    options = AutoGenOptions(
        difficulty=int(LevelDifficulty.SuperHard),
        tunnel_mode="mechanic",
        max_tunnels=1,
        tunnel_depth=6,
    )
    result = auto_generate_boxes(level_10(), options)
    assert result.tunnel_count == 1
    assert result.tunnel_boxes == 6
    assert_valid(result.level)


def test_a_tunnel_can_swallow_a_picture_far_bigger_than_the_slot_limit():
    """Tunnels are the only reason a picture may exceed 8x8 slots of surface."""
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), max_slot_cols=2, max_slot_rows=2)
    result = auto_generate_boxes(level_10(), options)
    assert result.surface_boxes + result.tunnel_count <= 2 * 2
    assert result.tunnel_boxes == 30 - result.surface_boxes
    board = BoardState.from_pixel_grid(result.level.pixel_grid)
    assert simulate_order(board, result.play_order, GameRules(result.belt_slots))
    assert_valid(result.level)


def test_bad_tunnel_options_are_rejected():
    with pytest.raises(AutoGenError, match="tunnel mode"):
        auto_generate_boxes(level_10(), AutoGenOptions(tunnel_mode="nope"))
    with pytest.raises(AutoGenError, match="dig window"):
        auto_generate_boxes(level_10(), AutoGenOptions(dig_window=0))


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_tunnels_stay_winnable_on_arbitrary_pictures(difficulty, seed):
    """Whatever the picture, the order the tunnels force must still win."""
    level = varied_level(12, 12, 5, seed=seed)
    result = auto_generate_boxes(
        level, AutoGenOptions(difficulty=difficulty, tunnel_mode="mechanic")
    )
    board = BoardState.from_pixel_grid(result.level.pixel_grid)
    assert simulate_order(board, result.play_order, GameRules(result.belt_slots))
    assert Counter(result.play_order) == Counter(result.solution.order)
    assert result.tunnel_boxes == sum(len(queue) for queue in result.tunnel_queues)
    assert result.release.max_dig <= result.dig_window - 1
    assert result.level.source_histogram() == result.level.target_histogram()
    assert_valid(result.level)


def test_the_report_explains_the_tunnel_queues():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), tunnel_mode="mechanic")
    report = format_report(auto_generate_boxes(level_10(), options), options)
    for fragment in (
        "Tunnel:",
        "độ chôn",
        "phải đào:",
        "hướng nhả box",
        "tunnel 0 từ đầu hàng:",
    ):
        assert fragment in report


# --------------------------------------------------------------------------- #
# Walls
# --------------------------------------------------------------------------- #
def wall_slots(result) -> set[tuple[int, int]]:
    """Every lattice slot the generated level left without a cell."""
    taken = {(cell.grid_x // SLOT, cell.grid_y // SLOT) for cell in result.level.grid_cells}
    return {
        (slot_x, slot_y)
        for slot_y in range(result.slot_rows)
        for slot_x in range(result.slot_cols)
        if (slot_x, slot_y) not in taken
    }


def test_reachability_walks_around_a_wall_but_never_through_it():
    # A ring of walls around (1, 1) seals it off; opening one side lets a route in.
    sealed = [(0, 1), (2, 1), (1, 0), (1, 2)]
    assert (1, 1) not in reachable_slots(3, 3, set(sealed))
    assert (1, 1) in reachable_slots(3, 3, set(sealed[:3]))


def test_a_box_pinched_on_two_sides_is_still_reachable_from_the_third():
    """The rule the designer described: wall two sides, come around the rest."""
    assert layout_is_open(5, 5, [(1, 2), (3, 2)], [])
    assert not layout_is_open(5, 5, [(1, 2), (3, 2), (2, 1), (2, 3)], [])


def test_a_full_lattice_without_walls_is_always_open():
    assert layout_is_open(5, 6, [], [])
    assert layout_is_open(5, 6, [], [(0, 5), (4, 5)])


def test_walls_are_capped_at_one_per_four_boxes():
    """A small picture cannot afford the pinch a large one shrugs off."""
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.SuperHard)]
    auto = AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard))
    assert plan_walls(40, auto, profile) == profile.walls
    assert plan_walls(6, auto, profile) == 1
    assert plan_walls(3, auto, profile) == 0
    assert plan_walls(40, AutoGenOptions(walls=0), profile) == 0
    assert plan_walls(40, AutoGenOptions(walls=1), profile) == 1


@pytest.mark.parametrize("difficulty", [int(LevelDifficulty.Easy), int(LevelDifficulty.Medium)])
def test_easy_and_medium_keep_the_grid_solid(difficulty):
    """Walls are a Hard mechanic; the gentle difficulties must not sprout them."""
    assert DIFFICULTY_PROFILES[difficulty].walls == 0
    result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
    assert result.wall_count == 0


@pytest.mark.parametrize(
    "difficulty", [int(LevelDifficulty.Hard), int(LevelDifficulty.SuperHard)]
)
def test_hard_difficulties_pinch_a_box_between_two_walls(difficulty):
    result = auto_generate_boxes(level_10(), tier_options(difficulty=difficulty))
    assert result.wall_count >= DIFFICULTY_PROFILES[difficulty].walls
    assert result.pinched_slots, "the point of a wall is to leave a box one way in"
    for pinch_x, pinch_y in result.pinched_slots:
        assert {(pinch_x - 1, pinch_y), (pinch_x + 1, pinch_y)} <= set(result.wall_slots)
        assert (pinch_x, pinch_y) not in set(result.wall_slots), "a pinched slot holds a box"


def test_walls_never_touch_so_they_cannot_grow_into_one_bar():
    result = auto_generate_boxes(
        level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), walls=4)
    )
    pinch_walls = {
        slot
        for pinch_x, pinch_y in result.pinched_slots
        for slot in ((pinch_x - 1, pinch_y), (pinch_x + 1, pinch_y))
    }
    for x, y in pinch_walls:
        assert (x, y + 1) not in pinch_walls and (x + 1, y) not in pinch_walls


def test_wall_slots_are_exactly_the_slots_the_level_left_empty():
    """Every empty lattice slot is a wall - the report cannot claim otherwise."""
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
        assert set(result.wall_slots) == wall_slots(result)


def test_walls_can_be_switched_off_and_asked_for_by_hand():
    off = auto_generate_boxes(
        level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), walls=0)
    )
    assert off.wall_count == 0 and off.pinched_slots == []
    asked = auto_generate_boxes(
        level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Easy), walls=2)
    )
    assert asked.wall_count >= 2 and asked.pinched_slots


def test_a_negative_wall_count_is_rejected():
    with pytest.raises(AutoGenError, match="Wall count"):
        auto_generate_boxes(level_10(), AutoGenOptions(walls=-2))


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_walls_never_seal_a_box_off_on_arbitrary_pictures(difficulty, seed):
    """Whatever the picture, no box may end up walled in on all four sides."""
    level = varied_level(12, 12, 5, seed=seed)
    result = auto_generate_boxes(
        level, AutoGenOptions(difficulty=difficulty, tunnel_mode="mechanic")
    )
    tunnels = [
        (cell.grid_x // SLOT, cell.grid_y // SLOT)
        for cell in result.level.grid_cells
        if isinstance(cell, TunnelCellData)
    ]
    assert set(result.wall_slots) == wall_slots(result)
    assert layout_is_open(result.slot_cols, result.slot_rows, result.wall_slots, tunnels)


def test_the_report_explains_the_walls():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard))
    result = auto_generate_boxes(level_10(), options)
    report = format_report(result, options)
    for fragment in ("Wall:", "vị trí slot", "box bị kẹp giữa hai wall"):
        assert fragment in report
    assert any("wall" in warning for warning in result.warnings)


# --------------------------------------------------------------------------- #
# Hidden effects drive the difficulty
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_hidden_share_follows_the_difficulty(difficulty):
    result = auto_generate_boxes(level_10(), tier_options(difficulty=difficulty))
    target = DIFFICULTY_PROFILES[difficulty].hidden_ratio
    # Of the surface, not of every box: a tunnel already conceals everything
    # behind its head, so the Hidden budget is only ever spent out front - and
    # the hard tiers now spend obstacle budget on tunnels, which shrinks it.
    assert result.surface_hidden_ratio == pytest.approx(target, abs=0.05)


def test_easy_hides_a_little_and_superhard_hides_the_most():
    easy = auto_generate_boxes(level_10(), tier_options(difficulty=int(LevelDifficulty.Easy)))
    hard = auto_generate_boxes(level_10(), tier_options(difficulty=int(LevelDifficulty.Hard)))
    super_hard = auto_generate_boxes(
        level_10(), tier_options(difficulty=int(LevelDifficulty.SuperHard))
    )
    # Easy hides a *little* - a handful of boxes is the gentle form of the
    # mechanic, and it is one of the two Easy spends its obstacle budget on.
    assert 0 < easy.hidden_boxes <= 3
    assert easy.hidden_boxes < hard.hidden_boxes < super_hard.hidden_boxes


def test_the_front_slot_row_is_never_hidden():
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
        front_row = [cell for cell in surface_boxes(result.level) if cell.grid_y == 0]
        assert front_row
        assert not any(cell.has_effect(HiddenCellEffectData) for cell in front_row)
        assert result.hidden_by_slot_row[0] == (0, 0)


def test_hiding_spends_itself_on_the_rarest_colors_first():
    """Hiding one of a dozen identical boxes hides nothing; hiding the only one does.

    Level 10 spends its Hidden on the one-and-two-box colors and leaves all 12
    Black ones visible. A rare color is hidden as fully as it *can* be, which is
    every one of its boxes that did not land on the front row - that row is
    always readable, so a box sitting there is simply not a candidate.

    Generated with the whole picture on the surface, because a tunnel swallows
    boxes of its own and would leave the colour counts here describing a subset.
    """
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.Hard), **LIKE_THE_HAND_MADE_LEVEL),
    )
    by_color = {color: (count, total) for color, count, total in result.hidden_by_color}
    front_row = Counter(int(cell.color) for cell in result.level.grid_cells if cell.grid_y == 0)

    assert by_color[int(ItemColor.Black)] == (0, 12), "the bulk color stays readable"
    for rare in (ItemColor.LightPink, ItemColor.Lime, ItemColor.Red, ItemColor.White):
        count, total = by_color[int(rare)]
        hideable = total - front_row.get(int(rare), 0)
        assert count == hideable, (
            f"{rare.name} has {total} box(es), {hideable} off the front row, "
            f"and only {count} hidden"
        )

    # No color may be hidden more than a strictly rarer one, in share terms.
    shares = [
        (total, count / total)
        for _, count, total in result.hidden_by_color
    ]
    for (total_a, share_a), (total_b, share_b) in zip(shares, shares[1:]):
        if total_a < total_b:
            assert share_a >= share_b or share_b == 0.0


def test_hidden_boxes_are_scattered_over_several_slot_rows():
    result = auto_generate_boxes(
        level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Hard))
    )
    rows_with_hidden = [row for row, count in result.hidden_by_slot_row if count]
    assert len(rows_with_hidden) >= 3, "hiding must not collapse into one solid band"


def test_hidden_ratio_can_be_overridden():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Easy), hidden_ratio=1.0)
    result = auto_generate_boxes(level_10(), options)
    front_row = sum(1 for cell in surface_boxes(result.level) if cell.grid_y == 0)
    # Everything except the always-visible front row.
    assert result.hidden_boxes == result.surface_boxes - front_row
    assert_valid(result.level)


def test_an_invalid_hidden_ratio_is_rejected():
    with pytest.raises(AutoGenError, match="Hidden ratio"):
        auto_generate_boxes(level_10(), AutoGenOptions(hidden_ratio=1.5))


def test_an_exact_hidden_count_beats_the_share():
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.SuperHard)]
    assert plan_hidden_count(30, AutoGenOptions(hidden_boxes=7, hidden_ratio=1.0), profile) == 7
    assert plan_hidden_count(30, AutoGenOptions(hidden_boxes=0), profile) == 0, "0 is off, not Auto"
    assert plan_hidden_count(30, AutoGenOptions(), profile) == round(profile.hidden_ratio * 30)


def test_asking_for_an_exact_number_of_hidden_boxes_gets_it():
    """Easy hides nothing on its own, so any hidden box here came from the count."""
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Easy), hidden_boxes=6)
    result = auto_generate_boxes(level_10(), options)

    assert result.hidden_boxes == 6
    assert_valid(result.level)


def test_more_hidden_boxes_than_the_back_rows_hold_is_clipped_and_reported():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Easy), hidden_boxes=999)
    result = auto_generate_boxes(level_10(), options)

    front_row = sum(1 for cell in surface_boxes(result.level) if cell.grid_y == 0)
    assert result.hidden_boxes == result.surface_boxes - front_row
    assert any("Chỉ ẩn được" in warning for warning in result.warnings), (
        "a clipped request must say so rather than look like it was honoured"
    )


def test_a_hidden_box_is_never_written_active():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), active_policy="all")
    result = auto_generate_boxes(level_10(), options)
    for cell in surface_boxes(result.level):
        if cell.has_effect(HiddenCellEffectData):
            assert cell.is_active is False
    assert_valid(result.level)


# --------------------------------------------------------------------------- #
# Balancing
# --------------------------------------------------------------------------- #
def test_balance_deletes_only_the_surplus_of_each_color():
    """A picture with no room to grow and no colour able to pay another."""
    grid = PixelGridData(4, 4, [0] * 10 + [1] * 6)
    report = balance_pixel_grid(grid, BALLS_PER_BOX)
    assert report.removed == Counter({0: 1, 1: 6})
    assert not report.added and not report.moved, "a full picture cannot grow"
    assert grid.histogram() == Counter({0: 9})


def test_balance_paints_the_missing_pixels_instead_of_deleting_the_surplus():
    """Empty cells beside a colour are the cheapest way to reach a multiple."""
    grid = PixelGridData(6, 6, [0] * 10 + [1] * 8 + [EMPTY_COLOR_ID] * 18)
    report = balance_pixel_grid(grid, BALLS_PER_BOX)
    assert not report.removed, "the empty rows pay for both colours"
    assert grid.histogram() == Counter({0: 18, 1: 9})
    assert sum(grid.histogram().values()) % BALLS_PER_BOX == 0


def test_balance_grows_every_colour_when_the_picture_has_room():
    # Two bands with empty rows under each, so both colours have room of their own.
    grid = PixelGridData(
        9, 9, [0] * 20 + [EMPTY_COLOR_ID] * 16 + [1] * 20 + [EMPTY_COLOR_ID] * 25
    )
    report = balance_pixel_grid(grid, BALLS_PER_BOX)
    assert report.added == Counter({0: 7, 1: 7})
    assert not report.removed and not report.moved
    assert grid.histogram() == Counter({0: 27, 1: 27})


def test_a_colour_walled_in_by_its_neighbour_borrows_instead_of_losing_pixels():
    """The colour with room grows by what the boxed-in one needs and hands it over."""
    # Colour 0 fills the top rows and colour 1 seals it in; only colour 1 can grow.
    grid = PixelGridData(9, 9, [0] * 20 + [1] * 20 + [EMPTY_COLOR_ID] * 41)
    report = balance_pixel_grid(grid, BALLS_PER_BOX)
    assert not report.removed, "borrowing costs the picture nothing"
    assert report.moved == Counter({(1, 0): 7}), "colour 1 paid colour 0"
    assert report.added == Counter({1: 14}), "7 for itself, 7 to hand over"
    assert grid.histogram() == Counter({0: 27, 1: 27})


def test_balance_added_pixels_touch_their_own_colour():
    """A pixel dropped away from its colour is a speck, and a one-pixel run."""
    grid = PixelGridData(9, 9, [0] * 20 + [1] * 20 + [EMPTY_COLOR_ID] * 41)
    before = {
        (row, column)
        for row in range(9)
        for column in range(9)
        if grid.get_color_id(row, column) != EMPTY_COLOR_ID
    }
    balance_pixel_grid(grid, BALLS_PER_BOX)
    for row in range(9):
        for column in range(9):
            color = grid.get_color_id(row, column)
            if color == EMPTY_COLOR_ID or (row, column) in before:
                continue
            assert any(
                0 <= row + dy < 9
                and 0 <= column + dx < 9
                and grid.get_color_id(row + dy, column + dx) == color
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))
            ), f"({row}, {column}) was painted away from its own colour"


def test_a_full_picture_balances_by_recolouring_instead_of_deleting():
    """Leftovers that add up to nine settle each other, pixel for pixel."""
    # 27 cells, no empty one left: six of one colour and three of another.
    grid = PixelGridData(9, 3, [0] * 6 + [1] * 21)
    report = balance_pixel_grid(grid, BALLS_PER_BOX)
    assert report.moved == Counter({(1, 0): 3}), "the colour nearest a multiple is topped up"
    assert not report.removed, "recolouring reaches a multiple without losing a pixel"
    assert grid.histogram() == Counter({0: 9, 1: 18})
    assert sum(grid.histogram().values()) == 27, "every pixel is still on the picture"


def test_the_residue_a_full_picture_cannot_recolour_is_all_that_is_deleted():
    """What is left is the whole picture's own shortfall, never more."""
    grid = PixelGridData(5, 5, [0] * 13 + [1] * 12)
    report = balance_pixel_grid(grid, BALLS_PER_BOX)
    assert report.removed_pixels == 25 % BALLS_PER_BOX == 7
    assert not report.added, "there is nowhere to paint"
    assert sum(count % BALLS_PER_BOX for count in grid.histogram().values()) == 0


def test_balance_prefers_the_bottom_because_pixels_are_eaten_top_down():
    grid = PixelGridData(2, 5, [0] * 10)
    balance_pixel_grid(grid, BALLS_PER_BOX)  # full grid, so the surplus is deleted
    assert sum(grid.histogram().values()) == 9
    assert all(grid.get_color_id(0, column) == 0 for column in range(2)), "top row preserved"
    bottom_row = [grid.get_color_id(4, column) for column in range(2)]
    assert EMPTY_COLOR_ID in bottom_row, "the deletion came from the last-eaten row"


def test_balance_reports_a_column_it_had_to_empty():
    grid = PixelGridData(3, 4, [0] * 9 + [1, EMPTY_COLOR_ID, EMPTY_COLOR_ID])
    assert balance_pixel_grid(grid, BALLS_PER_BOX).emptied_columns == []
    assert grid.histogram() == Counter({0: 9})


def test_generation_reports_the_pixels_it_deleted():
    level = make_level([0] * 10 + [1] * 6, 4, 4)
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Easy))
    result = auto_generate_boxes(level, options)
    assert sum(result.removed_pixels.values()) == 7
    assert result.total_boxes == 1
    assert "xoá 7 pixel dư" in format_report(result, options)


def test_generation_reports_the_pixels_it_painted_in():
    level = make_level([0] * 20 + [1] * 20 + [EMPTY_COLOR_ID] * 41, 9, 9)
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Easy))
    result = auto_generate_boxes(level, options)
    assert not result.removed_pixels, "growing the colours cost the picture nothing"
    assert sum(result.added_pixels.values()) == 14
    assert result.total_boxes == 6
    assert "thêm 14 pixel vào chỗ trống" in format_report(result, options)


# --------------------------------------------------------------------------- #
# conveyor behaviour
# --------------------------------------------------------------------------- #
def test_piece_is_preserved_because_the_belt_is_sized_from_it():
    """Writing back the peak would change the belt the next run is judged on."""
    for difficulty in ALL_DIFFICULTIES:
        level = level_10()
        result = auto_generate_boxes(level, AutoGenOptions(difficulty=difficulty))
        assert result.level.piece == level.piece
        assert result.belt_slots == level.piece * BALLS_PER_BOX


def test_a_belt_smaller_than_the_picture_needs_still_builds_the_grid():
    """Three boxes of belt cannot hold a picture whose worst moment wants five.

    The box grid is not the belt's to refuse: what boxes a picture needs is fixed
    by its histogram and is correct either way, so the grid is built and the belt
    is what gets the warning.
    """
    options = unrepaired(difficulty=int(LevelDifficulty.Hard), belt_slots=27)

    result = auto_generate_boxes(level_10(), options)

    assert not result.winnable and result.jam is not None
    assert result.level.source_histogram() == result.level.target_histogram()
    assert result.certified_belt > result.belt_slots, "verified on the belt it needs"
    assert result.level.piece == 27 // BALLS_PER_BOX, "piece follows the belt asked for"
    assert result.level.piece < result.certified_belt // BALLS_PER_BOX, (
        "the certified belt is a yardstick, never something the generator writes back"
    )


def test_a_picture_the_belt_cannot_hold_reports_where_it_jams():
    """The warning is the deliverable here: which pixel, which colours, which cell."""
    level = noisy_level(12, 12, 10, seed=7)

    result = auto_generate_boxes(level, unrepaired())

    assert result.jam is not None
    warning = next(w for w in result.warnings if "CHƯA THẮNG ĐƯỢC" in w)
    assert "KẸT tại pixel thứ" in warning
    assert "hàng" in warning and "cột" in warning, "a pixel index is not a place on the canvas"
    assert "piece" in warning, "the warning has to say how to fix it"
    assert "!! CHƯA THẮNG ĐƯỢC" in format_report(result, unrepaired())


def test_a_level_its_own_belt_can_play_carries_no_jam():
    result = auto_generate_boxes(level_10(), AutoGenOptions())

    assert result.winnable and result.jam is None
    assert result.certified_belt == result.belt_slots
    assert "CHƯA THẮNG ĐƯỢC" not in format_report(result, AutoGenOptions())


def test_level_10_generates_on_the_belt_its_own_piece_buys():
    """The belt is piece*9, which is the whole reason this picture generates.

    Level 10 as it is actually painted needs 40 balls at its worst moment. A
    fixed thirty-ball belt would reject it; the five boxes its own ``piece``
    buys hold it with room to spare.
    """
    level = level_10()
    scan = scan_picture(level.pixel_grid)
    assert scan.demand.peak_balls > DEFAULT_BELT_SLOTS, "a 30-ball belt would jam"
    assert scan.demand.peak_balls <= level.piece * BALLS_PER_BOX

    result = auto_generate_boxes(level, AutoGenOptions())
    assert result.belt_slots == level.piece * BALLS_PER_BOX


def test_the_certified_walkthrough_wins_on_the_belt_it_was_built_for():
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
        board = BoardState.from_pixel_grid(result.level.pixel_grid)
        assert simulate_order(board, result.solution.order, GameRules(result.belt_slots))
        assert result.metrics.min_safe_options >= 1


def test_no_generated_level_ever_exceeds_the_belt_it_declares():
    """The loss rule, stated directly: the run never needs more than the belt has."""
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
        board = BoardState.from_pixel_grid(result.level.pixel_grid)
        specs = [[result.solution.order[index] for index in group] for group in result.play_groups]
        residues = belt_residues(board, specs, GameRules(result.belt_slots))
        assert residues is not None, "the forced play order must win"
        assert max(residues) <= result.belt_slots


# --------------------------------------------------------------------------- #
# Metadata, determinism and errors
# --------------------------------------------------------------------------- #
def test_generation_replaces_obstacles_that_referenced_the_old_boxes():
    level = level_10()
    level.obstacles = [LargeBlockObstacleData(0, 0, 1, 1, 1)]
    result = auto_generate_boxes(level, AutoGenOptions(difficulty=int(LevelDifficulty.Easy)))
    assert result.level.obstacles == []
    assert result.dropped_obstacles == 1
    assert any("obstacle" in warning for warning in result.warnings)


def test_theme_can_be_left_alone():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), apply_theme=False)
    result = auto_generate_boxes(level_10(), options)
    assert result.level.theme_id == int(ThemeId.None_)


def test_generation_is_deterministic():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard))
    first = dumps_level(auto_generate_boxes(level_10(), options).level)
    second = dumps_level(auto_generate_boxes(level_10(), options).level)
    assert first == second


def test_generated_level_survives_a_serializer_round_trip():
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.Hard), **LIKE_THE_HAND_MADE_LEVEL),
    )
    reloaded = level_from_dict(level_to_dict(result.level))
    assert reloaded.source_histogram() == result.level.source_histogram()
    assert reloaded.target_histogram() == result.level.target_histogram()
    assert (reloaded.grid_cols, reloaded.grid_rows) == (15, 18)
    assert reloaded.piece == result.level.piece
    assert sum(cell.has_effect(HiddenCellEffectData) for cell in reloaded.grid_cells) == 12
    assert dumps_level(result.level).endswith("\n")


def test_the_source_level_is_never_mutated():
    level = level_10()
    before = list(level.pixel_grid.color_ids), list(level.grid_cells), level.piece
    auto_generate_boxes(level, AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard)))
    assert (list(level.pixel_grid.color_ids), list(level.grid_cells), level.piece) == before


def test_empty_pixel_grid_is_rejected():
    with pytest.raises(AutoGenError, match="Paint the pixel grid"):
        auto_generate_boxes(make_level([EMPTY_COLOR_ID] * 16, 4, 4), AutoGenOptions())


def test_a_picture_with_no_full_box_of_any_color_is_rejected():
    """A full picture too small to pay for one box: nothing to grow, nothing to swap."""
    level = make_level([0] * 4 + [1] * 4, 4, 2)
    with pytest.raises(AutoGenError, match="not a single box"):
        auto_generate_boxes(level, AutoGenOptions())


def test_a_picture_with_room_is_grown_into_a_box_instead_of_being_rejected():
    """The same eight pixels, on a grid with space, are painted up to one box."""
    level = make_level([0] * 4 + [1] * 4 + [EMPTY_COLOR_ID] * 8, 4, 4)
    result = auto_generate_boxes(level, AutoGenOptions())
    assert result.total_boxes >= 1
    assert result.added_pixels, "the empty half of the grid paid for the box"


def test_unknown_options_are_rejected():
    with pytest.raises(AutoGenError, match="difficulty"):
        auto_generate_boxes(level_10(), AutoGenOptions(difficulty=99))
    with pytest.raises(AutoGenError, match="isActive"):
        auto_generate_boxes(level_10(), AutoGenOptions(active_policy="nope"))


def test_report_covers_the_numbers_a_designer_checks():
    options = AutoGenOptions(
        difficulty=int(LevelDifficulty.Hard), **LIKE_THE_HAND_MADE_LEVEL
    )
    report = format_report(auto_generate_boxes(level_10(), options), options)
    for fragment in ("Hard", "5x6 slot", "gridCols 15", "Box ẩn (Hidden):", "piece", "Square_3x3"):
        assert fragment in report


# --------------------------------------------------------------------------- #
# Gameplay model
# --------------------------------------------------------------------------- #
def test_board_eats_the_picture_top_down_and_right_to_left():
    # rows are [0, 1] / [0, 1] / [2, 2], so play order is 1 0 1 0 2 2.
    board = BoardState.from_pixel_grid(PixelGridData(2, 3, [0, 1, 0, 1, 2, 2]))
    assert board.sequence == (1, 0, 1, 0, 2, 2)
    assert board.frontier_colors() == {1}, "only one cell is ever payable"
    assert board.run_capacity(1) == 1 and board.run_capacity(0) == 0
    assert board.next_gap(0) == 1 and board.next_gap(2) == 4
    assert board.fill(0, 5) == 0, "a colour that is not the frontier pays nothing"
    assert board.fill(1, 5) == 1
    assert board.frontier_colors() == {0}


def test_board_skips_holes_rather_than_stopping_at_them():
    board = BoardState.from_pixel_grid(
        PixelGridData(2, 3, [0, EMPTY_COLOR_ID, EMPTY_COLOR_ID, 1, 2, 2])
    )
    assert board.sequence == (0, 1, 2, 2), "empty cells are not stops"


def test_box_multiset_is_fixed_by_the_pixel_histogram():
    board = BoardState.from_pixel_grid(banded_level([0, 1, 0]).pixel_grid)
    assert box_multiset(board) == Counter({BoxSpec(0, 9): 2, BoxSpec(1, 9): 1})


def test_box_multiset_rejects_a_color_that_is_not_a_multiple_of_nine():
    board = BoardState.from_pixel_grid(PixelGridData(2, 2, [0, 0, 0, 1]))
    with pytest.raises(GameplayError, match="not a multiple of 9"):
        box_multiset(board)


def test_horizontal_bands_need_only_one_box_of_belt():
    board = BoardState.from_pixel_grid(banded_level([0, 1, 2, 0]).pixel_grid)
    boxes = box_multiset(board)
    assert minimum_belt(board, boxes) == BALLS_PER_BOX
    solution = solve_order(board, boxes, GameRules(BALLS_PER_BOX))
    assert solution is not None
    assert simulate_order(board, solution.order, GameRules(BALLS_PER_BOX))


def test_wrong_pick_loses_the_run_on_a_one_box_belt():
    board = BoardState.from_pixel_grid(banded_level([0, 1, 2, 0, 1]).pixel_grid)
    solution = solve_order(board, box_multiset(board), GameRules(BALLS_PER_BOX))
    assert solution is not None
    reversed_order = list(reversed(solution.order))
    assert reversed_order != solution.order
    assert not simulate_order(board, reversed_order, GameRules(BALLS_PER_BOX))
