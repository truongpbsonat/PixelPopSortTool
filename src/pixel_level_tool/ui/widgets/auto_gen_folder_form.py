from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pixel_level_tool.services.autogen_batch import (
    AutoGenBatchError,
    BatchSource,
    collect_sources,
    describe_sources,
)
from pixel_level_tool.services.box_autogen import AutoGenOptions
from pixel_level_tool.ui.dialogs.auto_gen_box_dialog import AutoGenBoxDialog

# How many times a folder run re-rolls each level by default. Ten is enough for
# the shuffle to find a winnable, mechanic-carrying grid on almost every picture,
# and a folder run is exactly where paying that cost is worth it: it runs
# unattended, so a level nobody re-rolled by hand is a level that ships as it
# first came out.
DEFAULT_FOLDER_SHUFFLE = 10


class AutoGenFolderForm(QWidget):
    """Where a folder run reads from, where it writes, and on what knobs.

    Shared by the one-shot dialog and the Auto Gen Folder window so the two
    always ask for the same things in the same words. The generator's own knobs
    are not duplicated here: **Tham số Auto Gen Box** opens the very dialog the
    single-level action uses.
    """

    sources_changed = Signal(int)

    def __init__(
        self,
        parent=None,
        *,
        source_folder: str = "",
        output_folder: str = "",
        preset_folder: str = "",
        options: AutoGenOptions | None = None,
        difficulty: int = 1,
    ) -> None:
        super().__init__(parent)
        self._options = options or AutoGenOptions(difficulty=difficulty)
        self.sources: list[BatchSource] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        folders = QGroupBox("Folder")
        folder_form = QFormLayout(folders)
        self.source_edit = QLineEdit(source_folder)
        folder_form.addRow(
            "Nguồn (ảnh hoặc file level)", self._with_browse(self.source_edit, self._browse_source)
        )
        self.output_edit = QLineEdit(output_folder)
        folder_form.addRow("Xuất level ra", self._with_browse(self.output_edit, self._browse_output))
        self.preset_edit = QLineEdit(preset_folder)
        folder_form.addRow(
            "Folder cấu hình genlv", self._with_browse(self.preset_edit, self._browse_preset)
        )
        self.summary_label = QLabel("Chưa chọn folder nguồn.")
        self.summary_label.setWordWrap(True)
        folder_form.addRow("", self.summary_label)
        root.addWidget(folders)

        picture = QGroupBox("Ảnh nguồn (bỏ qua nếu folder chỉ có file level)")
        picture_form = QFormLayout(picture)
        self.pixel_width = QSpinBox()
        self.pixel_width.setRange(1, 256)
        self.pixel_width.setValue(16)
        self.pixel_height = QSpinBox()
        self.pixel_height.setRange(1, 256)
        self.pixel_height.setValue(16)
        # On by default: a folder of art is a folder of *different* pictures, and
        # forcing one size onto all of them is what squashes a 40x24 piece into a
        # square. The two spin boxes above stay as the cap - see `image_grid_size`.
        self.size_from_image = QCheckBox("Lấy kích thước từ chính ảnh, hai ô trên là mức tối đa")
        self.size_from_image.setChecked(True)
        self.size_from_image.setToolTip(
            "Ảnh nhỏ hơn mức tối đa giữ nguyên kích thước gốc, không lấy mẫu lại.\n"
            "Ảnh lớn hơn được thu nhỏ vừa khung mà vẫn giữ đúng tỷ lệ.\n"
            "Bỏ tick thì mọi ảnh đều bị ép về đúng số đã gõ."
        )
        self.alpha = QSpinBox()
        self.alpha.setRange(0, 255)
        self.alpha.setValue(1)
        self.alpha.setToolTip("Pixel có alpha thấp hơn mức này được coi là ô trống")
        self.time = QSpinBox()
        self.time.setRange(1, 3600)
        self.time.setValue(60)
        self.piece = QSpinBox()
        self.piece.setRange(1, 99)
        self.piece.setValue(5)
        self.piece.setToolTip("Số box băng chuyền ghi vào level mới dựng từ ảnh")
        picture_form.addRow("Pixel Grid rộng", self.pixel_width)
        picture_form.addRow("Pixel Grid cao", self.pixel_height)
        picture_form.addRow("", self.size_from_image)
        picture_form.addRow("Ngưỡng alpha", self.alpha)
        picture_form.addRow("Thời gian (giây)", self.time)
        picture_form.addRow("Piece", self.piece)
        root.addWidget(picture)

        numbering = QGroupBox("Đánh số")
        numbering_form = QFormLayout(numbering)
        self.start_level = QSpinBox()
        self.start_level.setRange(1, 99999)
        self.start_level.setValue(1)
        self.start_level.setToolTip(
            "Ảnh/file có số trong tên (7.png, 7.2.png) giữ đúng số đó.\n"
            "File không có số được đánh tiếp từ đây, bỏ qua các số đã bị chiếm."
        )
        numbering_form.addRow("Level bắt đầu cho file không đánh số", self.start_level)
        root.addWidget(numbering)

        rules = QGroupBox("Cách chạy")
        rules_layout = QVBoxLayout(rules)
        self.use_presets = QCheckBox("Ưu tiên cấu hình genlv{level}.json của từng level nếu có")
        self.use_presets.setChecked(True)
        self.write_presets = QCheckBox("Lưu cấu hình genlv{level}.json (kèm seed) sau khi sinh")
        self.write_presets.setChecked(True)
        # The tier, answered once for the whole run. On by default because it is
        # what a folder run is for: a folder of art has no tier written anywhere,
        # and reading it off each picture is the only answer that is per-picture
        # without the designer opening the params dialog a hundred times.
        self.picture_difficulty = QCheckBox("Lấy độ khó thẳng từ ảnh cho MỌI level trong folder")
        self.picture_difficulty.setChecked(True)
        self.picture_difficulty.setToolTip(
            "Mỗi level tự đọc độ khó từ chính bức tranh của nó (số màu + độ vụn), đúng như ô\n"
            "'Lấy độ khó từ ảnh' trong bảng Tham số Auto Gen Box — nhưng cho cả folder, nên\n"
            "không phải mở bảng tham số cho từng level.\n"
            "\n"
            "Bật thì nó THẮNG cả genlv{level}.json và ô 'dùng độ khó ghi trong file level': đã\n"
            "bảo 'lấy từ ảnh cho mọi level' thì không có số nào của lượt chạy cũ được lật lại.\n"
            "Phần còn lại của preset vẫn giữ nguyên, chỉ riêng độ khó đổi, và các liều lượng để\n"
            "Auto sẽ đi theo mức mới.\n"
            "\n"
            "Tắt thì độ khó lấy theo thứ tự cũ: preset của level → độ khó ghi trong file level\n"
            "→ ô độ khó trong bảng Tham số."
        )
        self.use_level_difficulty = QCheckBox(
            "Dùng độ khó ghi trong từng file level (chỉ khi level đó không có cấu hình riêng)"
        )
        self.use_level_difficulty.setChecked(True)
        self.overwrite = QCheckBox("Ghi đè file level đã có trong folder xuất")
        self.overwrite.setChecked(True)
        for box in (
            self.use_presets,
            self.write_presets,
            self.picture_difficulty,
            self.use_level_difficulty,
            self.overwrite,
        ):
            rules_layout.addWidget(box)
        # Its own field rather than one more thing inside the params dialog: on a
        # folder run this is the cost dial for the whole batch, and one of the two
        # knobs that outrank a per-level preset - see `generate_folder`.
        shuffle_row = QHBoxLayout()
        self.shuffle_attempts = QSpinBox()
        self.shuffle_attempts.setRange(0, 24)
        # Ten, not "theo tham số": rolling is what makes an unattended run worth
        # trusting, and a folder run is the one place nobody is watching each
        # level to re-roll it by hand.
        self.shuffle_attempts.setValue(DEFAULT_FOLDER_SHUFFLE)
        self.shuffle_attempts.setSuffix(" lần")
        self.shuffle_attempts.setSpecialValueText("Theo tham số")
        self.shuffle_attempts.setToolTip(
            "Xóc lại cả lượt gen bấy nhiêu lần trên các seed liên tiếp rồi giữ bản tốt nhất, cho\n"
            "MỌI level trong lượt chạy này.\n"
            "\n"
            "Để 'Theo tham số' thì mỗi level dùng số xóc trong bảng Tham số Auto Gen Box, hoặc số\n"
            "ghi trong genlv{level}.json của chính nó nếu có.\n"
            "Đặt một con số thì con số đó THẮNG cả preset, như ô lấy độ khó từ ảnh ở trên.\n"
            "\n"
            "Vì sao nó được quyền đó: xóc là dial CHI PHÍ của cả lượt (N lần x cả trăm level là\n"
            "toàn bộ thời gian chạy), nên nó thuộc về lượt chạy chứ không thuộc về bức tranh nào.\n"
            "Và nó không đổi level là cái gì: mỗi lần xóc là một level hoàn chỉnh đã kiểm chứng,\n"
            "xóc chỉ CHỌN GIỮA chúng — nên ép nó không thể sinh ra lưới không ai chọn, khác với\n"
            "các liều lượng obstacle (những cái đó vẫn nhường preset).\n"
            "\n"
            "Thứ tự ưu tiên khi chọn bản tốt nhất: thắng được → còn obstacle → nhiều loại obstacle\n"
            "hơn → dạng obstacle cứng hơn → còn nhiều băng dư hơn.\n"
            "Report ghi seed của bản được giữ cho từng level, và preset lưu ra cũng mang seed đó."
        )
        shuffle_label = QLabel("Xóc lại cho cả folder")
        shuffle_label.setToolTip(self.shuffle_attempts.toolTip())
        shuffle_row.addWidget(shuffle_label)
        shuffle_row.addWidget(self.shuffle_attempts)
        shuffle_row.addStretch(1)
        rules_layout.addLayout(shuffle_row)

        params_row = QHBoxLayout()
        self.params_button = QPushButton("Tham số Auto Gen Box…")
        self.params_button.setToolTip(
            "Mở đúng bảng tham số của Auto Gen Box, dùng chung cho cả folder"
        )
        self.params_button.clicked.connect(self.edit_options)
        self.params_label = QLabel()
        self.params_label.setWordWrap(True)
        params_row.addWidget(self.params_button)
        params_row.addWidget(self.params_label, 1)
        rules_layout.addLayout(params_row)
        root.addWidget(rules)
        root.addStretch(1)

        self.source_edit.editingFinished.connect(self.refresh_sources)
        self.start_level.valueChanged.connect(self.refresh_sources)
        self.shuffle_attempts.valueChanged.connect(self._update_params_label)
        self.picture_difficulty.toggled.connect(self._update_difficulty_boxes)
        self._update_difficulty_boxes()
        self._update_params_label()
        if source_folder:
            self.refresh_sources()

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _with_browse(edit: QLineEdit, handler) -> QHBoxLayout:
        row = QHBoxLayout()
        button = QPushButton("Browse")
        button.clicked.connect(handler)
        row.addWidget(edit)
        row.addWidget(button)
        return row

    def _pick_folder(self, edit: QLineEdit, title: str) -> str:
        folder = QFileDialog.getExistingDirectory(self, title, edit.text())
        if folder:
            edit.setText(folder)
        return folder

    def _browse_source(self) -> None:
        if self._pick_folder(self.source_edit, "Folder ảnh hoặc file level"):
            if not self.output_edit.text():
                self.output_edit.setText(self.source_edit.text())
            self.refresh_sources()

    def _browse_output(self) -> None:
        self._pick_folder(self.output_edit, "Folder xuất level")

    def _browse_preset(self) -> None:
        self._pick_folder(self.preset_edit, "Folder cấu hình Auto Gen Box")

    def refresh_sources(self) -> None:
        folder = self.source_edit.text().strip()
        if not folder or not Path(folder).is_dir():
            self.sources = []
            self.summary_label.setText("Chưa chọn folder nguồn hợp lệ.")
            self.sources_changed.emit(0)
            return
        try:
            self.sources = collect_sources(folder, start_level=self.start_level.value())
        except AutoGenBatchError as exc:
            self.sources = []
            self.summary_label.setText(str(exc))
            self.sources_changed.emit(0)
            return
        text = describe_sources(self.sources)
        unnumbered = [source for source in self.sources if not source.numbered]
        if unnumbered:
            text += (
                f" {len(unnumbered)} file không có số trong tên, được đánh từ level "
                f"{unnumbered[0].level} ({unnumbered[0].path.name})."
            )
        self.summary_label.setText(text)
        self.sources_changed.emit(len(self.sources))

    def edit_options(self) -> None:
        dialog = AutoGenBoxDialog(self._options.difficulty, self, options=self._options)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._options = dialog.options()
            self._update_params_label()

    def _update_params_label(self) -> None:
        options = self._options
        # Same reason as the roll count below: the run is about to override the
        # dialog's tier, so quoting the dialog here would contradict it.
        if self.picture_difficulty.isChecked():
            tier = "độ khó theo ảnh từng level"
        elif options.auto_difficulty:
            tier = "theo bức tranh"
        else:
            tier = f"độ khó {options.difficulty}"
        seed = "auto" if options.seed is None else str(options.seed)
        # The roll count is read off the field beside this label when that field
        # is set, so saying the dialog's number here would contradict the run.
        override = self.shuffle_override
        rolls = (
            f"xóc {override} lần (cả folder)"
            if override is not None
            else f"xóc {options.shuffle_attempts} lần"
        )
        self.params_label.setText(
            f"{tier} · băng {options.belt_slots or 'theo piece'} · "
            f"{rolls} · seed {seed}"
            # Off is the one worth saying: a folder run with the climb off can
            # write a hundred levels labelled harder than they play, and one with
            # the burial floor off can bury a hundred jammed pictures at their
            # tier's own depth. Both are silent in every other column.
            + ("" if options.difficulty_climb else " · KHÔNG tự tăng độ khó")
            + ("" if options.jam_relief else " · KHÔNG hạ chôn box khi tranh kẹt")
        )

    def _update_difficulty_boxes(self) -> None:
        """Grey the level-file tier box out while the picture is answering instead.

        Left enabled it would read as a second opinion the run might take, when
        the picture box above has already settled it for every level.
        """
        forced = self.picture_difficulty.isChecked()
        self.use_level_difficulty.setEnabled(not forced)
        self.use_level_difficulty.setToolTip(
            "Đang lấy độ khó từ ảnh cho cả folder nên ô này không có tác dụng."
            if forced
            else ""
        )
        self._update_params_label()

    def problem(self) -> str | None:
        """What stops a run from starting, in the words the user needs to hear."""
        self.refresh_sources()
        if not self.sources:
            return "Folder nguồn không có ảnh hay file level nào."
        if not self.output_edit.text().strip():
            return "Chưa chọn folder xuất level."
        if (
            self.use_presets.isChecked() or self.write_presets.isChecked()
        ) and not self.preset_edit.text().strip():
            return (
                "Chưa chọn folder cấu hình genlv. Chọn folder đó, hoặc bỏ hai ô đọc/lưu cấu hình."
            )
        return None

    # -------------------------------------------------------------- accessors
    @property
    def options(self) -> AutoGenOptions:
        return self._options

    @options.setter
    def options(self, value: AutoGenOptions) -> None:
        self._options = value
        self._update_params_label()

    @property
    def shuffle_override(self) -> int | None:
        """The roll count this run forces on every level, or ``None`` for none.

        0 on the spinner is "Theo tham số": leave each level with whatever its
        preset, or the params dialog, asked for.
        """
        value = self.shuffle_attempts.value()
        return value or None

    @property
    def picture_difficulty_forced(self) -> bool:
        """Whether every level in this run reads its tier off its own picture."""
        return self.picture_difficulty.isChecked()

    @property
    def source_folder(self) -> Path:
        return Path(self.source_edit.text().strip())

    @property
    def output_folder(self) -> Path:
        return Path(self.output_edit.text().strip())

    @property
    def preset_folder(self) -> Path | None:
        text = self.preset_edit.text().strip()
        return Path(text) if text else None

    def run_kwargs(self) -> dict:
        """Everything :func:`generate_folder` needs beyond the source list."""
        return dict(
            image_width=self.pixel_width.value(),
            image_height=self.pixel_height.value(),
            image_size_from_source=self.size_from_image.isChecked(),
            alpha_threshold=self.alpha.value(),
            image_time=self.time.value(),
            image_piece=self.piece.value(),
            preset_folder=self.preset_folder,
            use_presets=self.use_presets.isChecked(),
            write_presets=self.write_presets.isChecked(),
            use_level_difficulty=self.use_level_difficulty.isChecked(),
            picture_difficulty=self.picture_difficulty.isChecked(),
            overwrite=self.overwrite.isChecked(),
            shuffle_attempts=self.shuffle_override,
        )
