from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QMessageBox, QVBoxLayout

from pixel_level_tool.services.box_autogen import AutoGenOptions
from pixel_level_tool.ui.widgets.auto_gen_folder_form import AutoGenFolderForm


class AutoGenFolderDialog(QDialog):
    """The one-shot Auto Gen Folder run: set it up, press go, read the report.

    Everything on it is :class:`AutoGenFolderForm`, which the Auto Gen Folder
    window uses as well - this dialog is that form plus a go button, for when a
    folder just needs generating without keeping a workbench open.
    """

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
        self.setWindowTitle("Auto Gen Box cả folder")
        self.setMinimumWidth(620)

        root = QVBoxLayout(self)
        self.form = AutoGenFolderForm(
            self,
            source_folder=source_folder,
            output_folder=output_folder,
            preset_folder=preset_folder,
            options=options,
            difficulty=difficulty,
        )
        root.addWidget(self.form)

        # The form's controls are reached straight off the dialog, so callers do
        # not have to know which of the two owns a given box.
        self.source_edit = self.form.source_edit
        self.output_edit = self.form.output_edit
        self.preset_edit = self.form.preset_edit
        self.summary_label = self.form.summary_label
        self.pixel_width = self.form.pixel_width
        self.pixel_height = self.form.pixel_height
        self.alpha = self.form.alpha
        self.time = self.form.time
        self.piece = self.form.piece
        self.start_level = self.form.start_level
        self.use_presets = self.form.use_presets
        self.write_presets = self.form.write_presets
        self.picture_difficulty = self.form.picture_difficulty
        self.use_level_difficulty = self.form.use_level_difficulty
        self.overwrite = self.form.overwrite
        self.shuffle_attempts = self.form.shuffle_attempts
        self.params_button = self.form.params_button
        self.params_label = self.form.params_label

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Sinh cả folder")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _accept(self) -> None:
        problem = self.form.problem()
        if problem is not None:
            QMessageBox.warning(self, "Auto Gen Folder", problem)
            return
        self.accept()

    def _refresh_sources(self) -> None:
        self.form.refresh_sources()

    @property
    def sources(self):
        return self.form.sources

    @property
    def options(self) -> AutoGenOptions:
        return self.form.options

    @property
    def source_folder(self) -> Path:
        return self.form.source_folder

    @property
    def output_folder(self) -> Path:
        return self.form.output_folder

    @property
    def preset_folder(self) -> Path | None:
        return self.form.preset_folder

    @property
    def shuffle_override(self) -> int | None:
        return self.form.shuffle_override

    def run_kwargs(self) -> dict:
        """Everything the run needs beyond the sources, straight off the form.

        The caller takes these rather than reading the boxes one by one, so a
        field added to the form reaches this path and the workbench window both.
        """
        return self.form.run_kwargs()
