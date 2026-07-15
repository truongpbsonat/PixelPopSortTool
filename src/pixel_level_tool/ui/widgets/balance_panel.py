from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from pixel_level_tool.domain.enums import COLOR_NAMES, COLOR_RGB, ItemColor
from pixel_level_tool.domain.level_models import PixelLevelData


class BalancePanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.summary = QLabel("Not balanced")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Color", "ID", "Source", "Target", "Delta"])
        layout.addWidget(self.summary)
        layout.addWidget(self.table)

    def refresh(self, level: PixelLevelData) -> None:
        source = level.source_histogram()
        target = level.target_histogram()
        self.table.setRowCount(len(ItemColor))
        for row, color in enumerate(ItemColor):
            rgb = COLOR_RGB[color]
            swatch = QTableWidgetItem(COLOR_NAMES[color])
            swatch.setBackground(QColor(*rgb))
            swatch.setForeground(QColor(255, 255, 255) if sum(rgb) < 360 else QColor(32, 32, 32))
            source_count = source.get(int(color), 0)
            target_count = target.get(int(color), 0)
            delta = source_count - target_count
            self.table.setItem(row, 0, swatch)
            self.table.setItem(row, 1, QTableWidgetItem(str(int(color))))
            self.table.setItem(row, 2, QTableWidgetItem(str(source_count)))
            self.table.setItem(row, 3, QTableWidgetItem(str(target_count)))
            self.table.setItem(row, 4, QTableWidgetItem(str(delta)))
        balanced = source == target and sum(source.values()) > 0
        self.summary.setText(
            f"{'Balanced' if balanced else 'Not Balanced'} | "
            f"Source {sum(source.values())} | Target {sum(target.values())}"
        )

