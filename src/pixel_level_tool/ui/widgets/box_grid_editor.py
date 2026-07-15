from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView

from pixel_level_tool.domain.enums import COLOR_RGB, CellShape, Direction, ItemColor
from pixel_level_tool.domain.level_models import BoxCellData, PixelLevelData
from pixel_level_tool.domain.shapes import footprint


CELL = 28
INNER_CELL_BORDER = QColor(255, 255, 255, 55)
OUTLINE_BORDER = QColor(20, 24, 30)


class BoxGridEditor(QGraphicsView):
    model_changed = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.level: PixelLevelData | None = None
        self.selected_color = ItemColor.Red
        self.selected_shape = CellShape.Square_3x3
        self.selected_direction = Direction.Up
        self.selected_active = True
        self.selected_index: int | None = None
        self._drag_index: int | None = None
        self._drag_offset: tuple[int, int] = (0, 0)
        self._drag_before: PixelLevelData | None = None
        self._drag_changed = False
        self.setFocusPolicy(Qt.StrongFocus)

    def set_level(self, level: PixelLevelData) -> None:
        self.level = level
        self.selected_index = None
        self._reset_drag()
        self.refresh()

    def set_tool(self, shape: CellShape, direction: Direction, color: ItemColor, is_active: bool) -> None:
        self.selected_shape = shape
        self.selected_direction = direction
        self.selected_color = color
        self.selected_active = is_active
        if self.level is not None and self.selected_index is not None and self.selected_index < len(self.level.grid_cells):
            cell = self.level.grid_cells[self.selected_index]
            if (
                cell.shape != shape
                or cell.direction != direction
                or cell.color != color
                or cell.is_active != is_active
            ):
                before = self.level.clone()
                old = BoxCellData(cell.grid_x, cell.grid_y, cell.shape, cell.direction, cell.color, cell.id, cell.is_active)
                cell.shape = shape
                cell.direction = direction
                cell.color = color
                cell.is_active = is_active
                if self.level.can_place(cell, ignore_index=self.selected_index):
                    self.model_changed.emit("Edit box", before)
                    self.refresh()
                else:
                    cell.shape = old.shape
                    cell.direction = old.direction
                    cell.color = old.color
                    cell.is_active = old.is_active

    def refresh(self) -> None:
        self.scene.clear()
        if self.level is None:
            return
        width = self.level.grid_cols * CELL
        height = self.level.grid_rows * CELL
        for row in range(self.level.grid_rows):
            label = QGraphicsTextItem(str(row))
            label.setDefaultTextColor(QColor(95, 103, 115))
            label.setPos(-24, row * CELL + 5)
            self.scene.addItem(label)
        for col in range(self.level.grid_cols):
            label = QGraphicsTextItem(str(col))
            label.setDefaultTextColor(QColor(95, 103, 115))
            label.setPos(col * CELL + 7, -24)
            self.scene.addItem(label)
        for row in range(self.level.grid_rows):
            for col in range(self.level.grid_cols):
                self.scene.addRect(col * CELL, row * CELL, CELL, CELL, QPen(QColor(210, 216, 224)))
        for index, cell in enumerate(self.level.grid_cells):
            self._draw_cell(index, cell)
        self.scene.setSceneRect(-32, -32, width + 48, height + 48)

    def _draw_cell(self, index: int, cell: BoxCellData) -> None:
        rgb = COLOR_RGB[cell.color]
        brush = QColor(*rgb)
        if not cell.is_active:
            brush.setAlpha(110)
        inner_pen = QPen(INNER_CELL_BORDER, 1)
        outline_pen = QPen(OUTLINE_BORDER, 2 if index == self.selected_index else 1.5)
        occupied = set(footprint(cell.shape, cell.direction))
        for dx, dy in occupied:
            item = QGraphicsRectItem((cell.grid_x + dx) * CELL, (cell.grid_y + dy) * CELL, CELL, CELL)
            item.setBrush(brush)
            item.setPen(inner_pen)
            item.setData(0, index)
            item.setData(1, "fill")
            self.scene.addItem(item)
        self._draw_outline(index, cell, occupied, outline_pen)
        label = QGraphicsTextItem(str(cell.id or index))
        label.setDefaultTextColor(QColor(20, 24, 30))
        label.setPos(cell.grid_x * CELL + 4, cell.grid_y * CELL + 3)
        label.setData(0, index)
        label.setData(1, "label")
        self.scene.addItem(label)

    def _draw_outline(
        self,
        index: int,
        cell: BoxCellData,
        occupied: set[tuple[int, int]],
        pen: QPen,
    ) -> None:
        for dx, dy in occupied:
            left = (cell.grid_x + dx) * CELL
            top = (cell.grid_y + dy) * CELL
            right = left + CELL
            bottom = top + CELL
            if (dx, dy - 1) not in occupied:
                self._add_outline_segment(index, left, top, right, top, pen)
            if (dx + 1, dy) not in occupied:
                self._add_outline_segment(index, right, top, right, bottom, pen)
            if (dx, dy + 1) not in occupied:
                self._add_outline_segment(index, left, bottom, right, bottom, pen)
            if (dx - 1, dy) not in occupied:
                self._add_outline_segment(index, left, top, left, bottom, pen)

    def _add_outline_segment(self, index: int, x1: int, y1: int, x2: int, y2: int, pen: QPen) -> None:
        item = QGraphicsLineItem(x1, y1, x2, y2)
        item.setPen(pen)
        item.setData(0, index)
        item.setData(1, "outline")
        self.scene.addItem(item)

    def _scene_cell_from_event(self, event) -> tuple[int, int]:
        point = self.mapToScene(event.position().toPoint())
        return int(point.x() // CELL), int(point.y() // CELL)

    def _reset_drag(self) -> None:
        self._drag_index = None
        self._drag_offset = (0, 0)
        self._drag_before = None
        self._drag_changed = False

    def mousePressEvent(self, event) -> None:
        if self.level is None:
            return
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            super().mousePressEvent(event)
            return
        col, row = self._scene_cell_from_event(event)
        clicked = self.itemAt(event.position().toPoint())
        if event.button() == Qt.LeftButton and clicked and clicked.data(0) is not None:
            self.selected_index = int(clicked.data(0))
            cell = self.level.grid_cells[self.selected_index]
            self._drag_index = self.selected_index
            self._drag_offset = (col - cell.grid_x, row - cell.grid_y)
            self._drag_before = self.level.clone()
            self._drag_changed = False
            self.refresh()
            return
        if event.button() == Qt.LeftButton and 0 <= row < self.level.grid_rows and 0 <= col < self.level.grid_cols:
            before = self.level.clone()
            box = BoxCellData(
                grid_x=col,
                grid_y=row,
                shape=self.selected_shape,
                direction=self.selected_direction,
                color=self.selected_color,
                is_active=self.selected_active,
            )
            if self.level.add_box(box):
                self.selected_index = len(self.level.grid_cells) - 1
                self.model_changed.emit("Add box", before)
                self.refresh()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.level is not None and self._drag_index is not None and event.buttons() & Qt.LeftButton:
            col, row = self._scene_cell_from_event(event)
            offset_x, offset_y = self._drag_offset
            target_x, target_y = col - offset_x, row - offset_y
            cell = self.level.grid_cells[self._drag_index]
            if (cell.grid_x, cell.grid_y) != (target_x, target_y):
                moved = BoxCellData(target_x, target_y, cell.shape, cell.direction, cell.color, cell.id, cell.is_active)
                if self.level.can_place(moved, ignore_index=self.selected_index):
                    cell.grid_x, cell.grid_y = target_x, target_y
                    self._drag_changed = True
                    self.refresh()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.setDragMode(QGraphicsView.RubberBandDrag)
        if self._drag_changed and self._drag_before is not None:
            self.model_changed.emit("Move box", self._drag_before)
        self._reset_drag()
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 0.87
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.level is not None and self.selected_index is not None:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                before = self.level.clone()
                del self.level.grid_cells[self.selected_index]
                self.selected_index = None
                self.model_changed.emit("Delete box", before)
                self.refresh()
                return
            if event.key() == Qt.Key_R:
                before = self.level.clone()
                cell = self.level.grid_cells[self.selected_index]
                directions = [Direction.Up, Direction.Right, Direction.Down, Direction.Left]
                cell.direction = directions[(directions.index(cell.direction) + 1) % len(directions)]
                if not self.level.can_place(cell, ignore_index=self.selected_index):
                    cell.direction = directions[(directions.index(cell.direction) - 1) % len(directions)]
                else:
                    self.model_changed.emit("Rotate box", before)
                    self.refresh()
                return
            if event.key() == Qt.Key_D and event.modifiers() & Qt.ControlModifier:
                source = self.level.grid_cells[self.selected_index]
                before = self.level.clone()
                for y in range(source.grid_y, self.level.grid_rows):
                    for x in range(source.grid_x + 1 if y == source.grid_y else 0, self.level.grid_cols):
                        duplicate = BoxCellData(x, y, source.shape, source.direction, source.color, 0, source.is_active)
                        if self.level.add_box(duplicate):
                            self.selected_index = len(self.level.grid_cells) - 1
                            self.model_changed.emit("Duplicate box", before)
                            self.refresh()
                            return
        super().keyPressEvent(event)

    def zoom_in(self) -> None:
        self.scale(1.15, 1.15)

    def zoom_out(self) -> None:
        self.scale(0.87, 0.87)
