import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDialog, QMessageBox

from pixel_level_tool.domain.enums import ItemColor, LevelDifficulty, ThemeId
from pixel_level_tool.domain.level_models import PixelGridData, PixelLevelData
from pixel_level_tool.services.box_autogen import AutoGenOptions
from pixel_level_tool.ui.dialogs.auto_gen_box_dialog import AutoGenBoxDialog
from pixel_level_tool.ui.main_window import MainWindow


def _banded_level(band_colors, width=3, band_height=3) -> PixelLevelData:
    color_ids = [color for color in band_colors for _ in range(width * band_height)]
    return PixelLevelData(
        pixel_grid=PixelGridData(width, band_height * len(band_colors), color_ids),
        level=4,
    )


def test_dialog_lists_every_difficulty_and_returns_options(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    assert dialog.difficulty.count() == len(LevelDifficulty)
    assert dialog.difficulty.currentData() == int(LevelDifficulty.Hard)

    options = dialog.options()
    assert options.difficulty == int(LevelDifficulty.Hard)
    assert options.max_slot_cols == 8 and options.max_slot_rows == 8
    assert options.hidden_ratio is None, "Auto defers to the difficulty's hidden share"
    assert options.tray_slots == 0, "Auto means piece 5 unless the picture needs more"
    assert options.active_policy == "none", "the level files leave every box inactive"


def test_dialog_shows_the_capacity_of_the_slot_limit(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Easy))
    qtbot.addWidget(dialog)

    dialog.slot_cols.setValue(5)
    dialog.slot_rows.setValue(6)
    text = dialog.capacity_label.text()
    assert "15 x 18" in text and "30 boxes" in text and "270 balls" in text


def test_dialog_disables_every_tunnel_knob_when_tunnels_are_off(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Easy))
    qtbot.addWidget(dialog)

    dialog.allow_tunnels.setChecked(False)
    for widget in (dialog.max_tunnels, dialog.tunnel_mode, dialog.tunnel_depth, dialog.dig_window):
        assert not widget.isEnabled()
    assert dialog.options().allow_tunnels is False


def test_dialog_defaults_to_tunnels_only_on_overflow(qtbot):
    dialog = AutoGenBoxDialog(int(LevelDifficulty.Hard))
    qtbot.addWidget(dialog)

    options = dialog.options()
    assert options.tunnel_mode == "overflow", "a picture that fits gets no tunnel unasked"
    assert options.tunnel_depth == 0 and options.dig_window is None, "Auto defers to the difficulty"


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
    assert window.level.piece == 5
    assert window.level.difficulty == int(LevelDifficulty.SuperHard)
    assert window.level.theme_id == int(ThemeId.SuperHard)
    assert window.validate().errors == []
    assert window.dirty is True

    window.undo_action.trigger()
    assert window.level.grid_cells == [], "Auto Gen Box must be a single undoable step"


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
