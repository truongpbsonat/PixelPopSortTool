from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pixel_level_tool.domain.enums import COLOR_RGB, CellShape, Direction, ItemColor, LockKeyGate, WoolCrateColor
from pixel_level_tool.domain.level_models import (
    ArrowLockCellEffectData,
    BoxCellData,
    ColorGateObstacleData,
    ElevatorLayerData,
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


EFFECT_TYPES = {
    "Frozen": FrozenCellEffectData,
    "Hidden": HiddenCellEffectData,
    "ArrowLock": ArrowLockCellEffectData,
    "KeyForLockedGate": KeyForLockedGateCellEffectData,
    "ScissorForWoolCrate": ScissorForWoolCrateCellEffectData,
}


def _effect_name(effect: object) -> str:
    return type(effect).__name__.replace("CellEffectData", "")


def _new_effect(name: str):
    return EFFECT_TYPES[name]()


def _color_icon(color: ItemColor) -> QIcon:
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor(35, 40, 48))
    painter.setBrush(QColor(*COLOR_RGB[color]))
    painter.drawRoundedRect(1, 1, 16, 16, 4, 4)
    painter.end()
    return QIcon(pixmap)


class EffectEditorDialog(QDialog):
    def __init__(self, cell: BoxCellData, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cell Effects")
        self.cell = cell
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        layout.addWidget(self.list)
        row = QHBoxLayout()
        self.add_combo = QComboBox()
        self.add_combo.addItems(EFFECT_TYPES)
        add = QPushButton("Add")
        remove = QPushButton("Remove")
        row.addWidget(self.add_combo)
        row.addWidget(add)
        row.addWidget(remove)
        layout.addLayout(row)
        self.value_label = QLabel("Value")
        self.value = QSpinBox()
        self.value.setRange(0, 99999)
        self.enum_value = QComboBox()
        layout.addWidget(self.value_label)
        layout.addWidget(self.value)
        layout.addWidget(self.enum_value)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        add.clicked.connect(self._add)
        remove.clicked.connect(self._remove)
        self.list.currentRowChanged.connect(self._show_value)
        self.value.valueChanged.connect(self._apply_value)
        self.enum_value.currentIndexChanged.connect(self._apply_value)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._refresh()

    def _refresh(self) -> None:
        row = self.list.currentRow()
        self.list.clear()
        self.list.addItems([_effect_name(effect) for effect in self.cell.effects or []])
        if self.list.count():
            self.list.setCurrentRow(max(0, min(row, self.list.count() - 1)))
        else:
            self._show_value(-1)

    def _add(self) -> None:
        effect_type = EFFECT_TYPES[self.add_combo.currentText()]
        if any(isinstance(effect, effect_type) for effect in self.cell.effects or []):
            return
        self.cell.effects = list(self.cell.effects or []) + [_new_effect(self.add_combo.currentText())]
        self._refresh()
        self.list.setCurrentRow(self.list.count() - 1)

    def _remove(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        effects = list(self.cell.effects or [])
        effects.pop(row)
        self.cell.effects = effects or None
        self._refresh()

    def _show_value(self, row: int) -> None:
        self.value.hide()
        self.enum_value.hide()
        self.value_label.hide()
        if row < 0 or row >= len(self.cell.effects or []):
            return
        effect = self.cell.effects[row]
        self.value_label.show()
        if isinstance(effect, FrozenCellEffectData):
            self.value_label.setText("Frozen Count")
            self.value.blockSignals(True)
            self.value.setValue(effect.frozen_count)
            self.value.blockSignals(False)
            self.value.show()
        else:
            enum_type = None
            current = 0
            if isinstance(effect, ArrowLockCellEffectData): enum_type, current = Direction, effect.required_direction
            elif isinstance(effect, KeyForLockedGateCellEffectData): enum_type, current = LockKeyGate, effect.lock_key_gate
            elif isinstance(effect, ScissorForWoolCrateCellEffectData): enum_type, current = WoolCrateColor, effect.scissor_color
            if enum_type is None:
                self.value_label.setText("No properties")
                return
            self.enum_value.blockSignals(True)
            self.enum_value.clear()
            for member in enum_type:
                self.enum_value.addItem(member.name.removesuffix("_"), int(member))
            self.enum_value.setCurrentIndex(max(0, self.enum_value.findData(int(current))))
            self.enum_value.blockSignals(False)
            self.enum_value.show()

    def _apply_value(self) -> None:
        row = self.list.currentRow()
        if row < 0 or row >= len(self.cell.effects or []):
            return
        effect = self.cell.effects[row]
        value = self.enum_value.currentData()
        if isinstance(effect, FrozenCellEffectData): effect.frozen_count = self.value.value()
        elif isinstance(effect, ArrowLockCellEffectData) and value is not None: effect.required_direction = Direction(value)
        elif isinstance(effect, KeyForLockedGateCellEffectData) and value is not None: effect.lock_key_gate = LockKeyGate(value)
        elif isinstance(effect, ScissorForWoolCrateCellEffectData) and value is not None: effect.scissor_color = WoolCrateColor(value)


class BoxInspector(QWidget):
    model_changed = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.level: PixelLevelData | None = None
        self.selected_indices: list[int] = []
        layout = QVBoxLayout(self)
        self.title = QLabel("Select one box")
        layout.addWidget(self.title)

        self.stored_panel = QWidget()
        stored_layout = QVBoxLayout(self.stored_panel)
        stored_layout.setContentsMargins(0, 0, 0, 0)
        self.stored_label = QLabel("Stored boxes (JSON order)")
        stored_layout.addWidget(self.stored_label)
        self.stored_cells = QListWidget()
        self.stored_cells.setIconSize(QSize(18, 18))
        self.stored_cells.setAlternatingRowColors(True)
        stored_layout.addWidget(self.stored_cells)
        stored_form = QFormLayout()
        self.stored_x = QSpinBox()
        self.stored_y = QSpinBox()
        self.stored_x.setRange(-9999, 9999)
        self.stored_y.setRange(-9999, 9999)
        self.stored_shape = QComboBox()
        self.stored_direction = QComboBox()
        self.stored_color = QComboBox()
        self.stored_active = QCheckBox()
        for shape in CellShape:
            self.stored_shape.addItem(f"{int(shape)}  {shape.name}", int(shape))
        for direction in Direction:
            self.stored_direction.addItem(f"{int(direction)}  {direction.name}", int(direction))
        for color in ItemColor:
            self.stored_color.addItem(_color_icon(color), f"{int(color)}  {color.name}", int(color))
        stored_form.addRow("Grid X", self.stored_x)
        stored_form.addRow("Grid Y", self.stored_y)
        stored_form.addRow("Shape", self.stored_shape)
        stored_form.addRow("Direction", self.stored_direction)
        stored_form.addRow("Color", self.stored_color)
        stored_form.addRow("Active", self.stored_active)
        stored_layout.addLayout(stored_form)
        self.stored_effects_button = QPushButton("Edit Stored Box Effects")
        stored_layout.addWidget(self.stored_effects_button)
        layout.addWidget(self.stored_panel)

        self.effects_label = QLabel("Box effects")
        layout.addWidget(self.effects_label)
        self.effects = QListWidget()
        layout.addWidget(self.effects)
        row = QHBoxLayout()
        self.add_combo = QComboBox()
        self.add_combo.addItems(EFFECT_TYPES)
        self.add_button = QPushButton("Add Effect")
        self.remove_button = QPushButton("Remove")
        self.edit_button = QPushButton("Edit")
        row.addWidget(self.add_combo)
        row.addWidget(self.add_button)
        row.addWidget(self.edit_button)
        row.addWidget(self.remove_button)
        layout.addLayout(row)
        layout.addStretch(1)
        self.add_button.clicked.connect(self._add)
        self.remove_button.clicked.connect(self._remove)
        self.edit_button.clicked.connect(self._edit)
        self.effects.itemDoubleClicked.connect(lambda _: self._edit())
        self.stored_cells.currentRowChanged.connect(self._show_stored)
        self.stored_cells.itemDoubleClicked.connect(lambda _: self.stored_effects_button.click())
        self.stored_x.editingFinished.connect(self._apply_stored)
        self.stored_y.editingFinished.connect(self._apply_stored)
        self.stored_shape.currentIndexChanged.connect(self._apply_stored)
        self.stored_direction.currentIndexChanged.connect(self._apply_stored)
        self.stored_color.currentIndexChanged.connect(self._apply_stored)
        self.stored_active.toggled.connect(self._apply_stored)
        self.stored_effects_button.clicked.connect(self._edit_stored_effects)
        self._updating_stored = False
        self.stored_panel.hide()

    def set_context(self, level: PixelLevelData, selected_indices: list[int]) -> None:
        self.level = level
        self.selected_indices = [index for index in selected_indices if index < len(level.grid_cells)]
        self._refresh()

    def _cell(self) -> BoxCellData | None:
        if self.level is None or len(self.selected_indices) != 1:
            return None
        return self.level.grid_cells[self.selected_indices[0]]

    def _refresh(self) -> None:
        cell = self._cell()
        self.effects.clear()
        stored_row = self.stored_cells.currentRow()
        self._updating_stored = True
        self.stored_cells.clear()
        if cell is None:
            self.title.setText("Select one box")
        elif isinstance(cell, TunnelCellData):
            self.title.setText(f"Tunnel {cell.id or self.selected_indices[0]} at ({cell.grid_x}, {cell.grid_y}) — {len(cell.stored_cells)} stored")
            for index, stored in enumerate(cell.stored_cells):
                effects = ", ".join(_effect_name(effect) for effect in stored.effects or [])
                suffix = f" · {effects}" if effects else ""
                item = QListWidgetItem(
                    _color_icon(stored.color),
                    f"#{index + 1}  {stored.color.name} · {stored.shape.name} · {stored.direction.name}{suffix}",
                )
                item.setData(Qt.UserRole, index)
                item.setToolTip(
                    f"storedCells[{index}] — color {stored.color.name}, shape {stored.shape.name}, "
                    f"direction {stored.direction.name}"
                )
                self.stored_cells.addItem(item)
        else:
            self.title.setText(f"Box {cell.id or self.selected_indices[0]} at ({cell.grid_x}, {cell.grid_y})")
        is_tunnel = isinstance(cell, TunnelCellData)
        self.stored_panel.setVisible(is_tunnel)
        self.effects_label.setVisible(not is_tunnel)
        self.effects.setVisible(not is_tunnel)
        if cell is not None:
            self.effects.addItems([_effect_name(effect) for effect in cell.effects or []])
        can_edit_effects = cell is not None and not is_tunnel
        for widget in (self.add_button, self.remove_button, self.edit_button, self.add_combo):
            widget.setVisible(not is_tunnel)
            widget.setEnabled(can_edit_effects)
        if is_tunnel and self.stored_cells.count():
            self.stored_cells.setCurrentRow(max(0, min(stored_row, self.stored_cells.count() - 1)))
        self._updating_stored = False
        self._show_stored(self.stored_cells.currentRow())

    def _stored_cell(self) -> BoxCellData | None:
        tunnel = self._cell()
        row = self.stored_cells.currentRow()
        if not isinstance(tunnel, TunnelCellData) or not 0 <= row < len(tunnel.stored_cells):
            return None
        return tunnel.stored_cells[row]

    def _show_stored(self, row: int) -> None:
        if self._updating_stored:
            return
        stored = self._stored_cell()
        self._updating_stored = True
        controls = (
            self.stored_x,
            self.stored_y,
            self.stored_shape,
            self.stored_direction,
            self.stored_color,
            self.stored_active,
            self.stored_effects_button,
        )
        for control in controls:
            control.setEnabled(stored is not None)
        if stored is not None:
            self.stored_x.setValue(stored.grid_x)
            self.stored_y.setValue(stored.grid_y)
            self.stored_shape.setCurrentIndex(self.stored_shape.findData(int(stored.shape)))
            self.stored_direction.setCurrentIndex(self.stored_direction.findData(int(stored.direction)))
            self.stored_color.setCurrentIndex(self.stored_color.findData(int(stored.color)))
            self.stored_active.setChecked(stored.is_active)
        self._updating_stored = False

    def _apply_stored(self) -> None:
        if self._updating_stored or self.level is None:
            return
        stored = self._stored_cell()
        if stored is None:
            return
        values = (
            self.stored_x.value(),
            self.stored_y.value(),
            CellShape(self.stored_shape.currentData()),
            Direction(self.stored_direction.currentData()),
            ItemColor(self.stored_color.currentData()),
            self.stored_active.isChecked(),
        )
        current = (stored.grid_x, stored.grid_y, stored.shape, stored.direction, stored.color, stored.is_active)
        if values == current:
            return
        before = self.level.clone()
        (
            stored.grid_x,
            stored.grid_y,
            stored.shape,
            stored.direction,
            stored.color,
            stored.is_active,
        ) = values
        self.model_changed.emit("Edit tunnel stored box", before)

    def _edit_stored_effects(self) -> None:
        stored = self._stored_cell()
        if stored is None or self.level is None:
            return
        before = self.level.clone()
        working = deepcopy(stored)
        dialog = EffectEditorDialog(working, self)
        if dialog.exec() != QDialog.Accepted:
            return
        if working.effects == stored.effects:
            return
        stored.effects = working.effects
        self.model_changed.emit("Edit tunnel stored box effects", before)

    def _add(self) -> None:
        cell = self._cell()
        if cell is None:
            return
        effect_type = EFFECT_TYPES[self.add_combo.currentText()]
        if any(isinstance(effect, effect_type) for effect in cell.effects or []):
            return
        before = self.level.clone()
        cell.effects = list(cell.effects or []) + [_new_effect(self.add_combo.currentText())]
        self.model_changed.emit("Add box effect", before)

    def _remove(self) -> None:
        cell = self._cell()
        row = self.effects.currentRow()
        if cell is None or row < 0:
            return
        before = self.level.clone()
        effects = list(cell.effects or [])
        effects.pop(row)
        cell.effects = effects or None
        self.model_changed.emit("Remove box effect", before)

    def _edit(self) -> None:
        cell = self._cell()
        if cell is None:
            return
        before = self.level.clone()
        working = deepcopy(cell)
        dialog = EffectEditorDialog(working, self)
        if dialog.exec() != QDialog.Accepted:
            return
        cell.effects = working.effects
        self.model_changed.emit("Edit box effects", before)


class ElevatorLayersDialog(QDialog):
    def __init__(self, elevator: ElevatorObstacleData, surface_cells: list[BoxCellData], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Elevator Layers (bottom to top)")
        self.resize(760, 480)
        self.elevator = elevator
        self.surface_cells = surface_cells
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.layers = QListWidget()
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["X", "Y", "Shape", "Direction", "Color", "Active"])
        top.addWidget(self.layers, 1)
        top.addWidget(self.table, 4)
        root.addLayout(top)
        row = QHBoxLayout()
        for text, handler in (("Add", self._add), ("Duplicate", self._duplicate), ("Remove", self._remove), ("Up", self._up), ("Down", self._down), ("Cell Effects", self._effects)):
            button = QPushButton(text)
            button.clicked.connect(handler)
            row.addWidget(button)
        root.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        root.addWidget(buttons)
        self.layers.currentRowChanged.connect(self._load_table)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self._refresh_layers()

    def _refresh_layers(self, row: int | None = None) -> None:
        current = self.layers.currentRow() if row is None else row
        self.layers.clear()
        self.layers.addItems([f"Layer {index + 1}{' (bottom)' if index == 0 else ''}" for index in range(len(self.elevator.layers))])
        if self.layers.count(): self.layers.setCurrentRow(max(0, min(current, self.layers.count() - 1)))
        else: self.table.setRowCount(0)

    def _clone_surface(self) -> ElevatorLayerData:
        cells = []
        for source in self.surface_cells:
            clone = deepcopy(source)
            clone.id = 0
            clone.internal_uid = uuid4().hex
            cells.append(clone)
        return ElevatorLayerData(cells)

    def _add(self) -> None:
        self._store_table()
        self.elevator.layers.append(self._clone_surface())
        self._refresh_layers(len(self.elevator.layers) - 1)

    def _duplicate(self) -> None:
        self._store_table()
        row = self.layers.currentRow()
        if row < 0: return
        clone = deepcopy(self.elevator.layers[row])
        for cell in clone.cells:
            cell.id = 0
            cell.internal_uid = uuid4().hex
        self.elevator.layers.insert(row + 1, clone)
        self._refresh_layers(row + 1)

    def _remove(self) -> None:
        row = self.layers.currentRow()
        if row >= 0:
            self.elevator.layers.pop(row)
            self._refresh_layers(max(0, row - 1))

    def _up(self) -> None:
        self._store_table(); row = self.layers.currentRow()
        if row > 0:
            self.elevator.layers[row - 1], self.elevator.layers[row] = self.elevator.layers[row], self.elevator.layers[row - 1]
            self._refresh_layers(row - 1)

    def _down(self) -> None:
        self._store_table(); row = self.layers.currentRow()
        if 0 <= row < len(self.elevator.layers) - 1:
            self.elevator.layers[row + 1], self.elevator.layers[row] = self.elevator.layers[row], self.elevator.layers[row + 1]
            self._refresh_layers(row + 1)

    def _load_table(self, row: int) -> None:
        self.table.setRowCount(0)
        if row < 0 or row >= len(self.elevator.layers): return
        for cell in self.elevator.layers[row].cells:
            r = self.table.rowCount(); self.table.insertRow(r)
            values = [cell.grid_x, cell.grid_y, int(cell.shape), int(cell.direction), int(cell.color), int(cell.is_active)]
            for column, value in enumerate(values): self.table.setItem(r, column, QTableWidgetItem(str(value)))

    def _store_table(self) -> None:
        row = self.layers.currentRow()
        if row < 0 or row >= len(self.elevator.layers): return
        cells = self.elevator.layers[row].cells
        for index, cell in enumerate(cells[:self.table.rowCount()]):
            try:
                cell.grid_x = int(self.table.item(index, 0).text())
                cell.grid_y = int(self.table.item(index, 1).text())
                cell.shape = CellShape(int(self.table.item(index, 2).text()))
                cell.direction = Direction(int(self.table.item(index, 3).text()))
                cell.color = ItemColor(int(self.table.item(index, 4).text()))
                cell.is_active = bool(int(self.table.item(index, 5).text()))
            except (ValueError, AttributeError):
                pass

    def _effects(self) -> None:
        row, cell_row = self.layers.currentRow(), self.table.currentRow()
        if row < 0 or cell_row < 0 or cell_row >= len(self.elevator.layers[row].cells): return
        cell = self.elevator.layers[row].cells[cell_row]
        working = deepcopy(cell)
        if EffectEditorDialog(working, self).exec() == QDialog.Accepted:
            cell.effects = working.effects

    def _accept(self) -> None:
        self._store_table()
        self.accept()


class ObstaclesPanel(QWidget):
    model_changed = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.level: PixelLevelData | None = None
        self.selected_indices: list[int] = []
        root = QVBoxLayout(self)
        self.list = QListWidget(); root.addWidget(self.list)
        add_row = QHBoxLayout()
        self.type_combo = QComboBox(); self.type_combo.addItems(["LinkedContainer", "Pins", "LargeBlock", "ColorGate", "LockedGate", "WoolCrate", "Elevator"])
        self.add_button = QPushButton("Add from Selection"); self.remove_button = QPushButton("Remove")
        add_row.addWidget(self.type_combo); add_row.addWidget(self.add_button); add_row.addWidget(self.remove_button); root.addLayout(add_row)
        form = QFormLayout()
        self.spins = {}
        for name in ("gridX", "gridY", "width", "height", "count", "priority"):
            spin = QSpinBox(); spin.setRange(-9999 if name in ("gridX", "gridY") else 0, 99999); spin.editingFinished.connect(self._apply_properties)
            self.spins[name] = spin; form.addRow(name, spin)
        self.direction = QComboBox(); self.key = QComboBox(); self.color = QComboBox(); self.ropes = QLineEdit()
        for member in Direction: self.direction.addItem(member.name, int(member))
        for member in LockKeyGate: self.key.addItem(member.name.removesuffix("_"), int(member))
        for member in ItemColor: self.color.addItem(member.name, int(member))
        self.direction.currentIndexChanged.connect(self._apply_properties); self.key.currentIndexChanged.connect(self._apply_properties); self.color.currentIndexChanged.connect(self._apply_properties); self.ropes.editingFinished.connect(self._apply_properties)
        form.addRow("direction", self.direction); form.addRow("key", self.key); form.addRow("color", self.color); form.addRow("ropes", self.ropes)
        root.addLayout(form)
        self.layers_button = QPushButton("Edit Elevator Layers"); root.addWidget(self.layers_button)
        self.status = QLabel(); self.status.setWordWrap(True); root.addWidget(self.status)
        self.add_button.clicked.connect(self._add); self.remove_button.clicked.connect(self._remove); self.list.currentRowChanged.connect(self._show_properties); self.layers_button.clicked.connect(self._edit_layers)
        self._updating = False

    def set_context(self, level: PixelLevelData, selected_indices: list[int]) -> None:
        current = self.list.currentRow()
        self.level = level; self.selected_indices = [i for i in selected_indices if i < len(level.grid_cells)]
        self.list.blockSignals(True); self.list.clear()
        self.list.addItems([f"{type(item).__name__.replace('ObstacleData', '')} #{item.id or index}" for index, item in enumerate(level.obstacles)])
        self.list.blockSignals(False)
        if self.list.count(): self.list.setCurrentRow(max(0, min(current, self.list.count() - 1)))
        else: self._show_properties(-1)

    def _selected_cells(self) -> list[BoxCellData]:
        if self.level is None: return []
        return [self.level.grid_cells[i] for i in self.selected_indices]

    def _bbox(self, cells: list[BoxCellData]) -> tuple[int, int, int, int]:
        occupied = [point for cell in cells for point in cell.occupied_cells()]
        xs, ys = [p[0] for p in occupied], [p[1] for p in occupied]
        return min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1

    def _add(self) -> None:
        cells = self._selected_cells(); name = self.type_combo.currentText()
        if (name == "LinkedContainer" and len(cells) != 2) or (name == "Pins" and len(cells) < 2) or (name not in ("LinkedContainer", "Pins") and not cells):
            self.status.setText("Select exactly 2 boxes for LinkedContainer, 2+ for Pins, or 1+ for an area obstacle."); return
        before = self.level.clone(); uids = [cell.internal_uid for cell in cells]
        if name == "LinkedContainer": obstacle = LinkedContainerObstacleData(uids)
        elif name == "Pins": obstacle = PinsObstacleData(uids)
        else:
            x, y, width, height = self._bbox(cells)
            if name == "LargeBlock": obstacle = LargeBlockObstacleData(x, y, width, height)
            elif name == "ColorGate": obstacle = ColorGateObstacleData(x, y, width, height)
            elif name == "LockedGate": obstacle = LockedGateObstacleData(x, y, width, height)
            elif name == "WoolCrate": obstacle = WoolCrateObstacleData(x, y, width, height)
            else:
                hidden = []
                for source in cells:
                    clone = deepcopy(source); clone.id = 0; clone.internal_uid = uuid4().hex; hidden.append(clone)
                obstacle = ElevatorObstacleData(x, y, width, height, [ElevatorLayerData(hidden)])
        self.level.obstacles.append(obstacle); self.model_changed.emit(f"Add {name} obstacle", before)

    def _remove(self) -> None:
        row = self.list.currentRow()
        if self.level is None or row < 0: return
        before = self.level.clone(); self.level.obstacles.pop(row); self.model_changed.emit("Remove obstacle", before)

    def _show_properties(self, row: int) -> None:
        self._updating = True
        obstacle = self.level.obstacles[row] if self.level is not None and 0 <= row < len(self.level.obstacles) else None
        area = isinstance(obstacle, (LargeBlockObstacleData, ColorGateObstacleData, LockedGateObstacleData, WoolCrateObstacleData, ElevatorObstacleData))
        for name, spin in self.spins.items():
            spin.setEnabled(area and hasattr(obstacle, {"gridX":"grid_x","gridY":"grid_y"}.get(name, name)))
            if obstacle is not None and spin.isEnabled(): spin.setValue(getattr(obstacle, {"gridX":"grid_x","gridY":"grid_y"}.get(name, name)))
        self.direction.setEnabled(isinstance(obstacle, PinsObstacleData)); self.key.setEnabled(isinstance(obstacle, LockedGateObstacleData)); self.color.setEnabled(isinstance(obstacle, ColorGateObstacleData)); self.ropes.setEnabled(isinstance(obstacle, WoolCrateObstacleData)); self.layers_button.setEnabled(isinstance(obstacle, ElevatorObstacleData))
        if isinstance(obstacle, PinsObstacleData): self.direction.setCurrentIndex(self.direction.findData(int(obstacle.required_direction)))
        if isinstance(obstacle, LockedGateObstacleData): self.key.setCurrentIndex(self.key.findData(int(obstacle.lock_key_gate)))
        if isinstance(obstacle, ColorGateObstacleData): self.color.setCurrentIndex(self.color.findData(int(obstacle.required_color)))
        if isinstance(obstacle, WoolCrateObstacleData): self.ropes.setText(",".join(color.name.removesuffix("_") for color in obstacle.ropes))
        self._updating = False

    def _apply_properties(self) -> None:
        if self._updating or self.level is None: return
        row = self.list.currentRow()
        if row < 0: return
        obstacle = self.level.obstacles[row]; before = self.level.clone(); changed = False
        mapping = {"gridX":"grid_x", "gridY":"grid_y", "width":"width", "height":"height", "count":"count", "priority":"priority"}
        for name, attr in mapping.items():
            if self.spins[name].isEnabled() and getattr(obstacle, attr) != self.spins[name].value(): setattr(obstacle, attr, self.spins[name].value()); changed = True
        if isinstance(obstacle, PinsObstacleData): value = Direction(self.direction.currentData()); changed |= obstacle.required_direction != value; obstacle.required_direction = value
        elif isinstance(obstacle, LockedGateObstacleData): value = LockKeyGate(self.key.currentData()); changed |= obstacle.lock_key_gate != value; obstacle.lock_key_gate = value
        elif isinstance(obstacle, ColorGateObstacleData): value = ItemColor(self.color.currentData()); changed |= obstacle.required_color != value; obstacle.required_color = value
        elif isinstance(obstacle, WoolCrateObstacleData):
            try: ropes = [WoolCrateColor[token.strip() if token.strip() != "None" else "None_"] for token in self.ropes.text().split(",") if token.strip()]
            except KeyError: self.status.setText("Ropes must be comma-separated color names."); return
            changed |= obstacle.ropes != ropes; obstacle.ropes = ropes
        if changed: self.model_changed.emit("Edit obstacle", before)

    def _edit_layers(self) -> None:
        if self.level is None: return
        row = self.list.currentRow(); obstacle = self.level.obstacles[row] if row >= 0 else None
        if not isinstance(obstacle, ElevatorObstacleData): return
        before = self.level.clone(); working = deepcopy(obstacle)
        surfaces = [cell for cell in self.level.grid_cells if obstacle.grid_x <= cell.grid_x < obstacle.grid_x + obstacle.width and obstacle.grid_y <= cell.grid_y < obstacle.grid_y + obstacle.height]
        if ElevatorLayersDialog(working, surfaces, self).exec() == QDialog.Accepted:
            obstacle.layers = working.layers; self.model_changed.emit("Edit Elevator layers", before)
