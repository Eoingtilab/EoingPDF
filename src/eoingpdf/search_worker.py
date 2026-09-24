"""Sequential extraction and embedding with atomic index publication."""
from .localization import tr
import json
from pathlib import Path
import tempfile
from PySide6.QtCore import QObject, Signal
from .transform_process import TransformWorker


class SearchChild(TransformWorker):
    child_option = '--search-child'


class SearchWorker(QObject):
    progress = Signal(int)
    result = Signal(bool, str)
    finished = Signal()

    def __init__(self, options, parent):
        super().__init__(parent)
        self.options = dict(options)
        self.child = None
        self.temporary = None
        self.cancelled = False
        self.done = False
        self.phase = options.get('mode')
        self.outcome = None
        self.prepared = None

    @property
    def process(self):
        return self.child.process

    @property
    def cancel_timer(self):
        return self.child.cancel_timer

    def start(self):
        if self.child is not None or self.done:
            return
        try:
            self.begin()
        except (OSError, ValueError, KeyError, TypeError):
            self.finish(False, tr('검색 임시 폴더를 만들지 못했습니다. 저장 위치와 권한을 확인해 주세요.'))

    def begin(self):
        if self.phase == 'build':
            folder = Path(self.options['database']).resolve().parent
            folder.mkdir(parents=True, exist_ok=True)
            self.temporary = tempfile.TemporaryDirectory(prefix='eoing-index-', dir=folder)
            self.options['staged'] = str(Path(self.temporary.name) / 'pending.sqlite3')
            self.phase = 'prepare'
        self.launch()

    def launch(self):
        self.outcome = None
        self.child = SearchChild(dict(self.options, mode=self.phase), self)
        self.child.progress.connect(self.on_progress)
        self.child.result.connect(self.capture)
        self.child.finished.connect(self.advance)
        self.child.start()
        if self.cancelled:
            self.child.requestInterruption()

    def on_progress(self, value):
        self.progress.emit(value // 2 if self.phase == 'prepare' else
                           50 + value // 2 if self.phase == 'complete' else value)

    def capture(self, success, message):
        self.outcome = success, message

    def isRunning(self):
        return self.child is not None and not self.done

    def requestInterruption(self):
        self.cancelled = True
        if self.child is not None and not self.done:
            self.child.requestInterruption()

    def advance(self):
        success, message = self.outcome or (False, tr('검색 작업을 완료하지 못했습니다.'))
        if self.cancelled:
            success, message = False, tr('검색 작업을 취소했습니다.')
        if success and self.phase == 'prepare':
            try:
                self.prepared = json.loads(message)
                if not isinstance(self.prepared, dict):
                    raise ValueError()
            except (ValueError, TypeError):
                success, message = False, tr('검색 준비 결과가 올바르지 않습니다.')
            else:
                self.child.deleteLater()
                self.phase = 'complete'
                try:
                    self.launch()
                except (OSError, ValueError):
                    self.finish(False, tr('검색 처리 프로세스를 시작하지 못했습니다.'))
                return
        if success and self.phase == 'complete':
            message = json.dumps(self.prepared, ensure_ascii=False)
        self.finish(success, message)

    def finish(self, success, message):
        if self.done:
            return
        self.done = True
        if self.temporary is not None:
            try:
                self.temporary.cleanup()
            except OSError:
                success, message = False, tr('검색 임시 파일을 정리하지 못했습니다. 앱을 닫고 다시 시도해 주세요.')
            self.temporary = None
        self.options.clear()
        self.result.emit(success, message)
        self.finished.emit()
