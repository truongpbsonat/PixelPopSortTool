from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel

from pixel_level_tool.domain.enums import COLOR_NAMES, COLOR_RGB, ItemColor


class ReplaceColorDialog(QDialog):
    def __init__(self, initial_source: ItemColor = ItemColor.Red, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Replace Color in Current Level")
        layout = QFormLayout(self)
        layout.addRow(QLabel("Replace the color in both Box Ball Grid and Pixel Grid."))

        self.source_combo = self._create_color_combo()
        self.target_combo = self._create_color_combo()
        self.source_combo.setCurrentIndex(self.source_combo.findData(initial_source))
        target = next(color for color in ItemColor if color != initial_source)
        self.target_combo.setCurrentIndex(self.target_combo.findData(target))
        layout.addRow("Color A", self.source_combo)
        layout.addRow("Color B", self.target_combo)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Replace All")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.source_combo.currentIndexChanged.connect(self._update_apply_state)
        self.target_combo.currentIndexChanged.connect(self._update_apply_state)
        layout.addRow(self.buttons)
        self._update_apply_state()

    @staticmethod
    def _create_color_combo() -> QComboBox:
        combo = QComboBox()
        combo.setIconSize(QSize(18, 18))
        for color in ItemColor:
            pixmap = QPixmap(18, 18)
            pixmap.fill(QColor(*COLOR_RGB[color]))
            combo.addItem(QIcon(pixmap), f"{int(color):2d}  {COLOR_NAMES[color]}", color)
        return combo

    @property
    def source_color(self) -> ItemColor:
        return self.source_combo.currentData()

    @property
    def target_color(self) -> ItemColor:
        return self.target_combo.currentData()

    def _update_apply_state(self) -> None:
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(self.source_color != self.target_color)
