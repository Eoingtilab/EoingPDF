"""Use one GUI-capable Qt application for mixed engine and widget tests."""
import os


def pytest_configure(config):
    # Must run before test module collection: process tests create a Qt core
    # application at import time, which otherwise prevents later QWidget use.
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    config._eoing_qt_application = QApplication.instance() or QApplication([])
