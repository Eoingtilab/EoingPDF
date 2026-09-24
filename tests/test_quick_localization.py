import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.localization import install_language
from eoingpdf.quick import QuickWindow


@pytest.mark.parametrize('locale,title,done,cancelled', [
    ('ko-KR', 'PDF로 바꾸고 있어요', '완료했어요!', '작업을 취소했어요'),
    ('en-US', 'Converting to PDF', 'All done!', 'Task cancelled'),
    ('ja-JP', 'PDFに変換しています', '完了しました！', '操作をキャンセルしました'),
])
def test_quick_window_uses_os_language_and_formats_results(monkeypatch, locale, title, done, cancelled):
    app = QApplication.instance()
    previous = getattr(app, 'eoing_locale', 'ko-KR')
    monkeypatch.setattr('eoingpdf.localization.system_locale', lambda: locale)
    install_language(app)
    window = QuickWindow('convert', ['a.pdf', 'b.pdf'])
    window.pending_start = False
    try:
        assert window.title.text() == title
        assert '2' in window.status.text()
        window.completed({'outputs': ['a.pdf'], 'errors': [], 'cancelled': False})
        assert window.title.text() == done
        assert '{' not in window.status.text()
        window.completed({'outputs': [], 'errors': [], 'cancelled': True})
        assert window.title.text() == cancelled
    finally:
        window.close()
        window.deleteLater()
        install_language(app, previous)
