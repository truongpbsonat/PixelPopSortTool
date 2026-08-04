from __future__ import annotations

"""Auto Gen Box: the two opt-in obstacles, ArrowLock and LinkedContainer.

Both mechanics are a per-level choice rather than a difficulty side effect, so the
first thing checked here is that nothing appears unless it was asked for. After
that the tests split along the two ways each mechanic can be got wrong:

* an **ArrowLock** whose arrow points at a wall, at a tunnel or off the grid can
  never be opened, and one whose key box is opened *after* it makes the certified
  walkthrough illegal;
* a **LinkedContainer** drops two boxes on one tap, so it needs two free tray
  slots at that instant, and the validator additionally rejects a pair whose two
  halves do not look alike or that targets an arrow-locked box.
"""

import pytest

from pixel_level_tool.domain.enums import LevelDifficulty
from pixel_level_tool.domain.level_models import (
    ArrowLockCellEffectData,
    HiddenCellEffectData,
    LinkedContainerObstacleData,
    PixelLevelData,
    TunnelCellData,
)
from pixel_level_tool.services.box_autogen import (
    ARROW_BOX_BUDGET,
    DIFFICULTY_PROFILES,
    DIRECTION_STEPS,
    LINK_BOX_BUDGET,
    MIN_STALL_GAP,
    SLOT,
    AutoGenError,
    AutoGenOptions,
    auto_generate_boxes,
    format_report,
    plan_arrow_count,
    plan_link_count,
)
from pixel_level_tool.services.level_serializer import dumps_level, level_from_dict, level_to_dict
from pixel_level_tool.services.level_validator import LevelValidator
from pixel_level_tool.services.mechanics_scanner import MechanicsScanner
from pixel_level_tool.services.pixel_gameplay import (
    BoardState,
    BoxSpec,
    GameRules,
    GameplayError,
    resolve_link_groups,
    simulate_groups,
    simulate_order,
)
from tests.test_box_autogen import (
    ALL_DIFFICULTIES,
    assert_valid,
    banded_level,
    level_10,
    noisy_level,
    surface_boxes,
)


BOTH_OBSTACLES = {"use_arrow_lock": True, "use_linked_container": True}


def link_pairs(level: PixelLevelData) -> list[tuple]:
    """Every LinkedContainer as the pair of boxes it actually targets."""
    by_uid = {cell.internal_uid: cell for cell in level.grid_cells}
    pairs = []
    for obstacle in level.obstacles:
        assert isinstance(obstacle, LinkedContainerObstacleData)
        assert len(set(obstacle.target_uids)) == 2
        pairs.append(tuple(by_uid[uid] for uid in obstacle.target_uids))
    return pairs


def arrow_boxes(level: PixelLevelData) -> list:
    return [cell for cell in surface_boxes(level) if cell.has_effect(ArrowLockCellEffectData)]


def arrow_direction(cell):
    return next(
        effect.required_direction
        for effect in cell.effects
        if isinstance(effect, ArrowLockCellEffectData)
    )


def test_neither_obstacle_appears_unless_it_is_asked_for():
    """Both mechanics are a per-level choice, so the default has to be off."""
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(level_10(), AutoGenOptions(difficulty=difficulty))
        assert result.level.obstacles == []
        assert arrow_boxes(result.level) == []
        assert result.arrow_locks == [] and result.linked_pairs == []


# --------------------------------------------------------------------------- #
# LinkedContainer
# --------------------------------------------------------------------------- #
def test_linked_containers_are_generated_and_validate():
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(
            level_10(), AutoGenOptions(difficulty=difficulty, use_linked_container=True)
        )
        assert result.link_count, f"difficulty {difficulty} generated no link at all"
        assert len(result.level.obstacles) == result.link_count
        assert_valid(result.level)


def test_a_linked_pair_ties_two_boxes_that_sit_side_by_side():
    """The obstacle draws a bar between the two boxes, so they have to touch."""
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.Hard), use_linked_container=True),
    )
    for left, right in link_pairs(result.level):
        distance = abs(left.grid_x - right.grid_x) + abs(left.grid_y - right.grid_y)
        assert distance == SLOT, (
            f"({left.grid_x}, {left.grid_y}) is not beside ({right.grid_x}, {right.grid_y})"
        )


def test_no_box_belongs_to_two_linked_containers():
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), use_linked_container=True),
    )
    uids = [uid for obstacle in result.level.obstacles for uid in obstacle.target_uids]
    assert len(uids) == len(set(uids))


def test_a_linked_pair_never_mixes_a_hidden_box_with_a_visible_one():
    """The validator rejects that pair, because the two halves must look alike."""
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), use_linked_container=True),
    )
    assert result.hidden_boxes, "this difficulty is supposed to hide most of the grid"
    for left, right in link_pairs(result.level):
        assert left.has_effect(HiddenCellEffectData) == right.has_effect(HiddenCellEffectData)


def test_a_linked_box_never_also_carries_an_arrow_lock():
    """LinkedContainer cannot target an ArrowLock box, so the two must not overlap."""
    result = auto_generate_boxes(
        level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Hard), **BOTH_OBSTACLES)
    )
    assert result.link_count and result.arrow_count
    for left, right in link_pairs(result.level):
        assert not left.has_effect(ArrowLockCellEffectData)
        assert not right.has_effect(ArrowLockCellEffectData)
    assert_valid(result.level)


def test_easy_links_two_boxes_the_board_wants_almost_at_once():
    """The easy link is a freebie: both colors drain the moment they arrive."""
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.Easy), use_linked_container=True),
    )
    assert result.linked_mode == "sync"
    assert result.max_link_gap < MIN_STALL_GAP


def test_hard_deliberately_links_a_wanted_box_to_one_needed_much_later():
    """The hard link is the point of the mechanic: the partner squats in the tray."""
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.Hard), use_linked_container=True),
    )
    assert result.linked_mode == "stall"
    assert result.max_link_gap >= MIN_STALL_GAP
    assert all(gap >= MIN_STALL_GAP for _, _, gap in result.linked_pairs)


def test_the_linked_mode_can_be_forced_against_the_difficulty():
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(
            difficulty=int(LevelDifficulty.SuperHard),
            use_linked_container=True,
            linked_mode="sync",
        ),
    )
    assert result.linked_mode == "sync"
    assert result.max_link_gap < MIN_STALL_GAP


def test_a_level_with_links_is_still_winnable_with_its_piece():
    """Two boxes on one tap need two free tray slots at that instant, not one."""
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(
            level_10(), AutoGenOptions(difficulty=difficulty, use_linked_container=True)
        )
        board = BoardState.from_pixel_grid(result.level.pixel_grid)
        assert simulate_groups(board, result.play_groups_specs, GameRules(result.level.piece))


def test_link_count_is_capped_by_the_number_of_boxes():
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    assert plan_link_count(
        30, AutoGenOptions(use_linked_container=True, linked_pairs=99), profile
    ) == 30 // LINK_BOX_BUDGET
    assert plan_link_count(30, AutoGenOptions(linked_pairs=4), profile) == 0, "off unless asked"
    assert plan_link_count(30, AutoGenOptions(use_linked_container=True, linked_pairs=0), profile) == 0


def test_a_negative_link_count_is_rejected():
    with pytest.raises(AutoGenError, match="Linked pair count cannot be negative"):
        auto_generate_boxes(level_10(), AutoGenOptions(linked_pairs=-2))


def test_an_unknown_linked_mode_is_rejected():
    with pytest.raises(AutoGenError, match="Unsupported linked container mode"):
        auto_generate_boxes(level_10(), AutoGenOptions(linked_mode="nonsense"))


def test_asking_for_links_a_picture_cannot_carry_only_warns():
    """Two boxes in a column leave no pair the tray survives, and that is not an error."""
    result = auto_generate_boxes(banded_level([0, 1]), AutoGenOptions(use_linked_container=True))
    assert result.link_count == 0
    assert result.level.obstacles == []
    assert any("LinkedContainer" in warning for warning in result.warnings)
    assert_valid(result.level)


def test_resolve_link_groups_folds_the_partner_forward():
    assert resolve_link_groups([0, 1, 2, 3], [(1, 3)]) == [[0], [1, 3], [2]]
    assert resolve_link_groups([3, 2, 1, 0], [(1, 3)]) == [[3, 1], [2], [0]]
    assert resolve_link_groups([0, 1, 2], []) == [[0], [1], [2]]


def test_resolve_link_groups_rejects_a_box_linked_twice():
    with pytest.raises(GameplayError, match="more than one LinkedContainer"):
        resolve_link_groups([0, 1, 2], [(0, 1), (1, 2)])


def test_resolve_link_groups_rejects_a_box_linked_to_itself():
    with pytest.raises(GameplayError, match="link box 1 to itself"):
        resolve_link_groups([0, 1], [(1, 1)])


def test_a_group_of_two_needs_two_free_tray_slots_at_once():
    """The player never gets the pause where the first box drains before the second lands."""
    board = BoardState.from_pixel_grid(banded_level([0, 1]).pixel_grid)
    assert simulate_order(board, [BoxSpec(0, 9), BoxSpec(1, 9)], GameRules(1))
    assert not simulate_groups(board, [[BoxSpec(0, 9), BoxSpec(1, 9)]], GameRules(1))
    assert simulate_groups(board, [[BoxSpec(0, 9), BoxSpec(1, 9)]], GameRules(2))


# --------------------------------------------------------------------------- #
# ArrowLock
# --------------------------------------------------------------------------- #
def test_arrow_locks_are_generated_and_validate():
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(
            level_10(), AutoGenOptions(difficulty=difficulty, use_arrow_lock=True)
        )
        assert result.arrow_count, f"difficulty {difficulty} generated no arrow lock at all"
        assert len(arrow_boxes(result.level)) == result.arrow_count
        assert_valid(result.level)


def test_an_arrow_always_points_at_a_real_box_right_next_to_it():
    """Pointing at a wall, at a tunnel or off the grid would leave the lock keyless."""
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(
            level_10(),
            AutoGenOptions(difficulty=difficulty, use_arrow_lock=True, tunnel_mode="mechanic"),
        )
        assert result.tunnel_count, "tunnel_mode='mechanic' must plant a tunnel to dodge"
        anchors = {(cell.grid_x, cell.grid_y): cell for cell in result.level.grid_cells}
        for cell in arrow_boxes(result.level):
            dx, dy = DIRECTION_STEPS[arrow_direction(cell)]
            key = anchors.get((cell.grid_x + dx * SLOT, cell.grid_y + dy * SLOT))
            assert key is not None, (
                f"box at ({cell.grid_x}, {cell.grid_y}) points "
                f"{arrow_direction(cell).name} at nothing openable"
            )
            assert not isinstance(key, TunnelCellData), "a tunnel is not a key"


def test_an_arrow_never_points_at_a_wall_slot():
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), use_arrow_lock=True),
    )
    assert result.wall_slots, "SuperHard is supposed to reserve a few walls"
    walls = set(result.wall_slots)
    for slot, _, key, _ in result.arrow_locks:
        assert slot not in walls and key not in walls


def test_the_key_of_every_arrow_lock_is_opened_before_it():
    """Otherwise the certified walkthrough is illegal and nothing has been proven."""
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(
            level_10(), AutoGenOptions(difficulty=difficulty, **BOTH_OBSTACLES)
        )
        assert result.arrow_count
        for slot, _, key, wait in result.arrow_locks:
            assert slot != key
            assert wait >= 1, f"the key of the box at {slot} is not opened first"
        assert result.max_arrow_wait >= 1


def test_no_arrow_lock_is_itself_the_key_of_another_one():
    """A chain of locks reads as a broken level rather than as difficulty."""
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), use_arrow_lock=True),
    )
    locked = {slot for slot, _, _, _ in result.arrow_locks}
    keys = {key for _, _, key, _ in result.arrow_locks}
    assert not (locked & keys)


def test_a_hidden_box_never_also_carries_an_arrow_lock():
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), use_arrow_lock=True),
    )
    assert result.hidden_boxes and result.arrow_count
    for cell in arrow_boxes(result.level):
        assert not cell.has_effect(HiddenCellEffectData)


def test_an_arrow_locked_box_never_starts_active():
    result = auto_generate_boxes(
        level_10(),
        AutoGenOptions(
            difficulty=int(LevelDifficulty.Hard), use_arrow_lock=True, active_policy="all"
        ),
    )
    assert result.arrow_count
    assert all(not cell.is_active for cell in arrow_boxes(result.level))


def test_arrow_locks_stay_rarer_at_easy_than_at_super_hard():
    """Arrow is a hard mechanic, so even switched on it starts as a light touch."""
    shares = []
    for difficulty in ALL_DIFFICULTIES:
        result = auto_generate_boxes(
            level_10(), AutoGenOptions(difficulty=difficulty, use_arrow_lock=True)
        )
        shares.append(result.arrow_count / result.surface_boxes)
    assert shares[0] < shares[-1]
    assert shares[0] <= 0.10


def test_arrow_count_is_capped_by_the_number_of_boxes():
    profile = DIFFICULTY_PROFILES[int(LevelDifficulty.Hard)]
    assert plan_arrow_count(
        30, AutoGenOptions(use_arrow_lock=True, arrow_ratio=1.0), profile
    ) == 30 // ARROW_BOX_BUDGET
    assert plan_arrow_count(30, AutoGenOptions(arrow_ratio=1.0), profile) == 0, "off unless asked"
    assert plan_arrow_count(30, AutoGenOptions(use_arrow_lock=True, arrow_ratio=0.0), profile) == 0


def test_an_out_of_range_arrow_ratio_is_rejected():
    with pytest.raises(AutoGenError, match="Arrow lock ratio must be between 0 and 1"):
        auto_generate_boxes(level_10(), AutoGenOptions(arrow_ratio=1.5))


def test_asking_for_arrows_a_picture_cannot_carry_only_warns():
    """Two boxes stacked in one column leave no earlier neighbour to be the key."""
    result = auto_generate_boxes(banded_level([0, 1]), AutoGenOptions(use_arrow_lock=True))
    assert result.arrow_count == 0
    assert any("ArrowLock" in warning for warning in result.warnings)
    assert_valid(result.level)


# --------------------------------------------------------------------------- #
# Both at once
# --------------------------------------------------------------------------- #
def test_both_obstacles_survive_a_round_trip_through_json():
    result = auto_generate_boxes(
        level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Hard), **BOTH_OBSTACLES)
    )
    level = result.level
    level.assign_deterministic_ids()
    restored = level_from_dict(level_to_dict(level))

    assert len(restored.obstacles) == result.link_count
    assert len(arrow_boxes(restored)) == result.arrow_count
    assert {frozenset((left.id, right.id)) for left, right in link_pairs(level)} == {
        frozenset((left.id, right.id)) for left, right in link_pairs(restored)
    }
    assert LevelValidator().validate(restored).errors == []
    document = dumps_level(level)
    assert "LinkedContainer" in document and "ArrowLock" in document


def test_the_mechanics_scanner_discovers_both_obstacles():
    result = auto_generate_boxes(
        level_10(), AutoGenOptions(difficulty=int(LevelDifficulty.Hard), **BOTH_OBSTACLES)
    )
    mechanics = MechanicsScanner().scan(result.level)
    assert "ArrowLock" in mechanics and "LinkedContainer" in mechanics


def test_the_report_explains_both_obstacles():
    options = AutoGenOptions(difficulty=int(LevelDifficulty.Hard), **BOTH_OBSTACLES)
    report = format_report(auto_generate_boxes(level_10(), options), options)
    assert "LinkedContainer" in report and "stall" in report
    assert "ArrowLock" in report and "slot chìa" in report


def test_both_obstacles_hold_up_on_noisy_pictures():
    for seed in range(4):
        level = noisy_level(9, 9, 4, seed)
        for difficulty in ALL_DIFFICULTIES:
            result = auto_generate_boxes(
                level.clone(), AutoGenOptions(difficulty=difficulty, **BOTH_OBSTACLES)
            )
            assert_valid(result.level)
            board = BoardState.from_pixel_grid(result.level.pixel_grid)
            assert simulate_groups(board, result.play_groups_specs, GameRules(result.level.piece))
