import sys
from pathlib import Path
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication, QLineEdit
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.localization import install_language, tr
from eoingpdf.license_ui import LicenseDialog

app = QApplication.instance() or QApplication([])
state = Mock(data={})
state.valid_session.return_value = False
folder = ROOT / 'temp/license-ui-synthetic'
folder.mkdir(parents=True, exist_ok=True)
with patch('eoingpdf.license_ui.store', return_value=state), patch('eoingpdf.license_ui.LicenseWorker') as worker:
    for locale in ('ko-KR', 'en-US', 'ja-JP'):
        install_language(app, locale)
        dialog = LicenseDialog(required=True)
        dialog.show()
        QTest.qWait(30)
        assert dialog.key.text() == ''
        assert dialog.key.echoMode() == QLineEdit.Password
        assert dialog.activate.text() == tr('활성화 / 재활성화')
        dialog.finish_dialog()
        assert dialog.isVisible()
        assert dialog.status.text() == tr('라이선스를 활성화한 뒤 계속할 수 있습니다.')
        dialog.completed(False, '라이선스가 만료되었습니다.')
        assert dialog.status.text() == tr('라이선스가 만료되었습니다.')
        dialog.grab().save(str(folder / f'{locale}.png'))
        dialog.reject()
        assert not dialog.isVisible()
    worker.assert_not_called()
install_language(app, 'ko-KR')
print('PASS: three-language license UI, password masking, activation gate and errors; synthetic empty store only')
