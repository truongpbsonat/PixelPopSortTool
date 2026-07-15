from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QKeyEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from pixel_level_tool.domain.enums import COLOR_NAMES, COLOR_RGB, CellShape, Direction, ItemColor
from pixel_level_tool.domain.level_models import (
    ArrowLockCellEffectData,
    BoxCellData,
    ColorGateObstacleData,
    ElevatorObstacleData,
    FrozenCellEffectData,
    HiddenCellEffectData,
    KeyForLockedGateCellEffectData,
    LargeBlockObstacleData,
    LinkedContainerObstacleData,
    LockedGateObstacleData,
    PinsObstacleData,
    PixelLevelData,
    ScissorForWoolCrateCellEffectData,
    TunnelCellData,
    WoolCrateObstacleData,
)
from pixel_level_tool.domain.shapes import footprint


CELL = 28
INNER_CELL_BORDER = QColor(255, 255, 255, 55)
OUTLINE_BORDER = QColor(20, 24, 30)
SELECTION_BORDER = QColor(255, 235, 59)
SELECTION_HALO = QColor(20, 24, 30, 230)

FILL_Z = 1
LABEL_Z = 2
OBSTACLE_FILL_Z = 3
OBSTACLE_LINE_Z = 5
BADGE_Z = 7
SELECTION_HALO_Z = 19
SELECTION_Z = 20


class BoxGridEditor(QGraphicsView):
    model_changed = Signal(str, object)
    selection_changed = Signal(object)

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
        self.selected_is_tunnel = False
        self.selected_index: int | None = None
        self.selected_indices: set[int] = set()
        self._drag_index: int | None = None
        self._drag_offset: tuple[int, int] = (0, 0)
        self._drag_before: PixelLevelData | None = None
        self._drag_changed = False
        self.setFocusPolicy(Qt.StrongFocus)

    def set_level(self, level: PixelLevelData) -> None:
        selected_uids = {
            self.level.grid_cells[index].internal_uid
            for index in self.selected_indices
            if self.level is not None and index < len(self.level.grid_cells)
        }
        self.level = level
        self.selected_indices = {
            index for index, cell in enumerate(level.grid_cells) if cell.internal_uid in selected_uids
        }
        self.selected_index = next(iter(self.selected_indices), None)
        self._reset_drag()
        self.refresh()

    def set_tool(
        self,
        shape: CellShape,
        direction: Direction,
        color: ItemColor,
        is_active: bool,
        is_tunnel: bool = False,
    ) -> None:
        self.selected_shape = shape
        self.selected_direction = direction
        self.selected_color = color
        self.selected_active = is_active
        self.selected_is_tunnel = is_tunnel
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

    def clear_selection(self) -> None:
        if self.selected_index is None and not self.selected_indices:
            return
        self.selected_index = None
        self.selected_indices.clear()
        self.scene.clearSelection()
        self._reset_drag()
        self.selection_changed.emit([])
        self.refresh()

    def refresh(self) -> None:
        self.scene.clear()
        if self.level is None:
            return
        width = self.level.grid_cols * CELL
        height = self.level.grid_rows * CELL
        for row in range(self.level.grid_rows):
            label = QGraphicsTextItem(str(row))
            label.setDefaultTextColor(QColor(95, 103, 115))
            label.setPos(-24, self._scene_row(row) * CELL + 5)
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
        self._draw_obstacles()
        self.scene.setSceneRect(-32, -32, width + 48, height + 48)

    def _draw_cell(self, index: int, cell: BoxCellData) -> None:
        rgb = COLOR_RGB[cell.color]
        brush = QColor(*rgb)
        if not cell.is_active:
            brush.setAlpha(110)
        inner_pen = QPen(INNER_CELL_BORDER, 1)
        outline_pen = QPen(OUTLINE_BORDER, 1.5)
        outline_pen.setCosmetic(True)
        occupied = set(footprint(cell.shape, cell.direction))
        scene_occupied = {
            (cell.grid_x + dx, self._scene_row(cell.grid_y + dy))
            for dx, dy in occupied
        }
        for dx, dy in occupied:
            item = QGraphicsRectItem(
                (cell.grid_x + dx) * CELL,
                self._scene_row(cell.grid_y + dy) * CELL,
                CELL,
                CELL,
            )
            item.setBrush(brush)
            item.setPen(inner_pen)
            item.setData(0, index)
            item.setData(1, "fill")
            item.setFlag(QGraphicsItem.ItemIsSelectable, True)
            item.setZValue(FILL_Z)
            self.scene.addItem(item)
        self._draw_outline(index, scene_occupied, outline_pen)
        if index in self.selected_indices:
            halo_pen = QPen(SELECTION_HALO, 7)
            halo_pen.setCosmetic(True)
            self._draw_outline(index, scene_occupied, halo_pen, "selection-halo", SELECTION_HALO_Z)
            selection_pen = QPen(SELECTION_BORDER, 3.5)
            selection_pen.setCosmetic(True)
            self._draw_outline(index, scene_occupied, selection_pen, "selection-outline", SELECTION_Z)
        scene_top = min(scene_y for _, scene_y in scene_occupied)
        label = QGraphicsTextItem(str(cell.id or index))
        label.setDefaultTextColor(QColor(20, 24, 30))
        label.setPos(cell.grid_x * CELL + 4, scene_top * CELL + 3)
        label.setData(0, index)
        label.setData(1, "label")
        label.setZValue(LABEL_Z)
        self.scene.addItem(label)
        if isinstance(cell, TunnelCellData):
            stored_colors = ", ".join(COLOR_NAMES[stored.color] for stored in cell.stored_cells) or "empty"
            tunnel_tooltip = (
                f"Tunnel facing {cell.direction.name}; "
                f"{len(cell.stored_cells)} stored box(es): {stored_colors}"
            )
            self._draw_tunnel_icon(index, cell, scene_top, tunnel_tooltip)
            self._add_badge(
                f"TUN {self._direction_symbol(cell.direction)}",
                cell.grid_x * CELL + CELL + 1,
                scene_top * CELL + 2,
                QColor(18, 105, 120, 235),
                QColor(255, 255, 255),
                "tunnel-badge",
                index,
                tunnel_tooltip,
            )
        labels = []
        for effect in cell.effects or []:
            if isinstance(effect, FrozenCellEffectData):
                labels.append(f"ICE x{effect.frozen_count}")
            elif isinstance(effect, HiddenCellEffectData):
                labels.append("HIDE")
            elif isinstance(effect, ArrowLockCellEffectData):
                labels.append(f"AR {self._direction_symbol(effect.required_direction)}")
            elif isinstance(effect, KeyForLockedGateCellEffectData):
                labels.append(f"KEY {effect.lock_key_gate.name.removesuffix('_')}")
            elif isinstance(effect, ScissorForWoolCrateCellEffectData):
                labels.append(f"SC {effect.scissor_color.name.removesuffix('_')}")
        if labels:
            self._add_badge(
                " | ".join(labels),
                cell.grid_x * CELL + 2,
                (scene_top + cell.height) * CELL - 14,
                QColor(24, 31, 43, 225),
                QColor(255, 255, 255),
                "effect-badge",
                index,
                "Effects: " + ", ".join(labels),
            )

    def _draw_tunnel_icon(
        self,
        index: int,
        cell: TunnelCellData,
        scene_top: int,
        tooltip: str,
    ) -> None:
        """Draw a portal and rotate its arrow to match the tunnel direction."""
        center_x = (cell.grid_x + cell.width / 2) * CELL
        center_y = (scene_top + cell.height / 2) * CELL
        icon_size = min(52.0, max(22.0, min(cell.width, cell.height) * CELL * 0.62))

        # This base icon faces Up; the inner path cuts the tunnel mouth out.
        path = QPainterPath()
        path.setFillRule(Qt.OddEvenFill)
        path.addRoundedRect(-12, -9, 24, 22, 5, 5)
        path.addRoundedRect(-6, -4, 12, 17, 3, 3)
        path.moveTo(0, -17)
        path.lineTo(-6, -10)
        path.lineTo(6, -10)
        path.closeSubpath()

        icon = QGraphicsPathItem(path)
        icon.setBrush(QBrush(QColor(16, 74, 86, 235)))
        icon_pen = QPen(QColor(225, 251, 255), 1.4)
        icon_pen.setCosmetic(True)
        icon.setPen(icon_pen)
        icon.setScale(icon_size / 34.0)
        icon.setPos(center_x, center_y)
        icon.setTransformOriginPoint(0, 0)
        icon.setRotation({
            Direction.Up: 0,
            Direction.Right: 90,
            Direction.Down: 180,
            Direction.Left: 270,
        }[cell.direction])
        icon.setData(0, index)
        icon.setData(1, "tunnel-icon")
        icon.setToolTip(tooltip)
        icon.setZValue(BADGE_Z - 0.2)
        self.scene.addItem(icon)

        count_background = QGraphicsEllipseItem(center_x - 9, center_y - 9, 18, 18)
        count_background.setBrush(QBrush(QColor(248, 252, 253, 240)))
        count_pen = QPen(QColor(16, 74, 86), 1.2)
        count_pen.setCosmetic(True)
        count_background.setPen(count_pen)
        count_background.setData(0, index)
        count_background.setData(1, "tunnel-count")
        count_background.setToolTip(tooltip)
        count_background.setZValue(BADGE_Z)
        self.scene.addItem(count_background)

        count = QGraphicsTextItem(str(len(cell.stored_cells)))
        count.setDefaultTextColor(QColor(16, 74, 86))
        font = count.font()
        font.setPointSizeF(8)
        font.setBold(True)
        count.setFont(font)
        count.document().setDocumentMargin(0)
        bounds = count.boundingRect()
        count.setPos(center_x - bounds.width() / 2, center_y - bounds.height() / 2)
        count.setData(0, index)
        count.setData(1, "tunnel-count-text")
        count.setToolTip(tooltip)
        count.setZValue(BADGE_Z + 0.1)
        self.scene.addItem(count)

    def _draw_obstacles(self) -> None:
        if self.level is None:
            return
        area_colors = {
            LargeBlockObstacleData: QColor(35, 39, 47, 105),
            ColorGateObstacleData: QColor(122, 63, 181, 100),
            LockedGateObstacleData: QColor(195, 69, 54, 100),
            WoolCrateObstacleData: QColor(155, 105, 47, 105),
            ElevatorObstacleData: QColor(31, 146, 169, 100),
        }
        for obstacle in self.level.obstacles:
            if type(obstacle) in area_colors:
                color = area_colors[type(obstacle)]
                pen = QPen(color.lighter(165), 3)
                pen.setCosmetic(True)
                rect = self.scene.addRect(
                    obstacle.grid_x * CELL,
                    self._scene_top(obstacle.grid_y, obstacle.height) * CELL,
                    obstacle.width * CELL,
                    obstacle.height * CELL,
                    pen,
                    QBrush(color),
                )
                rect.setData(1, "obstacle-area")
                rect.setToolTip(self._obstacle_label(obstacle))
                rect.setZValue(OBSTACLE_FILL_Z)
                self._add_badge(
                    self._obstacle_label(obstacle),
                    obstacle.grid_x * CELL + 2,
                    self._scene_top(obstacle.grid_y, obstacle.height) * CELL + 2,
                    color.darker(170),
                    QColor(255, 255, 255),
                    "obstacle-badge",
                    tooltip=self._obstacle_label(obstacle),
                )
            elif isinstance(obstacle, (LinkedContainerObstacleData, PinsObstacleData)):
                targets = [self.level.box_by_uid(uid) for uid in obstacle.target_uids]
                targets = [cell for cell in targets if cell is not None]
                if len(targets) < 2:
                    continue
                color = QColor(155, 70, 235) if isinstance(obstacle, LinkedContainerObstacleData) else QColor(230, 150, 30)
                for left, right in zip(targets, targets[1:]):
                    pen = QPen(color, 4)
                    pen.setCosmetic(True)
                    line = self.scene.addLine(
                        (left.grid_x + left.width / 2) * CELL,
                        self._scene_center_y(left.grid_y, left.height) * CELL,
                        (right.grid_x + right.width / 2) * CELL,
                        self._scene_center_y(right.grid_y, right.height) * CELL,
                        pen,
                    )
                    line.setData(1, "obstacle-link")
                    line.setZValue(OBSTACLE_LINE_Z)
                prefix = "L" if isinstance(obstacle, LinkedContainerObstacleData) else f"P{self._direction_symbol(obstacle.required_direction)}"
                description = "Linked container" if isinstance(obstacle, LinkedContainerObstacleData) else f"Pins {self._direction_symbol(obstacle.required_direction)}"
                for target_number, target in enumerate(targets, 1):
                    self._add_badge(
                        f"{prefix}{target_number}",
                        target.grid_x * CELL + CELL + 1,
                        self._scene_top(target.grid_y, target.height) * CELL + (CELL + 2 if target.height > 1 else 2),
                        color.darker(150),
                        QColor(255, 255, 255),
                        "obstacle-badge",
                        tooltip=f"{description}, target {target_number} of {len(targets)}",
                    )

    @staticmethod
    def _direction_symbol(direction: Direction) -> str:
        return {
            Direction.Up: "↑",
            Direction.Right: "→",
            Direction.Down: "↓",
            Direction.Left: "←",
        }[direction]

    @staticmethod
    def _obstacle_label(obstacle: object) -> str:
        if isinstance(obstacle, LargeBlockObstacleData):
            return f"BLOCK x{obstacle.count}"
        if isinstance(obstacle, ColorGateObstacleData):
            return f"GATE {COLOR_NAMES[obstacle.required_color]} x{obstacle.count}"
        if isinstance(obstacle, LockedGateObstacleData):
            return f"LOCK {obstacle.lock_key_gate.name.removesuffix('_')} P{obstacle.priority}"
        if isinstance(obstacle, WoolCrateObstacleData):
            ropes = "/".join(color.name.removesuffix('_') for color in obstacle.ropes)
            return f"WOOL {ropes} P{obstacle.priority}"
        if isinstance(obstacle, ElevatorObstacleData):
            return f"LIFT L{len(obstacle.layers)}"
        return type(obstacle).__name__.replace("ObstacleData", "")

    def _add_badge(
        self,
        value: str,
        x: float,
        y: float,
        background: QColor,
        foreground: QColor,
        kind: str,
        box_index: int | None = None,
        tooltip: str = "",
    ) -> None:
        text = QGraphicsTextItem(value)
        text.setDefaultTextColor(foreground)
        font = text.font()
        font.setPointSizeF(7)
        font.setBold(True)
        text.setFont(font)
        text.document().setDocumentMargin(0)
        width = text.boundingRect().width() + 6
        height = 13
        badge = QGraphicsRectItem(x, y, width, height)
        badge.setBrush(QBrush(background))
        badge.setPen(QPen(background.lighter(145), 1))
        badge.setData(0, box_index)
        badge.setData(1, kind)
        badge.setToolTip(tooltip)
        badge.setZValue(BADGE_Z)
        self.scene.addItem(badge)
        text.setPos(x + 3, y)
        text.setData(0, box_index)
        text.setData(1, f"{kind}-text")
        text.setToolTip(tooltip)
        text.setZValue(BADGE_Z + 0.1)
        self.scene.addItem(text)

    def _draw_outline(
        self,
        index: int,
        occupied: set[tuple[int, int]],
        pen: QPen,
        kind: str = "outline",
        z_value: float = LABEL_Z,
    ) -> None:
        for grid_x, scene_y in occupied:
            left = grid_x * CELL
            top = scene_y * CELL
            right = left + CELL
            bottom = top + CELL
            if (grid_x, scene_y - 1) not in occupied:
                self._add_outline_segment(index, left, top, right, top, pen, kind, z_value)
            if (grid_x + 1, scene_y) not in occupied:
                self._add_outline_segment(index, right, top, right, bottom, pen, kind, z_value)
            if (grid_x, scene_y + 1) not in occupied:
                self._add_outline_segment(index, left, bottom, right, bottom, pen, kind, z_value)
            if (grid_x - 1, scene_y) not in occupied:
                self._add_outline_segment(index, left, top, left, bottom, pen, kind, z_value)

    def _add_outline_segment(self, index: int, x1: int, y1: int, x2: int, y2: int, pen: QPen, kind: str, z_value: float) -> None:
        item = QGraphicsLineItem(x1, y1, x2, y2)
        item.setPen(pen)
        item.setData(0, index)
        item.setData(1, kind)
        item.setZValue(z_value)
        self.scene.addItem(item)

    def _box_index_at(self, viewport_position) -> int | None:
        scene_position = self.mapToScene(viewport_position)
        for item in self.scene.items(scene_position):
            index = item.data(0)
            if index is not None:
                return int(index)
        return None

    def _scene_cell_from_event(self, event) -> tuple[int, int]:
        point = self.mapToScene(event.position().toPoint())
        scene_row = int(point.y() // CELL)
        return int(point.x() // CELL), self._model_row(scene_row)

    def _scene_row(self, model_row: int) -> int:
        if self.level is None:
            return model_row
        return self.level.grid_rows - 1 - model_row

    def _model_row(self, scene_row: int) -> int:
        if self.level is None:
            return scene_row
        return self.level.grid_rows - 1 - scene_row

    def _scene_top(self, model_y: int, height: int) -> int:
        if self.level is None:
            return model_y
        return self.level.grid_rows - model_y - height

    def _scene_center_y(self, model_y: int, height: int) -> float:
        if self.level is None:
            return model_y + height / 2
        return self.level.grid_rows - model_y - height / 2

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
        if event.button() == Qt.RightButton:
            self.clear_selection()
            event.accept()
            return
        col, row = self._scene_cell_from_event(event)
        clicked_index = self._box_index_at(event.position().toPoint())
        if event.button() == Qt.LeftButton and clicked_index is not None:
            if event.modifiers() & Qt.ControlModifier:
                if clicked_index in self.selected_indices:
                    self.selected_indices.remove(clicked_index)
                else:
                    self.selected_indices.add(clicked_index)
                self.selected_index = clicked_index if clicked_index in self.selected_indices else next(iter(self.selected_indices), None)
                self.selection_changed.emit(sorted(self.selected_indices))
                self.refresh()
                return
            self.selected_indices = {clicked_index}
            self.selected_index = clicked_index
            self.selection_changed.emit([clicked_index])
            cell = self.level.grid_cells[self.selected_index]
            self._drag_index = self.selected_index
            self._drag_offset = (col - cell.grid_x, row - cell.grid_y)
            self._drag_before = self.level.clone()
            self._drag_changed = False
            self.refresh()
            return
        if event.button() == Qt.LeftButton and event.modifiers() & Qt.ControlModifier:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.LeftButton and 0 <= row < self.level.grid_rows and 0 <= col < self.level.grid_cols:
            before = self.level.clone()
            cell_data = {
                "grid_x": col,
                "grid_y": row,
                "shape": self.selected_shape,
                "direction": self.selected_direction,
                "color": self.selected_color,
                "is_active": self.selected_active,
            }
            if self.selected_is_tunnel:
                stored_cell = BoxCellData(
                    grid_x=0,
                    grid_y=0,
                    shape=self.selected_shape,
                    direction=self.selected_direction,
                    color=self.selected_color,
                    is_active=self.selected_active,
                )
                box = TunnelCellData(**cell_data, stored_cells=[stored_cell])
            else:
                box = BoxCellData(**cell_data)
            if self.level.add_box(box):
                self.selected_index = len(self.level.grid_cells) - 1
                self.selected_indices = {self.selected_index}
                self.selection_changed.emit([self.selected_index])
                self.model_changed.emit("Add tunnel" if self.selected_is_tunnel else "Add box", before)
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
        if event.modifiers() & Qt.ControlModifier:
            selected = {int(item.data(0)) for item in self.scene.selectedItems() if item.data(0) is not None}
            if selected:
                self.selected_indices.update(selected)
                self.selected_index = next(iter(self.selected_indices), None)
                self.selection_changed.emit(sorted(self.selected_indices))
                self.refresh()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 0.87
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.clear_selection()
            event.accept()
            return
        if self.level is not None and self.selected_index is not None:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                before = self.level.clone()
                for index in sorted(self.selected_indices or {self.selected_index}, reverse=True):
                    self.level.remove_box(index)
                self.selected_index = None
                self.selected_indices.clear()
                self.selection_changed.emit([])
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
                        duplicate = deepcopy(source)
                        duplicate.grid_x = x
                        duplicate.grid_y = y
                        duplicate.id = 0
                        duplicate.internal_uid = uuid4().hex
                        if self.level.add_box(duplicate):
                            self.selected_index = len(self.level.grid_cells) - 1
                            self.selected_indices = {self.selected_index}
                            self.selection_changed.emit([self.selected_index])
                            self.model_changed.emit("Duplicate box", before)
                            self.refresh()
                            return
        super().keyPressEvent(event)

    def zoom_in(self) -> None:
        self.scale(1.15, 1.15)

    def zoom_out(self) -> None:
        self.scale(0.87, 0.87)
