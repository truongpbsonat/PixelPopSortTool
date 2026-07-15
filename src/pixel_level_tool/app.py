from __future__ import annotations

import argparse
import sys

from pixel_level_tool import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="MarbleSortPixelLevelTool")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    parser.add_argument("--smoke-test", action="store_true", help="Initialize the application and exit.")
    args = parser.parse_args(argv)

    if args.version:
        print(f"MarbleSort Pixel Level Tool {__version__}")
        return 0

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    app.setApplicationName("MarbleSort Pixel Level Tool")
    app.setOrganizationName("MarbleSort")

    from pixel_level_tool.ui.main_window import MainWindow

    window = MainWindow()
    if args.smoke_test:
        window.close()
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

