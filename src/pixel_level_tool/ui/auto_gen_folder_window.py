"""The Auto Gen Folder workbench: a folder of art or levels, generated in one go.

A window rather than a dialog because a folder run is work a designer sits with:
the sources are listed and previewed before anything is generated, the run keeps
going on a worker thread while the list stays usable, and the log of what came
out stays on screen afterwards - to be sorted through, exported, or opened in the
editor. The one-shot dialog (:class:`AutoGenFolderDialog`) is the same settings
without the workbench around them.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pixel_level_tool.domain.enums import COLOR_RGB, EMPTY_COLOR_ID, ItemColor
from pixel_level_tool.domain.level_models import PixelGridData
from pixel_level_tool.services.autogen_batch import (
    REPORT_COLUMNS,
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_JAM,
    STATUS_SKIPPED,
    BatchSource,
    BatchSummary,
    generate_folder,
    load_level_source,
    output_file_name,
    report_row,
    status_label,
    write_report_csv,
)
from pixel_level_tool.services.box_autogen import AutoGenOptions
from pixel_level_tool.services.image_importer import ImageImportError, import_image_to_color_ids
from pixel_level_tool.services.legacy_level_importer import LegacyLevelImportError
from pixel_level_tool.services.level_serializer import LevelSerializationError
from pixel_level_tool.ui.widgets.auto_gen_folder_form import AutoGenFolderForm

_STATUS_COLORS = {
    STATUS_JAM: QColor("#e06c00"),
    STATUS_ERROR: QColor("#d13438"),
    STATUS_SKIPPED: QColor("#8a8a8a"),
    STATUS_CANCELLED: QColor("#8a8a8a"),
}

SOURCE_COLUMNS = ("File", "Loại", "Level", "Kết quả")


class PicturePreview(QWidget):
    """The picture a source carries, drawn as flat colour cells."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.grid: PixelGridData | None = None
        self.setMinimumHeight(220)

    def show_grid(self, grid: PixelGridData | None) -> None:
        self.grid = grid
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt name
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#11151c"))
        grid = self.grid
        if grid is None or grid.width <= 0 or grid.height <= 0:
            painter.setPen(QColor("#8a8a8a"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Chọn một dòng để xem bức tranh"
            )
            return
        grid.ensure_dense()
        # Square cells, centred, so a wide picture is not stretched into a blur.
        size = max(1, min(self.width() // grid.width, self.height() // grid.height))
        left = (self.width() - size * grid.width) // 2
        top = (self.height() - size * grid.height) // 2
        for row in range(grid.height):
            for column in range(grid.width):
                color_id = grid.color_ids[row * grid.width + column]
                if color_id == EMPTY_COLOR_ID:
                    continue
                try:
                    rgb = COLOR_RGB[ItemColor(color_id)]
                except ValueError:
                    rgb = (128, 128, 128)
                painter.fillRect(
                    left + column * size, top + row * size, size, size, QColor(*rgb)
                )


class GenerateWorker(QThread):
    """Runs the batch off the UI thread; the service itself knows nothing of Qt."""

    progress = Signal(int, int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, sources, output_folder, options: AutoGenOptions, kwargs: dict, parent=None):
        super().__init__(parent)
        self._sources = list(sources)
        self._output = output_folder
        self._options = options
        self._kwargs = kwargs
        self._stop = threading.Event()

    def cancel(self) -> None:
        self._stop.set()

    def run(self) -> None:  # noqa: D102 - QThread entry point
        try:
            summary = generate_folder(
                self._sources,
                self._output,
                self._options,
                progress=lambda index, total, source: self.progress.emit(
                    index, total, source.path.name
                ),
                should_cancel=self._stop.is_set,
                **self._kwargs,
            )
        except Exception as exc:  # the worker must never take the window with it
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.done.emit(summary)


class AutoGenFolderWindow(QMainWindow):
    """Sources on the left, settings and log on the right, a run in between."""

    open_level_requested = Signal(str)

    def __init__(
        self,
        parent=None,
        *,
        settings=None,
        options: AutoGenOptions | None = None,
        difficulty: int = 1,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Auto Gen Folder — sinh box cho cả folder")
        self.resize(1280, 820)
        self.settings = settings
        self.worker: GenerateWorker | None = None
        self.summary: BatchSummary | None = None
        self._preview_cache: dict[tuple, PixelGridData | None] = {}

        self.form = AutoGenFolderForm(
            self,
            source_folder=self._setting("autogen_batch_source_dir", "last_level_folder"),
            output_folder=self._setting("autogen_batch_output_dir"),
            preset_folder=self._setting("autogen_config_dir"),
            options=options,
            difficulty=difficulty,
        )
        self._build_ui()
        self.form.sources_changed.connect(self._fill_sources)
        self._fill_sources(len(self.form.sources))

    # ------------------------------------------------------------------- setup
    def _setting(self, key: str, fallback_key: str | None = None) -> str:
        if self.settings is None:
            return ""
        value = self.settings.get(key, "")
        if not value and fallback_key is not None:
            value = self.settings.get(fallback_key, "")
        return value or ""

    def _build_ui(self) -> None:
        bar = self.addToolBar("Auto Gen Folder")
        self.pick_action = QAction("Chọn folder nguồn", self)
        self.pick_action.triggered.connect(self.form._browse_source)
        self.refresh_action = QAction("Làm mới", self)
        self.refresh_action.triggered.connect(self.form.refresh_sources)
        self.prev_action = QAction("◀", self)
        self.prev_action.triggered.connect(lambda: self._step_selection(-1))
        self.next_action = QAction("▶", self)
        self.next_action.triggered.connect(lambda: self._step_selection(1))
        self.run_action = QAction("▶ Sinh cả folder", self)
        self.run_action.triggered.connect(self.toggle_run)
        self.export_action = QAction("Xuất CSV", self)
        self.export_action.triggered.connect(self.export_csv)
        self.export_action.setEnabled(False)
        self.clear_action = QAction("Xoá log", self)
        self.clear_action.triggered.connect(self.clear_log)
        for action in (
            self.pick_action,
            self.refresh_action,
            self.prev_action,
            self.next_action,
        ):
            bar.addAction(action)
        bar.addSeparator()
        bar.addAction(self.run_action)
        bar.addSeparator()
        for action in (self.export_action, self.clear_action):
            bar.addAction(action)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Nguồn trong folder"))
        self.source_table = QTableWidget(0, len(SOURCE_COLUMNS))
        self.source_table.setHorizontalHeaderLabels(list(SOURCE_COLUMNS))
        self.source_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.source_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.source_table.verticalHeader().setVisible(False)
        self.source_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.source_table.itemSelectionChanged.connect(self._selection_changed)
        left_layout.addWidget(self.source_table, 1)
        self.only_selected = QCheckBox("Chỉ sinh các dòng đang chọn")
        self.only_selected.setToolTip(
            "Bỏ trống là chạy cả folder. Tích vào để sinh lại vài level mà không đụng phần còn lại."
        )
        left_layout.addWidget(self.only_selected)
        left_layout.addWidget(QLabel("Bức tranh của dòng đang chọn"))
        self.preview = PicturePreview()
        left_layout.addWidget(self.preview, 1)
        self.preview_label = QLabel("—")
        self.preview_label.setWordWrap(True)
        left_layout.addWidget(self.preview_label)
        splitter.addWidget(left)

        tabs = QTabWidget()
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(self.form)
        tabs.addTab(settings_scroll, "Cấu hình")

        results = QWidget()
        results_layout = QVBoxLayout(results)
        self.result_table = QTableWidget(0, len(REPORT_COLUMNS))
        self.result_table.setHorizontalHeaderLabels(list(REPORT_COLUMNS))
        self.result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            len(REPORT_COLUMNS) - 1, QHeaderView.ResizeMode.Stretch
        )
        self.result_table.itemDoubleClicked.connect(self._open_generated_level)
        results_layout.addWidget(self.result_table, 1)
        results_layout.addWidget(
            QLabel("Bấm đúp một dòng để mở level vừa sinh trong cửa sổ chính.")
        )
        tabs.addTab(results, "Kết quả")
        self.tabs = tabs
        splitter.addWidget(tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(splitter, 1)
        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress_label = QLabel("")
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.progress_label, 2)
        central_layout.addLayout(progress_row)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Chọn folder nguồn để bắt đầu.")

    # ----------------------------------------------------------------- sources
    def _fill_sources(self, _count: int = 0) -> None:
        sources = self.form.sources
        self.source_table.setRowCount(len(sources))
        for row, source in enumerate(sources):
            values = (
                source.path.name,
                "ảnh" if source.kind == "image" else "level",
                output_file_name(source.level, source.category).removesuffix(".json")
                + ("" if source.numbered else " (tự đánh)"),
                "",
            )
            for column, text in enumerate(values):
                self.source_table.setItem(row, column, QTableWidgetItem(text))
        self.statusBar().showMessage(self.form.summary_label.text())
        if sources and not self.source_table.selectedItems():
            self.source_table.selectRow(0)

    def _step_selection(self, direction: int) -> None:
        rows = self.source_table.rowCount()
        if not rows:
            return
        current = self.source_table.currentRow()
        self.source_table.selectRow(max(0, min(rows - 1, current + direction)))

    def selected_sources(self) -> list[BatchSource]:
        rows = sorted({index.row() for index in self.source_table.selectedIndexes()})
        return [self.form.sources[row] for row in rows if row < len(self.form.sources)]

    def _selection_changed(self) -> None:
        chosen = self.selected_sources()
        if not chosen:
            self.preview.show_grid(None)
            self.preview_label.setText("—")
            return
        source = chosen[0]
        grid, note = self._picture_of(source)
        self.preview.show_grid(grid)
        painted = 0 if grid is None else sum(1 for c in grid.color_ids if c != EMPTY_COLOR_ID)
        colors = 0 if grid is None else len({c for c in grid.color_ids if c != EMPTY_COLOR_ID})
        size = "—" if grid is None else f"{grid.width}x{grid.height}"
        self.preview_label.setText(
            f"{source.path.name} → level "
            f"{output_file_name(source.level, source.category).removesuffix('.json')}"
            f" · {size} · {painted} pixel · {colors} màu" + (f" · {note}" if note else "")
        )

    def _picture_of(self, source: BatchSource) -> tuple[PixelGridData | None, str]:
        """The source's picture, sampled at the current size for an image."""
        key = (
            source.path,
            source.kind,
            self.form.pixel_width.value(),
            self.form.pixel_height.value(),
            self.form.alpha.value(),
        )
        if key in self._preview_cache:
            grid = self._preview_cache[key]
            return grid, "" if grid is not None else "không đọc được"
        try:
            if source.kind == "image":
                width = self.form.pixel_width.value()
                height = self.form.pixel_height.value()
                grid = PixelGridData(
                    width,
                    height,
                    import_image_to_color_ids(
                        source.path, width, height, self.form.alpha.value()
                    ),
                )
            else:
                # The same reader the run uses, so a source the run can generate
                # is a source the preview can draw - old-format exports included.
                level, _ = load_level_source(source.path)
                grid = level.pixel_grid
        except (
            ImageImportError,
            LegacyLevelImportError,
            LevelSerializationError,
            OSError,
            ValueError,
        ) as exc:
            self._preview_cache[key] = None
            return None, f"không đọc được: {exc}"
        self._preview_cache[key] = grid
        return grid, ""

    # --------------------------------------------------------------------- run
    @property
    def running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def toggle_run(self) -> None:
        if self.running:
            self.worker.cancel()
            self.run_action.setText("Đang dừng…")
            self.run_action.setEnabled(False)
            return
        self.start_run()

    def start_run(self) -> None:
        problem = self.form.problem()
        if problem is not None:
            QMessageBox.warning(self, "Auto Gen Folder", problem)
            return
        self._fill_sources()
        sources = self.selected_sources() if self.only_selected.isChecked() else self.form.sources
        if not sources:
            QMessageBox.warning(self, "Auto Gen Folder", "Chưa chọn dòng nào để sinh.")
            return
        if len(sources) > 20 and QMessageBox.question(
            self,
            "Auto Gen Folder",
            f"{len(sources)} level sẽ được sinh vào {self.form.output_folder}.\n\n"
            "Việc này có thể mất vài phút. Bấm nút lần nữa là dừng — các level đã sinh "
            "vẫn được giữ.\n\nChạy luôn?",
        ) != QMessageBox.Yes:
            return

        self._remember_folders()
        self.progress.setVisible(True)
        self.progress.setRange(0, len(sources))
        self.progress.setValue(0)
        self.run_action.setText("⏹ Dừng")
        self.worker = GenerateWorker(
            sources, self.form.output_folder, self.form.options, self.form.run_kwargs(), self
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _remember_folders(self) -> None:
        if self.settings is None:
            return
        self.settings.set("autogen_batch_source_dir", str(self.form.source_folder))
        self.settings.set("autogen_batch_output_dir", str(self.form.output_folder))
        preset = self.form.preset_folder
        if preset is not None:
            self.settings.set("autogen_config_dir", str(preset))

    def _on_progress(self, index: int, total: int, name: str) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(index - 1)
        self.progress_label.setText(f"({index}/{total}) đang sinh {name}")

    def _on_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Auto Gen Folder", message)
        self.progress_label.setText(message)

    def _on_finished(self) -> None:
        self.run_action.setText("▶ Sinh cả folder")
        self.run_action.setEnabled(True)
        self.progress.setVisible(False)

    def _on_done(self, summary: BatchSummary) -> None:
        self.summary = summary
        self.show_summary(summary)

    def show_summary(self, summary: BatchSummary) -> None:
        """Fill the log, mark the source rows, and say how the run went."""
        self.result_table.setRowCount(len(summary.items))
        by_source = {}
        for row, item in enumerate(summary.items):
            color = _STATUS_COLORS.get(item.status)
            for column, text in enumerate(report_row(item)):
                cell = QTableWidgetItem(text)
                if 3 <= column <= 9:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if color is not None:
                    cell.setForeground(color)
                self.result_table.setItem(row, column, cell)
            by_source[item.source.path] = item
        for row, source in enumerate(self.form.sources):
            item = by_source.get(source.path)
            if item is None:
                continue
            cell = QTableWidgetItem(status_label(item.status))
            color = _STATUS_COLORS.get(item.status)
            if color is not None:
                cell.setForeground(color)
            self.source_table.setItem(row, len(SOURCE_COLUMNS) - 1, cell)
        self.export_action.setEnabled(bool(summary.items))
        headline = (
            f"{summary.total} nguồn · {summary.generated} xong · {summary.jammed} kẹt · "
            f"{summary.failed} lỗi · {summary.skipped} bỏ qua"
        )
        if summary.unburied:
            headline += f" · {summary.unburied} hạ chôn box về Easy (nâng piece)"
        # A level quietly easier than its tier, and a level quietly carrying no
        # mechanics at all, are the two outcomes a folder run can hide.
        if summary.relieved:
            headline += f" · {summary.relieved} hạ bậc obs"
        if summary.bare:
            headline += f" · {summary.bare} không có obs"
        if summary.cancelled:
            headline = "Đã huỷ giữa chừng — " + headline
        self.progress_label.setText(headline)
        self.statusBar().showMessage(headline)
        self.tabs.setCurrentIndex(1)

    # ------------------------------------------------------------------- after
    def _open_generated_level(self, item: QTableWidgetItem) -> None:
        if self.summary is None:
            return
        row = item.row()
        if row >= len(self.summary.items):
            return
        output = self.summary.items[row].output
        if output is None:
            QMessageBox.information(
                self, "Auto Gen Folder", "Dòng này không sinh ra file level nào."
            )
            return
        self.open_level_requested.emit(str(output))

    def clear_log(self) -> None:
        self.result_table.setRowCount(0)
        self.summary = None
        self.export_action.setEnabled(False)
        for row in range(self.source_table.rowCount()):
            self.source_table.setItem(row, len(SOURCE_COLUMNS) - 1, QTableWidgetItem(""))
        self.progress_label.setText("")

    def export_csv(self) -> None:
        if self.summary is None:
            return
        suggested = str(Path(self.form.output_edit.text() or ".") / "autogen_folder.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Xuất CSV", suggested, "CSV (*.csv)")
        if not path:
            return
        try:
            written = write_report_csv(self.summary, path)
        except OSError as exc:
            QMessageBox.warning(self, "Xuất CSV", f"Không ghi được {path}:\n{exc}")
            return
        self.statusBar().showMessage(f"Đã xuất {written}", 5000)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt name
        """A run owns a thread, so it is stopped and waited for before closing."""
        if self.running:
            if QMessageBox.question(
                self,
                "Auto Gen Folder",
                "Đang sinh dở. Dừng và đóng cửa sổ?",
            ) != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(5000)
        self._remember_folders()
        event.accept()
