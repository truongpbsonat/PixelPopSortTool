from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
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
from pixel_level_tool.domain.enums import EMPTY_COLOR_ID, THEME_ID_LABELS, LevelDifficulty, ThemeId
from pixel_level_tool.domain.level_models import PixelGridData, PixelLevelData
from pixel_level_tool.services.autogen_batch import (
    AutoGenBatchError,
    BatchSource,
    BatchSummary,
    generate_folder,
)
from pixel_level_tool.services.autogen_config import (
    AutoGenConfigError,
    load_autogen_config,
    save_autogen_config,
)
from pixel_level_tool.services.box_autogen import (
    AutoGenError,
    AutoGenOptions,
    auto_generate_boxes,
    balance_summary,
    jam_headline,
    scan_level,
    format_report,
)
from pixel_level_tool.services.image_importer import ImageImportError, import_image_to_color_ids
from pixel_level_tool.services.legacy_level_importer import LegacyLevelImportError, import_legacy_pixel_grid
from pixel_level_tool.services.level_converter import LevelConvertError, convert_file, convert_folder
from pixel_level_tool.services.level_serializer import LevelSerializationError, load_level, save_level
from pixel_level_tool.services.level_validator import LevelValidator
from pixel_level_tool.services.mechanics_batch import scan_mechanics_in_folder
from pixel_level_tool.services.mechanics_scanner import MechanicsScanner
from pixel_level_tool.services.recent_files_service import RecentFilesService
from pixel_level_tool.services.settings_service import SettingsService
from pixel_level_tool.ui.auto_gen_folder_window import AutoGenFolderWindow
from pixel_level_tool.ui.dialogs.auto_gen_batch_report_dialog import AutoGenBatchReportDialog
from pixel_level_tool.ui.dialogs.auto_gen_box_dialog import AutoGenBoxDialog
from pixel_level_tool.ui.dialogs.auto_gen_folder_dialog import AutoGenFolderDialog
from pixel_level_tool.ui.dialogs.image_import_dialog import ImageImportDialog
from pixel_level_tool.ui.dialogs.new_level_dialog import NewLevelDialog
from pixel_level_tool.ui.dialogs.resize_grid_dialog import ResizeGridDialog
from pixel_level_tool.ui.theme import apply_theme, normalize_theme
from pixel_level_tool.ui.widgets.box_grid_editor import BoxGridEditor
from pixel_level_tool.ui.widgets.box_inspector import BoxInspector, ObstaclesPanel
from pixel_level_tool.ui.widgets.color_palette import ColorPalette
from pixel_level_tool.ui.widgets.pixel_grid_editor import PixelGridEditor
from pixel_level_tool.ui.widgets.shape_palette import ShapePalette
from pixel_level_tool.ui.widgets.autogen_report_panel import AutoGenReportPanel
from pixel_level_tool.ui.widgets.validation_panel import ValidationPanel


class MainWindow(QMainWindow):
    _LEVEL_FILE_PATTERN = re.compile(r"^(?P<level>\d+)(?:\.(?P<category>\d+))?\.json$", re.IGNORECASE)
    _DIFFICULTY_FORCED_THEME = {
        int(LevelDifficulty.Hard): int(ThemeId.Hard),
        int(LevelDifficulty.SuperHard): int(ThemeId.SuperHard),
    }

    def __init__(self) -> None:
        super().__init__()
        self.settings = SettingsService()
        self.theme = normalize_theme(self.settings.get("theme"))
        application = QApplication.instance()
        if application is not None:
            apply_theme(application, self.theme)
        self.recent_files = RecentFilesService(self.settings)
        self.validator = LevelValidator()
        self.mechanics_scanner = MechanicsScanner()
        self.level = PixelLevelData()
        self.path: Path | None = None
        self.level_folder: Path | None = None
        self.auto_level_save = False
        # The Auto Gen Box preset for the level in hand: read from genlv{N}.json on
        # open, replaced by every successful generate, written back on Save.
        self.autogen_options: AutoGenOptions | None = None
        self.dirty = False
        self._replace_color_source = None
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
        self.open_file_action = QAction("Open File", self)
        self.prev_level_action = QAction("Prev", self)
        self.next_level_action = QAction("Next", self)
        self.save_action = QAction("Save", self)
        self.save_as_action = QAction("Save As", self)
        self.convert_file_action = QAction("Convert File", self)
        self.convert_all_action = QAction("Convert All", self)
        self.scan_mechanics_action = QAction("Scan Mechanics In Folder", self)
        self.gen_folder_quick_action = QAction("Gen Folder (nhanh)", self)
        self.gen_folder_quick_action.setToolTip(
            "Sinh box cho cả folder trong một lần hỏi - không mở cửa sổ Auto Gen Folder"
        )
        self.autogen_config_action = QAction("Auto Gen Config Folder", self)
        self.validate_action = QAction("Validate", self)
        self.undo_action = QAction("Undo", self)
        self.redo_action = QAction("Redo", self)
        for action in (
            self.new_action,
            self.open_action,
            self.open_file_action,
            self.prev_level_action,
            self.next_level_action,
            self.save_action,
            self.save_as_action,
            self.convert_file_action,
            self.convert_all_action,
            self.scan_mechanics_action,
            self.gen_folder_quick_action,
            self.autogen_config_action,
            self.validate_action,
            self.undo_action,
            self.redo_action,
        ):
            toolbar.addAction(action)
        toolbar.addSeparator()
        self.dark_mode_button = QPushButton("Dark")
        self.light_mode_button = QPushButton("Light")
        self.theme_button_group = QButtonGroup(self)
        self.theme_button_group.setExclusive(True)
        for button in (self.dark_mode_button, self.light_mode_button):
            button.setCheckable(True)
            button.setProperty("themeButton", True)
            self.theme_button_group.addButton(button)
            toolbar.addWidget(button)
        self.dark_mode_button.setChecked(self.theme == "dark")
        self.light_mode_button.setChecked(self.theme == "light")
        self.dark_mode_button.setToolTip("Use dark mode")
        self.light_mode_button.setToolTip("Use light mode")
        self.new_action.setShortcut(QKeySequence.New)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_file_action.setShortcut("Ctrl+Shift+O")
        self.prev_level_action.setShortcut("Alt+Left")
        self.next_level_action.setShortcut("Alt+Right")
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_as_action.setShortcut(QKeySequence.SaveAs)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action.setShortcut(QKeySequence.Redo)
        action_tooltips = (
            (self.new_action, "Create a new level"),
            (self.open_action, "Open a level folder"),
            (self.open_file_action, "Open one level file without changing the selected folder"),
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
        self.convert_file_action.setToolTip(
            "Convert one old-format level file to the new format in place"
        )
        self.convert_all_action.setToolTip(
            "Convert every level file in a folder to the new format in place"
        )
        self.scan_mechanics_action.setToolTip(
            "Preview or update discovered mechanics in all level JSON files under a folder"
        )
        self.autogen_config_action.setToolTip(
            "Chọn folder chứa cấu hình Auto Gen Box (genlv{level}.json). Cấu hình được ghi mỗi"
            " lần Save level và nạp lại khi mở level đó."
        )

        meta = QWidget()
        meta_layout = QGridLayout(meta)
        self.level_spin = QSpinBox()
        self.level_spin.setRange(1, 99999)
        self.load_level_button = QPushButton("Load Level")
        self.load_level_button.setToolTip("Load this level number from the selected folder")
        self.difficulty_spin = QSpinBox()
        self.difficulty_spin.setRange(0, 99999)
        self.theme_combo = QComboBox()
        self.theme_combo.setToolTip(
            "Theme for this level. Hard / Super Hard difficulties default to the"
            " matching theme, but you can still change it manually."
        )
        for theme in (
            ThemeId.None_,
            ThemeId.Theme0,
            ThemeId.Theme1,
            ThemeId.Theme2,
            ThemeId.Theme3,
            ThemeId.Theme4,
            ThemeId.Hard,
            ThemeId.SuperHard,
        ):
            self.theme_combo.addItem(THEME_ID_LABELS[theme], int(theme))
        self.mechanics_field = QLineEdit()
        self.mechanics_field.setReadOnly(True)
        self.mechanics_field.setPlaceholderText("None")
        self.mechanics_field.setToolTip(
            "Mechanics detected from the current level data. This list is regenerated on Save."
        )
        meta_layout.addWidget(QLabel("Level"), 0, 0)
        meta_layout.addWidget(self.level_spin, 0, 1)
        meta_layout.addWidget(self.load_level_button, 0, 2)
        meta_layout.addWidget(QLabel("Difficulty"), 0, 3)
        meta_layout.addWidget(self.difficulty_spin, 0, 4)
        meta_layout.addWidget(QLabel("Theme"), 0, 5)
        meta_layout.addWidget(self.theme_combo, 0, 6)
        meta_layout.addWidget(QLabel("Mechanics"), 1, 0)
        meta_layout.addWidget(self.mechanics_field, 1, 1, 1, 7)
        meta_layout.setColumnStretch(7, 1)

        self.color_palette = ColorPalette()
        self.shape_palette = ShapePalette()
        self.box_editor = BoxGridEditor()
        self.pixel_editor = PixelGridEditor()
        self.box_editor.setMinimumSize(0, 0)
        self.pixel_editor.setMinimumSize(0, 0)
        self.box_editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.pixel_editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.validation_panel = ValidationPanel()
        self.autogen_report_panel = AutoGenReportPanel()
        self.box_inspector = BoxInspector()
        self.obstacles_panel = ObstaclesPanel()

        left = QWidget()
        left.setMinimumWidth(0)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Box Ball Grid"))
        left_layout.addWidget(self.shape_palette)
        left_layout.addWidget(self.box_editor, 1)
        self.auto_gen_box_button = QPushButton("Auto Gen Box")
        self.auto_gen_box_button.setToolTip(
            "Dựng toàn bộ Box Ball Grid từ Pixel Grid theo độ khó đã chọn"
        )
        self.auto_gen_box_button.clicked.connect(self.auto_gen_boxes)
        self.auto_gen_folder_button = QPushButton("Auto Gen Folder")
        self.auto_gen_folder_button.setToolTip(
            "Mở cửa sổ sinh box cho cả một folder ảnh hoặc folder file level:"
            " xem trước từng bức tranh, chạy nền, log kết quả, xuất CSV"
        )
        self.auto_gen_folder_button.clicked.connect(self.open_auto_gen_folder_window)
        resize_box = QPushButton("Resize Box Grid")
        resize_box.clicked.connect(self.resize_box_grid)
        self.deselect_box_button = QPushButton("Deselect Box")
        self.deselect_box_button.setToolTip("Clear the box selection (also Esc or right-click the Box Grid)")
        self.deselect_box_button.clicked.connect(self.box_editor.clear_selection)
        self.swap_boxes_button = QPushButton("Swap Boxes")
        self.swap_boxes_button.setToolTip("Swap the grid positions of the 2 selected boxes")
        self.swap_boxes_button.setEnabled(False)
        self.swap_boxes_button.clicked.connect(self.box_editor.swap_selected)
        box_zoom_in = QPushButton("Box +")
        box_zoom_out = QPushButton("Box -")
        box_zoom_in.clicked.connect(self.box_editor.zoom_in)
        box_zoom_out.clicked.connect(self.box_editor.zoom_out)
        box_zoom_row = QHBoxLayout()
        box_zoom_row.addWidget(self.auto_gen_box_button)
        box_zoom_row.addWidget(self.auto_gen_folder_button)
        box_zoom_row.addWidget(resize_box)
        box_zoom_row.addWidget(self.deselect_box_button)
        box_zoom_row.addWidget(self.swap_boxes_button)
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
        self.replace_color_button = QPushButton("Switch Color")
        self.replace_color_button.setCheckable(True)
        self.replace_color_button.setToolTip(
            "Use the selected color as the source, then choose its replacement from the palette"
        )
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

        self.palette_panel = QWidget()
        self.palette_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        self.palette_layout = QVBoxLayout(self.palette_panel)
        self.palette_title = QLabel("Colors")
        self.palette_layout.addWidget(self.palette_title)
        self.palette_layout.addWidget(self.color_palette)
        self.palette_layout.addStretch(1)

        self.side_tabs = QTabWidget()
        self.side_tabs.addTab(self.box_inspector, "Box Inspector")
        self.side_tabs.addTab(self.obstacles_panel, "Obstacles")
        self.side_tabs.addTab(self.validation_panel, "Validation")
        self.side_tabs.addTab(self.autogen_report_panel, "Auto Gen Report")

        self.side_splitter = QSplitter(Qt.Orientation.Vertical)
        self.side_splitter.addWidget(self.palette_panel)
        self.side_splitter.addWidget(self.side_tabs)
        self.side_splitter.setCollapsible(0, False)
        self.side_splitter.setSizes([280, 540])
        self.side_splitter.setStretchFactor(0, 0)
        self.side_splitter.setStretchFactor(1, 1)

        root_splitter = QSplitter()
        root_splitter.addWidget(splitter)
        root_splitter.addWidget(self.side_splitter)
        root_splitter.setSizes([990, 330])
        root_splitter.setStretchFactor(0, 1)
        root_splitter.setStretchFactor(1, 0)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(meta)
        central_layout.addWidget(root_splitter, 1)
        self.setCentralWidget(central)
        self._update_palette_minimum_height()
        self.statusBar().showMessage("Ready")

    def _update_palette_minimum_height(self) -> None:
        """Keep enough top-right height for every currently wrapped palette row."""
        width = max(1, self.color_palette.width())
        palette_height = self.color_palette.layout().heightForWidth(width)
        margins = self.palette_layout.contentsMargins()
        extra_height = (
            margins.top()
            + margins.bottom()
            + self.palette_layout.spacing()
            + self.palette_title.sizeHint().height()
        )
        self.palette_panel.setMinimumHeight(palette_height + extra_height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_palette_minimum_height()

    def _connect(self) -> None:
        self.dark_mode_button.clicked.connect(lambda: self._set_theme("dark"))
        self.light_mode_button.clicked.connect(lambda: self._set_theme("light"))
        self.new_action.triggered.connect(self.new_level)
        self.open_action.triggered.connect(self.open_level)
        self.open_file_action.triggered.connect(self.open_file)
        self.load_level_button.clicked.connect(self.load_level_from_folder)
        self.prev_level_action.triggered.connect(self.open_previous_level)
        self.next_level_action.triggered.connect(self.open_next_level)
        self.save_action.triggered.connect(self.save)
        self.save_as_action.triggered.connect(self.save_as)
        self.convert_file_action.triggered.connect(self.convert_level_file)
        self.convert_all_action.triggered.connect(self.convert_level_folder)
        self.scan_mechanics_action.triggered.connect(self.scan_mechanics_folder)
        self.gen_folder_quick_action.triggered.connect(self.auto_gen_boxes_folder)
        self.autogen_config_action.triggered.connect(self.choose_autogen_config_folder)
        self.validate_action.triggered.connect(self.validate)
        self.undo_action.triggered.connect(self.commands.undo)
        self.redo_action.triggered.connect(self.commands.redo)
        self.difficulty_spin.valueChanged.connect(self._difficulty_changed)
        self.theme_combo.currentIndexChanged.connect(self._metadata_changed)
        self.color_palette.color_changed.connect(self._replace_color_from_palette)
        self.color_palette.color_changed.connect(self.pixel_editor.set_color)
        self.color_palette.color_changed.connect(lambda color: self.box_editor.set_tool(self.shape_palette.shape, self.shape_palette.direction, color, self.shape_palette.is_active, self.shape_palette.is_tunnel))
        self.shape_palette.shape_changed.connect(lambda: self.box_editor.set_tool(self.shape_palette.shape, self.shape_palette.direction, self.color_palette.selected_color, self.shape_palette.is_active, self.shape_palette.is_tunnel))
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

    def _set_theme(self, theme: str) -> None:
        theme = normalize_theme(theme)
        self.theme = theme
        self.dark_mode_button.setChecked(theme == "dark")
        self.light_mode_button.setChecked(theme == "light")
        application = QApplication.instance()
        if application is not None:
            apply_theme(application, theme)
        self.settings.set("theme", theme)

    def _set_pixel_mode(self, mode: str) -> None:
        self.pixel_editor.mode = mode
        button = self.pixel_tool_buttons[mode]
        if not button.isChecked():
            button.setChecked(True)

    def _box_selection_changed(self, indices) -> None:
        selected = list(indices)
        self.box_inspector.set_context(self.level, selected)
        self.obstacles_panel.set_context(self.level, selected)
        self.swap_boxes_button.setEnabled(len(selected) == 2)

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

    def _theme_combo_index(self, value: int) -> int:
        index = self.theme_combo.findData(value)
        return index if index != -1 else 0

    def _difficulty_changed(self) -> None:
        difficulty_value = self.difficulty_spin.value()
        forced_theme = self._DIFFICULTY_FORCED_THEME.get(difficulty_value)
        if forced_theme is not None:
            index = self._theme_combo_index(forced_theme)
            if self.theme_combo.currentIndex() != index:
                self.theme_combo.blockSignals(True)
                self.theme_combo.setCurrentIndex(index)
                self.theme_combo.blockSignals(False)
        self._metadata_changed()

    def _metadata_changed(self) -> None:
        changed = False
        difficulty_value = self.difficulty_spin.value()
        theme_value = int(self.theme_combo.currentData())

        metadata_values = (
            ("difficulty", difficulty_value),
            ("theme_id", theme_value),
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
        if self.auto_level_save and self.level_folder is not None:
            name = self._default_file_name()
        else:
            name = self.path.name if self.path else "Untitled"
        self.setWindowTitle(f"{star}{name} - MarbleSort Pixel Level Tool")

    def _refresh_all(self) -> None:
        self.level.pixel_grid.ensure_dense()
        for widget in (
            self.level_spin,
            self.difficulty_spin,
            self.theme_combo,
        ):
            widget.blockSignals(True)
        self.level_spin.setValue(self.level.level)
        self.difficulty_spin.setValue(self.level.difficulty)
        self.theme_combo.setCurrentIndex(self._theme_combo_index(self.level.theme_id))
        self.mechanics_field.setText(", ".join(self.mechanics_scanner.scan(self.level)))
        for widget in (
            self.level_spin,
            self.difficulty_spin,
            self.theme_combo,
        ):
            widget.blockSignals(False)
        self.box_editor.set_level(self.level)
        self.box_editor.set_tool(
            self.shape_palette.shape,
            self.shape_palette.direction,
            self.color_palette.selected_color,
            self.shape_palette.is_active,
            self.shape_palette.is_tunnel,
            apply_to_selection=False,
        )
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
            level_name=f"Pixel Level {dialog.level.value()}",
            time=dialog.time.value(),
            piece=dialog.piece.value(),
            pixel_grid=PixelGridData(dialog.pixel_width.value(), dialog.pixel_height.value()),
        )
        self.path = None
        self.autogen_options = None
        # The report describes the grid that was just replaced, so it goes with it.
        self.autogen_report_panel.clear()
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

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Pixel level file",
            self.settings.get("last_open_dir", ""),
            "JSON (*.json)",
        )
        if not path or not self._confirm_discard():
            return
        self._load_path(Path(path))

    def load_level_from_folder(self) -> None:
        if self.level_folder is None:
            QMessageBox.warning(self, "No level folder", "Select a level folder first.")
            return

        level_number = self.level_spin.value()
        candidates = [
            path
            for path in self._level_files(self.level_folder)
            if self._level_file_key(path)[0] == level_number
        ]
        preferred_key = (level_number, self.level.category)
        target = next(
            (path for path in candidates if self._level_file_key(path) == preferred_key),
            candidates[0] if candidates else None,
        )
        if target is None:
            QMessageBox.warning(
                self,
                "Level not found",
                f"Level {level_number} was not found in {self.level_folder}.",
            )
            return
        if not self._confirm_discard():
            return
        self._load_path(target, from_level_folder=True)

    def _load_path(self, path: Path, *, from_level_folder: bool = False) -> bool:
        try:
            self.level = load_level(path)
        except (LevelSerializationError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return False
        self.path = path
        self.auto_level_save = from_level_folder
        self.settings.set("last_open_dir", str(path.parent))
        if from_level_folder:
            self.level_folder = path.parent
            self.settings.set("last_level_folder", str(path.parent))
        self.recent_files.add(path)
        self.commands.clear()
        self._set_dirty(False)
        self._refresh_all()
        self.autogen_options = self._load_autogen_config()
        # The report describes the grid that was just replaced, so it goes with it.
        self.autogen_report_panel.clear()
        message = f"Opened level {self.level.level}: {path.name}"
        if self.autogen_options is not None:
            message += " — đã nạp cấu hình Auto Gen Box"
        self.statusBar().showMessage(message, 5000)
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
        self._sync_level_number_from_spin()
        if self.auto_level_save and self.level_folder is not None:
            target = self.level_folder / self._default_file_name()
        elif self.path is not None:
            target = self.path
        else:
            return self.save_as()
        return self._save_to_path(target)

    def _sync_level_number_from_spin(self) -> None:
        value = self.level_spin.value()
        if self.level.level != value:
            self.level.level = value
            self._set_dirty(True)

    def _save_to_path(self, target: Path) -> bool:
        result = self.validate()
        if not result.is_valid:
            QMessageBox.warning(self, "Validation failed", "Fix validation errors before saving.")
            return False
        previous_mechanics = self.level.mechanics
        try:
            scanned_mechanics = self.mechanics_scanner.scan(self.level)
            self.level.mechanics = scanned_mechanics
            save_level(target, self.level)
        except Exception as exc:
            self.level.mechanics = previous_mechanics
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self.path = target
        self.settings.set("last_save_dir", str(target.parent))
        self.recent_files.add(target)
        self._set_dirty(False)
        self._refresh_level_navigation()
        self.statusBar().showMessage(f"Saved {target}", 5000)
        self._save_autogen_config()
        return True

    def save_as(self) -> bool:
        self._sync_level_number_from_spin()
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

    # ----------------------------------------------------------------- #
    # Auto Gen Box presets (genlv{level}.json)
    # ----------------------------------------------------------------- #
    def choose_autogen_config_folder(self) -> Path | None:
        start_dir = self.settings.get(
            "autogen_config_dir",
            self.settings.get("last_level_folder", ""),
        )
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn folder lưu cấu hình Auto Gen Box", start_dir
        )
        if not folder:
            return None
        self.settings.set("autogen_config_dir", folder)
        self.statusBar().showMessage(f"Cấu hình Auto Gen Box sẽ được lưu vào {folder}", 5000)
        return Path(folder)

    def _autogen_config_dir(self, *, prompt: bool = False) -> Path | None:
        """The folder picked once and remembered. Only asks when there is something to write."""
        folder = self.settings.get("autogen_config_dir", "")
        if folder:
            return Path(folder)
        return self.choose_autogen_config_folder() if prompt else None

    def _load_autogen_config(self) -> AutoGenOptions | None:
        folder = self._autogen_config_dir()
        if folder is None:
            return None
        try:
            return load_autogen_config(folder, self.level.level, self.level.category)
        except AutoGenConfigError as exc:
            QMessageBox.warning(self, "Auto Gen config", f"Không đọc được cấu hình:\n{exc}")
            return None

    def _save_autogen_config(self) -> None:
        """Write the preset for the level just saved. Never fails the level save itself."""
        if self.autogen_options is None:
            return
        folder = self._autogen_config_dir(prompt=True)
        if folder is None:
            self.statusBar().showMessage(
                "Chưa chọn folder cấu hình nên cấu hình Auto Gen Box không được lưu."
                " Dùng Auto Gen Config Folder để chọn.",
                8000,
            )
            return
        try:
            path = save_autogen_config(
                folder, self.level.level, self.level.category, self.autogen_options
            )
        except (AutoGenConfigError, OSError) as exc:
            QMessageBox.warning(
                self, "Auto Gen config", f"Không lưu được cấu hình Auto Gen Box:\n{exc}"
            )
            return
        self.statusBar().showMessage(f"Đã lưu cấu hình Auto Gen Box vào {path}", 5000)

    def auto_gen_boxes(self) -> None:
        # Scanned before the dialog is built, so the designer sees what the
        # picture costs on the conveyor before touching a single knob.
        scan = scan_level(
            self.level,
            belt_slots=self.autogen_options.belt_slots if self.autogen_options else 0,
        )
        dialog = AutoGenBoxDialog(
            self.level.difficulty, self, options=self.autogen_options, scan=scan
        )
        if not self._is_dialog_accepted(dialog.exec()):
            return
        options = dialog.options()

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            # Generate before creating the undo command so a failed run leaves no
            # dirty, no-op history entry.
            result = auto_generate_boxes(self.level, options)
        except AutoGenError as exc:
            QMessageBox.critical(self, "Auto Gen Box failed", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()

        # Balancing prefers painting empty cells and recolouring over deleting, so
        # the prompt says which of the three this picture actually needed rather
        # than always asking about deletions.
        if (
            result.added_pixels or result.moved_pixels or result.removed_pixels
        ) and QMessageBox.question(
            self,
            "Auto Gen Box",
            "Để mọi màu chia hết thành box 9 bóng, Pixel Grid sẽ được cân bằng: "
            + balance_summary(result.added_pixels, result.moved_pixels, result.removed_pixels)
            + ".\n\nTiếp tục?",
        ) != QMessageBox.Yes:
            return

        generated = result.level

        def mutate() -> None:
            self.level = generated

        self._wrap_change("Auto gen box", mutate)
        # Keep the seed this run settled on, so saving and reopening the level
        # regenerates the very same grid instead of a fresh roll.
        self.autogen_options = replace(options, seed=result.seed)
        self.autogen_report_panel.set_report(
            format_report(result, options), alert=jam_headline(result)
        )
        self.side_tabs.setCurrentWidget(self.autogen_report_panel)
        self.statusBar().showMessage(
            ("KẸT — " if result.jam is not None else "")
            + f"Đã sinh {result.total_boxes} box trong "
            f"{result.slot_cols}x{result.slot_rows} slot ({result.grid_cols}x{result.grid_rows}), "
            f"băng {result.solution.required_belt}/{result.belt_slots} bóng, "
            f"{result.hidden_boxes} box ẩn, "
            f"{result.wall_count} wall",
            8000,
        )
        # A level that cannot be finished used to interrupt with a message box.
        # It does not any more: the report panel is what a designer keeps open
        # beside the grid, it is already brought to the front here, and its banner
        # says the same thing without a click - and without being gone afterwards.

    def open_auto_gen_folder_window(self) -> None:
        """The Auto Gen Folder workbench, kept as one window per editor."""
        window = getattr(self, "auto_gen_folder_window", None)
        if window is None:
            window = AutoGenFolderWindow(
                self,
                settings=self.settings,
                options=self.autogen_options,
                difficulty=self.level.difficulty,
            )
            window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
            window.open_level_requested.connect(self.open_generated_level)
            self.auto_gen_folder_window = window
        window.show()
        window.raise_()
        window.activateWindow()

    def open_generated_level(self, path: str) -> None:
        """Open a level the folder run just wrote, from its row in the log."""
        if not self._confirm_discard():
            return
        self._load_path(Path(path), from_level_folder=True)
        self.raise_()
        self.activateWindow()

    def auto_gen_boxes_folder(self) -> None:
        """Auto Gen Box over every picture in one folder - art files or level files."""
        dialog = AutoGenFolderDialog(
            self,
            source_folder=self.settings.get(
                "autogen_batch_source_dir", self.settings.get("last_level_folder", "")
            ),
            output_folder=self.settings.get("autogen_batch_output_dir", ""),
            preset_folder=self.settings.get("autogen_config_dir", ""),
            options=self.autogen_options,
            difficulty=self.level.difficulty,
        )
        if not self._is_dialog_accepted(dialog.exec()):
            return

        sources = dialog.sources
        output_folder = dialog.output_folder
        preset_folder = dialog.preset_folder
        # Generating one level takes seconds, so a big folder is minutes the
        # designer cannot do anything else during. Say so before it starts, the
        # way the mechanics folder scan does, rather than after.
        if len(sources) > 20 and QMessageBox.question(
            self,
            "Auto Gen Box cả folder",
            f"{len(sources)} level sẽ được sinh vào {output_folder}.\n\n"
            "Việc này có thể mất vài phút. Bấm Cancel là dừng giữa chừng — "
            "các level đã sinh vẫn được giữ.\n\nChạy luôn?",
        ) != QMessageBox.Yes:
            return

        progress_dialog = QProgressDialog("Đang sinh box...", "Cancel", 0, len(sources), self)
        progress_dialog.setWindowTitle("Auto Gen Box cả folder")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)

        def update_progress(current: int, total: int, source: BatchSource) -> None:
            progress_dialog.setMaximum(total)
            progress_dialog.setValue(current - 1)
            progress_dialog.setLabelText(
                f"({current}/{total}) {source.path.name} → level {source.level}"
            )
            QApplication.processEvents()

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            summary = generate_folder(
                sources,
                output_folder,
                dialog.options,
                # Read off the form in one go rather than box by box: the
                # workbench window takes the same dict, so a field added to the
                # form cannot reach one path and be dropped on the other.
                **dialog.run_kwargs(),
                progress=update_progress,
                should_cancel=progress_dialog.wasCanceled,
            )
        except AutoGenBatchError as exc:
            QMessageBox.critical(self, "Auto Gen Box cả folder", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
            progress_dialog.setValue(len(sources))

        self.settings.set("autogen_batch_source_dir", str(dialog.source_folder))
        self.settings.set("autogen_batch_output_dir", str(output_folder))
        if preset_folder is not None:
            self.settings.set("autogen_config_dir", str(preset_folder))

        AutoGenBatchReportDialog(summary, self, default_dir=str(output_folder)).exec()
        self.statusBar().showMessage(
            f"Auto Gen Folder: {summary.generated} xong, {summary.jammed} kẹt, "
            f"{summary.failed} lỗi, {summary.skipped} bỏ qua"
            + (f", {summary.unburied} hạ chôn box về Easy" if summary.unburied else ""),
            8000,
        )
        self._reload_after_batch(summary)

    def _reload_after_batch(self, summary: BatchSummary) -> None:
        """The level on screen is stale if the run just wrote over its own file."""
        if self.path is None or not any(item.output == self.path for item in summary.items):
            return
        if self.dirty:
            QMessageBox.warning(
                self,
                "Auto Gen Box cả folder",
                f"{self.path.name} vừa bị ghi đè, nhưng bản đang mở có thay đổi chưa lưu."
                " Mở lại file để lấy bản vừa sinh, hoặc Save để giữ bản đang sửa.",
            )
            return
        self._load_path(self.path, from_level_folder=self.auto_level_save)

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

    def replace_color(self, checked: bool = False) -> None:
        if not checked:
            self._replace_color_source = None
            self.statusBar().showMessage("Switch color cancelled", 3000)
            return

        self._replace_color_source = self.color_palette.selected_color
        self.statusBar().showMessage(
            f"Switching {self._replace_color_source.name}: choose the target color from the palette"
        )

    def _replace_color_from_palette(self, target) -> None:
        source = self._replace_color_source
        if source is None or not self.replace_color_button.isChecked():
            return

        self._replace_color_source = None
        self.replace_color_button.setChecked(False)
        if source == target:
            self.statusBar().showMessage("Switch color cancelled: source and target are the same", 3000)
            return

        before = self.level.clone()
        box_count, pixel_count = self.level.replace_color(source, target)
        if not box_count and not pixel_count:
            self.statusBar().showMessage(f"No {source.name} items found in the current level", 5000)
            return

        self.commands.push(f"Replace {source.name} with {target.name}", before, self.level)
        self._set_dirty(True)
        self._refresh_all()
        self.statusBar().showMessage(
            f"Replaced {source.name} with {target.name}: {box_count} boxes, {pixel_count} pixels",
            5000,
        )

    def import_image(self) -> None:
        grid = self.level.pixel_grid
        dialog = ImageImportDialog(grid.width, grid.height, self)
        if not self._is_dialog_accepted(dialog.exec()):
            return

        width = dialog.width.value()
        height = dialog.height.value()
        try:
            # Import before creating the undo command.  A bad path or an
            # unreadable image must not create a dirty, no-op history entry.
            color_ids = import_image_to_color_ids(
                dialog.selected_path,
                width,
                height,
                dialog.alpha.value(),
            )
        except ImageImportError as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return

        def mutate() -> None:
            grid.width = width
            grid.height = height
            grid.color_ids = color_ids

        self._wrap_change("Import image", mutate)
        painted_count = sum(color_id != EMPTY_COLOR_ID for color_id in color_ids)
        self.statusBar().showMessage(
            f"Imported {width}x{height} image ({painted_count} painted pixels)",
            5000,
        )

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

    def convert_level_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Convert old-format level file",
            self.settings.get("last_convert_dir", self.settings.get("last_open_dir", "")),
            "JSON (*.json)",
        )
        if not path:
            return
        source = Path(path)
        if QMessageBox.question(
            self,
            "Convert level file",
            f"Convert and overwrite '{source.name}' with the new format?",
        ) != QMessageBox.Yes:
            return
        try:
            convert_file(source)
        except (LevelConvertError, LevelSerializationError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Convert failed", str(exc))
            return
        self.settings.set("last_convert_dir", str(source.parent))
        self.statusBar().showMessage(f"Converted {source.name} to the new format", 5000)
        if not self.dirty and self.path is not None and self.path == source:
            self._load_path(source, from_level_folder=self.auto_level_save)

    def convert_level_folder(self) -> None:
        start_dir = self.settings.get("last_convert_dir", self.settings.get("last_level_folder", ""))
        folder = QFileDialog.getExistingDirectory(self, "Convert all levels in folder", start_dir)
        if not folder:
            return
        folder_path = Path(folder)
        json_count = len(list(folder_path.glob("*.json")))
        if json_count == 0:
            QMessageBox.information(self, "Convert all", "No .json files found in the selected folder.")
            return
        if QMessageBox.question(
            self,
            "Convert all levels",
            f"Convert and overwrite up to {json_count} .json file(s) in\n{folder_path}\n"
            "with the new format?",
        ) != QMessageBox.Yes:
            return
        summary = convert_folder(folder_path)
        self.settings.set("last_convert_dir", str(folder_path))
        lines = [f"Converted {len(summary.converted)} file(s)."]
        if summary.skipped:
            lines.append(f"Skipped {len(summary.skipped)}:")
            lines.extend(f"  • {path.name}: {reason}" for path, reason in summary.skipped[:20])
            if len(summary.skipped) > 20:
                lines.append(f"  … and {len(summary.skipped) - 20} more.")
        QMessageBox.information(self, "Convert all", "\n".join(lines))
        self.statusBar().showMessage(
            f"Converted {len(summary.converted)} file(s), skipped {len(summary.skipped)}", 5000
        )

    def scan_mechanics_folder(self) -> None:
        start_dir = self.settings.get("last_mechanics_scan_dir", self.settings.get("last_level_folder", ""))
        folder = QFileDialog.getExistingDirectory(self, "Scan Mechanics In Folder", start_dir)
        if not folder:
            return
        folder_path = Path(folder)
        json_count = sum(1 for path in folder_path.rglob("*.json") if path.is_file())
        if json_count == 0:
            QMessageBox.information(
                self,
                "Scan Mechanics In Folder",
                "No .json files were found in the selected folder or its subfolders.",
            )
            return

        mode_dialog = QMessageBox(self)
        mode_dialog.setWindowTitle("Scan Mechanics In Folder")
        mode_dialog.setText(f"Found {json_count} JSON file(s) under:\n{folder_path}")
        mode_dialog.setInformativeText(
            "Preview performs a dry run. Update writes only files whose mechanics list changes."
        )
        preview_button = mode_dialog.addButton("Preview / Dry Run", QMessageBox.ActionRole)
        update_button = mode_dialog.addButton("Update Files", QMessageBox.AcceptRole)
        mode_dialog.addButton(QMessageBox.Cancel)
        mode_dialog.exec()
        selected_button = mode_dialog.clickedButton()
        if selected_button not in (preview_button, update_button):
            return
        dry_run = selected_button is preview_button

        progress_dialog = QProgressDialog("Scanning mechanics...", "Cancel", 0, json_count, self)
        progress_dialog.setWindowTitle("Scan Mechanics In Folder")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)

        def update_progress(current: int, total: int, path: Path) -> None:
            progress_dialog.setMaximum(total)
            progress_dialog.setValue(current - 1)
            progress_dialog.setLabelText(f"Scanning {path}")
            QApplication.processEvents()

        summary = scan_mechanics_in_folder(
            folder_path,
            dry_run=dry_run,
            progress=update_progress,
            should_cancel=progress_dialog.wasCanceled,
            scanner=self.mechanics_scanner,
        )
        progress_dialog.setValue(json_count)
        self.settings.set("last_mechanics_scan_dir", str(folder_path))

        lines = [
            f"Total: {summary.total}",
            f"Changed: {summary.changed}",
            f"Unchanged: {summary.unchanged}",
            f"Failed: {summary.failed}",
        ]
        if dry_run:
            lines.insert(0, "Preview / Dry Run — no files were written.")
        if summary.cancelled:
            lines.insert(0, "Cancelled before all files were scanned.")
        if summary.failures:
            lines.append("")
            lines.append("Failures:")
            lines.extend(f"{failure.path}: {failure.error}" for failure in summary.failures[:20])
            if len(summary.failures) > 20:
                lines.append(f"... and {len(summary.failures) - 20} more failure(s).")
        if summary.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"{warning.path}: {warning.message}" for warning in summary.warnings[:20])
            if len(summary.warnings) > 20:
                lines.append(f"... and {len(summary.warnings) - 20} more warning(s).")

        QMessageBox.information(self, "Mechanics scan report", "\n".join(lines))
        self.statusBar().showMessage(
            f"Mechanics scan: {summary.changed} changed, {summary.unchanged} unchanged, "
            f"{summary.failed} failed",
            7000,
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
