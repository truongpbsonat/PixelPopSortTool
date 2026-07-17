from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QWidget

from pixel_level_tool.domain.enums import CellShape, Direction


class ShapePalette(QWidget):
    shape_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)
        self.cell_type_combo = QComboBox()
        self.cell_type_combo.addItem("Normal", False)
        self.cell_type_combo.addItem("Tunnel", True)
        self.shape_combo = QComboBox()
        for shape in CellShape:
            self.shape_combo.addItem(f"{int(shape)}  {shape.name}", shape)
        self.direction_combo = QComboBox()
        for direction in Direction:
            self.direction_combo.addItem(f"{int(direction)}  {direction.name}", direction)
        layout.addRow("Type", self.cell_type_combo)
        layout.addRow("Shape", self.shape_combo)
        layout.addRow("Direction", self.direction_combo)
        self.cell_type_combo.currentIndexChanged.connect(lambda _index: self.shape_changed.emit())
        self.shape_combo.currentIndexChanged.connect(lambda _index: self.shape_changed.emit())
        self.direction_combo.currentIndexChanged.connect(lambda _index: self.shape_changed.emit())

    @property
    def shape(self) -> CellShape:
        return self.shape_combo.currentData()

    @property
    def direction(self) -> Direction:
        return self.direction_combo.currentData()

    @property
    def is_active(self) -> bool:
        return False

    @property
    def is_tunnel(self) -> bool:
        return bool(self.cell_type_combo.currentData())

