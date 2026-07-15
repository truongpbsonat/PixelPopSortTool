import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt

from pixel_level_tool.domain.enums import CellShape, Direction, ItemColor
from pixel_level_tool.domain.level_models import (
    BoxCellData,
    FrozenCellEffectData,
    LinkedContainerObstacleData,
    PixelLevelData,
    TunnelCellData,
)
from pixel_level_tool.ui.widgets.box_grid_editor import CELL, BoxGridEditor
from pixel_level_tool.ui.widgets.box_inspector import BoxInspector, ObstaclesPanel


def make_level():
    return PixelLevelData(
        grid_rows=4,
        grid_cols=8,
        grid_cells=[
            BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red),
            BoxCellData(3, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.DarkBlue),
        ],
    )


def test_ctrl_click_multi_selects_boxes(qtbot):
    editor = BoxGridEditor(); qtbot.addWidget(editor); editor.resize(400, 220); editor.show(); qtbot.waitExposed(editor)
    editor.set_level(make_level())
    first = editor.mapFromScene(QPointF(CELL / 2, 3 * CELL + CELL / 2))
    second = editor.mapFromScene(QPointF(3 * CELL + CELL / 2, 3 * CELL + CELL / 2))
    qtbot.mouseClick(editor.viewport(), Qt.LeftButton, pos=first)
    qtbot.mouseClick(editor.viewport(), Qt.LeftButton, Qt.ControlModifier, pos=second)
    assert editor.selected_indices == {0, 1}


def test_box_inspector_adds_typed_effect_and_emits_snapshot(qtbot):
    level = make_level(); inspector = BoxInspector(); qtbot.addWidget(inspector); inspector.set_context(level, [0])
    changes = []; inspector.model_changed.connect(lambda label, before: changes.append((label, before)))
    inspector.add_combo.setCurrentText("Frozen"); qtbot.mouseClick(inspector.add_button, Qt.LeftButton)
    assert level.grid_cells[0].effects == [FrozenCellEffectData(1)]
    assert changes[0][0] == "Add box effect"
    assert changes[0][1].grid_cells[0].effects is None


def test_tunnel_stored_boxes_keep_json_order_and_are_editable(qtbot):
    tunnel = TunnelCellData(
        0,
        0,
        CellShape.Square_3x3,
        Direction.Right,
        ItemColor.DarkBlue,
        stored_cells=[
            BoxCellData(4, 5, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red),
            BoxCellData(6, 7, CellShape.Rectangle_6x1, Direction.Left, ItemColor.SkyBlue),
        ],
    )
    level = PixelLevelData(grid_cells=[tunnel])
    inspector = BoxInspector()
    qtbot.addWidget(inspector)
    inspector.set_context(level, [0])

    assert not inspector.stored_panel.isHidden()
    assert [inspector.stored_cells.item(row).text() for row in range(2)] == [
        "#1  Red · Rectangle_3x1 · Up",
        "#2  Sky Blue · Rectangle_6x1 · Left",
    ]
    assert all(not inspector.stored_cells.item(row).icon().isNull() for row in range(2))

    inspector.stored_cells.setCurrentRow(1)
    assert inspector.stored_x.value() == 6
    assert inspector.stored_y.value() == 7
    assert inspector.stored_color.currentData() == int(ItemColor.SkyBlue)

    changes = []
    inspector.model_changed.connect(lambda label, before: changes.append((label, before)))
    inspector.stored_color.setCurrentIndex(inspector.stored_color.findData(int(ItemColor.Green)))

    assert tunnel.stored_cells[1].color == ItemColor.Green
    assert changes[0][0] == "Edit tunnel stored box"
    assert changes[0][1].grid_cells[0].stored_cells[1].color == ItemColor.SkyBlue


def test_obstacle_panel_creates_linked_container_from_selection(qtbot):
    level = make_level(); panel = ObstaclesPanel(); qtbot.addWidget(panel); panel.set_context(level, [0, 1])
    changes = []; panel.model_changed.connect(lambda label, before: changes.append(label))
    panel.type_combo.setCurrentText("LinkedContainer"); qtbot.mouseClick(panel.add_button, Qt.LeftButton)
    assert isinstance(level.obstacles[0], LinkedContainerObstacleData)
    assert level.obstacles[0].target_uids == [cell.internal_uid for cell in level.grid_cells]
    assert changes == ["Add LinkedContainer obstacle"]
