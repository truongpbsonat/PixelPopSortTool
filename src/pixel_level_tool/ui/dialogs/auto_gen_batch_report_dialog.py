from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pixel_level_tool.services.autogen_batch import (
    REPORT_COLUMNS,
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_JAM,
    STATUS_SKIPPED,
    BatchSummary,
    report_row,
)

# Only the rows that need reading first are coloured; a finished level stays
# on the palette's own text colour so the table does not turn into a rainbow.
_STATUS_COLORS = {
    STATUS_JAM: QColor("#e06c00"),
    STATUS_ERROR: QColor("#d13438"),
    STATUS_SKIPPED: QColor("#8a8a8a"),
    STATUS_CANCELLED: QColor("#8a8a8a"),
}


class AutoGenBatchReportDialog(QDialog):
    """One row per source file, in the order they were generated."""

    def __init__(self, summary: BatchSummary, parent=None, *, default_dir: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Kết quả Auto Gen Box cả folder")
        self.resize(1180, 620)
        self._summary = summary
        self._default_dir = default_dir

        root = QVBoxLayout(self)
        headline = QLabel(self._headline(summary))
        headline.setWordWrap(True)
        root.addWidget(headline)

        self.table = QTableWidget(len(summary.items), len(REPORT_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(list(REPORT_COLUMNS))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        for row, item in enumerate(summary.items):
            color = _STATUS_COLORS.get(item.status)
            for column, text in enumerate(report_row(item)):
                cell = QTableWidgetItem(text)
                if column >= 3 and column <= 9:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if color is not None:
                    cell.setForeground(color)
                self.table.setItem(row, column, cell)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(REPORT_COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        buttons_row = QHBoxLayout()
        self.export_button = QPushButton("Xuất CSV")
        self.export_button.clicked.connect(self.export_csv)
        buttons_row.addWidget(self.export_button)
        buttons_row.addStretch(1)
        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)
        buttons_row.addWidget(close_box)
        root.addLayout(buttons_row)

    @staticmethod
    def _headline(summary: BatchSummary) -> str:
        parts = [
            f"{summary.total} file nguồn",
            f"{summary.generated} level sinh xong",
        ]
        if summary.jammed:
            parts.append(f"{summary.jammed} KẸT (vẫn ghi file)")
        if summary.failed:
            parts.append(f"{summary.failed} lỗi")
        if summary.skipped:
            parts.append(f"{summary.skipped} bỏ qua")
        # The one that is actionable rather than merely informative: every one of
        # these is a picture whose `piece` is too small, and the fix is a number.
        if summary.unburied:
            parts.append(f"{summary.unburied} hạ chôn box về Easy (nâng piece)")
        # The two the designer has to know about: a level quietly easier than
        # its tier, and a level quietly carrying no mechanics at all.
        if summary.relieved:
            parts.append(f"{summary.relieved} hạ bậc obs")
        if summary.bare:
            parts.append(f"{summary.bare} không có obs")
        text = " · ".join(parts)
        if summary.cancelled:
            text = "Đã huỷ giữa chừng — " + text
        return text

    def export_csv(self) -> None:
        suggested = str(Path(self._default_dir or ".") / "autogen_folder.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Xuất CSV", suggested, "CSV (*.csv)")
        if not path:
            return
        try:
            # utf-8-sig so Excel opens the Vietnamese columns without mangling them.
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(REPORT_COLUMNS)
                writer.writerows(report_row(item) for item in self._summary.items)
        except OSError as exc:
            QMessageBox.warning(self, "Xuất CSV", f"Không ghi được {path}:\n{exc}")
            return
        QMessageBox.information(self, "Xuất CSV", f"Đã xuất {path}")
