from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


THEMES = {"dark", "light"}
DEFAULT_THEME = "dark"


def normalize_theme(value: object) -> str:
    return value if isinstance(value, str) and value in THEMES else DEFAULT_THEME


def apply_theme(application: QApplication, theme: str) -> None:
    """Apply an explicit application palette instead of inheriting the OS theme."""
    theme = normalize_theme(theme)
    application.setStyle("Fusion")

    palette = QPalette()
    if theme == "dark":
        colors = {
            QPalette.Window: "#20242a",
            QPalette.WindowText: "#f3f6fa",
            QPalette.Base: "#16191e",
            QPalette.AlternateBase: "#292e36",
            QPalette.ToolTipBase: "#303640",
            QPalette.ToolTipText: "#f3f6fa",
            QPalette.Text: "#f3f6fa",
            QPalette.Button: "#343a43",
            QPalette.ButtonText: "#f3f6fa",
            QPalette.BrightText: "#ffffff",
            QPalette.Highlight: "#00a7c8",
            QPalette.HighlightedText: "#ffffff",
            QPalette.PlaceholderText: "#9aa3ad",
        }
        disabled_text = "#747c86"
        border = "#59636f"
        checked = "#006d82"
    else:
        colors = {
            QPalette.Window: "#f4f6f8",
            QPalette.WindowText: "#1d252d",
            QPalette.Base: "#ffffff",
            QPalette.AlternateBase: "#e9edf1",
            QPalette.ToolTipBase: "#ffffff",
            QPalette.ToolTipText: "#1d252d",
            QPalette.Text: "#1d252d",
            QPalette.Button: "#ffffff",
            QPalette.ButtonText: "#1d252d",
            QPalette.BrightText: "#000000",
            QPalette.Highlight: "#0089a5",
            QPalette.HighlightedText: "#ffffff",
            QPalette.PlaceholderText: "#6f7882",
        }
        disabled_text = "#929aa3"
        border = "#aeb7c1"
        checked = "#cceff5"

    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(disabled_text))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(disabled_text))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(disabled_text))
    application.setPalette(palette)
    application.setStyleSheet(
        f"""
        QToolBar {{ spacing: 4px; padding: 3px; }}
        QPushButton {{ padding: 4px 10px; border: 1px solid {border}; border-radius: 4px; }}
        QPushButton:hover {{ border-color: #00a7c8; }}
        QPushButton:checked {{
            background-color: {checked};
            border: 2px solid #00a7c8;
            font-weight: 600;
        }}
        QPushButton[themeButton="true"] {{ min-width: 50px; }}
        QLineEdit, QSpinBox, QComboBox {{ padding: 3px; }}
        """
    )
