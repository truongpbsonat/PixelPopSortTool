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


def test_dragging_box_onto_another_box_swaps_them(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)
    editor.resize(420, 240)
    editor.show()
    qtbot.waitExposed(editor)

    level = PixelLevelData(
        grid_rows=4,
        grid_cols=8,
        grid_cells=[
            BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red),
            BoxCellData(4, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Blue),
        ],
    )
    editor.set_level(level)
    changes = []
    editor.model_changed.connect(lambda label, before: changes.append((label, before)))
    source = editor.mapFromScene(QPointF(CELL / 2, 3 * CELL + CELL / 2))
    target = editor.mapFromScene(QPointF(4 * CELL + CELL / 2, 3 * CELL + CELL / 2))

    qtbot.mousePress(editor.viewport(), Qt.LeftButton, pos=source)
    qtbot.mouseMove(editor.viewport(), pos=target)

    # Swapping is visualized during the drag, before the mouse is released.
    assert [(cell.grid_x, cell.grid_y) for cell in level.grid_cells] == [(4, 0), (0, 0)]
    assert changes == []

    qtbot.mouseRelease(editor.viewport(), Qt.LeftButton, pos=target)

    assert [(cell.grid_x, cell.grid_y) for cell in level.grid_cells] == [(4, 0), (0, 0)]
    assert [label for label, _ in changes] == ["Swap boxes"]
    assert [(cell.grid_x, cell.grid_y) for cell in changes[0][1].grid_cells] == [(0, 0), (4, 0)]


def test_shift_drag_selects_every_box_in_area(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)
    editor.resize(420, 240)
    editor.show()
    qtbot.waitExposed(editor)
    level = PixelLevelData(
        grid_rows=4,
        grid_cols=8,
        grid_cells=[
            BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red),
            BoxCellData(4, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Blue),
        ],
    )
    editor.set_level(level)
    start = editor.mapFromScene(QPointF(-CELL / 2, 2.5 * CELL))
    end = editor.mapFromScene(QPointF(7.5 * CELL, 3.5 * CELL))

    qtbot.mousePress(editor.viewport(), Qt.LeftButton, Qt.ShiftModifier, pos=start)
    qtbot.mouseMove(editor.viewport(), pos=end)
    qtbot.mouseRelease(editor.viewport(), Qt.LeftButton, Qt.ShiftModifier, pos=end)

    assert editor.selected_indices == {0, 1}


def test_dragging_a_selected_group_moves_all_boxes_together(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)
    editor.resize(420, 280)
    editor.show()
    qtbot.waitExposed(editor)
    level = PixelLevelData(
        grid_rows=6,
        grid_cols=8,
        grid_cells=[
            BoxCellData(0, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Red),
            BoxCellData(4, 0, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Blue),
        ],
    )
    editor.set_level(level)
    editor.selected_indices = {0, 1}
    editor.selected_index = 0
    changes = []
    editor.model_changed.connect(lambda label, before: changes.append(label))
    source = editor.mapFromScene(QPointF(CELL / 2, 5 * CELL + CELL / 2))
    target = editor.mapFromScene(QPointF(CELL / 2, 3 * CELL + CELL / 2))

    qtbot.mousePress(editor.viewport(), Qt.LeftButton, pos=source)
    qtbot.mouseMove(editor.viewport(), pos=target)
    qtbot.mouseRelease(editor.viewport(), Qt.LeftButton, pos=target)

    assert editor.selected_indices == {0, 1}
    assert [(cell.grid_x, cell.grid_y) for cell in level.grid_cells] == [(0, 2), (4, 2)]
    assert changes == ["Move boxes"]


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


def test_black_box_is_visually_distinct_from_empty_grid(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)

    level = PixelLevelData(grid_rows=4, grid_cols=4)
    level.add_box(BoxCellData(0, 0, CellShape.Square_3x3, Direction.Up, ItemColor.Black))
    editor.set_level(level)

    grid_items = [
        item for item in editor.scene.items()
        if isinstance(item, QGraphicsRectItem) and item.data(1) == "grid-cell"
    ]
    outline_items = [
        item for item in editor.scene.items()
        if isinstance(item, QGraphicsLineItem) and item.data(1) == "outline"
    ]
    label = next(
        item for item in editor.scene.items()
        if isinstance(item, QGraphicsTextItem) and item.data(1) == "label"
    )
    label_background = next(
        item for item in editor.scene.items()
        if isinstance(item, QGraphicsRectItem) and item.data(1) == "label-background"
    )

    assert len({item.brush().color().rgb() for item in grid_items}) == 2
    assert all(item.pen().color().lightness() > 128 for item in outline_items)
    assert all(item.pen().widthF() == 2 for item in outline_items)
    assert label.font().bold()
    assert label_background.brush().color().alpha() > 0
    assert label_background.pen().style() != Qt.NoPen
    assert label_background.pen().widthF() == 1
    assert label.zValue() > label_background.zValue()


def test_selected_outline_stays_above_box_and_obstacle_layers(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)

    cell = BoxCellData(
        1,
        1,
        CellShape.Rectangle_3x2,
        Direction.Up,
        ItemColor.Blue,
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
    top = BoxCellData(3, 5, CellShape.Rectangle_3x1, Direction.Up, ItemColor.Blue)
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
    level.obstacles = [ColorGateObstacleData(0, 0, 3, 1, 2, ItemColor.Blue)]
    editor.set_level(level)

    badge_text = {
        item.toPlainText()
        for item in editor.scene.items()
        if isinstance(item, QGraphicsTextItem) and item.data(1) in {"effect-badge-text", "obstacle-badge-text"}
    }

    assert "ICE x3" in badge_text
    assert "GATE Blue x2" in badge_text
    assert any(item.data(1) == "obstacle-area" and item.zValue() > 1 for item in editor.scene.items())


def test_tunnel_has_rotated_icon_direction_and_stored_count(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)
    tunnel = TunnelCellData(
        0,
        0,
        CellShape.Square_3x3,
        Direction.Left,
        ItemColor.Blue,
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


def test_tunnel_tool_adds_valid_tunnel_to_box_grid(qtbot):
    editor = BoxGridEditor()
    qtbot.addWidget(editor)
    editor.resize(320, 320)
    editor.show()
    qtbot.waitExposed(editor)

    level = PixelLevelData(grid_rows=6, grid_cols=6)
    editor.set_level(level)
    editor.set_tool(
        CellShape.Rectangle_3x1,
        Direction.Right,
        ItemColor.Green,
        True,
        is_tunnel=True,
    )
    changes = []
    editor.model_changed.connect(lambda label, before: changes.append((label, before)))
    position = editor.mapFromScene(QPointF(CELL / 2, 4 * CELL + CELL / 2))

    qtbot.mouseClick(editor.viewport(), Qt.LeftButton, pos=position)

    assert len(level.grid_cells) == 1
    tunnel = level.grid_cells[0]
    assert isinstance(tunnel, TunnelCellData)
    assert (tunnel.grid_x, tunnel.grid_y) == (0, 1)
    assert tunnel.shape == CellShape.Rectangle_3x1
    assert tunnel.direction == Direction.Right
    assert tunnel.color == ItemColor.Green
    assert len(tunnel.stored_cells) == 1
    assert type(tunnel.stored_cells[0]) is BoxCellData
    assert tunnel.stored_cells[0].shape == CellShape.Rectangle_3x1
    assert tunnel.stored_cells[0].direction == Direction.Right
    assert tunnel.stored_cells[0].color == ItemColor.Green
    assert changes[0][0] == "Add tunnel"
    assert changes[0][1].grid_cells == []
