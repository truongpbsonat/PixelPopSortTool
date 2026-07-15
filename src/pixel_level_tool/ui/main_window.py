from __future__ import annotations

import re
from pathlib import Path

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
    QTabWidget,
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
from pixel_level_tool.ui.dialogs.replace_color_dialog import ReplaceColorDialog
from pixel_level_tool.ui.dialogs.resize_grid_dialog import ResizeGridDialog
from pixel_level_tool.ui.widgets.box_grid_editor import BoxGridEditor
from pixel_level_tool.ui.widgets.box_inspector import BoxInspector, ObstaclesPanel
from pixel_level_tool.ui.widgets.color_palette import ColorPalette
from pixel_level_tool.ui.widgets.pixel_grid_editor import PixelGridEditor
from pixel_level_tool.ui.widgets.shape_palette import ShapePalette
from pixel_level_tool.ui.widgets.validation_panel import ValidationPanel


class MainWindow(QMainWindow):
    _LEVEL_FILE_PATTERN = re.compile(r"^(?P<level>\d+)(?:\.(?P<category>\d+))?\.json$", re.IGNORECASE)

    def __init__(self) -> None:
        super().__init__()
        self.settings = SettingsService()
        self.recent_files = RecentFilesService(self.settings)
        self.validator = LevelValidator()
        self.level = PixelLevelData()
        self.path: Path | None = None
        self.level_folder: Path | None = None
        self.auto_level_save = False
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
        self.open_action = QAction("Open Folder", self)
        self.prev_level_action = QAction("Prev", self)
        self.next_level_action = QAction("Next", self)
        self.save_action = QAction("Save", self)
        self.save_as_action = QAction("Save As", self)
        self.validate_action = QAction("Validate", self)
        self.undo_action = QAction("Undo", self)
        self.redo_action = QAction("Redo", self)
        for action in (
            self.new_action,
            self.open_action,
            self.prev_level_action,
            self.next_level_action,
            self.save_action,
            self.save_as_action,
            self.validate_action,
            self.undo_action,
            self.redo_action,
        ):
            toolbar.addAction(action)
        self.new_action.setShortcut(QKeySequence.New)
        self.open_action.setShortcut(QKeySequence.Open)
        self.prev_level_action.setShortcut("Alt+Left")
        self.next_level_action.setShortcut("Alt+Right")
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_as_action.setShortcut(QKeySequence.SaveAs)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action.setShortcut(QKeySequence.Redo)
        action_tooltips = (
            (self.new_action, "Create a new level"),
            (self.open_action, "Open a level folder"),
            (self.prev_level_action, "Open the previous level"),
            (self.next_level_action, "Open the next level"),
            (self.save_action, "Save the current level"),
            (self.save_as_action, "Save the current level as a new file"),
            (self.undo_action, "Undo the last edit"),
            (self.redo_action, "Redo the last undone edit"),
        )
        for action, description in action_tooltips:
            action.setToolTip(f"{description} ({action.shortcut().toString()})")
        self.validate_action.setToolTip("Validate the current level")

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
        self.box_inspector = BoxInspector()
        self.obstacles_panel = ObstaclesPanel()

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
        self.replace_color_button = QPushButton("Replace Color")
        self.replace_color_button.setToolTip("Replace every Color A with Color B in the current level")
        self.trim_empty_button = QPushButton("Trim Empty Border")
        self.trim_empty_button.setToolTip("Remove empty rows and columns only from the outside edges")
        self.import_button = QPushButton("Import Image")
        self.import_legacy_button = QPushButton("Import Old JSON")
        self.resize_pixel_button = QPushButton("Resize Pixel Grid")
        self.rotate_pixel_button = QPushButton("Rotate 90° CW")
        self.rotate_pixel_button.setToolTip("Rotate the entire pixel grid 90 degrees clockwise")
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
            self.replace_color_button,
            self.trim_empty_button,
            self.import_button,
            self.import_legacy_button,
        ):
            pixel_buttons_bottom.addWidget(button)
        for button in (
            self.resize_pixel_button,
            self.rotate_pixel_button,
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

        side = QTabWidget()
        side.addTab(self.color_palette, "Colors")
        side.addTab(self.box_inspector, "Box Inspector")
        side.addTab(self.obstacles_panel, "Obstacles")
        side.addTab(self.validation_panel, "Validation")

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
        self.prev_level_action.triggered.connect(self.open_previous_level)
        self.next_level_action.triggered.connect(self.open_next_level)
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
        self.box_editor.selection_changed.connect(self._box_selection_changed)
        self.box_inspector.model_changed.connect(self._model_changed)
        self.obstacles_panel.model_changed.connect(self._model_changed)
        self.pixel_editor.model_changed.connect(self._model_changed)
        self.pixel_editor.color_picked.connect(self.color_palette.set_selected_color)
        self.paint_button.clicked.connect(lambda: self._set_pixel_mode("paint"))
        self.erase_button.clicked.connect(lambda: self._set_pixel_mode("erase"))
        self.eyedropper_button.clicked.connect(lambda: self._set_pixel_mode("eyedropper"))
        self.flood_button.clicked.connect(lambda: self._set_pixel_mode("flood"))
        self.fill_button.clicked.connect(lambda: self.pixel_editor.fill_all(int(self.color_palette.selected_color)))
        self.clear_button.clicked.connect(lambda: self.pixel_editor.fill_all(EMPTY_COLOR_ID))
        self.replace_color_button.clicked.connect(self.replace_color)
        self.trim_empty_button.clicked.connect(self.trim_empty_pixel_border)
        self.grid_lines_button.toggled.connect(self._toggle_pixel_grid_lines)
        self.pixel_zoom_in_button.clicked.connect(self.pixel_editor.zoom_in)
        self.pixel_zoom_out_button.clicked.connect(self.pixel_editor.zoom_out)
        self.import_button.clicked.connect(self.import_image)
        self.import_legacy_button.clicked.connect(self.import_legacy_pixel_grid)
        self.resize_pixel_button.clicked.connect(self.resize_pixel_grid)
        self.rotate_pixel_button.clicked.connect(self.rotate_pixel_grid_clockwise)

    def _set_pixel_mode(self, mode: str) -> None:
        self.pixel_editor.mode = mode
        button = self.pixel_tool_buttons[mode]
        if not button.isChecked():
            button.setChecked(True)

    def _box_selection_changed(self, indices) -> None:
        selected = list(indices)
        self.box_inspector.set_context(self.level, selected)
        self.obstacles_panel.set_context(self.level, selected)

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
        previous_level = self.level.level
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
            if self.level.level != previous_level:
                self._refresh_level_navigation()

    def _set_dirty(self, dirty: bool) -> None:
        self.dirty = dirty
        star = "*" if dirty else ""
        if self.auto_level_save and self.level_folder is not None:
            name = self._default_file_name()
        else:
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
        selected = sorted(self.box_editor.selected_indices)
        self.box_inspector.set_context(self.level, selected)
        self.obstacles_panel.set_context(self.level, selected)
        self.pixel_editor.set_level(self.level)
        self.color_palette.refresh(self.level)
        self.pixel_editor.set_color(self.color_palette.selected_color)
        self.validate()
        self._set_dirty(self.dirty)
        self._refresh_level_navigation()

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
        # Keep an explicitly selected folder so a new level can be saved there
        # immediately without opening a file picker again.
        self.auto_level_save = self.level_folder is not None
        self.commands.clear()
        self._set_dirty(False)
        self._refresh_all()

    def open_level(self) -> None:
        start_dir = self.settings.get(
            "last_level_folder",
            self.settings.get("last_open_dir", ""),
        )
        folder = QFileDialog.getExistingDirectory(self, "Select Pixel level folder", start_dir)
        if not folder:
            return

        selected_folder = Path(folder)
        files = self._level_files(selected_folder)
        target = self._matching_level_path(files) or (files[0] if files else None)
        if target is not None and not self._confirm_discard():
            return

        if target is not None:
            self._load_path(target, from_level_folder=True)
        else:
            self.level_folder = selected_folder
            self.auto_level_save = True
            self.path = None
            self.settings.set("last_level_folder", str(selected_folder))
            self.settings.set("last_open_dir", str(selected_folder))
            self._set_dirty(self.dirty)
            self._refresh_level_navigation()
            self.statusBar().showMessage(
                f"Selected empty level folder: {selected_folder}. Save will create {self._default_file_name()}.",
                7000,
            )

    def _load_path(self, path: Path, *, from_level_folder: bool = False) -> bool:
        try:
            self.level = load_level(path)
        except (LevelSerializationError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return False
        self.path = path
        self.level_folder = path.parent
        self.auto_level_save = from_level_folder
        self.settings.set("last_open_dir", str(path.parent))
        if from_level_folder:
            self.settings.set("last_level_folder", str(path.parent))
        self.recent_files.add(path)
        self.commands.clear()
        self._set_dirty(False)
        self._refresh_all()
        self.statusBar().showMessage(f"Opened level {self.level.level}: {path.name}", 5000)
        return True

    @classmethod
    def _level_file_key(cls, path: Path) -> tuple[int, int] | None:
        match = cls._LEVEL_FILE_PATTERN.fullmatch(path.name)
        if match is None:
            return None
        return int(match.group("level")), int(match.group("category") or 0)

    @classmethod
    def _level_files(cls, folder: Path) -> list[Path]:
        try:
            files = [path for path in folder.iterdir() if path.is_file() and cls._level_file_key(path) is not None]
        except OSError:
            return []
        return sorted(files, key=lambda path: (cls._level_file_key(path), path.name.lower()))

    def _current_level_key(self) -> tuple[int, int]:
        return self.level.level, self.level.category

    def _matching_level_path(self, files: list[Path]) -> Path | None:
        current_key = self._current_level_key()
        return next((path for path in files if self._level_file_key(path) == current_key), None)

    def _navigation_target(self, direction: int, files: list[Path] | None = None) -> Path | None:
        if self.level_folder is None:
            return None
        files = self._level_files(self.level_folder) if files is None else files
        if not files:
            return None
        current_key = self._current_level_key()
        if direction < 0:
            candidates = [path for path in files if self._level_file_key(path) < current_key]
            return candidates[-1] if candidates else None
        candidates = [path for path in files if self._level_file_key(path) > current_key]
        return candidates[0] if candidates else None

    def _refresh_level_navigation(self) -> None:
        files = self._level_files(self.level_folder) if self.level_folder is not None else []
        previous_path = self._navigation_target(-1, files)
        next_path = self._navigation_target(1, files)
        self.prev_level_action.setEnabled(previous_path is not None)
        self.next_level_action.setEnabled(next_path is not None)
        self.prev_level_action.setText(
            f"Prev ({previous_path.stem})" if previous_path is not None else "Prev"
        )
        self.next_level_action.setText(
            f"Next ({next_path.stem})" if next_path is not None else "Next"
        )

    def _open_adjacent_level(self, direction: int) -> None:
        target = self._navigation_target(direction)
        if target is None or not self._confirm_discard():
            return
        self._load_path(target, from_level_folder=True)

    def open_previous_level(self) -> None:
        self._open_adjacent_level(-1)

    def open_next_level(self) -> None:
        self._open_adjacent_level(1)

    def validate(self):
        snapshot = self.level.clone()
        snapshot.assign_deterministic_ids()
        result = self.validator.validate(snapshot)
        self.validation_panel.set_result(result)
        return result

    def save(self) -> bool:
        if self.auto_level_save and self.level_folder is not None:
            target = self.level_folder / self._default_file_name()
        elif self.path is not None:
            target = self.path
        else:
            return self.save_as()
        return self._save_to_path(target)

    def _save_to_path(self, target: Path) -> bool:
        result = self.validate()
        if not result.is_valid:
            QMessageBox.warning(self, "Validation failed", "Fix validation errors before saving.")
            return False
        try:
            save_level(target, self.level, create_backup=True)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self.path = target
        self.level_folder = target.parent
        self.settings.set("last_save_dir", str(target.parent))
        self.recent_files.add(target)
        self._set_dirty(False)
        self._refresh_level_navigation()
        self.statusBar().showMessage(f"Saved {target}", 5000)
        return True

    def save_as(self) -> bool:
        default_dir = self.settings.get("last_save_dir", "")
        default_name = self._default_file_name()
        path, _ = QFileDialog.getSaveFileName(self, "Save Pixel level", str(Path(default_dir) / default_name), "JSON (*.json)")
        if not path:
            return False
        target = Path(path)
        if target.suffix.lower() != ".json":
            target = target.with_suffix(".json")
        if not self._save_to_path(target):
            return False
        # Save As deliberately leaves the file at the exact custom location/name.
        # Prev/Next will restore level-number based saving after a folder level is opened.
        self.auto_level_save = False
        self._set_dirty(False)
        return True

    def _default_file_name(self) -> str:
        return f"{self.level.level}.json" if self.level.category == 0 else f"{self.level.level}.{self.level.category}.json"

    def resize_box_grid(self) -> None:
        dialog = ResizeGridDialog("Resize Box Grid", "Columns", "Rows", self.level.grid_cols, self.level.grid_rows, self)
        if not self._is_dialog_accepted(dialog.exec()):
            return
        rows, cols = dialog.height.value(), dialog.width.value()

        removed, invalid_obstacles = self.level.resize_issues(rows, cols)
        drop_invalid = False
        if removed or invalid_obstacles:
            details = []
            if removed:
                details.append(f"{len(removed)} box(es)")
            if invalid_obstacles:
                details.append(f"{len(invalid_obstacles)} obstacle(s)")
            if QMessageBox.question(
                self,
                "Box Grid data out of bounds",
                f"Resize will remove {' and '.join(details)} outside the new bounds. Continue?",
            ) != QMessageBox.Yes:
                return
            drop_invalid = True

        def mutate() -> None:
            self.level.resize_box_grid(rows, cols, drop_out_of_bounds=drop_invalid)

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

    def rotate_pixel_grid_clockwise(self) -> None:
        old_width = self.level.pixel_grid.width
        old_height = self.level.pixel_grid.height

        def mutate() -> None:
            self.level.pixel_grid.rotate_clockwise()

        self._wrap_change("Rotate pixel grid clockwise", mutate)
        self.statusBar().showMessage(
            f"Rotated pixel grid 90° clockwise ({old_width}x{old_height} -> {old_height}x{old_width})",
            5000,
        )

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

    def replace_color(self) -> None:
        dialog = ReplaceColorDialog(self.color_palette.selected_color, self)
        if not self._is_dialog_accepted(dialog.exec()):
            return

        source = dialog.source_color
        target = dialog.target_color
        before = self.level.clone()
        box_count, pixel_count = self.level.replace_color(source, target)
        if not box_count and not pixel_count:
            self.statusBar().showMessage(f"No {source.name} items found in the current level", 5000)
            return

        self.commands.push(f"Replace {source.name} with {target.name}", before, self.level)
        self._set_dirty(True)
        self._refresh_all()
        self.color_palette.set_selected_color(target, emit=True)
        self.statusBar().showMessage(
            f"Replaced {source.name} with {target.name}: {box_count} boxes, {pixel_count} pixels",
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
            dropped_path = Path(urls[0].toLocalFile())
            if dropped_path.is_dir():
                files = self._level_files(dropped_path)
                if files:
                    self.level_folder = dropped_path
                    self.auto_level_save = True
                    self._load_path(self._matching_level_path(files) or files[0], from_level_folder=True)
            else:
                self._load_path(dropped_path)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
