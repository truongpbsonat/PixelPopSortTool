import random

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor, LevelDifficulty, ThemeId
from pixel_level_tool.domain.level_models import BoxCellData, PixelGridData, PixelLevelData
from pixel_level_tool.services.autogen_config import load_autogen_config, save_autogen_config
from pixel_level_tool.services.box_autogen import AutoGenOptions, scan_level
from pixel_level_tool.services.level_serializer import save_level
from pixel_level_tool.ui.dialogs.auto_gen_box_dialog import AutoGenBoxDialog
from pixel_level_tool.ui.main_window import MainWindow


def _noisy_level(width, height, colors, seed) -> PixelLevelData:
    """A picture painted as specks: every tap leaves most of its box on the belt."""
    rng = random.Random(seed)
    ids = [rng.randrange(colors) for _ in range(width * height)]
    return PixelLevelData(pixel_grid=PixelGridData(width, height, ids), level=1, piece=5)


def _banded_level(band_colors, width=3, band_height=3) -> PixelLevelData:
    color_ids = [color for color in band_colors for _ in range(width * band_height)]
    return PixelLevelData(
        pixel_grid=PixelGridData(width, band_height * len(band_colors), color_ids),
        level=4,
    )


def _valid_level(level_number: int, category: int = 0) -> PixelLevelData:
    return PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        level=level_number,
        category=category,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red, 300)],
        pixel_grid=PixelGridData(3, 1, [int(ItemColor.Red)] * 3),
    )


def _preset() -> AutoGenOptions:
    """Every knob off its default, so a prefill that misses one shows up."""
    return AutoGenOptions(
        difficulty=int(LevelDifficulty.Hard),
        max_slot_cols=6,
        max_slot_rows=7,
        hidden_ratio=0.35,
        hidden_boxes=9,
        auto_difficulty=True,
        belt_slots=27,
        active_policy="row0",
        allow_tunnels=True,
        max_tunnels=2,
        tunnel_count=3,
        tunnel_mode="mechanic",
        tunnel_placement="random",
        tunnel_depth=5,
        dig_window=3,
        walls=2,
        use_arrow_lock=True,
        arrow_ratio=0.20,
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
        jam_relief=False,
        repair_picture=False,
        ease_difficulty=1,
        ease_obstacles=2,
        shuffle_attempts=4,
        apply_theme=False,
        seed=4321,
    )


def _window_with_config_folder(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixel_level_tool.services.settings_service.app_data_dir", lambda: tmp_path / "app-data"
    )
    window = MainWindow()
    qtbot.addWidget(window)
    config_dir = tmp_path / "autogen"
    config_dir.mkdir()
    window.settings.set("autogen_config_dir", str(config_dir))
    return window, config_dir


def test_dialog_lists_every_difficulty_and_returns_options(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    assert dialog.difficulty.count() == len(LevelDifficulty)
    assert dialog.difficulty.currentData() == int(LevelDifficulty.Hard)

    options = dialog.options()
    assert options.difficulty == int(LevelDifficulty.Hard)
    assert options.max_slot_cols == 8 and options.max_slot_rows == 8
    assert options.hidden_ratio is None, "Auto defers to the difficulty's hidden share"
    assert options.belt_slots == 0, "Auto means the runtime's thirty-ball conveyor"
    assert options.active_policy == "none", "the level files leave every box inactive"


def test_dialog_shows_the_capacity_of_the_slot_limit(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Easy))
    qtbot.addWidget(dialog)

    dialog.slot_cols.setValue(5)
    dialog.slot_rows.setValue(6)
    text = dialog.capacity_label.text()
    assert "15 x 18" in text and "30 box" in text and "270 ball" in text


def test_dialog_disables_every_tunnel_knob_when_tunnels_are_off(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Easy))
    qtbot.addWidget(dialog)

    dialog.allow_tunnels.setChecked(False)
    for widget in (
        dialog.max_tunnels,
        dialog.tunnel_count,
        dialog.tunnel_mode,
        dialog.tunnel_placement,
        dialog.tunnel_depth,
        dialog.dig_window,
    ):
        assert not widget.isEnabled()
    assert dialog.options().allow_tunnels is False


def test_dialog_defaults_the_tunnel_decision_to_the_difficulty(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    options = dialog.options()
    assert options.tunnel_mode == "auto", "the tier's obstacle budget decides, not the dialog"
    assert options.tunnel_depth == 0 and options.dig_window is None, "Auto defers to the difficulty"


def test_dialog_can_still_pin_tunnels_to_overflow_only(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    dialog.tunnel_mode.setCurrentIndex(dialog.tunnel_mode.findData("overflow"))
    assert dialog.options().tunnel_mode == "overflow"


def test_dialog_can_ask_for_tunnels_as_a_mechanic_with_an_explicit_dig_depth(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    dialog.tunnel_mode.setCurrentIndex(dialog.tunnel_mode.findData("mechanic"))
    dialog.tunnel_depth.setValue(5)
    dialog.dig_window.setValue(3)

    options = dialog.options()
    assert options.tunnel_mode == "mechanic"
    assert options.tunnel_depth == 5
    assert options.dig_window == 3


def test_dialog_defers_the_wall_count_to_the_difficulty_but_can_override_it(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    assert dialog.options().walls is None, "Auto means the difficulty decides"
    dialog.walls.setValue(0)
    assert dialog.options().walls == 0, "0 must switch walls off, not read as Auto"
    dialog.walls.setValue(3)
    assert dialog.options().walls == 3


def test_dialog_hands_both_obstacles_to_the_difficulty_by_default(qtbot):
    """The middle tick state is the default and it means "the tier decides"."""
    dialog = AutoGenBoxDialog(int(LevelDifficulty.SuperHard))
    qtbot.addWidget(dialog)

    options = dialog.options()
    assert options.use_arrow_lock is None
    assert options.use_linked_container is None
    # Auto may still spend them, so their doses stay live rather than greyed out.
    assert dialog.arrow_ratio.isEnabled()
    assert dialog.linked_pairs.isEnabled() and dialog.linked_mode.isEnabled()


def test_unticking_an_obstacle_switches_it_off_and_greys_out_its_knobs(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.SuperHard))
    qtbot.addWidget(dialog)

    dialog.use_arrow_lock.setCheckState(Qt.CheckState.Unchecked)
    dialog.use_linked_container.setCheckState(Qt.CheckState.Unchecked)

    options = dialog.options()
    assert options.use_arrow_lock is False
    assert options.use_linked_container is False
    assert not dialog.arrow_ratio.isEnabled()
    assert not dialog.linked_pairs.isEnabled() and not dialog.linked_mode.isEnabled()


def test_the_obstacle_budget_line_follows_the_difficulty(qtbot):
    """The ceiling applies to every row under it, so it is stated once, up top."""
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Easy))
    qtbot.addWidget(dialog)

    assert "Easy" in dialog.obstacle_budget_label.text()
    assert "1-2 lo\u1ea1i" in dialog.obstacle_budget_label.text()

    dialog.difficulty.setCurrentIndex(dialog.difficulty.findData(int(LevelDifficulty.Hard)))
    assert "Hard" in dialog.obstacle_budget_label.text()
    assert "4-6 lo\u1ea1i" in dialog.obstacle_budget_label.text()


def test_obstacle_relief_is_on_by_default_and_can_be_switched_off(qtbot):
    """A hard picture should get gentler obstacle forms without being asked twice."""
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    assert dialog.obstacle_relief.isChecked()
    assert dialog.options().obstacle_relief is True

    dialog.obstacle_relief.setChecked(False)
    assert dialog.options().obstacle_relief is False


def test_jam_relief_is_on_by_default_and_can_be_switched_off(qtbot):
    """Its own tick because the belt check above cannot reach the case it covers.

    A picture that does not win on the level's own belt refuses nothing, so
    relief never fires on it and the burial would ship at the tier's own form on
    a level nobody can finish.
    """
    dialog = AutoGenBoxDialog(int(LevelDifficulty.SuperHard))
    qtbot.addWidget(dialog)

    assert dialog.jam_relief.isChecked()
    assert dialog.options().jam_relief is True

    dialog.jam_relief.setChecked(False)
    assert dialog.options().jam_relief is False


def test_dialog_enables_the_arrow_and_link_knobs_when_the_obstacle_is_ticked(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    dialog.use_arrow_lock.setChecked(True)
    dialog.use_linked_container.setChecked(True)
    assert dialog.arrow_ratio.isEnabled()
    assert dialog.linked_pairs.isEnabled() and dialog.linked_mode.isEnabled()

    options = dialog.options()
    assert options.use_arrow_lock is True and options.use_linked_container is True
    assert options.arrow_ratio is None, "Auto defers to the difficulty's arrow share"
    assert options.linked_pairs is None, "Auto defers to the difficulty's pair count"
    assert options.linked_mode == "auto", "Auto defers to the difficulty's link feel"


def test_dialog_can_override_the_arrow_share_and_the_link_pairing(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Easy))
    qtbot.addWidget(dialog)

    dialog.use_arrow_lock.setChecked(True)
    dialog.arrow_ratio.setValue(20)
    dialog.use_linked_container.setChecked(True)
    dialog.linked_pairs.setValue(0)
    dialog.linked_mode.setCurrentIndex(dialog.linked_mode.findData("stall"))

    options = dialog.options()
    assert options.arrow_ratio == pytest.approx(0.20)
    assert options.linked_pairs == 0, "0 must switch links off, not read as Auto"
    assert options.linked_mode == "stall"


def test_auto_gen_button_can_generate_both_optional_obstacles(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    # Six bands rather than four: a Hard level links in "stall" mode, which needs
    # two neighbouring boxes the walkthrough wants several picks apart, and a
    # four-band picture is too short to put such a pair side by side.
    window.level = _banded_level(
        [
            int(ItemColor.Red),
            int(ItemColor.Blue),
            int(ItemColor.Green),
            int(ItemColor.Red),
            int(ItemColor.Blue),
            int(ItemColor.Green),
        ],
        width=6,
    )
    window._refresh_all()

    monkeypatch.setattr(AutoGenBoxDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        AutoGenBoxDialog,
        "options",
        lambda self: AutoGenOptions(
            difficulty=int(LevelDifficulty.Hard),
            use_arrow_lock=True,
            use_linked_container=True,
        ),
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kwargs: QMessageBox.Yes))

    window.auto_gen_box_button.click()

    assert window.level.obstacles, "the LinkedContainer obstacles must reach the level"
    assert window.validate().errors == []
    assert "LinkedContainer" in window.mechanics_field.text()

    window.undo_action.trigger()
    assert window.level.obstacles == [], "Auto Gen Box must be a single undoable step"


def test_auto_gen_button_fills_the_box_grid_and_is_undoable(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = _banded_level([int(ItemColor.Red), int(ItemColor.Blue), int(ItemColor.Green)])
    window._refresh_all()
    assert window.level.grid_cells == []

    monkeypatch.setattr(AutoGenBoxDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        AutoGenBoxDialog,
        "options",
        lambda self: AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard)),
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kwargs: QMessageBox.Yes))

    window.auto_gen_box_button.click()

    assert window.level.grid_cells, "the box grid must be filled"
    assert window.level.source_histogram() == window.level.target_histogram()
    assert window.level.grid_cols <= 24 and window.level.grid_rows <= 24
    assert window.level.grid_cols % 3 == 0 and window.level.grid_rows % 3 == 0
    assert window.level.piece >= 1, "piece records the boxes the run really peaked at"
    assert window.level.difficulty == int(LevelDifficulty.SuperHard)
    assert window.level.theme_id == int(ThemeId.SuperHard)
    assert window.validate().errors == []
    assert window.dirty is True

    window.undo_action.trigger()
    assert window.level.grid_cells == [], "Auto Gen Box must be a single undoable step"


def test_the_count_knobs_default_to_auto(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    options = dialog.options()
    assert options.hidden_boxes is None
    assert options.tunnel_count is None
    assert options.arrow_boxes is None


def test_an_exact_count_greys_out_the_share_beside_it(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)
    dialog.use_arrow_lock.setChecked(True)
    assert dialog.hidden_ratio.isEnabled() and dialog.arrow_ratio.isEnabled()

    dialog.hidden_boxes.setValue(4)
    dialog.arrow_boxes.setValue(3)

    assert not dialog.hidden_ratio.isEnabled(), "a count wins, so the share must not look live"
    assert not dialog.arrow_ratio.isEnabled()
    options = dialog.options()
    assert options.hidden_boxes == 4 and options.arrow_boxes == 3


def test_tunnel_placement_defaults_to_the_difficulty_and_lists_every_mode(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    assert dialog.options().tunnel_placement == "auto"
    values = [dialog.tunnel_placement.itemData(i) for i in range(dialog.tunnel_placement.count())]
    assert values == ["auto", "back", "front", "random"]

    dialog.tunnel_placement.setCurrentIndex(dialog.tunnel_placement.findData("front"))
    assert dialog.options().tunnel_placement == "front"


def test_the_tunnel_ceiling_starts_on_auto_so_the_picture_decides(qtbot):
    """A fixed four capped every picture at the same number, big or small."""
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    assert dialog.max_tunnels.value() == 0
    assert dialog.max_tunnels.specialValueText() == "Auto"
    assert dialog.options().max_tunnels == 0


def test_an_exact_tunnel_count_greys_out_the_ceiling(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Easy))
    qtbot.addWidget(dialog)
    assert dialog.max_tunnels.isEnabled()

    dialog.tunnel_count.setValue(2)

    assert not dialog.max_tunnels.isEnabled()
    assert dialog.options().tunnel_count == 2


def test_a_count_back_on_auto_hands_its_share_back(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    dialog.hidden_boxes.setValue(4)
    dialog.hidden_boxes.setValue(-1)

    assert dialog.hidden_ratio.isEnabled()
    assert dialog.options().hidden_boxes is None


def test_zero_is_a_real_answer_for_every_count_knob(qtbot):
    """0 switches the mechanic off; only Auto means "let the difficulty decide"."""
    dialog = AutoGenBoxDialog(int(LevelDifficulty.SuperHard))
    qtbot.addWidget(dialog)
    dialog.use_arrow_lock.setChecked(True)

    dialog.hidden_boxes.setValue(0)
    dialog.tunnel_count.setValue(0)
    dialog.arrow_boxes.setValue(0)

    options = dialog.options()
    assert options.hidden_boxes == 0
    assert options.tunnel_count == 0
    assert options.arrow_boxes == 0


def test_dialog_prefilled_from_a_preset_hands_the_same_options_back(qtbot):
    preset = _preset()

    dialog = AutoGenBoxDialog(int(LevelDifficulty.Easy), options=preset)
    qtbot.addWidget(dialog)

    assert dialog.options() == preset, "every knob must survive the trip through the widgets"
    assert dialog.difficulty.currentData() == int(LevelDifficulty.Hard), (
        "a saved preset outranks the difficulty of the level in hand"
    )
    assert dialog.arrow_boxes.isEnabled() and dialog.linked_pairs.isEnabled(), (
        "a preset that switches an obstacle on must unlock its knobs too"
    )
    assert not dialog.arrow_ratio.isEnabled(), (
        "this preset carries an exact arrow count, which outranks the share"
    )


def test_dialog_seed_is_auto_until_a_preset_brings_one(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Easy))
    qtbot.addWidget(dialog)

    assert dialog.seed.value() == -1 and dialog.options().seed is None

    dialog.set_options(AutoGenOptions(seed=99))
    assert dialog.options().seed == 99


def test_saving_a_generated_level_writes_its_autogen_preset(qtbot, monkeypatch, tmp_path):
    window, config_dir = _window_with_config_folder(qtbot, monkeypatch, tmp_path)
    window.level = _banded_level(
        [int(ItemColor.Red), int(ItemColor.Blue), int(ItemColor.Green)], width=6
    )
    window.level.level = 8
    window._refresh_all()
    monkeypatch.setattr(AutoGenBoxDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        AutoGenBoxDialog,
        "options",
        lambda self: AutoGenOptions(difficulty=int(LevelDifficulty.Hard), use_arrow_lock=True),
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kwargs: QMessageBox.Yes))

    window.auto_gen_box_button.click()
    assert window._save_to_path(tmp_path / "8.json")

    saved = load_autogen_config(config_dir, 8)
    assert saved is not None, "Save must drop genlv8.json next to the other presets"
    assert saved.difficulty == int(LevelDifficulty.Hard) and saved.use_arrow_lock is True
    assert saved.seed is not None, "the seed of that run is what makes the grid reproducible"


def test_opening_a_level_loads_the_preset_that_belongs_to_it(qtbot, monkeypatch, tmp_path):
    window, config_dir = _window_with_config_folder(qtbot, monkeypatch, tmp_path)
    save_autogen_config(config_dir, 7, 0, _preset())
    level_path = tmp_path / "7.json"
    save_level(level_path, _valid_level(7))

    assert window._load_path(level_path)

    assert window.autogen_options == _preset()
    dialog = AutoGenBoxDialog(window.level.difficulty, window, options=window.autogen_options)
    qtbot.addWidget(dialog)
    assert dialog.options().seed == 4321, "the dialog opens on the seed that built this level"


def test_opening_a_level_without_a_preset_drops_the_previous_one(qtbot, monkeypatch, tmp_path):
    window, config_dir = _window_with_config_folder(qtbot, monkeypatch, tmp_path)
    save_autogen_config(config_dir, 7, 0, _preset())
    save_level(tmp_path / "7.json", _valid_level(7))
    save_level(tmp_path / "9.json", _valid_level(9))

    assert window._load_path(tmp_path / "7.json")
    assert window.autogen_options is not None
    assert window._load_path(tmp_path / "9.json")

    assert window.autogen_options is None, "level 9 must not inherit level 7's config"


def test_a_level_save_still_succeeds_when_no_config_folder_is_picked(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixel_level_tool.services.settings_service.app_data_dir", lambda: tmp_path / "app-data"
    )
    monkeypatch.setattr(
        "pixel_level_tool.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: "",
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = _valid_level(7)
    window.autogen_options = AutoGenOptions()

    assert window._save_to_path(tmp_path / "7.json"), "a declined folder must not fail the save"
    assert list(tmp_path.glob("genlv*.json")) == []


def test_the_config_folder_is_asked_for_once_and_then_remembered(qtbot, monkeypatch, tmp_path):
    config_dir = tmp_path / "autogen"
    config_dir.mkdir()
    asked = []
    monkeypatch.setattr(
        "pixel_level_tool.services.settings_service.app_data_dir", lambda: tmp_path / "app-data"
    )
    monkeypatch.setattr(
        "pixel_level_tool.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: (asked.append(1), str(config_dir))[1],
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = _valid_level(7)
    window.autogen_options = AutoGenOptions(seed=5)

    assert window._save_to_path(tmp_path / "7.json")
    assert window._save_to_path(tmp_path / "7.json")

    assert asked == [1], "the folder is a one-time choice, not a prompt on every save"
    assert load_autogen_config(config_dir, 7).seed == 5


def test_auto_gen_reports_a_failure_without_touching_the_level(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = PixelLevelData(pixel_grid=PixelGridData(3, 3))  # nothing painted
    window._refresh_all()

    messages = []
    monkeypatch.setattr(AutoGenBoxDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        QMessageBox, "critical", staticmethod(lambda parent, title, text: messages.append(text))
    )

    window.auto_gen_box_button.click()

    assert messages and "Paint the pixel grid" in messages[0]
    assert window.level.grid_cells == []
    assert not window.commands.can_undo


# --------------------------------------------------------------------------- #
# The report lives in a tab, not in a modal
# --------------------------------------------------------------------------- #
def test_the_report_lands_in_its_own_tab_and_that_tab_is_raised(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = _banded_level([int(ItemColor.Red), int(ItemColor.Blue), int(ItemColor.Green)])
    window._refresh_all()
    assert window.autogen_report_panel.report == "", "nothing generated yet"

    monkeypatch.setattr(AutoGenBoxDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        AutoGenBoxDialog,
        "options",
        lambda self: AutoGenOptions(difficulty=int(LevelDifficulty.Easy)),
    )
    # No message box is patched: the report must not be shown as one any more.
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    window.auto_gen_box_button.click()

    report = window.autogen_report_panel.report
    assert "Độ khó" in report and "Số box" in report
    assert window.side_tabs.currentWidget() is window.autogen_report_panel


def test_a_level_that_cannot_be_finished_says_so_on_the_report_banner(qtbot, monkeypatch):
    """The jam has to be the first thing read, not the thirteenth number on the page."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = _noisy_level(12, 12, 10, seed=7)
    window._refresh_all()

    monkeypatch.setattr(AutoGenBoxDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        AutoGenBoxDialog, "options", lambda self: AutoGenOptions(repair_picture=False)
    )
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    # A modal would be gone the moment it is dismissed, which is the opposite of
    # what a note about the level in hand is for.
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: pytest.fail("no modal here"))
    )

    window.auto_gen_box_button.click()

    banner = window.autogen_report_panel.alert
    assert "CHƯA THẮNG ĐƯỢC" in banner
    assert "hàng" in banner and "cột" in banner, "the banner has to name the cell"
    assert "piece" in banner
    assert "KẸT tại pixel thứ" in window.autogen_report_panel.report, "detail stays in the body"


def test_a_level_that_plays_out_leaves_the_banner_off(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = _banded_level([int(ItemColor.Red), int(ItemColor.Blue), int(ItemColor.Green)])
    window._refresh_all()

    monkeypatch.setattr(AutoGenBoxDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(AutoGenBoxDialog, "options", lambda self: AutoGenOptions())
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    window.auto_gen_box_button.click()

    assert window.autogen_report_panel.alert == ""


def test_the_dialog_opens_no_taller_than_the_screen(qtbot):
    """The form is long; a screen is not. It scrolls rather than growing past one."""
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)
    dialog.show()

    available = dialog.screen().availableGeometry()
    assert dialog.height() <= available.height()
    assert dialog.width() <= available.width()


def test_the_scan_panel_stays_short_enough_to_sit_above_the_knobs(qtbot):
    """Six lines is the budget: past that the panel pushes the form off screen."""
    level = _noisy_level(12, 12, 10, seed=7)
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard), scan=scan_level(level))
    qtbot.addWidget(dialog)

    assert len(dialog.scan_label.text().splitlines()) <= 6


def test_opening_another_level_drops_a_report_that_is_no_longer_about_it(qtbot, tmp_path):
    """A report about the grid of a level that is no longer open is just wrong."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.autogen_report_panel.set_report("báo cáo của level cũ")
    save_level(tmp_path / "7.json", _valid_level(7))

    assert window._load_path(tmp_path / "7.json")

    assert window.autogen_report_panel.report == ""
