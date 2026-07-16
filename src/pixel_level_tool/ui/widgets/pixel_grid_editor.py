from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from pixel_level_tool.domain.enums import COLOR_RGB, EMPTY_COLOR_ID, ItemColor
from pixel_level_tool.domain.level_models import PixelLevelData


CELL = 24
MAX_GRID_SIZE = 256
RESIZE_GRAB_PIXELS = 8


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
        self._resize_edges: frozenset[str] = frozenset()
        self._resize_before = None
        self._resize_start_position = None
        self._resize_start_scale = (1.0, 1.0)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setToolTip("Paint pixels, or drag any edge to resize the grid")

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

    def _resize_edges_at(self, event) -> frozenset[str]:
        """Return the closest horizontal and vertical grid edges under the pointer."""
        if self.level is None:
            return frozenset()
        point = self.mapToScene(event.position().toPoint())
        grid = self.level.pixel_grid
        scale_x = max(abs(self.transform().m11()), 0.001)
        scale_y = max(abs(self.transform().m22()), 0.001)
        tolerance_x = RESIZE_GRAB_PIXELS / scale_x
        tolerance_y = RESIZE_GRAB_PIXELS / scale_y
        width = grid.width * CELL
        height = grid.height * CELL
        edges: set[str] = set()
        if -tolerance_y <= point.y() <= height + tolerance_y:
            horizontal = min(
                ((abs(point.x()), "left"), (abs(point.x() - width), "right")),
                key=lambda candidate: candidate[0],
            )
            if horizontal[0] <= tolerance_x:
                edges.add(horizontal[1])
        if -tolerance_x <= point.x() <= width + tolerance_x:
            vertical = min(
                ((abs(point.y()), "top"), (abs(point.y() - height), "bottom")),
                key=lambda candidate: candidate[0],
            )
            if vertical[0] <= tolerance_y:
                edges.add(vertical[1])
        return frozenset(edges)

    def _update_resize_cursor(self, edges: frozenset[str]) -> None:
        if edges in (frozenset(("left", "top")), frozenset(("right", "bottom"))):
            self.viewport().setCursor(Qt.SizeFDiagCursor)
        elif edges in (frozenset(("right", "top")), frozenset(("left", "bottom"))):
            self.viewport().setCursor(Qt.SizeBDiagCursor)
        elif edges & {"left", "right"}:
            self.viewport().setCursor(Qt.SizeHorCursor)
        elif edges & {"top", "bottom"}:
            self.viewport().setCursor(Qt.SizeVerCursor)
        else:
            self.viewport().unsetCursor()

    @staticmethod
    def _rounded_cell_delta(distance: float, scale: float) -> int:
        cells = distance / (CELL * scale)
        return int(cells + (0.5 if cells >= 0 else -0.5))

    def _resize_to_event(self, event) -> None:
        if self.level is None or self._resize_before is None or self._resize_start_position is None:
            return
        grid = self.level.pixel_grid
        source = self._resize_before.pixel_grid
        delta = event.position() - self._resize_start_position
        scale_x, scale_y = self._resize_start_scale
        column_delta = self._rounded_cell_delta(delta.x(), scale_x)
        row_delta = self._rounded_cell_delta(delta.y(), scale_y)
        width, height = source.width, source.height
        if "right" in self._resize_edges:
            width += column_delta
        elif "left" in self._resize_edges:
            width -= column_delta
        if "bottom" in self._resize_edges:
            height += row_delta
        elif "top" in self._resize_edges:
            height -= row_delta
        width = max(1, min(MAX_GRID_SIZE, width))
        height = max(1, min(MAX_GRID_SIZE, height))
        if (width, height) != (grid.width, grid.height):
            # Always derive the preview from the state at mouse press. This lets
            # users shrink and expand again in one drag without losing pixels.
            column_offset = width - source.width if "left" in self._resize_edges else 0
            row_offset = height - source.height if "top" in self._resize_edges else 0
            color_ids = [EMPTY_COLOR_ID] * (width * height)
            for source_row in range(source.height):
                target_row = source_row + row_offset
                if not 0 <= target_row < height:
                    continue
                for source_column in range(source.width):
                    target_column = source_column + column_offset
                    if 0 <= target_column < width:
                        color_ids[target_row * width + target_column] = source.color_ids[
                            source_row * source.width + source_column
                        ]
            grid.width = width
            grid.height = height
            grid.color_ids = color_ids
            self.refresh()

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
        resize_edges = self._resize_edges_at(event)
        if event.button() == Qt.LeftButton and resize_edges:
            self._resize_edges = resize_edges
            self._resize_before = self.level.clone() if self.level is not None else None
            self._resize_start_position = event.position()
            self._resize_start_scale = (
                max(abs(self.transform().m11()), 0.001),
                max(abs(self.transform().m22()), 0.001),
            )
            self._stroke_changed = False
            self._stroke_before = None
            self._update_resize_cursor(resize_edges)
            event.accept()
            return
        cell = self._cell_at_event(event)
        self._stroke_changed = False
        self._stroke_before = self.level.clone() if self.level is not None else None
        if cell is not None:
            self._apply_at(*cell, erase=event.button() == Qt.RightButton)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._resize_edges and event.buttons() & Qt.LeftButton:
            self._resize_to_event(event)
            event.accept()
            return
        if not event.buttons():
            super().mouseMoveEvent(event)
            self._update_resize_cursor(self._resize_edges_at(event))
            return
        if event.buttons() & (Qt.LeftButton | Qt.RightButton):
            cell = self._cell_at_event(event)
            if cell is not None:
                self._apply_at(*cell, erase=bool(event.buttons() & Qt.RightButton))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._resize_edges and event.button() == Qt.LeftButton:
            before = self._resize_before
            changed = (
                self.level is not None
                and before is not None
                and self.level.pixel_grid != before.pixel_grid
            )
            self._resize_edges = frozenset()
            self._resize_before = None
            self._resize_start_position = None
            self._update_resize_cursor(self._resize_edges_at(event))
            if changed:
                self.model_changed.emit("Resize pixel grid", before)
            event.accept()
            return
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
