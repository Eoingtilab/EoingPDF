"""Private stdin protocol isolates MuPDF transformations from Qt rendering."""
import json
import sys
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from .localization import tr, current_locale, configure_language


class TransformWorker(QObject):
    child_option = '--transform-child'
    progress = Signal(int)
    result = Signal(bool, str)
    finished = Signal()

    def __init__(self, options, parent):
        super().__init__(parent)
        self.options = options
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.process.readAllStandardError)
        self.process.started.connect(self.assign_scope)
        self.process.finished.connect(self.complete)
        self.process.errorOccurred.connect(self.error)
        self.temporary = None
        self.buffer = b''
        self.received_result = False
        self.done = False
        self.cancelled = False
        self.scope = None
        self.cancel_timer = QTimer(self)
        self.cancel_timer.setSingleShot(True)
        self.cancel_timer.timeout.connect(lambda: self.process.kill() if self.isRunning() else None)

    def start(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='eoing-transform-')
        self.cancel_path = Path(self.temporary.name) / 'cancel'
        from .process_scope import ProcessScope
        self.scope = ProcessScope()
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert('TEMP', self.temporary.name)
        environment.insert('TMP', self.temporary.name)
        self.process.setProcessEnvironment(environment)
        packet = dict(self.options, cancel_path=str(self.cancel_path), locale=current_locale())
        payload = json.dumps(packet, ensure_ascii=True).encode('utf-8')
        self.options.clear()
        arguments = [] if getattr(sys, 'frozen', False) else [str(Path(__file__).resolve().parents[2] / 'main.py')]
        self.process.start(sys.executable, arguments + [self.child_option])
        self.process.write(payload)
        self.process.closeWriteChannel()

    def assign_scope(self):
        try:
            self.scope.assign(self.process.processId())
        except Exception:
            self.received_result = True
            self.result.emit(False, tr('작업 프로세스를 안전하게 격리하지 못했습니다. 앱을 다시 실행해 주세요.'))
            self.process.kill()

    def isRunning(self):
        return not self.done and self.process.state() != QProcess.NotRunning

    def requestInterruption(self):
        self.cancelled = True
        if self.temporary:
            self.cancel_path.touch()
        self.cancel_timer.start(5000)

    def read_output(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        if len(self.buffer) > 131072:
            self.process.kill()
            return
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                message = json.loads(line)
                if message.get('type') == 'progress':
                    self.progress.emit(max(0, min(100, int(message['value']))))
                elif message.get('type') == 'result' and not self.received_result:
                    self.received_result = True
                    self.result.emit(message.get('success') is True, str(message.get('message', '')))
            except (ValueError, TypeError, AttributeError, KeyError):
                self.process.kill()

    def error(self, error):
        if error == QProcess.FailedToStart:
            self.complete()

    def complete(self, *_):
        if self.done:
            return
        self.read_output()
        self.done = True
        self.cancel_timer.stop()
        if self.scope:
            self.scope.close()
        if not self.received_result:
            self.result.emit(False, tr('작업을 취소했습니다.') if self.cancelled else tr('처리 프로세스를 실행하거나 완료하지 못했습니다.'))
        if self.temporary:
            self.temporary.cleanup()
            self.temporary = None
        self.finished.emit()


def child_main():
    from .advanced import transform
    from .core import Cancelled

    def send(value):
        print(json.dumps(value, ensure_ascii=True), flush=True)

    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError(tr('요청 크기가 너무 큽니다.'))
        options = json.loads(raw)
        configure_language(options.pop('locale', None))
        cancel_path = Path(options.pop('cancel_path'))
        target = str(options['target'])
        changed = transform(**options, cancelled=cancel_path.exists,
                            progress=lambda value: send({'type': 'progress', 'value': value}))
        options.clear()
        message = tr('결과 파일을 저장했습니다.')
        if changed:
            message += tr(' 변경 항목: {count}', count=changed)
        send({'type': 'result', 'success': True, 'message': message + '\n' + target})
    except (ValueError, Cancelled) as error:
        send({'type': 'result', 'success': False, 'message': str(error)})
    except Exception:
        send({'type': 'result', 'success': False, 'message': tr('파일 상태와 저장 공간·폴더 권한을 확인해 주세요.')})
    return 0
