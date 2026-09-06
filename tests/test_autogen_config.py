import json

import pytest

from pixel_level_tool.services.autogen_config import (
    CONFIG_VERSION,
    AutoGenConfigError,
    config_file_name,
    load_autogen_config,
    options_from_document,
    options_to_document,
    save_autogen_config,
)
from pixel_level_tool.services.box_autogen import AutoGenOptions


def _tuned() -> AutoGenOptions:
    """Every knob moved off its default, so a round trip that drops one shows up."""
    return AutoGenOptions(
        difficulty=3,
        max_slot_cols=6,
        max_slot_rows=7,
        hidden_ratio=0.35,
        hidden_boxes=9,
        auto_difficulty=True,
        belt_slots=27,
        active_policy="row0",
        allow_tunnels=False,
        max_tunnels=2,
        tunnel_count=3,
        tunnel_mode="mechanic",
        tunnel_placement="front",
        tunnel_depth=5,
        dig_window=3,
        walls=2,
        use_arrow_lock=True,
        arrow_ratio=0.2,
        arrow_boxes=5,
        use_linked_container=True,
        linked_pairs=4,
        linked_mode="stall",
        frozen_boxes=6,
        blocks=3,
        lock_margin=45,
        lock_rounding="five",
        shuffle_obstacles=False,
        obstacle_relief=False,
        repair_picture=False,
        ease_difficulty=1,
        ease_obstacles=2,
        shuffle_attempts=4,
        apply_theme=False,
        seed=4321,
    )


def test_the_file_name_mirrors_the_level_file_it_belongs_to():
    assert config_file_name(1) == "genlv1.json"
    assert config_file_name(44) == "genlv44.json"
    assert config_file_name(1, 2) == "genlv1.2.json", "the category variant keeps its suffix"


def test_every_knob_survives_a_round_trip_through_disk(tmp_path):
    options = _tuned()

    path = save_autogen_config(tmp_path, 7, 0, options)

    assert path == tmp_path / "genlv7.json"
    assert load_autogen_config(tmp_path, 7) == options


def test_the_document_records_which_level_it_belongs_to(tmp_path):
    save_autogen_config(tmp_path, 12, 3, AutoGenOptions())

    document = json.loads((tmp_path / "genlv12.3.json").read_text(encoding="utf-8"))
    assert document["level"] == 12 and document["category"] == 3
    assert document["version"] == CONFIG_VERSION


def test_a_preset_written_before_auto_existed_hands_the_tunnel_ceiling_back(tmp_path):
    """The old fixed 4 was the dialog's default, not a number anyone chose."""
    document = options_to_document(AutoGenOptions(), level=3)
    document["version"] = 3
    document["maxTunnels"] = 4

    assert options_from_document(document).max_tunnels == 0, "reads as Auto"


def test_a_ceiling_saved_by_this_version_is_a_decision_and_stands(tmp_path):
    document = options_to_document(AutoGenOptions(max_tunnels=4), level=3)

    assert options_from_document(document).max_tunnels == 4


def test_auto_knobs_stay_null_rather_than_collapsing_to_zero(tmp_path):
    """None means "the difficulty decides"; 0 means "switch it off". Never confuse them."""
    save_autogen_config(tmp_path, 1, 0, AutoGenOptions(hidden_ratio=None, walls=None, seed=None))

    document = json.loads((tmp_path / "genlv1.json").read_text(encoding="utf-8"))
    assert document["hiddenRatio"] is None and document["walls"] is None and document["seed"] is None

    loaded = load_autogen_config(tmp_path, 1)
    assert loaded.hidden_ratio is None and loaded.walls is None and loaded.seed is None


def test_the_two_obstacle_toggles_keep_their_third_state(tmp_path):
    """null is "the difficulty decides", which is what a fresh preset carries.

    Reading it back as False would quietly switch both mechanics off for every
    level that was saved before the designer ever touched those boxes.
    """
    save_autogen_config(tmp_path, 2, 0, AutoGenOptions())

    document = json.loads((tmp_path / "genlv2.json").read_text(encoding="utf-8"))
    assert document["useArrowLock"] is None and document["useLinkedContainer"] is None

    restored = load_autogen_config(tmp_path, 2)
    assert restored.use_arrow_lock is None and restored.use_linked_container is None

    for value in (True, False):
        save_autogen_config(
            tmp_path, 3, 0, AutoGenOptions(use_arrow_lock=value, use_linked_container=value)
        )
        restored = load_autogen_config(tmp_path, 3)
        assert restored.use_arrow_lock is value and restored.use_linked_container is value


def test_a_zero_knob_is_read_back_as_zero_not_as_auto(tmp_path):
    save_autogen_config(tmp_path, 1, 0, AutoGenOptions(walls=0, linked_pairs=0, seed=0))

    loaded = load_autogen_config(tmp_path, 1)
    assert loaded.walls == 0 and loaded.linked_pairs == 0 and loaded.seed == 0


def test_a_level_without_a_preset_reads_as_none(tmp_path):
    assert load_autogen_config(tmp_path, 99) is None


def test_a_missing_key_keeps_its_default_and_an_unknown_key_is_ignored():
    options = options_from_document({"difficulty": 3, "somethingNewLater": 5})

    assert options.difficulty == 3
    assert options.max_slot_cols == AutoGenOptions().max_slot_cols


def test_a_hand_edited_file_with_the_wrong_type_names_the_key(tmp_path):
    (tmp_path / "genlv1.json").write_text('{"walls": "two"}', encoding="utf-8")

    with pytest.raises(AutoGenConfigError) as error:
        load_autogen_config(tmp_path, 1)
    assert "walls" in str(error.value)


def test_broken_json_is_reported_against_the_file(tmp_path):
    (tmp_path / "genlv1.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(AutoGenConfigError) as error:
        load_autogen_config(tmp_path, 1)
    assert "genlv1.json" in str(error.value)


def test_a_tick_mark_where_a_count_belongs_is_rejected():
    with pytest.raises(AutoGenConfigError):
        options_from_document({"maxTunnels": True})


def test_saving_twice_overwrites_rather_than_piling_up(tmp_path):
    save_autogen_config(tmp_path, 5, 0, AutoGenOptions(difficulty=1))
    save_autogen_config(tmp_path, 5, 0, AutoGenOptions(difficulty=4))

    assert load_autogen_config(tmp_path, 5).difficulty == 4
    assert [path.name for path in tmp_path.iterdir()] == ["genlv5.json"]


def test_the_document_keys_are_camel_case_like_the_level_files():
    document = options_to_document(_tuned(), level=1)

    assert "maxSlotCols" in document and "useArrowLock" in document
    assert not any(key.islower() and "_" in key for key in document)
