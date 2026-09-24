import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QPushButton

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.sniffer_ui import DiagnosticChips


def test_all_recommendations_remain_reachable_and_explanations_are_not_actions():
    chips = DiagnosticChips()
    received = []
    chips.action.connect(received.append)
    keys = ['metadata', 'presentation', 'four_up', 'rename', 'table', 'review']
    try:
        chips.display({'suggested_name': 'title.pdf', 'diagnostics': [
            {'action': key, 'title': key, 'code': f'D-{index}'}
            for index, key in enumerate(keys)]})
        assert chips.row.count() == 5  # Three chips, overflow, stretch.
        for index in range(3):
            chips.row.itemAt(index).widget().click()
        menu = chips.more_button.menu()
        assert len(menu.actions()) == 3
        for action in menu.actions()[:2]:
            action.trigger()
        assert received == keys[:5]
        assert not menu.actions()[-1].isEnabled()
        assert chips.suggested_name == 'title.pdf'
        old_more = chips.more_button
        chips.display({'diagnostics': []})
        assert chips.isHidden() and chips.more_button is None
        assert not old_more.isEnabled() and old_more.isHidden()
        assert chips.suggested_name == ''
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        assert not chips.findChildren(QPushButton)
    finally:
        chips.close()


def test_invalid_findings_do_not_crash_or_create_active_buttons():
    chips = DiagnosticChips()
    try:
        for findings in (None, 'bad', [None, {}, {'action': [], 'title': 'bad', 'code': 'D-01'}]):
            chips.display({'diagnostics': findings, 'suggested_name': None})
            assert chips.isHidden()
            assert chips.suggested_name == ''
            assert chips.row.count() == 1
    finally:
        chips.close()
