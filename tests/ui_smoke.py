import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from eoingpdf.app import Window, STYLE, ROOT
from eoingpdf.quick import QuickWindow
from eoingpdf.convert import text_pdf
import pymupdf as pdf
license_patch = patch('eoingpdf.license_ui.ensure_license', return_value=True)
license_patch.start()

app = QApplication([])
QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
app.setFont(QFont('Pretendard',10))
app.setStyleSheet(STYLE)
root = ROOT / 'temp/ui-test'
root.mkdir(parents=True, exist_ok=True)
source = root / '업무 안내.pdf'
text_pdf('문서 작업을 더 가볍게\n\n어잉PDF 사용 안내\n\n여러 문서를 선택한 뒤 우클릭으로 합칠 수 있습니다.\n원본은 그대로 보관하고 결과만 새 파일로 저장합니다.\n이미지와 텍스트, 오피스 문서를 함께 담아 보세요.\n\nEoingtilab', source)
window = Window()
window.folder.setText(str(root / 'output'))
window.add_files([str(source)])
window.show()
app.processEvents()
assert window.run_button.isEnabled()
window.grab().save(str(root / 'workspace.png'))
window.select_tool('extract')
window.add_files([str(source)])
window.page_input.setText('1')
window.start()
deadline = time.monotonic() + 15
while window.busy() and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(.01)
assert not window.busy(), 'UI job timed out'
assert window.last_output and window.last_output.is_file()
window.close()
quick = QuickWindow('merge', [str(source),str(source)], str(root / 'quick-output'))
quick.show()
deadline = time.monotonic() + 15
while (not quick.outputs or quick.worker.isRunning()) and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(.01)
assert quick.outputs, quick.status.text()
with pdf.open(quick.outputs[0]) as doc:
    assert doc.page_count == 2
quick.grab().save(str(root / 'quick.png'))
quick.close()
print('PASS: editor button flow, worker completion, quick merge, screenshots')
early = QuickWindow('merge', [str(source)], str(root / 'early-output'))
early.show()
early.close()
app.processEvents()
assert not early.worker.isRunning(), 'A closed window must not start queued work'
assert not (root / 'early-output').exists()
print('PASS: closing before queued startup does not launch a worker')
