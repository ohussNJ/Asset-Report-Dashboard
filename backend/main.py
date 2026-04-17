"""
Asset Report Dashboard
─────────────────────
Run:   py -3.12 main.py
Or:    double-click  AssetReport.bat

First-time setup:
    py -3.12 -m pip install -r requirements.txt
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from gui import AssetReportApp


def main():
    app = QApplication(sys.argv)

    # Dark palette so native dialogs match the theme
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor("#1a1a1a"))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorRole.Base,            QColor("#242424"))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor("#2a2a2a"))
    palette.setColor(QPalette.ColorRole.Text,            QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorRole.Button,          QColor("#2a2a2a"))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor("#3a3a5a"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#e0e0e0"))
    app.setPalette(palette)

    window = AssetReportApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
