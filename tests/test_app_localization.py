"""Language selection must not change operation routing or file selection rules."""
from pathlib import Path
import sys

import pymupdf as pdf
import pytest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.app import TOOLS, Window
from eoingpdf.localization import install_language, load_catalog


@pytest.mark.parametrize('locale', ['ko-KR', 'en-US', 'ja-JP'])
def test_main_window_translates_tools_without_changing_operations(tmp_path, locale):
    app = QApplication.instance()
    previous = getattr(app, 'eoing_locale', 'ko-KR')
    catalog = load_catalog(locale)
    install_language(app, locale)
    window = Window()
    source = tmp_path / 'document.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(source)
    try:
        for index, entry in enumerate(TOOLS):
            key, title, subtitle, hint, action = entry
            window.nav_buttons[index].click()
            assert window.tool == key
            assert window.title.text() == catalog[title]
            assert window.subtitle.text() == catalog[subtitle]
            assert window.option_hint.text() == catalog[hint]
            assert window.run_button.text() == catalog[action]
            assert window.rotation.isHidden() == (key != 'rotate')
            assert window.page_input.isHidden() == (key in {'merge', 'convert', 'summary', 'optimize'})
            window.add_files([str(source)])
            assert window.files.count() == 1
            assert window.run_button.isEnabled()
            assert window.count_label.text() == catalog['{count}개 파일'].format(count=1)
        window.clear_files()
        assert not window.run_button.isEnabled()
        assert window.count_label.text() == catalog['{count}개 파일'].format(count=0)
    finally:
        window.close()
        install_language(app, previous)
