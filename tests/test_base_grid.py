from __future__ import annotations

"""Stage 4: the box grid before a single obstacle exists, and what stands on it.

The order the generator works in is the whole subject here. A picture is read
into a box multiset, the boxes are laid out, whatever does not fit is stored in
tunnels that hand each box over exactly when the picture asks for it - and *that*
grid is replayed and proven to win before any mechanic is considered. Only then
are obstacles laid on top, each one a change to a grid that already had a winning
line, and each one re-certified.

Two guarantees come out of doing it in that order, and both are tested here:

* **The level is beatable before the difficulty is spent.** If the belt cannot
  hold the picture, that is known at stage 4 and reported against the picture,
  not blamed on the obstacles.
* **There is always something to ship.** A mechanic layer can be unplayable in
  ways no replay can see - a wall that seals a box in, a tunnel whose mouth faces
  no box - because the gameplay model taps a queue by index and walks no route
  across the grid. Those are read off the layout, disqualify the layer, and in
  the worst case the bare base grid goes out instead.

The scattered fixture is level 15's own box multiset - 72 boxes over ten colours,
read off the box grid of the shipped level - because that is the shape that
stresses all of this at once: 72 boxes overflow the 64-slot lattice, so tunnels
are forced rather than chosen, and ten colours scattered through a background
keep several of them live on the conveyor at the same time.
"""

from typing import NamedTuple

import pytest

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID, Direction, ItemColor, LevelDifficulty
from pixel_level_tool.domain.level_models import TunnelCellData
from pixel_level_tool.services.box_autogen import (
    BALLS_PER_BOX,
    DIFFICULTY_PROFILES,
    DIRECTION_STEPS,
    MAX_BOX_SLOTS,
    SLOT,
    AutoGenError,
    AutoGenOptions,
    ObstacleLayer,
    auto_generate_boxes,
    build_base_grid,
    format_report,
    scan_level,
    tunnels_can_release,
)
from pixel_level_tool.services.pixel_gameplay import (
    BoardState,
    GameRules,
    Solution,
    box_multiset,
    simulate_order,
    solve_order,
)
from tests.test_box_autogen import ALL_DIFFICULTIES, assert_valid, banded_level, make_level


# Level 15's box multiset, in balls per colour. Every surface cell of the shipped
# level is one box of its colorList colour and every tunnel storedCell is one
# more, so the file's own box grid names the picture's histogram exactly: 72
# boxes, 648 balls, ten colours, on a level that ships piece 5.
LEVEL_15_BALLS: dict[int, int] = {
    int(ItemColor.Green): 324,
    int(ItemColor.Purple): 117,
    int(ItemColor.Yellow): 63,
    int(ItemColor.Brown): 45,
    int(ItemColor.Red): 27,
    int(ItemColor.Periwinkle): 27,
    int(ItemColor.Blue): 18,
    int(ItemColor.White): 9,
    int(ItemColor.Pink): 9,
    int(ItemColor.LightPink): 9,
}
LEVEL_15_WIDTH, LEVEL_15_HEIGHT = 26, 25
LEVEL_15_BOXES = sum(LEVEL_15_BALLS.values()) // BALLS_PER_BOX


def scattered_level(speckles: int = 27, level: int = 15):
    """Level 15's histogram, painted as regions with a speckled background.

    The runtime reads top row down and right to left, so a colour laid out in
    whole rows is one contiguous run in play order and a speckle is a one-pixel
    interruption of the background. That is how level 15 is painted - solid
    regions with a decorated rim - and the speckle count is the dial between "ten
    colours in bands" and "ten colours as noise".
    """
    green = int(ItemColor.Green)
    cells = [green] * (LEVEL_15_WIDTH * LEVEL_15_HEIGHT)
    # Level 15 leaves two cells unpainted; 648 balls is exactly 72 boxes.
    cells[-1] = cells[-2] = EMPTY_COLOR_ID
    at = 0
    for colour, balls in LEVEL_15_BALLS.items():
        if colour == green:
            continue
        for _ in range(balls):
            cells[at] = colour
            at += 1
    purple = int(ItemColor.Purple)
    painted, index = 0, at
    while painted < speckles and index < len(cells) - 2:
        if cells[index] == green:
            cells[index] = purple
            # Paid for out of the solid region, so the multiset stays exact.
            for back in range(at - 1, -1, -1):
                if cells[back] == purple:
                    cells[back] = green
                    break
            painted += 1
        index += 7
    grid = make_level(cells, LEVEL_15_WIDTH, LEVEL_15_HEIGHT, level=level)
    grid.piece = 5
    return grid


class Floor(NamedTuple):
    """Stage 4 on its own, with what it takes to replay it."""

    base: ObstacleLayer
    solution: Solution
    board: BoardState
    rules: GameRules

    def play_order(self) -> list:
        """The pick order the base forces, as boxes."""
        return [self.solution.order[index] for index in self.base.release.sequence]


def base_of(level, **knobs) -> Floor:
    """Build the floor for a level, so what it is made of can be looked at."""
    options = AutoGenOptions(**knobs)
    board = BoardState.from_pixel_grid(level.pixel_grid)
    rules = GameRules(level.piece * BALLS_PER_BOX, BALLS_PER_BOX)
    solution = solve_order(board, box_multiset(board, BALLS_PER_BOX), rules)
    assert solution is not None, "fixture must be winnable on its own belt"
    base = build_base_grid(
        board=board,
        solution=solution,
        scan=scan_level(level),
        options=options,
        tier_profile=DIFFICULTY_PROFILES[options.difficulty],
        difficulty=options.difficulty,
        rules=rules,
        seed=7,
    )
    return Floor(base, solution, board, rules)


def tunnels_of(level):
    return [cell for cell in level.grid_cells if isinstance(cell, TunnelCellData)]


# --------------------------------------------------------------------------- #
# The fixture is the picture it claims to be
# --------------------------------------------------------------------------- #
def test_the_scattered_fixture_carries_level_15s_own_boxes():
    scan = scan_level(scattered_level())

    assert scan.colors == len(LEVEL_15_BALLS)
    assert scan.painted == sum(LEVEL_15_BALLS.values())
    assert scan.boxes == LEVEL_15_BOXES == 72
    assert dict(scan.histogram) == LEVEL_15_BALLS
    # Every colour is already a whole number of boxes, as the shipped level is.
    assert scan.trimmed_pixels == 0
    # And it does not fit the lattice, so tunnels are forced rather than chosen.
    assert scan.boxes > MAX_BOX_SLOTS * MAX_BOX_SLOTS


def test_the_speckles_break_the_picture_up_without_changing_what_it_holds():
    plain, speckled = scan_level(scattered_level(0)), scan_level(scattered_level(54))

    assert dict(plain.histogram) == dict(speckled.histogram)
    assert speckled.run_count > plain.run_count
    assert speckled.fragmentation > plain.fragmentation
    # Scatter costs conveyor, which is the whole reason it is the hard case.
    assert speckled.demand.peak_balls > plain.demand.peak_balls


# --------------------------------------------------------------------------- #
# Stage 4 is the picture and nothing else
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_the_base_grid_carries_no_mechanic_whatever_the_tier_is(difficulty):
    base = base_of(scattered_level(), difficulty=difficulty).base

    assert not base.hidden and base.hidden_count == 0
    assert not base.linked and base.link_count == 0
    assert not base.arrows and base.arrow_count == 0
    assert base.wanted_window == 1
    assert all(window == 1 for window in base.dig_windows)
    assert base.release.max_dig == 0, "a base tunnel never makes the player dig"


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_the_base_grid_holds_every_box_and_wins_before_any_obstacle(difficulty):
    floor = base_of(scattered_level(), difficulty=difficulty)
    base = floor.base

    assert not base.faults, "the floor has to be playable or there is no level"
    assert len(base.placements) + sum(len(queue) for queue in base.queues) == LEVEL_15_BOXES
    assert 0 < base.played_belt <= floor.rules.belt_slots
    # Replayed in the order the base itself forces, not in the ideal walkthrough.
    assert simulate_order(floor.board, floor.play_order(), floor.rules)
    # A queue that hands each box over exactly when the picture asks for it
    # releases in walkthrough order, so the two are the same play.
    assert floor.play_order() == floor.solution.order


def test_a_picture_too_big_for_the_lattice_overflows_into_tunnels_at_the_base():
    base = base_of(scattered_level(), difficulty=int(LevelDifficulty.Easy)).base
    stored = sum(len(queue) for queue in base.queues)

    assert stored > 0, "72 boxes do not fit 64 slots, so the base must store some"
    assert len(base.placements) <= MAX_BOX_SLOTS * MAX_BOX_SLOTS
    assert base.cols <= MAX_BOX_SLOTS and base.rows <= MAX_BOX_SLOTS


def test_the_base_ignores_the_tunnels_a_designer_asked_for_as_a_mechanic():
    """A typed tunnel count is a request for a mechanic, and the floor has none.

    It matters because the floor is what the run falls back to: if the count that
    made every mechanic layer unplayable were also applied here, there would be
    nothing left to fall back to.
    """
    level = banded_level([0, 1, 2])
    plain = base_of(level, difficulty=int(LevelDifficulty.Hard)).base
    asked = base_of(
        level, difficulty=int(LevelDifficulty.Hard), tunnel_count=2, dig_window=4
    ).base

    assert [len(queue) for queue in asked.queues] == [len(queue) for queue in plain.queues]
    assert asked.wanted_window == 1


# --------------------------------------------------------------------------- #
# What the run reports about its own floor
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_the_run_reports_the_floor_it_certified(difficulty):
    result = auto_generate_boxes(
        scattered_level(), AutoGenOptions(difficulty=difficulty, seed=3)
    )

    assert result.base_surface_boxes + result.base_tunnel_boxes == LEVEL_15_BOXES
    assert 0 < result.base_belt <= result.certified_belt
    # The base releases in walkthrough order, so its peak *is* the walkthrough's -
    # which is what makes it the honest baseline for what the obstacles cost.
    assert result.base_belt == result.walkthrough_belt
    assert result.obstacle_belt_cost == max(0, result.played_belt - result.base_belt)
    assert "Lưới box gốc (chưa obstacle): THẮNG ĐƯỢC" in format_report(
        result, AutoGenOptions(difficulty=difficulty)
    )


@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
def test_a_scattered_level_generates_whole_valid_and_winnable(difficulty):
    """The end of the whole chain, on the picture that motivated it."""
    level = scattered_level()
    result = auto_generate_boxes(level, AutoGenOptions(difficulty=difficulty, seed=3))

    assert result.winnable, "level 15's histogram has to be beatable on piece 5"
    assert result.total_boxes == LEVEL_15_BOXES
    assert result.level.source_histogram() == result.level.target_histogram()
    assert result.valid
    assert result.played_belt <= result.certified_belt
    assert_valid(result.level)


# --------------------------------------------------------------------------- #
# The faults no replay can see
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("difficulty", ALL_DIFFICULTIES)
@pytest.mark.parametrize("colours", [[0, 1], [0, 1, 2], [0, 1, 2, 3]])
def test_no_shipped_tunnel_is_ever_sealed_in(difficulty, colours):
    """The failure the gameplay model cannot see, on the grids that used to have it.

    A tunnel hands its queue out through its mouth, and the simulation taps a
    queue by index without ever asking where the mouth points - so a tunnel
    facing a wall, another tunnel or the edge of the lattice replays as a win and
    is dead in the runtime. Small grids are where it happens, because there is
    nothing else on the side to point at.
    """
    result = auto_generate_boxes(
        banded_level(colours), AutoGenOptions(difficulty=difficulty, seed=4)
    )
    box_slots = {
        (cell.grid_x // SLOT, cell.grid_y // SLOT)
        for cell in result.level.grid_cells
        if not isinstance(cell, TunnelCellData)
    }
    for tunnel in tunnels_of(result.level):
        step = DIRECTION_STEPS[Direction(int(tunnel.direction))]
        front = (tunnel.grid_x // SLOT + step[0], tunnel.grid_y // SLOT + step[1])
        assert front in box_slots, "a tunnel mouth must face a box that can clear"


def test_a_layer_that_cannot_be_played_is_dropped_for_a_gentler_one():
    """SuperHard scatters its tunnels and seals a mouth on a three-box grid.

    The placement is what differs between the forms - SuperHard drops a tunnel
    anywhere in the lattice, the gentler forms park it on the back row - so a
    lattice this small is playable at one form and not at another, which is
    exactly what the ladder exists for.
    """
    result = auto_generate_boxes(
        banded_level([0, 1, 2]),
        AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), seed=1),
    )
    relief = result.obstacle_relief

    assert relief.faulted, "the fixture is only useful if some form faults"
    assert all("tunnel" in " ".join(faults) for _, faults in relief.faulted)
    assert relief.form < relief.difficulty
    assert not result.obstacle_free, "a gentler form was playable, so it shipped"


def test_when_every_form_is_unplayable_the_bare_base_grid_ships():
    """A level with no mechanics beats no level, and beats a broken one.

    Three tunnels asked of a three-box grid: `_tunnel_slots` prefers slots that
    leave every mouth a box to hand its queue to, and a lattice this cramped has
    none, so it seats them anyway and the fault is real at every form.
    """
    result = auto_generate_boxes(
        banded_level([0, 1, 2]),
        AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), tunnel_count=3, seed=4),
    )

    assert result.obstacle_free
    assert result.obstacle_relief.faulted
    assert result.hidden_boxes == 0 and result.arrow_count == 0 and result.link_count == 0
    assert result.tunnel_count == 0
    assert result.winnable and result.valid
    assert_valid(result.level)
    # And the plan says what happened rather than listing mechanics that are not
    # on the grid.
    assert result.obstacle_plan.count == 0
    assert any("không có obstacle nào" in warning for warning in result.warnings)


def test_a_picture_whose_floor_cannot_be_laid_out_fails_loudly():
    """The one case with no fallback: the base itself is unplayable."""
    with pytest.raises(AutoGenError, match="before any obstacle is added|tunnels are disabled"):
        auto_generate_boxes(
            scattered_level(),
            AutoGenOptions(difficulty=int(LevelDifficulty.Easy), allow_tunnels=False),
        )


# --------------------------------------------------------------------------- #
# A tunnel needs a box to hand its queue to, and the placement has to leave one
# --------------------------------------------------------------------------- #
# The regression this pins: an overflowing picture fills the back row with
# tunnels, and the next tunnel used to go into the row in front of it - which is
# the one slot the tunnel behind it was pointing at. That tunnel then had nothing
# but tunnels on every side, `sealed_tunnel_mouths` failed the base grid, and
# because the base grid is the fallback there was nothing left to ship: 81 boxes
# on a 64-slot lattice refused the level outright with "Raise the slot limit or
# use a smaller picture", when the boxes fitted perfectly well.
def _boxy_level(size: int, colors: int = 8) -> PixelLevelData:
    """A picture of whole-box runs, sized to need far more boxes than the lattice.

    Long runs so the conveyor is never the problem - the only thing under test is
    whether that many boxes can be laid out at all.
    """
    color_ids: list[int] = []
    color = 1
    while len(color_ids) < size * size:
        color_ids.extend([color] * BALLS_PER_BOX)
        color = color % colors + 1
    return make_level(color_ids[: size * size], size, size)


def test_tunnels_can_release_spots_a_tunnel_walled_in_by_tunnels():
    """The predicate itself: a chosen set where some tunnel has no free neighbour."""
    # A full back row plus the slot in front of its corner: (0, 2) is boxed in by
    # (1, 2) and (0, 1), both tunnels.
    assert not tunnels_can_release([(0, 2), (1, 2), (0, 1)], 2, 3)
    # Move that third tunnel one row further in and every mouth has a slot again.
    assert tunnels_can_release([(0, 2), (1, 2), (0, 0)], 2, 3)
    # A single tunnel on a lattice with room is always fine.
    assert tunnels_can_release([(0, 2)], 2, 3)


@pytest.mark.parametrize("size", [27, 30, 36, 42])
def test_a_picture_that_overflows_the_lattice_still_lays_out(size):
    """The boxes fit in lattice plus tunnels, so the run has no business refusing."""
    level = _boxy_level(size)
    boxes = sum(level.pixel_grid.histogram().values()) // BALLS_PER_BOX
    assert boxes > MAX_BOX_SLOTS**2, "the fixture has to overflow the lattice"

    result = auto_generate_boxes(
        level, AutoGenOptions(difficulty=int(LevelDifficulty.Medium), seed=7)
    )

    assert result.surface_boxes + result.tunnel_boxes == boxes
    assert result.winnable and result.valid
    assert_valid(result.level)


@pytest.mark.parametrize("size", [27, 30, 36, 42])
def test_every_tunnel_on_an_overflowing_grid_faces_a_real_box(size):
    """The property the placement now keeps, read off the finished layout."""
    result = auto_generate_boxes(
        _boxy_level(size), AutoGenOptions(difficulty=int(LevelDifficulty.Medium), seed=7)
    )
    assert result.tunnel_count, "the fixture has to need tunnels"

    box_slots = {
        (cell.grid_x // SLOT, cell.grid_y // SLOT)
        for cell in result.level.grid_cells
        if not isinstance(cell, TunnelCellData)
    }
    for (slot_x, slot_y), facing in result.tunnel_mouths:
        step = DIRECTION_STEPS[facing]
        assert (slot_x + step[0], slot_y + step[1]) in box_slots, (
            f"tunnel at ({slot_x}, {slot_y}) facing {facing.name} has no box to release into"
        )
