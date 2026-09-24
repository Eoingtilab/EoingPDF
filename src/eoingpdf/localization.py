"""Bundled translations with OS language selection and Korean fallback."""
import ctypes
import json
import os
import sys
from pathlib import Path

SUPPORTED = {'ko-KR', 'en-US', 'ja-JP'}
_messages = None
_locale = 'ko-KR'


def normalize_locale(name):
    language = str(name).replace('_', '-').split('-')[0].lower()
    return {'ko': 'ko-KR', 'en': 'en-US', 'ja': 'ja-JP'}.get(language, 'ko-KR')


def system_locale():
    if sys.platform == 'win32':
        try:
            function = ctypes.windll.kernel32.GetUserDefaultUILanguage
            function.restype = ctypes.c_ushort
            primary = function() & 0x3ff
            return {0x12: 'ko-KR', 0x09: 'en-US', 0x11: 'ja-JP'}.get(primary, 'ko-KR')
        except (AttributeError, OSError):
            pass
    from PySide6.QtCore import QLocale
    return normalize_locale(QLocale.system().name())


def load_catalog(locale, folder=None):
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    folder = Path(folder) if folder is not None else root / 'assets/locales'
    result = {}
    for name in dict.fromkeys(('ko-KR', normalize_locale(locale))):
        try:
            data = json.loads((folder / f'{name}.json').read_text(encoding='utf-8-sig'))
            if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
                continue
            result.update(data)
        except (OSError, ValueError):
            continue
    return result


def tr(text, **values):
    if _messages is None:
        configure_language()
    translated = _messages.get(text, text)
    try:
        return translated.format(**values) if values else translated
    except (KeyError, ValueError, IndexError):
        return text.format(**values) if values else text


def configure_language(locale=None):
    """Select messages without loading Qt, also used by document worker processes."""
    global _messages, _locale
    _locale = normalize_locale(locale or os.environ.get('EOINGPDF_LANGUAGE') or system_locale())
    _messages = load_catalog(_locale)
    return _locale


def current_locale():
    if _messages is None:
        configure_language()
    return _locale


def install_language(app, locale=None):
    from PySide6.QtCore import QTranslator, QLibraryInfo
    configure_language(locale or system_locale())
    previous = getattr(app, 'eoing_translator', None)
    if previous is not None:
        app.removeTranslator(previous)
        previous.deleteLater()
    translator = QTranslator(app)
    language = _locale.split('-')[0]
    if translator.load('qtbase_' + language, QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
    app.eoing_translator = translator
    app.eoing_locale = _locale
    return _locale


def install_korean(app):
    return install_language(app, 'ko-KR')
