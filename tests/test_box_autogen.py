from __future__ import annotations

import random
from collections import Counter

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
    bury_queue,
    choose_lattice,
    format_report,
    layout_is_open,
    plan_tunnels,
    plan_walls,
    reachable_slots,
    tunnel_blocks,
)
from pixel_level_tool.services.level_serializer import dumps_level, level_from_dict, level_to_dict
from pixel_level_tool.services.level_validator import LevelValidator
from pixel_level_tool.services.mechanics_scanner import MechanicsScanner
from pixel_level_tool.services.pixel_gameplay import (
    BoardState,
    BoxSpec,
    GameRules,
    GameplayError,
    box_multiset,
    minimum_tray,
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
    rows = [[int(value) for value in line.split()] for line in LEVEL_10_ROWS.split("\n") if line.strip()]
    return make_level([value for row in rows for value in row], len(rows[0]), len(rows), level=10)


def banded_level(band_colors: list[int], width: int = 3, band_height: int = 3) -> PixelLevelData:
    """Full-width horizontal bands of one box worth of pixels each."""
    color_ids = [color for color in band_colors for _ in range(band_height * width)]
    return make_level(color_ids, width, band_height * len(band_colors))


def noisy_level(width: int, height: int, colors: int, seed: int) -> PixelLevelData:
    rnd = random.Random(seed)
    return make_level([rnd.randrange(colors) for _ in range(width * height)], width, height)


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


def test_regenerating_level_10_reproduces_its_structure():
    """Auto Gen Box must land on the same shape a designer authored by hand.

    Level 10 is a solid 5x6 rectangle, so the walls Hard would reserve are the
    one thing that has to be switched off to compare like for like.
    """
    result = auto_generate_boxes(
        level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Hard), walls=0)
    )
    generated = result.level

    assert (result.slot_cols, result.slot_rows) == (5, 6)
    assert result.wall_count == 0
    assert (generated.grid_cols, generated.grid_rows) == (15, 18)
    assert result.total_boxes == 30
    assert result.tunnel_count == 0
    assert sum(result.removed_pixels.values()) == 0, "an aligned picture loses no pixels"
    assert result.hidden_boxes == 12
    assert generated.piece == 5
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
    assert MechanicsScanner().scan(generated) == ["Hidden"]
    assert_valid(generated)


def test_level_10_needs_fewer_tray_slots_than_it_ships_with():
    """The solver must not inflate piece the way a greedy walkthrough does."""
    board = BoardState.from_pixel_grid(level_10().pixel_grid)
    boxes = box_multiset(board)
    assert minimum_tray(board, boxes) == 3
    assert solve_order(board, boxes, GameRules(5)) is not None


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
    tunnels, stored = plan_tunnels(30, 4, options, DIFFICULTY_PROFILES[int(LevelDifficulty.Easy)])
    assert (tunnels, stored) == (2, 28)
    assert 30 - stored == 4 - tunnels, "every surviving surface slot carries a box"


def test_overflow_mode_leaves_a_picture_that_fits_alone():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard))
    assert plan_tunnels(30, 64, options, DIFFICULTY_PROFILES[int(LevelDifficulty.SuperHard)]) == (0, 0)


def test_mechanic_mode_plants_the_difficultys_tunnels_even_when_everything_fits():
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), tunnel_mode="mechanic")
    assert plan_tunnels(30, 64, options, profile) == (profile.tunnels, profile.tunnels * profile.tunnel_depth)


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
    options = AutoGenOptions(difficulty=difficulty, tunnel_mode="mechanic")
    result = auto_generate_boxes(level_10(), options)

    assert result.tunnel_count == DIFFICULTY_PROFILES[difficulty].tunnels
    assert result.tunnel_boxes > 0
    assert result.total_boxes == 30
    assert result.level.source_histogram() == result.level.target_histogram()
    assert sorted(MechanicsScanner().scan(result.level))[0] == "Hidden" or result.hidden_boxes == 0
    assert "Tunnel" in MechanicsScanner().scan(result.level)
    assert_valid(result.level)

    # The order the tunnels force on the player, not just the ideal walkthrough.
    board = BoardState.from_pixel_grid(result.level.pixel_grid)
    assert simulate_order(board, result.play_order, GameRules(result.level.piece))
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
            level_10(), AutoGenOptions(difficulty=difficulty, tunnel_mode="mechanic")
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
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), tunnel_mode="mechanic")
    result = auto_generate_boxes(level_10(), options)
    tunnels = tunnels_of(result.level)
    assert len(tunnels) == 2
    back_row = (result.slot_rows - 1) * SLOT
    assert all(tunnel.grid_y == back_row for tunnel in tunnels)
    assert {tunnel.grid_x for tunnel in tunnels} == {0, (result.slot_cols - 1) * SLOT}
    occupied = [cell for box in result.level.grid_cells for cell in box.occupied_cells()]
    assert len(occupied) == len(set(occupied)), "an emptied tunnel keeps its slot to itself"


def test_digging_is_narrowed_until_the_tray_survives_it():
    """Burying costs tray slots, so a tight piece has to flatten the queue."""
    options = AutoGenOptions(
        difficulty=int(LevelDifficulty.SuperHard),
        tunnel_mode="mechanic",
        dig_window=8,
        tray_slots=3,
    )
    result = auto_generate_boxes(level_10(), options)
    assert result.dig_window < 8
    assert any("Độ chôn của tunnel bị thu hẹp" in warning for warning in result.warnings)
    board = BoardState.from_pixel_grid(result.level.pixel_grid)
    assert simulate_order(board, result.play_order, GameRules(result.level.piece))


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
    assert simulate_order(board, result.play_order, GameRules(result.level.piece))
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
    level = noisy_level(12, 12, 5, seed=seed)
    result = auto_generate_boxes(
        level, AutoGenOptions(difficulty=difficulty, tunnel_mode="mechanic")
    )
    board = BoardState.from_pixel_grid(result.level.pixel_grid)
    assert simulate_order(board, result.play_order, GameRules(result.level.piece))
    assert Counter(result.play_order) == Counter(result.solution.order)
    assert result.tunnel_boxes == sum(len(queue) for queue in result.tunnel_queues)
    assert result.release.max_dig <= result.dig_window - 1
    assert result.level.source_histogram() == result.level.target_histogram()
    assert_valid(result.level)


def test_the_report_explains_the_tunnel_queues():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), tunnel_mode="mechanic")
    report = format_report(auto_generate_boxes(level_10(), options), options)
    for fragment in ("Tunnel:", "độ chôn", "phải đào:", "tunnel 0 từ đầu hàng:"):
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
    result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
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
    level = noisy_level(12, 12, 5, seed=seed)
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
    result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
    target = DIFFICULTY_PROFILES[difficulty].hidden_ratio
    assert result.hidden_ratio == pytest.approx(target, abs=0.05)


def test_easy_hides_nothing_and_superhard_hides_the_most():
    easy = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Easy)))
    hard = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Hard)))
    super_hard = auto_generate_boxes(
        level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard))
    )
    assert easy.hidden_boxes == 0
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

    Level 10 hides all of LightPink/Lime/Red (1-2 boxes each) and none of the 12
    Black ones, which is the ordering this reproduces.
    """
    result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Hard)))
    by_color = {color: (count, total) for color, count, total in result.hidden_by_color}

    assert by_color[int(ItemColor.Black)] == (0, 12), "the bulk color stays readable"
    for rare in (ItemColor.LightPink, ItemColor.Lime, ItemColor.Red):
        count, total = by_color[int(rare)]
        assert count == total, f"{rare.name} has {total} box(es) and must be fully hidden"

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
    grid = PixelGridData(4, 4, [0] * 10 + [1] * 6)
    removed, _ = balance_pixel_grid(grid, BALLS_PER_BOX)
    assert removed == Counter({0: 1, 1: 6})
    assert grid.histogram() == Counter({0: 9})


def test_balance_prefers_the_bottom_because_pixels_are_eaten_top_down():
    grid = PixelGridData(2, 5, [0] * 10)
    balance_pixel_grid(grid, BALLS_PER_BOX)
    assert sum(grid.histogram().values()) == 9
    assert all(grid.get_color_id(0, column) == 0 for column in range(2)), "top row preserved"
    bottom_row = [grid.get_color_id(4, column) for column in range(2)]
    assert EMPTY_COLOR_ID in bottom_row, "the deletion came from the last-eaten row"


def test_balance_reports_a_column_it_had_to_empty():
    grid = PixelGridData(3, 4, [0] * 9 + [1, EMPTY_COLOR_ID, EMPTY_COLOR_ID])
    _, emptied = balance_pixel_grid(grid, BALLS_PER_BOX)
    assert emptied == []
    assert grid.histogram() == Counter({0: 9})


def test_generation_reports_the_pixels_it_deleted():
    level = make_level([0] * 10 + [1] * 6, 4, 4)
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Easy))
    result = auto_generate_boxes(level, options)
    assert sum(result.removed_pixels.values()) == 7
    assert result.total_boxes == 1
    assert "Đã xoá 7 pixel" in format_report(result, options)


# --------------------------------------------------------------------------- #
# piece / tray behaviour
# --------------------------------------------------------------------------- #
def test_piece_defaults_to_five_like_the_level_files():
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
        assert result.level.piece == 5


def test_piece_can_be_overridden_and_the_result_still_wins():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), tray_slots=3)
    result = auto_generate_boxes(level_10(), options)
    assert result.level.piece == 3
    board = BoardState.from_pixel_grid(result.level.pixel_grid)
    assert simulate_order(board, result.solution.order, GameRules(3))


def test_piece_is_raised_when_the_picture_cannot_be_played_with_the_target():
    level = noisy_level(9, 9, 5, seed=7)
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Easy), tray_slots=1)
    result = auto_generate_boxes(level, options)
    assert result.level.piece >= 1
    if result.level.piece > 1:
        assert any("piece đã được nâng" in warning for warning in result.warnings)
    assert_valid(result.level)


def test_the_certified_walkthrough_wins_with_the_chosen_piece():
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
        board = BoardState.from_pixel_grid(result.level.pixel_grid)
        assert simulate_order(board, result.solution.order, GameRules(result.level.piece))
        assert result.metrics.min_safe_options >= 1


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
        level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Hard), walls=0)
    )
    reloaded = level_from_dict(level_to_dict(result.level))
    assert reloaded.source_histogram() == result.level.source_histogram()
    assert reloaded.target_histogram() == result.level.target_histogram()
    assert (reloaded.grid_cols, reloaded.grid_rows) == (15, 18)
    assert reloaded.piece == 5
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
    level = make_level([0] * 4 + [1] * 4 + [EMPTY_COLOR_ID] * 8, 4, 4)
    with pytest.raises(AutoGenError, match="not a single box"):
        auto_generate_boxes(level, AutoGenOptions())


def test_unknown_options_are_rejected():
    with pytest.raises(AutoGenError, match="difficulty"):
        auto_generate_boxes(level_10(), AutoGenOptions(difficulty=99))
    with pytest.raises(AutoGenError, match="isActive"):
        auto_generate_boxes(level_10(), AutoGenOptions(active_policy="nope"))


def test_report_covers_the_numbers_a_designer_checks():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), walls=0)
    report = format_report(auto_generate_boxes(level_10(), options), options)
    for fragment in ("Hard", "5x6 slot", "gridCols 15", "Box ẩn (Hidden):", "piece", "Square_3x3"):
        assert fragment in report


# --------------------------------------------------------------------------- #
# Gameplay model
# --------------------------------------------------------------------------- #
def test_board_eats_each_column_from_the_top():
    board = BoardState.from_pixel_grid(PixelGridData(2, 3, [0, 1, 0, 1, 2, 2]))
    assert board.frontier_colors() == {0, 1}
    assert board.run_capacity(0) == 2  # column 0 starts with two zeroes
    assert board.fill(0, 5) == 2
    assert board.frontier_colors() == {1, 2}


def test_box_multiset_is_fixed_by_the_pixel_histogram():
    board = BoardState.from_pixel_grid(banded_level([0, 1, 0]).pixel_grid)
    assert box_multiset(board) == Counter({BoxSpec(0, 9): 2, BoxSpec(1, 9): 1})


def test_box_multiset_rejects_a_color_that_is_not_a_multiple_of_nine():
    board = BoardState.from_pixel_grid(PixelGridData(2, 2, [0, 0, 0, 1]))
    with pytest.raises(GameplayError, match="not a multiple of 9"):
        box_multiset(board)


def test_horizontal_bands_need_only_one_tray_slot():
    board = BoardState.from_pixel_grid(banded_level([0, 1, 2, 0]).pixel_grid)
    boxes = box_multiset(board)
    assert minimum_tray(board, boxes) == 1
    solution = solve_order(board, boxes, GameRules(1))
    assert solution is not None
    assert simulate_order(board, solution.order, GameRules(1))


def test_wrong_pick_loses_the_run_at_one_tray_slot():
    board = BoardState.from_pixel_grid(banded_level([0, 1, 2, 0, 1]).pixel_grid)
    solution = solve_order(board, box_multiset(board), GameRules(1))
    assert solution is not None
    reversed_order = list(reversed(solution.order))
    assert reversed_order != solution.order
    assert not simulate_order(board, reversed_order, GameRules(1))
