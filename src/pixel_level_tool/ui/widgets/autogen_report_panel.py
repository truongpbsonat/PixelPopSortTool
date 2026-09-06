from __future__ import annotations

"""The Auto Gen Box report, parked in a tab instead of a modal.

The report is the only record of *why* a generated grid looks the way it does -
which colours the balancing ate, how much conveyor the walkthrough spends, how
close the walls came to strangling the lattice. A message box shows it once and
then it is gone, which is exactly wrong for something a designer wants open
beside the grid while they read it. So it lives next to Validation, stays put
until the next run replaces it, and can be selected and copied.
"""

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget


PLACEHOLDER = "Chưa chạy Auto Gen Box lần nào cho level này."


class AutoGenReportPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        # A run can produce a grid that is complete, correct, and unfinishable -
        # and the body of the report looks exactly the same either way. So the one
        # thing that changes what a designer should do next gets a banner above
        # the text rather than a line inside it, where it would read as the
        # thirteenth number on the page.
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        self.banner.setStyleSheet(
            "background: #5c1a1a; color: #ffd9d9; padding: 6px; border-radius: 3px;"
        )
        layout.addWidget(self.banner)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        # Fixed-width, because the report lines up counts and slot coordinates and
        # a proportional font pulls those columns apart. Wrapped, because this
        # lives in the narrow side panel: the warnings at the end are whole
        # paragraphs, and a horizontal scrollbar would bury them.
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text.setPlaceholderText(PLACEHOLDER)
        layout.addWidget(self.text)

    def set_report(self, report: str, alert: str = "") -> None:
        """Show one run's report, with ``alert`` as the banner when there is one."""
        self.banner.setText(alert)
        self.banner.setVisible(bool(alert))
        self.text.setPlainText(report)
        # Long reports otherwise open wherever the last one was scrolled to.
        self.text.verticalScrollBar().setValue(0)

    def clear(self) -> None:
        """Drop the report, because it describes a level that is no longer open."""
        self.banner.clear()
        self.banner.setVisible(False)
        self.text.clear()

    @property
    def report(self) -> str:
        return self.text.toPlainText()

    @property
    def alert(self) -> str:
        # isHidden, not isVisible: a widget inside a panel nobody has shown yet is
        # not visible, but it is not hidden either, and what is asked here is
        # whether this run raised an alert at all.
        return "" if self.banner.isHidden() else self.banner.text()
