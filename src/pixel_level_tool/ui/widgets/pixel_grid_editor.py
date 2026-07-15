from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from pixel_level_tool.domain.enums import COLOR_RGB, EMPTY_COLOR_ID, ItemColor
from pixel_level_tool.domain.level_models import PixelLevelData


CELL = 24


class PixelGridEditor(QGraphicsView):
    model_changed = Signal(str, object)
    color_picked = Signal(ItemColor)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing, False)
        self.level: PixelLevelData | None = None
        self.selected_color = ItemColor.Red
        self.mode = "paint"
        self.show_grid_lines = True
        self._stroke_changed = False
        self._stroke_before = None

    def set_level(self, level: PixelLevelData) -> None:
        self.level = level
        self.refresh()

    def set_color(self, color: ItemColor) -> None:
        self.selected_color = color

    def refresh(self) -> None:
        self.scene.clear()
        if self.level is None:
            return
        grid = self.level.pixel_grid
        for row in range(grid.height):
            for col in range(grid.width):
                color_id = grid.get_color_id(row, col)
                if color_id == EMPTY_COLOR_ID:
                    brush = QColor(238, 240, 244) if (row + col) % 2 == 0 else QColor(222, 226, 232)
                else:
                    brush = QColor(*COLOR_RGB[ItemColor(color_id)])
                pen = QPen(QColor(200, 206, 214)) if self.show_grid_lines else QPen(Qt.NoPen)
                self.scene.addRect(col * CELL, row * CELL, CELL, CELL, pen, brush)
        frontier_pen = QPen(QColor(20, 24, 30), 2)
        for col, frontier in enumerate(grid.frontier_rows()):
            if frontier is not None:
                self.scene.addLine(col * CELL, frontier * CELL, (col + 1) * CELL, frontier * CELL, frontier_pen)
        self.scene.setSceneRect(0, 0, grid.width * CELL, grid.height * CELL)

    def _cell_at_event(self, event) -> tuple[int, int] | None:
        if self.level is None:
            return None
        point = self.mapToScene(event.position().toPoint())
        col = int(point.x() // CELL)
        row = int(point.y() // CELL)
        if 0 <= row < self.level.pixel_grid.height and 0 <= col < self.level.pixel_grid.width:
            return row, col
        return None

    def _apply_at(self, row: int, col: int, erase: bool = False) -> None:
        if self.level is None:
            return
        grid = self.level.pixel_grid
        if self.mode == "eyedropper":
            value = grid.get_color_id(row, col)
            if value != EMPTY_COLOR_ID:
                self.selected_color = ItemColor(value)
                self.color_picked.emit(self.selected_color)
            return
        if self.mode == "flood":
            self.flood_fill_at(row, col)
            return
        color_id = EMPTY_COLOR_ID if erase or self.mode == "erase" else int(self.selected_color)
        if grid.get_color_id(row, col) != color_id:
            grid.set_color_id(row, col, color_id)
            self._stroke_changed = True
            self.refresh()

    def mousePressEvent(self, event) -> None:
        cell = self._cell_at_event(event)
        self._stroke_changed = False
        self._stroke_before = self.level.clone() if self.level is not None else None
        if cell is not None:
            self._apply_at(*cell, erase=event.button() == Qt.RightButton)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & (Qt.LeftButton | Qt.RightButton):
            cell = self._cell_at_event(event)
            if cell is not None:
                self._apply_at(*cell, erase=bool(event.buttons() & Qt.RightButton))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._stroke_changed:
            self.model_changed.emit("Paint pixels", self._stroke_before)
        self._stroke_changed = False
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            self.scale(1.15 if event.angleDelta().y() > 0 else 0.87, 1.15 if event.angleDelta().y() > 0 else 0.87)
        else:
            super().wheelEvent(event)

    def fill_all(self, color_id: int) -> None:
        if self.level is None:
            return
        before = self.level.clone()
        self.level.pixel_grid.fill(color_id)
        self.model_changed.emit("Fill pixels", before)
        self.refresh()

    def flood_fill(self) -> None:
        self.flood_fill_at(0, 0)

    def flood_fill_at(self, start_row: int, start_col: int) -> None:
        if self.level is None:
            return
        grid = self.level.pixel_grid
        if grid.width == 0 or grid.height == 0:
            return
        target = grid.get_color_id(start_row, start_col)
        replacement = int(self.selected_color)
        if target == replacement:
            return
        before = self.level.clone()
        queue: deque[tuple[int, int]] = deque([(start_row, start_col)])
        while queue:
            row, col = queue.popleft()
            if grid.get_color_id(row, col) != target:
                continue
            grid.set_color_id(row, col, replacement)
            for nr, nc in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if 0 <= nr < grid.height and 0 <= nc < grid.width:
                    queue.append((nr, nc))
        self.model_changed.emit("Flood fill", before)
        self.refresh()

    def zoom_in(self) -> None:
        self.scale(1.15, 1.15)

    def zoom_out(self) -> None:
        self.scale(0.87, 0.87)
