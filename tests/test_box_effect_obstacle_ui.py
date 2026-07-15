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
            BoxCellData(3, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Blue),
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
        ItemColor.Blue,
        stored_cells=[
            BoxCellData(4, 5, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red),
            BoxCellData(6, 7, CellShape.Rectangle_6x1, Direction.Left, ItemColor.Cyan),
        ],
    )
    level = PixelLevelData(grid_cells=[tunnel])
    inspector = BoxInspector()
    qtbot.addWidget(inspector)
    inspector.set_context(level, [0])

    assert not inspector.stored_panel.isHidden()
    assert [inspector.stored_cells.item(row).text() for row in range(2)] == [
        "#1  Red · Rectangle_3x1 · Up",
        "#2  Cyan · Rectangle_6x1 · Left",
    ]
    assert all(not inspector.stored_cells.item(row).icon().isNull() for row in range(2))

    inspector.stored_cells.setCurrentRow(1)
    assert inspector.stored_x.value() == 6
    assert inspector.stored_y.value() == 7
    assert inspector.stored_color.currentData() == int(ItemColor.Cyan)

    changes = []
    inspector.model_changed.connect(lambda label, before: changes.append((label, before)))
    inspector.stored_color.setCurrentIndex(inspector.stored_color.findData(int(ItemColor.Green)))

    assert tunnel.stored_cells[1].color == ItemColor.Green
    assert changes[0][0] == "Edit tunnel stored box"
    assert changes[0][1].grid_cells[0].stored_cells[1].color == ItemColor.Cyan


def test_tunnel_stored_boxes_can_be_added_deleted_and_reordered(qtbot):
    tunnel = TunnelCellData(
        0,
        0,
        CellShape.Square_3x3,
        Direction.Up,
        ItemColor.Blue,
        stored_cells=[
            BoxCellData(0, 0, color=ItemColor.Red),
            BoxCellData(0, 0, color=ItemColor.Green),
        ],
    )
    level = PixelLevelData(grid_rows=5, grid_cols=5, grid_cells=[tunnel])
    inspector = BoxInspector()
    qtbot.addWidget(inspector)
    inspector.set_context(level, [0])
    changes = []
    inspector.model_changed.connect(lambda label, before: changes.append((label, before)))

    qtbot.mouseClick(inspector.stored_add_button, Qt.LeftButton)

    assert len(tunnel.stored_cells) == 3
    assert tunnel.stored_cells[2].shape == tunnel.shape
    assert tunnel.stored_cells[2].direction == tunnel.direction
    assert tunnel.stored_cells[2].color == tunnel.color
    assert inspector.stored_cells.currentRow() == 2

    inspector.stored_cells.setCurrentRow(1)
    qtbot.mouseClick(inspector.stored_up_button, Qt.LeftButton)

    assert [cell.color for cell in tunnel.stored_cells] == [ItemColor.Green, ItemColor.Red, ItemColor.Blue]
    assert inspector.stored_cells.currentRow() == 0

    qtbot.mouseClick(inspector.stored_remove_button, Qt.LeftButton)

    assert [cell.color for cell in tunnel.stored_cells] == [ItemColor.Red, ItemColor.Blue]
    assert [label for label, _ in changes] == [
        "Add tunnel stored box",
        "Reorder tunnel stored boxes",
        "Delete tunnel stored box",
    ]

    qtbot.mouseClick(inspector.stored_remove_button, Qt.LeftButton)
    assert len(tunnel.stored_cells) == 1
    assert not inspector.stored_remove_button.isEnabled()


def test_existing_tunnel_direction_can_be_changed_when_placement_is_valid(qtbot):
    tunnel = TunnelCellData(
        0,
        0,
        CellShape.Rectangle_3x1,
        Direction.Up,
        ItemColor.Blue,
        stored_cells=[BoxCellData(0, 0)],
    )
    level = PixelLevelData(grid_rows=4, grid_cols=4, grid_cells=[tunnel])
    inspector = BoxInspector()
    qtbot.addWidget(inspector)
    inspector.set_context(level, [0])
    changes = []
    inspector.model_changed.connect(lambda label, before: changes.append((label, before)))

    inspector.tunnel_direction.setCurrentIndex(inspector.tunnel_direction.findData(int(Direction.Right)))

    assert tunnel.direction == Direction.Right
    assert changes[0][0] == "Change tunnel direction"
    assert changes[0][1].grid_cells[0].direction == Direction.Up


def test_tunnel_direction_rejects_out_of_bounds_rotation(qtbot):
    tunnel = TunnelCellData(
        0,
        0,
        CellShape.Rectangle_3x1,
        Direction.Up,
        ItemColor.Blue,
        stored_cells=[BoxCellData(0, 0)],
    )
    level = PixelLevelData(grid_rows=2, grid_cols=3, grid_cells=[tunnel])
    inspector = BoxInspector()
    qtbot.addWidget(inspector)
    inspector.set_context(level, [0])
    changes = []
    inspector.model_changed.connect(lambda label, before: changes.append(label))

    inspector.tunnel_direction.setCurrentIndex(inspector.tunnel_direction.findData(int(Direction.Right)))

    assert tunnel.direction == Direction.Up
    assert inspector.tunnel_direction.currentData() == int(Direction.Up)
    assert "Cannot rotate tunnel" in inspector.tunnel_status.text()
    assert changes == []


def test_obstacle_panel_creates_linked_container_from_selection(qtbot):
    level = make_level(); panel = ObstaclesPanel(); qtbot.addWidget(panel); panel.set_context(level, [0, 1])
    changes = []; panel.model_changed.connect(lambda label, before: changes.append(label))
    panel.type_combo.setCurrentText("LinkedContainer"); qtbot.mouseClick(panel.add_button, Qt.LeftButton)
    assert isinstance(level.obstacles[0], LinkedContainerObstacleData)
    assert level.obstacles[0].target_uids == [cell.internal_uid for cell in level.grid_cells]
    assert changes == ["Add LinkedContainer obstacle"]
