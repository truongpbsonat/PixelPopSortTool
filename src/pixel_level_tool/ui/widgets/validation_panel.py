from __future__ import annotations

from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from pixel_level_tool.services.level_validator import ValidationResult


class ValidationPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        layout.addWidget(self.list)

    def set_result(self, result: ValidationResult) -> None:
        self.list.clear()
        if not result.messages:
            self.list.addItem("No validation messages.")
            return
        for message in result.messages:
            item = QListWidgetItem(f"{message.severity.upper()}: {message.message}")
            self.list.addItem(item)

