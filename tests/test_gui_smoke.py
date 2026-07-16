import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QDialog

from pixel_level_tool.domain.enums import CellShape, Direction, EMPTY_COLOR_ID, ItemColor
from pixel_level_tool.domain.level_models import BoxCellData, PixelGridData, PixelLevelData, TunnelCellData
from pixel_level_tool.services.level_serializer import save_level
from pixel_level_tool.ui.main_window import MainWindow
from pixel_level_tool.ui.widgets.box_grid_editor import CELL


def _valid_level(level_number: int, category: int = 0) -> PixelLevelData:
    return PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        level=level_number,
        category=category,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red, 300)],
        pixel_grid=PixelGridData(3, 1, [int(ItemColor.Red)] * 3),
    )


def test_main_window_smoke(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.new_action is not None
    assert window.open_action is not None
    assert window.open_file_action is not None
    assert window.load_level_button is not None
    assert window.save_action is not None
    assert window.import_legacy_button is not None
    assert window.trim_empty_button is not None
    assert window.replace_color_button is not None
    assert window.rotate_pixel_button is not None
    assert window.dark_mode_button is not None
    assert window.light_mode_button is not None
    assert window.box_editor is not None
    assert window.pixel_editor is not None
    assert not hasattr(window, "level_grid_version_spin")
    assert not hasattr(window, "category_spin")
    assert not hasattr(window, "name_edit")
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


def test_color_palette_stays_above_the_side_tabs(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.side_splitter.orientation() == Qt.Orientation.Vertical
    assert window.side_splitter.widget(0).isAncestorOf(window.color_palette)
    assert window.side_splitter.widget(1) is window.side_tabs
    assert [window.side_tabs.tabText(index) for index in range(window.side_tabs.count())] == [
        "Box Inspector",
        "Obstacles",
        "Validation",
    ]

    window.side_tabs.setCurrentIndex(1)
    assert window.side_tabs.currentWidget() is window.obstacles_panel
    assert window.side_splitter.widget(0).isAncestorOf(window.color_palette)
    window.close()


def test_theme_buttons_switch_theme_and_persist_choice(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixel_level_tool.services.settings_service.app_data_dir",
        lambda: tmp_path,
    )
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.theme == "dark"
    assert window.dark_mode_button.isChecked()

    window.light_mode_button.click()

    assert window.theme == "light"
    assert window.light_mode_button.isChecked()
    assert not window.dark_mode_button.isChecked()
    assert window.settings.get("theme") == "light"
    window.close()

    restored_window = MainWindow()
    qtbot.addWidget(restored_window)
    assert restored_window.theme == "light"
    assert restored_window.light_mode_button.isChecked()
    restored_window.close()


def test_tunnel_direction_change_survives_main_window_refresh(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    tunnel = TunnelCellData(
        0,
        0,
        CellShape.Rectangle_3x1,
        Direction.Up,
        ItemColor.Blue,
        stored_cells=[BoxCellData(0, 0)],
    )
    window.level = PixelLevelData(
        grid_rows=4,
        grid_cols=4,
        grid_cells=[tunnel],
        pixel_grid=PixelGridData(3, 1),
    )
    window._refresh_all()
    window.box_editor.selected_index = 0
    window.box_editor.selected_indices = {0}
    window._box_selection_changed([0])

    window.box_inspector.tunnel_direction.setCurrentIndex(
        window.box_inspector.tunnel_direction.findData(int(Direction.Right))
    )

    assert window.level.grid_cells[0].direction == Direction.Right
    assert window.box_inspector.tunnel_direction.currentData() == int(Direction.Right)

    window.commands.undo()

    assert window.level.grid_cells[0].direction == Direction.Up
    window._set_dirty(False)
    window.close()


def test_switching_from_normal_creates_tunnel_on_first_grid_click(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    normal = BoxCellData(0, 0, CellShape.Square_3x3, Direction.Up, ItemColor.Red)
    window.level = PixelLevelData(
        grid_rows=6,
        grid_cols=8,
        grid_cells=[normal],
        pixel_grid=PixelGridData(3, 1),
    )
    window._refresh_all()
    window.show()
    qtbot.waitExposed(window)
    window.box_editor.selected_index = 0
    window.box_editor.selected_indices = {0}
    window._box_selection_changed([0])

    window.shape_palette.cell_type_combo.setCurrentText("Tunnel")

    assert window.shape_palette.is_tunnel
    assert window.box_editor.selected_is_tunnel

    first_empty_cell = window.box_editor.mapFromScene(QPointF(4.5 * CELL, 5.5 * CELL))
    qtbot.mouseClick(window.box_editor.viewport(), Qt.LeftButton, pos=first_empty_cell)

    assert len(window.level.grid_cells) == 2
    assert isinstance(window.level.grid_cells[1], TunnelCellData)
    window._set_dirty(False)
    window.close()


def test_palette_color_recolors_selected_box(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red)],
        pixel_grid=PixelGridData(3, 1),
    )
    window._refresh_all()
    window.box_editor.selected_index = 0
    window.box_editor.selected_indices = {0}

    window.color_palette._buttons[ItemColor.Green].click()

    assert window.level.grid_cells[0].color == ItemColor.Green
    assert window.pixel_editor.selected_color == ItemColor.Green
    assert window.box_editor.selected_color == ItemColor.Green
    assert window.box_editor.selected_indices == {0}
    assert window.dirty
    window._set_dirty(False)
    window.close()


def test_deselect_box_button_clears_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red)],
    )
    window._refresh_all()
    window.box_editor.selected_index = 0
    window.box_editor.selected_indices = {0}

    window.deselect_box_button.click()

    assert window.box_editor.selected_index is None
    assert window.box_editor.selected_indices == set()
    assert window.box_inspector.selected_indices == []
    window.close()


def test_toolbar_tooltips_show_keyboard_shortcuts(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    actions = (
        window.new_action,
        window.open_action,
        window.open_file_action,
        window.prev_level_action,
        window.next_level_action,
        window.save_action,
        window.save_as_action,
        window.undo_action,
        window.redo_action,
    )
    for action in actions:
        shortcut = action.shortcut().toString()
        assert shortcut
        assert f"({shortcut})" in action.toolTip()

    assert window.validate_action.toolTip() == "Validate the current level"
    window.close()


def test_rotate_pixel_grid_updates_scene_and_supports_undo(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.level.pixel_grid = PixelGridData(3, 2, [0, 1, 2, 3, 4, 5])
    window._refresh_all()

    window.rotate_pixel_button.click()

    assert (window.level.pixel_grid.width, window.level.pixel_grid.height) == (2, 3)
    assert window.level.pixel_grid.color_ids == [3, 0, 4, 1, 5, 2]
    assert window.pixel_editor.scene.sceneRect().width() == 48
    assert window.pixel_editor.scene.sceneRect().height() == 72
    assert window.dirty

    window.commands.undo()

    assert (window.level.pixel_grid.width, window.level.pixel_grid.height) == (3, 2)
    assert window.level.pixel_grid.color_ids == [0, 1, 2, 3, 4, 5]
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


def test_level_folder_files_are_sorted_numerically_and_ignore_other_json(tmp_path):
    for name in ("10.json", "2.1.json", "2.json", "notes.json", "3.json.bak"):
        (tmp_path / name).write_text("{}", encoding="utf-8")

    assert [path.name for path in MainWindow._level_files(tmp_path)] == [
        "2.json",
        "2.1.json",
        "10.json",
    ]


def test_open_folder_and_prev_next_navigate_existing_levels(qtbot, monkeypatch, tmp_path):
    app_data = tmp_path / "app-data"
    level_folder = tmp_path / "levels"
    level_folder.mkdir()
    save_level(level_folder / "1.json", _valid_level(1))
    save_level(level_folder / "3.json", _valid_level(3))
    monkeypatch.setattr("pixel_level_tool.services.settings_service.app_data_dir", lambda: app_data)
    monkeypatch.setattr(
        "pixel_level_tool.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: str(level_folder),
    )
    window = MainWindow()
    qtbot.addWidget(window)

    window.open_action.trigger()

    assert window.level.level == 1
    assert window.path == level_folder / "1.json"
    assert not window.prev_level_action.isEnabled()
    assert window.next_level_action.isEnabled()
    assert "3" in window.next_level_action.text()

    window.next_level_action.trigger()

    assert window.level.level == 3
    assert window.path == level_folder / "3.json"
    assert window.prev_level_action.isEnabled()
    assert not window.next_level_action.isEnabled()
    window.close()


def test_open_file_preserves_selected_level_folder(qtbot, monkeypatch, tmp_path):
    app_data = tmp_path / "app-data"
    selected_folder = tmp_path / "selected-levels"
    selected_folder.mkdir()
    external_folder = tmp_path / "external"
    external_folder.mkdir()
    external_path = external_folder / "custom.json"
    save_level(external_path, _valid_level(8))
    monkeypatch.setattr("pixel_level_tool.services.settings_service.app_data_dir", lambda: app_data)
    monkeypatch.setattr(
        "pixel_level_tool.ui.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(external_path), "JSON (*.json)"),
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.level_folder = selected_folder
    window.auto_level_save = True

    window.open_file_action.trigger()

    assert window.level.level == 8
    assert window.path == external_path
    assert window.level_folder == selected_folder
    assert not window.auto_level_save
    window.close()


def test_load_level_button_loads_number_from_selected_folder(qtbot, tmp_path):
    level_folder = tmp_path / "levels"
    level_folder.mkdir()
    save_level(level_folder / "2.json", _valid_level(2))
    save_level(level_folder / "7.json", _valid_level(7))
    window = MainWindow()
    qtbot.addWidget(window)
    window.level_folder = level_folder
    window.auto_level_save = True
    window.level_spin.setValue(7)

    assert not window.dirty

    window.load_level_button.click()

    assert window.level.level == 7
    assert window.path == level_folder / "7.json"
    assert window.level_folder == level_folder
    assert window.auto_level_save
    window.close()


def test_save_in_level_folder_uses_current_level_number(qtbot, monkeypatch, tmp_path):
    app_data = tmp_path / "app-data"
    level_folder = tmp_path / "levels"
    level_folder.mkdir()
    saved_paths = []
    monkeypatch.setattr("pixel_level_tool.services.settings_service.app_data_dir", lambda: app_data)
    monkeypatch.setattr(
        "pixel_level_tool.ui.main_window.save_level",
        lambda path, level, **kwargs: saved_paths.append(path),
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = _valid_level(12, category=2)
    window.level_folder = level_folder
    window.auto_level_save = True
    window._refresh_all()

    assert window.save()

    assert saved_paths == [level_folder / "12.2.json"]
    assert window.path == level_folder / "12.2.json"
    window.close()


def test_save_as_uses_custom_path_and_disables_numbered_auto_save(qtbot, monkeypatch, tmp_path):
    app_data = tmp_path / "app-data"
    level_folder = tmp_path / "levels"
    level_folder.mkdir()
    custom_path_without_suffix = tmp_path / "exports" / "special-name"
    saved_paths = []
    monkeypatch.setattr("pixel_level_tool.services.settings_service.app_data_dir", lambda: app_data)
    monkeypatch.setattr(
        "pixel_level_tool.ui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(custom_path_without_suffix), "JSON (*.json)"),
    )
    monkeypatch.setattr(
        "pixel_level_tool.ui.main_window.save_level",
        lambda path, level, **kwargs: saved_paths.append(path),
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = _valid_level(7)
    window.level_folder = level_folder
    window.auto_level_save = True
    window._refresh_all()

    assert window.save_as()

    assert saved_paths == [custom_path_without_suffix.with_suffix(".json")]
    assert window.path == custom_path_without_suffix.with_suffix(".json")
    assert not window.auto_level_save
    window.close()


def test_color_palette_shows_pixel_minus_box_delta(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = PixelLevelData(
        grid_rows=3,
        grid_cols=3,
        grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red, 300)],
        pixel_grid=PixelGridData(4, 1, [int(ItemColor.Red)] * 3 + [int(ItemColor.Green)]),
    )

    window._refresh_all()

    assert window.color_palette._buttons[ItemColor.Red].text() == ""
    assert window.color_palette._buttons[ItemColor.Green].text() == "+1"
    assert window.color_palette._buttons[ItemColor.Blue].text() == ""

    window.level.pixel_grid = PixelGridData(2, 1, [int(ItemColor.Red)] * 2)
    window._refresh_all()

    assert window.color_palette._buttons[ItemColor.Red].text() == "-1"
    window.close()


def test_switch_color_waits_for_palette_target_updates_level_and_supports_undo(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.level = PixelLevelData(
        grid_rows=3,
        grid_cols=4,
        grid_cells=[
            BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red, 300),
            BoxCellData(0, 1, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Green, 301),
        ],
        pixel_grid=PixelGridData(
            4,
            1,
            [int(ItemColor.Red), int(ItemColor.Green), int(ItemColor.Red), EMPTY_COLOR_ID],
        ),
    )
    window._refresh_all()

    window.replace_color_button.click()

    assert window.replace_color_button.isChecked()
    assert window._replace_color_source == ItemColor.Red
    assert [cell.color for cell in window.level.grid_cells] == [ItemColor.Red, ItemColor.Green]

    window.color_palette._buttons[ItemColor.Cyan].click()

    assert not window.replace_color_button.isChecked()
    assert window._replace_color_source is None
    assert [cell.color for cell in window.level.grid_cells] == [ItemColor.Cyan, ItemColor.Green]
    assert window.level.pixel_grid.color_ids == [9, 1, 9, EMPTY_COLOR_ID]
    assert window.color_palette.selected_color == ItemColor.Cyan
    assert window.dirty

    window.commands.undo()

    assert [cell.color for cell in window.level.grid_cells] == [ItemColor.Red, ItemColor.Green]
    assert window.level.pixel_grid.color_ids == [0, 1, 0, EMPTY_COLOR_ID]
    window._set_dirty(False)
    window.close()
