import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsRectItem

from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor
from pixel_level_tool.domain.level_models import BoxCellData, PixelLevelData
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

    press_pos = editor.mapFromScene(QPointF(2 * CELL + CELL / 2, 2 * CELL + CELL / 2))
    move_pos = editor.mapFromScene(QPointF(4 * CELL + CELL / 2, 4 * CELL + CELL / 2))

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
    level.add_box(BoxCellData(1, 1, CellShape.Rectangle_3x2, Direction.Up, ItemColor.Blue))
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
