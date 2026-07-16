from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import QLabel, QLayout, QLayoutItem, QPushButton, QSizePolicy, QWidget

from pixel_level_tool.domain.enums import COLOR_NAMES, COLOR_RGB, ItemColor
from pixel_level_tool.domain.level_models import PixelLevelData


class FlowLayout(QLayout):
    """Lay widgets left-to-right and wrap them when the row is full."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientations()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def horizontalSpacing(self) -> int:
        return self._spacing

    def verticalSpacing(self) -> int:
        return self._spacing

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        row_height = 0

        for item in self._items:
            item_size = item.sizeHint()
            next_x = x + item_size.width() + self._spacing
            if next_x - self._spacing > effective.right() + 1 and row_height > 0:
                x = effective.x()
                y += row_height + self._spacing
                next_x = x + item_size.width() + self._spacing
                row_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))
            x = next_x
            row_height = max(row_height, item_size.height())

        return y + row_height - rect.y() + margins.bottom()


class ColorPalette(QWidget):
    color_changed = Signal(ItemColor)
    COLUMN_COUNT = 5
    SWATCH_SIZE = 51

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected = ItemColor.Red
        self._buttons: dict[ItemColor, QPushButton] = {}
        self._id_labels: dict[ItemColor, QLabel] = {}
        self._balance_text: dict[ItemColor, str] = {color: "" for color in ItemColor}
        layout = FlowLayout(self)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        for color in ItemColor:
            button = QPushButton()
            button.setCheckable(True)
            button.setFixedSize(QSize(self.SWATCH_SIZE, self.SWATCH_SIZE))
            button.setToolTip(f"{int(color):2d}  {COLOR_NAMES[color]}")
            button.clicked.connect(lambda checked=False, picked=color: self.set_selected_color(picked, emit=True))
            id_label = QLabel(str(int(color)), button)
            id_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            id_label.setStyleSheet(
                "QLabel {"
                "background-color: #ffffff;"
                "color: #000000;"
                "border: 1px solid #000000;"
                "border-radius: 2px;"
                "padding: 0 2px;"
                "font-size: 9px;"
                "font-weight: 700;"
                "}"
            )
            id_label.adjustSize()
            id_label.move(0, 0)
            id_label.raise_()
            self._buttons[color] = button
            self._id_labels[color] = id_label
            layout.addWidget(button)

        self.set_selected_color(self._selected)

    def sizeHint(self) -> QSize:
        color_count = len(ItemColor)
        columns = min(self.COLUMN_COUNT, color_count)
        rows = math.ceil(color_count / columns)
        spacing = self.layout().horizontalSpacing()
        return QSize(
            columns * self.SWATCH_SIZE + (columns - 1) * spacing,
            rows * self.SWATCH_SIZE + (rows - 1) * self.layout().verticalSpacing(),
        )

    def minimumSizeHint(self) -> QSize:
        # The palette may be clipped while the user gives the lower-right tabs
        # more room with the splitter.
        return QSize(0, 0)

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
