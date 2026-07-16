from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QSpinBox


class NewLevelDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Pixel Level")
        layout = QFormLayout(self)
        self.level = QSpinBox()
        self.level.setRange(1, 99999)
        self.level.setValue(1)
        self.box_rows = QSpinBox()
        self.box_rows.setRange(1, 200)
        self.box_rows.setValue(10)
        self.box_cols = QSpinBox()
        self.box_cols.setRange(1, 200)
        self.box_cols.setValue(10)
        self.pixel_width = QSpinBox()
        self.pixel_width.setRange(1, 256)
        self.pixel_width.setValue(8)
        self.pixel_height = QSpinBox()
        self.pixel_height.setRange(1, 256)
        self.pixel_height.setValue(8)
        layout.addRow("Level", self.level)
        layout.addRow("Box rows", self.box_rows)
        layout.addRow("Box cols", self.box_cols)
        layout.addRow("Pixel width", self.pixel_width)
        layout.addRow("Pixel height", self.pixel_height)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

