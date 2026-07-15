import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDialog

from pixel_level_tool.domain.enums import CellShape, Direction, EMPTY_COLOR_ID, ItemColor
from pixel_level_tool.domain.level_models import BoxCellData, PixelGridData, PixelLevelData
from pixel_level_tool.ui.main_window import MainWindow


def test_main_window_smoke(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.new_action is not None
    assert window.open_action is not None
    assert window.save_action is not None
    assert window.import_legacy_button is not None
    assert window.trim_empty_button is not None
    assert window.replace_color_button is not None
    assert window.box_editor is not None
    assert window.pixel_editor is not None
    assert not hasattr(window, "level_grid_version_spin")
    assert not hasattr(window, "category_spin")
    assert window.box_editor.minimumWidth() == 0
    assert window.pixel_editor.minimumWidth() == 0
    assert "Cargo" not in window.windowTitle()
    window.close()


def test_pixel_tool_buttons_show_active_mode(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.pixel_editor.mode == "paint"
    assert window.paint_button.isChecked()

    window.erase_button.click()

    assert window.pixel_editor.mode == "erase"
    assert window.erase_button.isChecked()
    assert not window.paint_button.isChecked()

    window.eyedropper_button.click()

    assert window.pixel_editor.mode == "eyedropper"
    assert window.eyedropper_button.isChecked()
    assert not window.erase_button.isChecked()
    window.close()


def test_resize_pixel_grid_updates_model_and_scene(qtbot, monkeypatch):
    class ValueBox:
        def __init__(self, value):
            self._value = value

        def value(self):
            return self._value

    class DialogStub:
        Accepted = QDialog.Accepted

        def __init__(self, *args, **kwargs):
            self.width = ValueBox(3)
            self.height = ValueBox(2)

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr("pixel_level_tool.ui.main_window.ResizeGridDialog", DialogStub)
    window = MainWindow()
    qtbot.addWidget(window)
    window.level.pixel_grid.resize(2, 2)
    window.level.pixel_grid.color_ids = [0, 1, 2, 3]
    window._refresh_all()

    window.resize_pixel_grid()

    assert window.level.pixel_grid.width == 3
    assert window.level.pixel_grid.height == 2
    assert window.level.pixel_grid.color_ids == [0, 1, EMPTY_COLOR_ID, 2, 3, EMPTY_COLOR_ID]
    assert window.pixel_editor.scene.sceneRect().width() == 72
    assert window.pixel_editor.scene.sceneRect().height() == 48
    window._set_dirty(False)
    window.close()


def test_trim_empty_pixel_border_updates_scene_and_supports_undo(qtbot):
    empty = EMPTY_COLOR_ID
    window = MainWindow()
    qtbot.addWidget(window)
    window.level.pixel_grid = PixelGridData(
        4,
        4,
        [
            empty, empty, empty, empty,
            empty, 1, empty, empty,
            empty, empty, 2, empty,
            empty, empty, empty, empty,
        ],
    )
    window._refresh_all()

    window.trim_empty_button.click()

    assert (window.level.pixel_grid.width, window.level.pixel_grid.height) == (2, 2)
    assert window.level.pixel_grid.color_ids == [1, empty, empty, 2]
    assert window.pixel_editor.scene.sceneRect().width() == 48
    assert window.pixel_editor.scene.sceneRect().height() == 48
    assert window.dirty

    window.commands.undo()

    assert (window.level.pixel_grid.width, window.level.pixel_grid.height) == (4, 4)
    assert window.level.pixel_grid.color_ids[5] == 1
    assert window.level.pixel_grid.color_ids[10] == 2
    window._set_dirty(False)
    window.close()


def test_import_legacy_pixel_grid_replaces_only_pixel_grid(qtbot, monkeypatch, tmp_path):
    path = tmp_path / "old.json"
    path.write_text(
        '{"pixelBoard":{"dimensions":{"cols":2,"rows":1},"colors":[0,2]}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "pixel_level_tool.ui.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(path), "JSON (*.json)"),
    )
    window = MainWindow()
    qtbot.addWidget(window)
    original_cells = list(window.level.grid_cells)

    window.import_legacy_pixel_grid()

    assert window.level.pixel_grid.width == 2
    assert window.level.pixel_grid.height == 1
    assert window.level.pixel_grid.color_ids == [EMPTY_COLOR_ID, 2]
    assert window.level.grid_cells == original_cells
    assert window.dirty
    window._set_dirty(False)
    window.close()


def test_visible_metadata_fields_are_user_editable(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.game_mode_spin.setValue(7)
    window.map_type_spin.setValue(9)
    window.board_spin.setValue(4)
    window.difficulty_spin.setValue(2)

    assert window.level.game_mode == 7
    assert window.level.map_type == 9
    assert window.level.board == 4
    assert window.level.difficulty == 2
    window._set_dirty(False)
    window.close()


def test_default_save_name_uses_category_variant_suffix(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.level.level = 12
    window.level.category = 0
    assert window._default_file_name() == "12.json"

    window.level.category = 2
    assert window._default_file_name() == "12.2.json"
    window.close()


def test_color_palette_shows_pixel_minus_box_delta(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red, 300)],
        pixel_grid=PixelGridData(4, 1, [0, 0, 0, 1]),
    )

    window._refresh_all()

    assert window.color_palette._buttons[ItemColor.Red].text() == ""
    assert window.color_palette._buttons[ItemColor.Green].text() == "+1"
    assert window.color_palette._buttons[ItemColor.Blue].text() == ""

    window.level.pixel_grid = PixelGridData(2, 1, [0, 0])
    window._refresh_all()

    assert window.color_palette._buttons[ItemColor.Red].text() == "-1"
    window.close()


def test_replace_color_updates_entire_level_and_supports_undo(qtbot, monkeypatch):
    class DialogStub:
        source_color = ItemColor.Red
        target_color = ItemColor.Cyan

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr("pixel_level_tool.ui.main_window.ReplaceColorDialog", DialogStub)
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = PixelLevelData(
        grid_rows=3,
        grid_cols=4,
        grid_cells=[
            BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red, 300),
            BoxCellData(0, 1, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Green, 301),
        ],
        pixel_grid=PixelGridData(4, 1, [0, 1, 0, EMPTY_COLOR_ID]),
    )
    window._refresh_all()

    window.replace_color_button.click()

    assert [cell.color for cell in window.level.grid_cells] == [ItemColor.Cyan, ItemColor.Green]
    assert window.level.pixel_grid.color_ids == [9, 1, 9, EMPTY_COLOR_ID]
    assert window.color_palette.selected_color == ItemColor.Cyan
    assert window.dirty

    window.commands.undo()

    assert [cell.color for cell in window.level.grid_cells] == [ItemColor.Red, ItemColor.Green]
    assert window.level.pixel_grid.color_ids == [0, 1, 0, EMPTY_COLOR_ID]
    window._set_dirty(False)
    window.close()
