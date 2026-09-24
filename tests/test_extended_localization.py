"""Language changes preserve operation identifiers, PDF data and worker results."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pymupdf as pdf
import pytest
from PySide6.QtCore import QObject
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.localization import current_locale, install_language, load_catalog


@pytest.fixture(params=['en-US', 'ja-JP'])
def translated(request):
    app = QApplication.instance()
    previous = current_locale()
    locale = request.param
    install_language(app, locale)
    try:
        yield locale, load_catalog(locale)
    finally:
        install_language(app, previous)


def test_all_advanced_tools_keep_identifiers(translated):
    from eoingpdf.advanced import TOOLS
    from eoingpdf.advanced_ui import AdvancedDialog
    _, catalog = translated
    dialog = AdvancedDialog()
    try:
        for index, (operation, (name, description)) in enumerate(TOOLS.items()):
            dialog.tool.setCurrentIndex(index)
            assert dialog.tool.currentData() == operation
            assert dialog.tool.currentText() == catalog[name] != name
            assert dialog.description.text() == catalog[description] != description
            assert dialog.user_password.isHidden() == (operation != 'encrypt')
            assert dialog.split_ranges.isHidden() == (operation != 'split_ranges')
            assert dialog.stamp_pages.isHidden() == (operation != 'stamp')
    finally:
        dialog.close()
        dialog.deleteLater()


def test_form_chrome_does_not_translate_document_fields(tmp_path, translated):
    from eoingpdf.form_ui import FormDialog
    _, catalog = translated
    path = tmp_path / '선택.pdf'
    with pdf.open() as document:
        page = document.new_page()
        widget = pdf.Widget()
        widget.field_name = '선택'
        widget.field_label = '닫기'
        widget.field_type = pdf.PDF_WIDGET_TYPE_TEXT
        widget.field_value = '저장'
        widget.rect = pdf.Rect(50, 50, 300, 80)
        page.add_widget(widget)
        document.save(path)
    original = path.read_bytes()
    dialog = FormDialog(path, 0)
    try:
        labels = [label.text() for label in dialog.findChildren(QLabel)]
        assert '닫기' in labels
        assert dialog.findChild(QLineEdit).text() == '저장'
        assert list(dialog.input_values().values()) == ['저장']
        assert dialog.close_button.text() == catalog['닫기'] != '닫기'
        assert dialog.windowTitle() == catalog['양식 입력 · {v0}페이지'].format(v0=1)
        assert path.read_bytes() == original
    finally:
        dialog.close()
        dialog.deleteLater()


def run_worker(worker):
    results, done = [], []
    worker.result.connect(lambda ok, message: results.append((ok, message)))
    worker.finished.connect(lambda: done.append(True))
    worker.start()
    deadline = time.monotonic() + 15
    try:
        while not done and time.monotonic() < deadline:
            QTest.qWait(20)
        assert done and len(results) == 1, results
        assert not worker.isRunning()
        return results[0]
    finally:
        if worker.isRunning():
            worker.process.kill()
            worker.process.waitForFinished(3000)


def test_real_workers_propagate_locale_and_preserve_unicode_paths(tmp_path, translated):
    from eoingpdf.transform_process import TransformWorker
    from eoingpdf.search_worker import SearchChild
    _, catalog = translated
    source, target = tmp_path / '선택 원본.pdf', tmp_path / '닫기 결과.pdf'
    with pdf.open() as document:
        document.new_page().insert_text((50, 60), 'Preserve document content.')
        document.save(source)
    original = source.read_bytes()
    parent = QObject()
    try:
        ok, message = run_worker(TransformWorker(dict(source=str(source), target=str(target), operation='reverse'), parent))
        assert ok, message
        assert message.startswith(catalog['결과 파일을 저장했습니다.'])
        assert message.endswith(str(target))
        with pdf.open(target) as result:
            assert result[0].get_text().strip() == 'Preserve document content.'
        result_bytes = target.read_bytes()
        ok, message = run_worker(TransformWorker(dict(source=str(source), target=str(target), operation='reverse'), parent))
        assert not ok
        assert message == catalog['원본이나 기존 파일을 덮어쓸 수 없습니다. 새 파일명을 선택해 주세요.']
        assert source.read_bytes() == original and target.read_bytes() == result_bytes
        ok, message = run_worker(SearchChild(dict(mode='unknown'), parent))
        assert not ok and message == catalog['지원하지 않는 검색 작업입니다.']
    finally:
        parent.deleteLater()


def test_summary_keeps_source_sentences_and_uses_localized_headings(tmp_path, translated):
    from eoingpdf.summary import summarize
    _, catalog = translated
    path = tmp_path / 'source.pdf'
    sentence = 'The document content must remain exactly as written.'
    with pdf.open() as document:
        document.new_page().insert_text((50, 60), sentence)
        document.save(path)
    result = summarize(path)
    assert result.startswith(catalog['전체 {count}페이지 · 핵심문장 {sentences}개'].format(count=1, sentences=1))
    assert '[p.1] ' + sentence in result


def test_engine_localization_does_not_import_qt():
    environment = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), EOINGPDF_LANGUAGE='en-US')
    result = subprocess.run([sys.executable, '-c',
        "import sys; import eoingpdf.core; "
        "from eoingpdf.localization import tr; print(tr('작업을 취소했습니다.')); "
        "assert not any(n.startswith('PySide6') for n in sys.modules)"],
        env=environment, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'The operation was cancelled.'


def test_literal_translation_keys_exist_in_all_catalogs():
    catalog = load_catalog('ko-KR')
    missing = []
    for path in (ROOT / 'src/eoingpdf').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tr'
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                key = node.args[0].value
                if key not in catalog:
                    missing.append((path.name, node.lineno, key))
    assert not missing
    for locale in ('en-US', 'ja-JP'):
        path = ROOT / f'assets/locales/{locale}.json'
        assert json.loads(path.read_text(encoding='utf-8')).keys() == catalog.keys()
