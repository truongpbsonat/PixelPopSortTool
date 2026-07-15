from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import QGridLayout, QPushButton, QWidget

from pixel_level_tool.domain.enums import COLOR_NAMES, COLOR_RGB, ItemColor
from pixel_level_tool.domain.level_models import PixelLevelData


class ColorPalette(QWidget):
    color_changed = Signal(ItemColor)
    COLUMN_COUNT = 5
    SWATCH_SIZE = 34

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected = ItemColor.Red
        self._buttons: dict[ItemColor, QPushButton] = {}
        self._balance_text: dict[ItemColor, str] = {color: "" for color in ItemColor}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        for index, color in enumerate(ItemColor):
            button = QPushButton()
            button.setCheckable(True)
            button.setFixedSize(QSize(self.SWATCH_SIZE, self.SWATCH_SIZE))
            button.setToolTip(f"{int(color):2d}  {COLOR_NAMES[color]}")
            button.clicked.connect(lambda checked=False, picked=color: self.set_selected_color(picked, emit=True))
            self._buttons[color] = button
            layout.addWidget(button, index // self.COLUMN_COUNT, index % self.COLUMN_COUNT)

        layout.setColumnStretch(self.COLUMN_COUNT, 1)
        self.set_selected_color(self._selected)

    @property
    def selected_color(self) -> ItemColor:
        return self._selected

    def set_selected_color(self, color: ItemColor, emit: bool = False) -> None:
        self._selected = color
        for item_color, button in self._buttons.items():
            rgb = COLOR_RGB[item_color]
            checked = item_color == color
            border = "3px solid #ffffff" if checked else "1px solid #7b828c"
            text = self._balance_text[item_color]
            text_color = "#f6f8fb" if sum(rgb) < 360 else "#20242c"
            button.setChecked(checked)
            button.setText(text)
            button.setStyleSheet(
                "QPushButton {"
                f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]});"
                f"border: {border};"
                "border-radius: 4px;"
                "font-size: 11px;"
                "font-weight: 700;"
                f"color: {text_color};"
                "}"
            )
        if emit:
            self.color_changed.emit(self._selected)

    def refresh(self, level: PixelLevelData) -> None:
        source = level.source_histogram()
        target = level.target_histogram()
        for color in ItemColor:
            delta = target.get(int(color), 0) - source.get(int(color), 0)
            self._balance_text[color] = f"{delta:+d}" if delta else ""
            self._buttons[color].setToolTip(
                f"{int(color):2d}  {COLOR_NAMES[color]}\n"
                f"Box: {source.get(int(color), 0)}  Pixel: {target.get(int(color), 0)}"
            )
        self.set_selected_color(self._selected)
