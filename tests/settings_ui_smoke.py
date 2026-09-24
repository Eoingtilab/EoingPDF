import sys
from pathlib import Path
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.settings_ui import SettingsDialog

app = QApplication.instance() or QApplication([])
shell = Mock()
dialog = SettingsDialog(shell_settings=shell)
dialog.show()
QTest.qWait(40)
assert dialog.tabs.count() == 3 and dialog.timer.isActive()
assert not dialog.check_button.isEnabled()
dialog.shell.click()
shell.assert_called_once()
with patch('eoingpdf.license_ui.settings') as settings:
    dialog.license_button.click()
    settings.assert_called_once_with(dialog)
updater = Mock(pending=None, running=False, message='테스트 서버 확인 완료')
app.updater = updater
dialog.refresh()
assert dialog.check_button.isEnabled()
dialog.check_button.click()
updater.check.assert_called_once()
updater.running = True
dialog.refresh()
assert not dialog.check_button.isEnabled()
updater.running = False
updater.pending = Path('synthetic-update.exe')
dialog.refresh()
assert '설정 창을 닫고' in dialog.update_status.text()
assert not dialog.check_button.isEnabled()
dialog.tabs.setCurrentIndex(2)
folder = ROOT / 'temp/settings-ui'
folder.mkdir(parents=True, exist_ok=True)
dialog.grab().save(str(folder / 'settings.png'))
dialog.close()
assert not dialog.timer.isActive()
del app.updater
from eoingpdf.localization import install_language
for locale, title, tab in [('en-US', 'EoingPDF · Settings', 'General'),
                           ('ja-JP', 'EoingPDF · 設定', '一般')]:
    install_language(app, locale)
    translated = SettingsDialog()
    translated.show()
    QTest.qWait(40)
    assert translated.windowTitle() == title
    assert translated.tabs.tabText(0) == tab
    assert translated.shell.text() != '우클릭 메뉴·기본 PDF 앱 설정'
    translated.grab().save(str(folder / f'{locale}.png'))
    translated.close()
install_language(app, 'ko-KR')
print('PASS: shell/license routing, update busy/pending states, no real network/license access, timer shutdown')
