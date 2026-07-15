import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsPathItem, QGraphicsRectItem, QGraphicsTextItem

from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor
from pixel_level_tool.domain.level_models import (
    BoxCellData,
    ColorGateObstacleData,
    FrozenCellEffectData,
    PixelLevelData,
    TunnelCellData,
)
from pixel_level_tool.ui.widgets.box_grid_editor import CELL, BoxGridEditor


def test_drag_keeps_grab_offset_and_records_one_change(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)
    editor.resize(320, 320)
    editor.show()
    qtbot.waitExposed(editor)

    level = PixelLevelData(grid_rows=8, grid_cols=8)
    level.add_box(BoxCellData(1, 1, CellShape.Square_3x3, Direction.Up, ItemColor.Red))
    editor.set_level(level)

    changes = []
    editor.model_changed.connect(lambda label, before: changes.append((label, before)))

    press_pos = editor.mapFromScene(QPointF(2 * CELL + CELL / 2, 5 * CELL + CELL / 2))
    move_pos = editor.mapFromScene(QPointF(4 * CELL + CELL / 2, 3 * CELL + CELL / 2))

    qtbot.mousePress(editor.viewport(), Qt.LeftButton, pos=press_pos)
    qtbot.mouseMove(editor.viewport(), pos=move_pos)

    assert (level.grid_cells[0].grid_x, level.grid_cells[0].grid_y) == (3, 3)
    assert changes == []

    qtbot.mouseRelease(editor.viewport(), Qt.LeftButton, pos=move_pos)

    assert len(changes) == 1
    assert changes[0][0] == "Move box"
    before = changes[0][1]
    assert (before.grid_cells[0].grid_x, before.grid_cells[0].grid_y) == (1, 1)


def test_box_cells_use_soft_inner_borders_and_separate_outline(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)

    level = PixelLevelData(grid_rows=6, grid_cols=6)
    level.add_box(BoxCellData(1, 1, CellShape.Rectangle_3x2, Direction.Up, ItemColor.DarkBlue))
    editor.set_level(level)

    fill_items = [
        item for item in editor.scene.items()
        if isinstance(item, QGraphicsRectItem) and item.data(1) == "fill"
    ]
    outline_items = [
        item for item in editor.scene.items()
        if isinstance(item, QGraphicsLineItem) and item.data(1) == "outline"
    ]

    assert len(fill_items) == 6
    assert outline_items
    assert all(item.pen().color().alpha() == 55 for item in fill_items)
    assert all(item.pen().widthF() == 1 for item in fill_items)
    assert all(item.pen().widthF() >= 1.5 for item in outline_items)


def test_selected_outline_stays_above_box_and_obstacle_layers(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)

    cell = BoxCellData(
        1,
        1,
        CellShape.Rectangle_3x2,
        Direction.Up,
        ItemColor.DarkBlue,
        effects=[FrozenCellEffectData(2)],
    )
    level = PixelLevelData(grid_rows=6, grid_cols=6, grid_cells=[cell])
    level.obstacles = [ColorGateObstacleData(1, 1, 3, 2, 2, ItemColor.Red)]
    editor.set_level(level)
    editor.selected_indices = {0}
    editor.selected_index = 0
    editor.refresh()

    selection_items = [item for item in editor.scene.items() if item.data(1) == "selection-outline"]
    blocking_layers = [
        item for item in editor.scene.items()
        if item.data(1) in {"fill", "obstacle-area", "effect-badge", "obstacle-badge"}
    ]

    assert selection_items
    assert all(item.pen().isCosmetic() for item in selection_items)
    assert min(item.zValue() for item in selection_items) > max(item.zValue() for item in blocking_layers)
    assert editor._box_index_at(editor.mapFromScene(QPointF(1.5 * CELL, 4.5 * CELL))) == 0


def test_escape_clears_box_selection(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)
    editor.set_level(
        PixelLevelData(
            grid_rows=3,
            grid_cols=3,
            grid_cells=[BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red)],
        )
    )
    editor.selected_index = 0
    editor.selected_indices = {0}
    selections = []
    editor.selection_changed.connect(selections.append)

    qtbot.keyClick(editor, Qt.Key_Escape)

    assert editor.selected_index is None
    assert editor.selected_indices == set()
    assert selections == [[]]


def test_box_grid_displays_model_row_zero_at_the_bottom(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)

    bottom = BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Green)
    top = BoxCellData(3, 5, CellShape.Rectangle_3x1, Direction.Up, ItemColor.DarkBlue)
    editor.set_level(PixelLevelData(grid_rows=6, grid_cols=6, grid_cells=[bottom, top]))

    fill_rows = {
        int(item.data(0)): int(item.rect().y() // CELL)
        for item in editor.scene.items()
        if isinstance(item, QGraphicsRectItem) and item.data(1) == "fill"
    }

    assert fill_rows[0] == 5
    assert fill_rows[1] == 0


def test_effect_and_obstacle_have_readable_grid_badges(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)

    cell = BoxCellData(
        0,
        0,
        CellShape.Rectangle_3x1,
        Direction.Up,
        ItemColor.Red,
        effects=[FrozenCellEffectData(3)],
    )
    level = PixelLevelData(grid_rows=3, grid_cols=4, grid_cells=[cell])
    level.obstacles = [ColorGateObstacleData(0, 0, 3, 1, 2, ItemColor.DarkBlue)]
    editor.set_level(level)

    badge_text = {
        item.toPlainText()
        for item in editor.scene.items()
        if isinstance(item, QGraphicsTextItem) and item.data(1) in {"effect-badge-text", "obstacle-badge-text"}
    }

    assert "ICE x3" in badge_text
    assert "GATE Dark Blue x2" in badge_text
    assert any(item.data(1) == "obstacle-area" and item.zValue() > 1 for item in editor.scene.items())


def test_tunnel_has_rotated_icon_direction_and_stored_count(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)
    tunnel = TunnelCellData(
        0,
        0,
        CellShape.Square_3x3,
        Direction.Left,
        ItemColor.DarkBlue,
        stored_cells=[BoxCellData(0, 0), BoxCellData(0, 0)],
    )
    editor.set_level(PixelLevelData(grid_cells=[tunnel]))

    badges = [
        item.toPlainText()
        for item in editor.scene.items()
        if isinstance(item, QGraphicsTextItem) and item.data(1) == "tunnel-badge-text"
    ]
    counts = [
        item.toPlainText()
        for item in editor.scene.items()
        if isinstance(item, QGraphicsTextItem) and item.data(1) == "tunnel-count-text"
    ]
    icons = [
        item
        for item in editor.scene.items()
        if isinstance(item, QGraphicsPathItem) and item.data(1) == "tunnel-icon"
    ]

    assert badges == ["TUN ←"]
    assert counts == ["2"]
    assert len(icons) == 1
    assert icons[0].rotation() == 270
