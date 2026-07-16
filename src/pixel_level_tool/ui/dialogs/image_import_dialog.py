from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


class ImageImportDialog(QDialog):
    def __init__(self, width: int, height: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Image")
        root = QVBoxLayout(self)
        form = QFormLayout()
        path_row = QHBoxLayout()
        self.path = QLineEdit()
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        path_row.addWidget(self.path)
        path_row.addWidget(browse)
        form.addRow("File", path_row)
        self.width = QSpinBox()
        self.width.setRange(1, 256)
        self.width.setValue(width)
        self.height = QSpinBox()
        self.height.setRange(1, 256)
        self.height.setValue(height)
        self.alpha = QSpinBox()
        self.alpha.setRange(0, 255)
        self.alpha.setValue(1)
        self.keep_aspect = QCheckBox()
        self.keep_aspect.setChecked(True)
        form.addRow("Target width", self.width)
        form.addRow("Target height", self.height)
        form.addRow("Alpha threshold", self.alpha)
        form.addRow("Keep aspect", self.keep_aspect)
        root.addLayout(form)
        self.preview = QLabel()
        self.preview.setMinimumHeight(160)
        self.preview.setScaledContents(False)
        root.addWidget(self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        # ``Apply`` has ``ApplyRole`` and therefore does not emit the
        # button-box ``accepted`` signal (that signal is reserved for
        # buttons with ``AcceptRole`` such as Ok/Save).  Connect the actual
        # button so clicking Apply closes the dialog and lets the import
        # workflow continue.
        apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        if apply_button is not None:
            apply_button.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tga)",
        )
        if path:
            self.path.setText(path)
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.preview.setPixmap(pixmap.scaledToHeight(160))

    @property
    def selected_path(self) -> Path:
        return Path(self.path.text())

