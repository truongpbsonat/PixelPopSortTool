from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QSpinBox


class ResizeGridDialog(QDialog):
    def __init__(self, title: str, width_label: str, height_label: str, width: int, height: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QFormLayout(self)
        layout.addRow(QLabel("Existing data is preserved from the top-left corner."))
        self.width = QSpinBox()
        self.width.setRange(1, 256)
        self.width.setValue(width)
        self.height = QSpinBox()
        self.height.setRange(1, 256)
        self.height.setValue(height)
        layout.addRow(width_label, self.width)
        layout.addRow(height_label, self.height)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

