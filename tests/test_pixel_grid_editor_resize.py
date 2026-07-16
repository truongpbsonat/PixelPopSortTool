import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QPointF, Qt

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID
from pixel_level_tool.domain.level_models import PixelGridData, PixelLevelData
from pixel_level_tool.ui.widgets.pixel_grid_editor import CELL, PixelGridEditor


def _shown_editor(qtbot, grid: PixelGridData) -> PixelGridEditor:
    editor = PixelGridEditor()
    qtbot.addWidget(editor)
    editor.resize(420, 320)
    editor.set_level(PixelLevelData(pixel_grid=grid))
    editor.show()
    qtbot.waitExposed(editor)
    return editor


def test_dragging_right_edge_resizes_and_records_one_change(qtbot):
    editor = _shown_editor(qtbot, PixelGridData(2, 2, [0, 1, 2, 3]))
    changes = []
    editor.model_changed.connect(lambda label, before: changes.append((label, before)))
    start = editor.mapFromScene(QPointF(2 * CELL, CELL))
    end = start + QPoint(2 * CELL, 0)

    qtbot.mousePress(editor.viewport(), Qt.LeftButton, pos=start)
    qtbot.mouseMove(editor.viewport(), pos=end)
    qtbot.mouseRelease(editor.viewport(), Qt.LeftButton, pos=end)

    assert (editor.level.pixel_grid.width, editor.level.pixel_grid.height) == (4, 2)
    assert editor.level.pixel_grid.color_ids == [
        0, 1, EMPTY_COLOR_ID, EMPTY_COLOR_ID,
        2, 3, EMPTY_COLOR_ID, EMPTY_COLOR_ID,
    ]
    assert len(changes) == 1
    assert changes[0][0] == "Resize pixel grid"
    assert (changes[0][1].pixel_grid.width, changes[0][1].pixel_grid.height) == (2, 2)


def test_dragging_bottom_right_corner_resizes_both_dimensions(qtbot):
    editor = _shown_editor(qtbot, PixelGridData(3, 3))
    start = editor.mapFromScene(QPointF(3 * CELL, 3 * CELL))
    end = start - QPoint(2 * CELL, CELL)

    qtbot.mousePress(editor.viewport(), Qt.LeftButton, pos=start)
    qtbot.mouseMove(editor.viewport(), pos=end)
    qtbot.mouseRelease(editor.viewport(), Qt.LeftButton, pos=end)

    assert (editor.level.pixel_grid.width, editor.level.pixel_grid.height) == (1, 2)
    assert editor.scene.sceneRect().width() == CELL
    assert editor.scene.sceneRect().height() == 2 * CELL


def test_shrinking_then_expanding_in_one_drag_does_not_discard_pixels(qtbot):
    editor = _shown_editor(qtbot, PixelGridData(3, 1, [0, 1, 2]))
    changes = []
    editor.model_changed.connect(lambda *args: changes.append(args))
    start = editor.mapFromScene(QPointF(3 * CELL, CELL / 2))

    qtbot.mousePress(editor.viewport(), Qt.LeftButton, pos=start)
    qtbot.mouseMove(editor.viewport(), pos=start - QPoint(2 * CELL, 0))
    assert editor.level.pixel_grid.color_ids == [0]
    qtbot.mouseMove(editor.viewport(), pos=start)
    qtbot.mouseRelease(editor.viewport(), Qt.LeftButton, pos=start)

    assert editor.level.pixel_grid.color_ids == [0, 1, 2]
    assert changes == []


def test_dragging_left_edge_adds_and_removes_columns_from_the_left(qtbot):
    editor = _shown_editor(qtbot, PixelGridData(2, 2, [0, 1, 2, 3]))
    start = editor.mapFromScene(QPointF(0, CELL))
    end = start - QPoint(2 * CELL, 0)

    qtbot.mousePress(editor.viewport(), Qt.LeftButton, pos=start)
    qtbot.mouseMove(editor.viewport(), pos=end)
    qtbot.mouseRelease(editor.viewport(), Qt.LeftButton, pos=end)

    assert (editor.level.pixel_grid.width, editor.level.pixel_grid.height) == (4, 2)
    assert editor.level.pixel_grid.color_ids == [
        EMPTY_COLOR_ID, EMPTY_COLOR_ID, 0, 1,
        EMPTY_COLOR_ID, EMPTY_COLOR_ID, 2, 3,
    ]


def test_dragging_top_edge_in_removes_rows_from_the_top(qtbot):
    editor = _shown_editor(qtbot, PixelGridData(2, 3, [0, 1, 2, 3, 4, 5]))
    start = editor.mapFromScene(QPointF(CELL, 0))
    end = start + QPoint(0, CELL)

    qtbot.mousePress(editor.viewport(), Qt.LeftButton, pos=start)
    qtbot.mouseMove(editor.viewport(), pos=end)
    qtbot.mouseRelease(editor.viewport(), Qt.LeftButton, pos=end)

    assert (editor.level.pixel_grid.width, editor.level.pixel_grid.height) == (2, 2)
    assert editor.level.pixel_grid.color_ids == [2, 3, 4, 5]


def test_resize_edges_use_directional_cursors(qtbot):
    editor = _shown_editor(qtbot, PixelGridData(2, 2))

    editor._update_resize_cursor(frozenset(("right",)))
    assert editor.viewport().cursor().shape() == Qt.SizeHorCursor

    editor._update_resize_cursor(frozenset(("right", "bottom")))
    assert editor.viewport().cursor().shape() == Qt.SizeFDiagCursor

    editor._update_resize_cursor(frozenset(("right", "top")))
    assert editor.viewport().cursor().shape() == Qt.SizeBDiagCursor
