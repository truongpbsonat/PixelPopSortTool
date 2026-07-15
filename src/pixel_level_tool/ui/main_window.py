from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from pixel_level_tool.domain.commands import CommandStack
from pixel_level_tool.domain.enums import EMPTY_COLOR_ID
from pixel_level_tool.domain.level_models import PixelGridData, PixelLevelData
from pixel_level_tool.services.image_importer import ImageImportError, import_image_to_color_ids
from pixel_level_tool.services.legacy_level_importer import LegacyLevelImportError, import_legacy_pixel_grid
from pixel_level_tool.services.level_serializer import LevelSerializationError, load_level, save_level
from pixel_level_tool.services.level_validator import LevelValidator
from pixel_level_tool.services.recent_files_service import RecentFilesService
from pixel_level_tool.services.settings_service import SettingsService
from pixel_level_tool.ui.dialogs.image_import_dialog import ImageImportDialog
from pixel_level_tool.ui.dialogs.new_level_dialog import NewLevelDialog
from pixel_level_tool.ui.dialogs.resize_grid_dialog import ResizeGridDialog
from pixel_level_tool.ui.widgets.box_grid_editor import BoxGridEditor
from pixel_level_tool.ui.widgets.color_palette import ColorPalette
from pixel_level_tool.ui.widgets.pixel_grid_editor import PixelGridEditor
from pixel_level_tool.ui.widgets.shape_palette import ShapePalette
from pixel_level_tool.ui.widgets.validation_panel import ValidationPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = SettingsService()
        self.recent_files = RecentFilesService(self.settings)
        self.validator = LevelValidator()
        self.level = PixelLevelData()
        self.path: Path | None = None
        self.dirty = False
        self.commands = CommandStack(self._apply_snapshot)
        self.setAcceptDrops(True)
        self._build_ui()
        self._connect()
        self._refresh_all()

    def _build_ui(self) -> None:
        self.setWindowTitle("MarbleSort Pixel Level Tool")
        self.resize(1320, 820)
        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)
        self.new_action = QAction("New", self)
        self.open_action = QAction("Open", self)
        self.save_action = QAction("Save", self)
        self.save_as_action = QAction("Save As", self)
        self.validate_action = QAction("Validate", self)
        self.undo_action = QAction("Undo", self)
        self.redo_action = QAction("Redo", self)
        for action in (
            self.new_action,
            self.open_action,
            self.save_action,
            self.save_as_action,
            self.validate_action,
            self.undo_action,
            self.redo_action,
        ):
            toolbar.addAction(action)
        self.new_action.setShortcut(QKeySequence.New)
        self.open_action.setShortcut(QKeySequence.Open)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_as_action.setShortcut(QKeySequence.SaveAs)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action.setShortcut(QKeySequence.Redo)

        meta = QWidget()
        meta_layout = QGridLayout(meta)
        self.level_spin = QSpinBox()
        self.level_spin.setRange(1, 99999)
        self.name_edit = QLineEdit()
        self.game_mode_spin = QSpinBox()
        self.game_mode_spin.setRange(0, 99999)
        self.map_type_spin = QSpinBox()
        self.map_type_spin.setRange(0, 99999)
        self.board_spin = QSpinBox()
        self.board_spin.setRange(0, 99999)
        self.difficulty_spin = QSpinBox()
        self.difficulty_spin.setRange(0, 99999)
        meta_layout.addWidget(QLabel("Level"), 0, 0)
        meta_layout.addWidget(self.level_spin, 0, 1)
        meta_layout.addWidget(QLabel("Name"), 0, 2)
        meta_layout.addWidget(self.name_edit, 0, 3, 1, 3)
        meta_layout.addWidget(QLabel("Game Mode"), 0, 6)
        meta_layout.addWidget(self.game_mode_spin, 0, 7)
        meta_layout.addWidget(QLabel("Map Type"), 1, 0)
        meta_layout.addWidget(self.map_type_spin, 1, 1)
        meta_layout.addWidget(QLabel("Board"), 1, 2)
        meta_layout.addWidget(self.board_spin, 1, 3)
        meta_layout.addWidget(QLabel("Difficulty"), 1, 4)
        meta_layout.addWidget(self.difficulty_spin, 1, 5)
        meta_layout.setColumnStretch(3, 1)

        self.color_palette = ColorPalette()
        self.shape_palette = ShapePalette()
        self.box_editor = BoxGridEditor()
        self.pixel_editor = PixelGridEditor()
        self.box_editor.setMinimumSize(0, 0)
        self.pixel_editor.setMinimumSize(0, 0)
        self.box_editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.pixel_editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.validation_panel = ValidationPanel()

        left = QWidget()
        left.setMinimumWidth(0)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Box Ball Grid"))
        left_layout.addWidget(self.shape_palette)
        left_layout.addWidget(self.box_editor, 1)
        resize_box = QPushButton("Resize Box Grid")
        resize_box.clicked.connect(self.resize_box_grid)
        box_zoom_in = QPushButton("Box +")
        box_zoom_out = QPushButton("Box -")
        box_zoom_in.clicked.connect(self.box_editor.zoom_in)
        box_zoom_out.clicked.connect(self.box_editor.zoom_out)
        box_zoom_row = QHBoxLayout()
        box_zoom_row.addWidget(resize_box)
        box_zoom_row.addWidget(box_zoom_in)
        box_zoom_row.addWidget(box_zoom_out)
        left_layout.addLayout(box_zoom_row)

        right = QWidget()
        right.setMinimumWidth(0)
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Pixel Grid"))
        pixel_controls = QVBoxLayout()
        pixel_buttons_top = QHBoxLayout()
        pixel_buttons_bottom = QHBoxLayout()
        pixel_buttons_size = QHBoxLayout()
        self.erase_button = QPushButton("Eraser")
        self.paint_button = QPushButton("Paint")
        self.eyedropper_button = QPushButton("Eyedropper")
        self.fill_button = QPushButton("Fill All")
        self.clear_button = QPushButton("Clear All")
        self.trim_empty_button = QPushButton("Trim Empty Border")
        self.trim_empty_button.setToolTip("Remove empty rows and columns only from the outside edges")
        self.import_button = QPushButton("Import Image")
        self.import_legacy_button = QPushButton("Import Old JSON")
        self.resize_pixel_button = QPushButton("Resize Pixel Grid")
        self.flood_button = QPushButton("Flood")
        self.pixel_tool_buttons = {
            "paint": self.paint_button,
            "erase": self.erase_button,
            "eyedropper": self.eyedropper_button,
            "flood": self.flood_button,
        }
        self.pixel_tool_group = QButtonGroup(self)
        self.pixel_tool_group.setExclusive(True)
        for button in self.pixel_tool_buttons.values():
            button.setCheckable(True)
            button.setStyleSheet(
                "QPushButton {"
                "padding: 4px 10px;"
                "border: 2px solid #8a929d;"
                "border-radius: 4px;"
                "background: #3a3f46;"
                "color: #f3f6fa;"
                "}"
                "QPushButton:checked {"
                "background: #3a3f46;"
                "border: 2px solid #00a7c8;"
                "font-weight: 600;"
                "}"
            )
            self.pixel_tool_group.addButton(button)
        self.paint_button.setChecked(True)
        self.grid_lines_button = QPushButton("Grid Lines")
        self.grid_lines_button.setCheckable(True)
        self.grid_lines_button.setChecked(True)
        self.pixel_zoom_in_button = QPushButton("Pixel +")
        self.pixel_zoom_out_button = QPushButton("Pixel -")
        for button in (
            self.paint_button,
            self.erase_button,
            self.eyedropper_button,
            self.flood_button,
            self.grid_lines_button,
        ):
            pixel_buttons_top.addWidget(button)
        for button in (
            self.fill_button,
            self.clear_button,
            self.trim_empty_button,
            self.import_button,
            self.import_legacy_button,
        ):
            pixel_buttons_bottom.addWidget(button)
        for button in (
            self.resize_pixel_button,
            self.pixel_zoom_in_button,
            self.pixel_zoom_out_button,
        ):
            pixel_buttons_size.addWidget(button)
        pixel_controls.addLayout(pixel_buttons_top)
        pixel_controls.addLayout(pixel_buttons_bottom)
        pixel_controls.addLayout(pixel_buttons_size)
        right_layout.addLayout(pixel_controls)
        right_layout.addWidget(self.pixel_editor, 1)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([620, 700])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        side = QSplitter(Qt.Vertical)
        side.addWidget(self.color_palette)
        side.addWidget(self.validation_panel)
        side.setSizes([180, 530])
        side.setChildrenCollapsible(False)

        root_splitter = QSplitter()
        root_splitter.addWidget(splitter)
        root_splitter.addWidget(side)
        root_splitter.setSizes([990, 330])
        root_splitter.setStretchFactor(0, 1)
        root_splitter.setStretchFactor(1, 0)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(meta)
        central_layout.addWidget(root_splitter, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready")

    def _connect(self) -> None:
        self.new_action.triggered.connect(self.new_level)
        self.open_action.triggered.connect(self.open_level)
        self.save_action.triggered.connect(self.save)
        self.save_as_action.triggered.connect(self.save_as)
        self.validate_action.triggered.connect(self.validate)
        self.undo_action.triggered.connect(self.commands.undo)
        self.redo_action.triggered.connect(self.commands.redo)
        for spin_box in (
            self.level_spin,
            self.game_mode_spin,
            self.map_type_spin,
            self.board_spin,
            self.difficulty_spin,
        ):
            spin_box.valueChanged.connect(self._metadata_changed)
        self.name_edit.textChanged.connect(self._metadata_changed)
        self.color_palette.color_changed.connect(self.pixel_editor.set_color)
        self.color_palette.color_changed.connect(lambda color: self.box_editor.set_tool(self.shape_palette.shape, self.shape_palette.direction, color, self.shape_palette.is_active))
        self.shape_palette.shape_changed.connect(lambda: self.box_editor.set_tool(self.shape_palette.shape, self.shape_palette.direction, self.color_palette.selected_color, self.shape_palette.is_active))
        self.box_editor.model_changed.connect(self._model_changed)
        self.pixel_editor.model_changed.connect(self._model_changed)
        self.pixel_editor.color_picked.connect(self.color_palette.set_selected_color)
        self.paint_button.clicked.connect(lambda: self._set_pixel_mode("paint"))
        self.erase_button.clicked.connect(lambda: self._set_pixel_mode("erase"))
        self.eyedropper_button.clicked.connect(lambda: self._set_pixel_mode("eyedropper"))
        self.flood_button.clicked.connect(lambda: self._set_pixel_mode("flood"))
        self.fill_button.clicked.connect(lambda: self.pixel_editor.fill_all(int(self.color_palette.selected_color)))
        self.clear_button.clicked.connect(lambda: self.pixel_editor.fill_all(EMPTY_COLOR_ID))
        self.trim_empty_button.clicked.connect(self.trim_empty_pixel_border)
        self.grid_lines_button.toggled.connect(self._toggle_pixel_grid_lines)
        self.pixel_zoom_in_button.clicked.connect(self.pixel_editor.zoom_in)
        self.pixel_zoom_out_button.clicked.connect(self.pixel_editor.zoom_out)
        self.import_button.clicked.connect(self.import_image)
        self.import_legacy_button.clicked.connect(self.import_legacy_pixel_grid)
        self.resize_pixel_button.clicked.connect(self.resize_pixel_grid)

    def _set_pixel_mode(self, mode: str) -> None:
        self.pixel_editor.mode = mode
        button = self.pixel_tool_buttons[mode]
        if not button.isChecked():
            button.setChecked(True)

    def _toggle_pixel_grid_lines(self, checked: bool) -> None:
        self.pixel_editor.show_grid_lines = checked
        self.pixel_editor.refresh()

    def _apply_snapshot(self, level: PixelLevelData) -> None:
        self.level = level
        self.dirty = True
        self._refresh_all()

    def _wrap_change(self, label: str, mutator) -> None:
        before = self.level.clone()
        mutator()
        self.commands.push(label, before, self.level)
        self._set_dirty(True)
        self._refresh_all()

    def _model_changed(self, label: str, before: PixelLevelData | None = None) -> None:
        before = before or self.level.clone()
        self.commands.push(label, before, self.level)
        self._set_dirty(True)
        self._refresh_all()

    def _metadata_changed(self) -> None:
        changed = False
        metadata_values = (
            ("level", self.level_spin.value()),
            ("level_name", self.name_edit.text()),
            ("game_mode", self.game_mode_spin.value()),
            ("map_type", self.map_type_spin.value()),
            ("board", self.board_spin.value()),
            ("difficulty", self.difficulty_spin.value()),
        )
        for attribute, value in metadata_values:
            if getattr(self.level, attribute) != value:
                setattr(self.level, attribute, value)
                changed = True
        if changed:
            self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self.dirty = dirty
        star = "*" if dirty else ""
        name = self.path.name if self.path else "Untitled"
        self.setWindowTitle(f"{star}{name} - MarbleSort Pixel Level Tool")

    def _refresh_all(self) -> None:
        self.level.pixel_grid.ensure_dense()
        for widget in (
            self.level_spin,
            self.name_edit,
            self.game_mode_spin,
            self.map_type_spin,
            self.board_spin,
            self.difficulty_spin,
        ):
            widget.blockSignals(True)
        self.level_spin.setValue(self.level.level)
        self.name_edit.setText(self.level.level_name or "")
        self.game_mode_spin.setValue(self.level.game_mode)
        self.map_type_spin.setValue(self.level.map_type)
        self.board_spin.setValue(self.level.board)
        self.difficulty_spin.setValue(self.level.difficulty)
        for widget in (
            self.level_spin,
            self.name_edit,
            self.game_mode_spin,
            self.map_type_spin,
            self.board_spin,
            self.difficulty_spin,
        ):
            widget.blockSignals(False)
        self.box_editor.set_level(self.level)
        self.box_editor.set_tool(self.shape_palette.shape, self.shape_palette.direction, self.color_palette.selected_color, self.shape_palette.is_active)
        self.pixel_editor.set_level(self.level)
        self.color_palette.refresh(self.level)
        self.pixel_editor.set_color(self.color_palette.selected_color)
        self.validate()
        self._set_dirty(self.dirty)

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        result = QMessageBox.question(
            self,
            "Unsaved changes",
            "Save changes before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if result == QMessageBox.Save:
            return self.save()
        return result == QMessageBox.Discard

    @staticmethod
    def _is_dialog_accepted(result: int) -> bool:
        return result == QDialog.DialogCode.Accepted

    def new_level(self) -> None:
        if not self._confirm_discard():
            return
        dialog = NewLevelDialog(self)
        if not self._is_dialog_accepted(dialog.exec()):
            return
        self.level = PixelLevelData(
            grid_rows=dialog.box_rows.value(),
            grid_cols=dialog.box_cols.value(),
            level=dialog.level.value(),
            level_name=dialog.name.text(),
            pixel_grid=PixelGridData(dialog.pixel_width.value(), dialog.pixel_height.value()),
        )
        self.path = None
        self.commands.clear()
        self._set_dirty(False)
        self._refresh_all()

    def open_level(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Pixel level", self.settings.get("last_open_dir", ""), "JSON (*.json)")
        if path:
            self._load_path(Path(path))

    def _load_path(self, path: Path) -> None:
        try:
            self.level = load_level(path)
        except LevelSerializationError as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self.path = path
        self.settings.set("last_open_dir", str(path.parent))
        self.recent_files.add(path)
        self.commands.clear()
        self._set_dirty(False)
        self._refresh_all()

    def validate(self):
        snapshot = self.level.clone()
        snapshot.assign_deterministic_ids()
        result = self.validator.validate(snapshot)
        self.validation_panel.set_result(result)
        return result

    def save(self) -> bool:
        if self.path is None:
            return self.save_as()
        result = self.validate()
        if not result.is_valid:
            QMessageBox.warning(self, "Validation failed", "Fix validation errors before saving.")
            return False
        try:
            save_level(self.path, self.level, create_backup=True)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self.recent_files.add(self.path)
        self._set_dirty(False)
        self.statusBar().showMessage(f"Saved {self.path}", 5000)
        return True

    def save_as(self) -> bool:
        default_dir = self.settings.get("last_save_dir", "")
        default_name = self._default_file_name()
        path, _ = QFileDialog.getSaveFileName(self, "Save Pixel level", str(Path(default_dir) / default_name), "JSON (*.json)")
        if not path:
            return False
        self.path = Path(path)
        self.settings.set("last_save_dir", str(self.path.parent))
        return self.save()

    def _default_file_name(self) -> str:
        return f"{self.level.level}.json" if self.level.category == 0 else f"{self.level.level}.{self.level.category}.json"

    def resize_box_grid(self) -> None:
        dialog = ResizeGridDialog("Resize Box Grid", "Columns", "Rows", self.level.grid_cols, self.level.grid_rows, self)
        if not self._is_dialog_accepted(dialog.exec()):
            return
        rows, cols = dialog.height.value(), dialog.width.value()

        def mutate() -> None:
            removed = self.level.resize_box_grid(rows, cols, drop_out_of_bounds=False)
            if removed:
                if QMessageBox.question(self, "Boxes out of bounds", "Drop boxes outside the new bounds?") == QMessageBox.Yes:
                    self.level.resize_box_grid(rows, cols, drop_out_of_bounds=True)

        self._wrap_change("Resize box grid", mutate)

    def resize_pixel_grid(self) -> None:
        dialog = ResizeGridDialog(
            "Resize Pixel Grid",
            "Width",
            "Height",
            self.level.pixel_grid.width,
            self.level.pixel_grid.height,
            self,
        )
        if not self._is_dialog_accepted(dialog.exec()):
            return
        width, height = dialog.width.value(), dialog.height.value()
        if width == self.level.pixel_grid.width and height == self.level.pixel_grid.height:
            return

        def mutate() -> None:
            self.level.pixel_grid.resize(width, height)

        self._wrap_change("Resize pixel grid", mutate)
        self.statusBar().showMessage(f"Resized pixel grid to {width}x{height}", 5000)

    def trim_empty_pixel_border(self) -> None:
        grid = self.level.pixel_grid
        old_width, old_height = grid.width, grid.height
        before = self.level.clone()
        if not grid.trim_empty_borders():
            message = (
                "Pixel grid has no empty outer rows or columns"
                if any(color_id != EMPTY_COLOR_ID for color_id in grid.color_ids)
                else "Pixel grid is empty; size was not changed"
            )
            self.statusBar().showMessage(message, 5000)
            return

        self.commands.push("Trim empty pixel border", before, self.level)
        self._set_dirty(True)
        self._refresh_all()
        self.statusBar().showMessage(
            f"Trimmed pixel grid from {old_width}x{old_height} to {grid.width}x{grid.height}",
            5000,
        )

    def import_image(self) -> None:
        grid = self.level.pixel_grid
        dialog = ImageImportDialog(grid.width, grid.height, self)
        if not self._is_dialog_accepted(dialog.exec()):
            return

        def mutate() -> None:
            try:
                width = dialog.width.value()
                height = dialog.height.value()
                color_ids = import_image_to_color_ids(dialog.selected_path, width, height, dialog.alpha.value())
                grid.width = width
                grid.height = height
                grid.color_ids = color_ids
            except ImageImportError as exc:
                QMessageBox.critical(self, "Import failed", str(exc))

        self._wrap_change("Import image", mutate)

    def import_legacy_pixel_grid(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Pixel Grid from Old Level",
            self.settings.get("last_legacy_import_dir", ""),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            pixel_grid = import_legacy_pixel_grid(path)
        except LegacyLevelImportError as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return

        self.settings.set("last_legacy_import_dir", str(Path(path).parent))

        def mutate() -> None:
            self.level.pixel_grid = pixel_grid

        self._wrap_change("Import old JSON pixel grid", mutate)
        painted_count = sum(color_id != EMPTY_COLOR_ID for color_id in pixel_grid.color_ids)
        self.statusBar().showMessage(
            f"Imported {pixel_grid.width}x{pixel_grid.height} pixel grid ({painted_count} painted pixels)",
            5000,
        )

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls and self._confirm_discard():
            self._load_path(Path(urls[0].toLocalFile()))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
