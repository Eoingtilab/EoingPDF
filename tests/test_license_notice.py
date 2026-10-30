"""Activation notice ordering with synthetic stores; no keys or live transport."""
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from eoingpdf import license_ui
from eoingpdf.localization import install_language, tr


@pytest.fixture
def state(monkeypatch):
    state = Mock(data={})
    state.valid_session.return_value = False
    monkeypatch.setattr(license_ui, 'store', lambda: state)
    return state


@pytest.mark.parametrize('locale', ['ko-KR', 'en-US', 'ja-JP'])
def test_required_activation_shows_translated_notice_before_accept_once(state, monkeypatch, locale):
    app = QApplication.instance()
    install_language(app, locale)
    dialog = license_ui.LicenseDialog(required=True)
    events = []
    dialog.accepted.connect(lambda: events.append('accepted'))

    def information(parent, title, message):
        assert parent is dialog and dialog.isVisible()
        assert dialog._activation_notice_shown
        assert title == tr('라이선스 활성화')
        assert message == tr('라이선스가 활성화되었습니다.')
        assert events == []
        events.append('notice')
        return QMessageBox.Ok

    monkeypatch.setattr(QMessageBox, 'information', information)
    try:
        dialog.show()
        state.valid_session.return_value = True
        dialog.completed(True, tr('라이선스가 활성화되었습니다.'))
        dialog.idle()
        assert events == ['notice', 'accepted']
        assert dialog.result() == QDialog.Accepted and not dialog.isVisible()
        dialog.idle()
        assert events == ['notice', 'accepted']
    finally:
        dialog.reject()
        dialog.deleteLater()
        app.processEvents()
        install_language(app, 'ko-KR')


def test_reentrant_idle_during_notice_does_not_accept_before_notice_closes(state, monkeypatch):
    dialog = license_ui.LicenseDialog(required=True)
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(True))

    def information(*args):
        dialog.idle()
        assert accepted == [] and dialog.isVisible()
        return QMessageBox.Ok

    notice = Mock(side_effect=information)
    monkeypatch.setattr(QMessageBox, 'information', notice)
    try:
        dialog.show()
        state.valid_session.return_value = True
        dialog.idle()
        notice.assert_called_once()
        assert accepted == [True]
    finally:
        dialog.reject()
        dialog.deleteLater()
        QApplication.instance().processEvents()


def test_failed_activation_keeps_required_dialog_open_without_notice(state, monkeypatch):
    notice = Mock()
    monkeypatch.setattr(QMessageBox, 'information', notice)
    dialog = license_ui.LicenseDialog(required=True)
    try:
        dialog.show()
        dialog.completed(False, 'Synthetic invalid license')
        dialog.idle()
        notice.assert_not_called()
        assert dialog.isVisible() and dialog.result() != QDialog.Accepted
        assert dialog.status.text() == 'Synthetic invalid license'
    finally:
        dialog.reject()
        dialog.deleteLater()
        QApplication.instance().processEvents()


def test_already_active_required_startup_accepts_without_extra_notice(state, monkeypatch):
    state.valid_session.return_value = True
    notice = Mock()
    monkeypatch.setattr(QMessageBox, 'information', notice)
    dialog = license_ui.LicenseDialog(required=True)
    try:
        dialog.show()
        QApplication.instance().processEvents()
        notice.assert_not_called()
        assert dialog.result() == QDialog.Accepted and not dialog.isVisible()
    finally:
        dialog.reject()
        dialog.deleteLater()
        QApplication.instance().processEvents()


def test_nonrequired_settings_stays_open_without_notice_after_activation(state, monkeypatch):
    notice = Mock()
    monkeypatch.setattr(QMessageBox, 'information', notice)
    dialog = license_ui.LicenseDialog(required=False)
    try:
        dialog.show()
        state.valid_session.return_value = True
        dialog.completed(True, tr('라이선스가 활성화되었습니다.'))
        dialog.idle()
        notice.assert_not_called()
        assert dialog.isVisible() and dialog.result() != QDialog.Accepted
        dialog.finish_dialog()
        assert dialog.result() == QDialog.Accepted and not dialog.isVisible()
    finally:
        dialog.reject()
        dialog.deleteLater()
        QApplication.instance().processEvents()
