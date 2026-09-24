"""On-demand presenter controls; document notes never leave the local process."""
from .localization import tr
from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QEvent, QPointF
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QTextBrowser, QSpinBox)
import pymupdf as pdf
from .core import open_pdf
from .sdk_theme import apply_style


class PresenterHud(QDialog):
    def __init__(self, audience):
        super().__init__(audience, Qt.Window)
        self.audience = audience
        self.setWindowTitle(tr('어잉PDF · 발표자 화면'))
        self.resize(820, 720)
        apply_style(self, '''
            QDialog {background:#f6f8fc;color:#193455;}
            QLabel {background:transparent;color:#193455;font-size:16px;padding:4px;}
            QTextBrowser {background:white;color:#193455;font-size:22px;padding:16px;border:1px solid #dbe5f5;border-radius:12px;}
            QPushButton {background:white;color:#193455;min-height:40px;border:1px solid #dbe5f5;border-radius:8px;}
            QSpinBox {background:white;color:#193455;min-height:36px;}
        ''')
        layout = QVBoxLayout(self)
        self.position = QLabel()
        layout.addWidget(self.position)
        row = QHBoxLayout()
        self.clock = QLabel('00:00')
        row.addWidget(self.clock)
        row.addWidget(QLabel(tr('발표 예정 시간')))
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 600)
        self.minutes.setValue(20)
        self.minutes.setSuffix(tr(' 분'))
        self.minutes.valueChanged.connect(self.update_clock)
        row.addWidget(self.minutes)
        layout.addLayout(row)
        self.pace = QLabel()
        layout.addWidget(self.pace)
        previews = QHBoxLayout()
        self.current = QLabel()
        self.current.setMouseTracking(True)
        self.current.installEventFilter(self)
        self.next = QLabel()
        for label in (self.current, self.next):
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumSize(240, 180)
            previews.addWidget(label)
        layout.addLayout(previews)
        layout.addWidget(QLabel(tr('현재 페이지의 스티커 메모 대본')))
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(False)
        layout.addWidget(self.notes, 1)
        buttons = QHBoxLayout()
        for caption, callback in (
            (tr('이전'), lambda: audience.advance(-1)),
            (tr('다음'), lambda: audience.advance(1)),
            (tr('페이지 목록 · G'), audience.show_grid),
            (tr('검은 화면 · B'), lambda: audience.set_blank('black')),
            (tr('흰 화면 · W'), lambda: audience.set_blank('white')),
            (tr('발표 종료'), audience.reject),
        ):
            button = QPushButton(caption)
            button.setAutoDefault(False)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.elapsed = QElapsedTimer()
        self.elapsed.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_clock)
        self.timer.start(1000)
        audience.page_changed.connect(self.refresh)
        audience.finished.connect(self.finish)
        self.refresh()

    def finish(self, result=0):
        self.timer.stop()
        super().done(result)

    def reject(self):
        self.audience.reject()

    def closeEvent(self, event):
        self.audience.reject()
        if self.audience.isVisible():
            event.ignore()
        else:
            event.accept()

    def update_clock(self, *_):
        seconds = self.elapsed.elapsed() // 1000
        self.clock.setText(f'{seconds // 60:02d}:{seconds % 60:02d}')
        expected = min(self.audience.count - 1,
                       int(seconds / (self.minutes.value() * 60) * self.audience.count))
        behind = expected - self.audience.index
        self.pace.setText(tr('예정 진도보다 {v0}페이지 늦습니다', v0=behind) if behind > 0 else tr('예정 진도에 맞춰 진행 중입니다'))
        self.pace.setStyleSheet('color:#b42318;background:#fee4e2;' if behind >= 2 else
                               'color:#854d0e;background:#fef3c7;' if behind == 1 else '')

    def refresh(self):
        audience = self.audience
        self.position.setText(tr('현재 {v0} / {v1} · 오른쪽은 다음 페이지', v0=audience.index + 1, v1=audience.count))
        try:
            with open_pdf(audience.path, audience.password) as document:
                for offset, label in ((0, self.current), (1, self.next)):
                    index = audience.index + offset
                    label.clear()
                    if index >= audience.count:
                        label.setText(tr('마지막 페이지입니다'))
                        continue
                    page = document[audience.pages[index]]
                    scale = min(340 / page.rect.width, 240 / page.rect.height)
                    raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                    image = QImage(raster.samples, raster.width, raster.height, raster.stride, QImage.Format_RGB888).copy()
                    label.setPixmap(QPixmap.fromImage(image))
                page = document[audience.pages[audience.index]]
                scripts = [(annotation.info.get('content') or '').strip()
                           for annotation in (page.annots() or ()) if annotation.type[0] == pdf.PDF_ANNOT_TEXT]
                self.notes.setPlainText('\n\n'.join(text for text in scripts if text) or tr('이 페이지에 스티커 메모 대본이 없습니다.'))
        except Exception as error:
            self.current.clear()
            self.next.clear()
            self.notes.setPlainText(tr('발표 자료를 읽지 못했습니다: {v0}', v0=error))
        self.update_clock()

    def keyPressEvent(self, event):
        self.audience.keyPressEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.current and event.type() == QEvent.MouseMove:
            preview = self.current.pixmap()
            canvas = self.audience.canvas
            shown = canvas.pixmap()
            if preview and not preview.isNull() and shown and not shown.isNull():
                small = preview.deviceIndependentSize()
                u = (event.position().x() - (self.current.width() - small.width()) / 2) / small.width()
                v = (event.position().y() - (self.current.height() - small.height()) / 2) / small.height()
                if 0 <= u <= 1 and 0 <= v <= 1:
                    large = shown.deviceIndependentSize()
                    canvas.move_pointer(QPointF((canvas.width() - large.width()) / 2 + u * large.width(),
                                               (canvas.height() - large.height()) / 2 + v * large.height()))
        return super().eventFilter(watched, event)
