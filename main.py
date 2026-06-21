from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

import config
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_TITLE)
    app.setOrganizationName(config.ORG_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setFont(QFont("微软雅黑", 10))

    app.setStyleSheet("""
        QMainWindow { background:#f5f5f5; }
        QToolBar { background:#ffffff; border:none; border-bottom:1px solid #e0e0e0; spacing:4px; padding:4px; }
        QToolBar QToolButton { padding:6px 10px; border-radius:4px; }
        QToolBar QToolButton:hover { background:#eef2ff; }
        QStatusBar { background:#ffffff; border-top:1px solid #e0e0e0; }
        QGroupBox { border:1px solid #e0e0e0; border-radius:6px; margin-top:10px; padding-top:10px; font-weight:bold; color:#444; }
        QGroupBox::title { subcontrol-origin: margin; left:10px; padding:0 4px; }
        QPushButton { padding:5px 12px; border-radius:4px; border:1px solid #d0d0d0; background:#fafafa; }
        QPushButton:hover { background:#eef2ff; border-color:#6366f1; }
        QPushButton:pressed { background:#e0e7ff; }
        QTreeWidget, QListWidget { border:1px solid #e0e0e0; border-radius:4px; background:#ffffff; }
        QTabWidget::pane { border:1px solid #e0e0e0; border-radius:4px; }
        QTabBar::tab { padding:6px 14px; border:1px solid #e0e0e0; border-bottom:none; border-top-left-radius:4px; border-top-right-radius:4px; background:#f0f0f0; }
        QTabBar::tab:selected { background:#ffffff; }
        QSplitter::handle { background:#dcdcdc; }
        QSplitter::handle:horizontal { width:2px; }
        QSplitter::handle:vertical { height:2px; }
        QProgressBar { border-radius:4px; border:1px solid #d0d0d0; text-align:center; height:16px; }
        QProgressBar::chunk { background:#6366f1; border-radius:3px; }
        QLineEdit, QComboBox, QSpinBox { padding:4px 6px; border:1px solid #d0d0d0; border-radius:4px; background:#ffffff; }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
