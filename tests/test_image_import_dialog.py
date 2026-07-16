import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox

from pixel_level_tool.ui.dialogs.image_import_dialog import ImageImportDialog


def test_apply_button_accepts_image_import_dialog(qtbot):
    dialog = ImageImportDialog(18, 18)
    qtbot.addWidget(dialog)
    dialog.show()

    buttons = dialog.findChild(QDialogButtonBox)
    apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
    qtbot.mouseClick(apply_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
