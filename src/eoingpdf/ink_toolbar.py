"""Visible slideshow tools and explicit user-initiated image/capture import."""
from pathlib import Path
from PySide6.QtGui import QColor, QImageReader, QPixmap, QIcon
from PySide6.QtWidgets import QWidget, QPushButton, QLabel, QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QColorDialog, QFileDialog, QApplication
from .flow_layout import FlowLayout
from .localization import tr


class InkToolbar(QWidget):
    def __init__(self, slides):
        super().__init__(slides)
        self.slides = slides
        from .screen_snip import ScreenSnipper
        self.snipper = ScreenSnipper(self)
        self.snipper.captured.connect(self.insert)
        row = FlowLayout(self)
        row.addWidget(slides.ink_tools)
        self.buttons = {}
        for key, text, callback in (
            ('erase', tr('지우개 · E'), lambda: slides.select_ink_tool('erase')),
            ('select', tr('선택·이동'), lambda: slides.select_ink_tool('select')),
            ('undo', tr('실행 취소'), lambda: slides.canvas.undo_ink()),
            ('redo', tr('다시 실행'), lambda: slides.canvas.redo_ink()),
            ('delete', tr('선택 삭제'), lambda: slides.canvas.delete_selected()),
            ('clear', tr('전체 지우기'), lambda: slides.canvas.clear_ink())):
            button = QPushButton(text)
            button.setAutoDefault(False)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.buttons[key] = button
        self.buttons['erase'].setToolTip(tr('작성한 판서만 지웁니다. 이미지는 선택 삭제로 제거하세요.'))
        self.colors = QComboBox()
        for text, color in ((tr('노랑'), '#ffd100'), (tr('빨강'), '#e53935'), (tr('파랑'), '#1976d2'),
                            (tr('초록'), '#24863d'), (tr('검정'), '#111111'), (tr('흰색'), '#ffffff')):
            icon = QPixmap(16, 16)
            icon.fill(QColor(color))
            self.colors.addItem(QIcon(icon), text, color)
        self.colors.activated.connect(lambda _: self.apply_color(QColor(self.colors.currentData())))
        row.addWidget(self.colors)
        custom = QPushButton(tr('다른 색'))
        custom.setAutoDefault(False)
        custom.clicked.connect(self.choose_color)
        row.addWidget(custom)
        row.addWidget(QLabel(tr('굵기')))
        self.width_control = QDoubleSpinBox()
        self.width_control.setRange(1, 40)
        self.width_control.setValue(2.5)
        self.width_control.setSuffix(' pt')
        self.width_control.valueChanged.connect(lambda value: setattr(slides.canvas, 'stroke_width', value))
        row.addWidget(self.width_control)
        row.addWidget(QLabel(tr('글자 크기')))
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 72)
        self.font_size.setValue(18)
        self.font_size.valueChanged.connect(lambda value: setattr(slides.canvas, 'text_size', value))
        row.addWidget(self.font_size)
        self.fill = QCheckBox(tr('도형 채우기'))
        from .sdk_theme import apply_style
        apply_style(self.fill, 'QCheckBox {color:#e5ecfa;}')
        self.fill.toggled.connect(lambda checked: setattr(slides.canvas, 'shape_fill', checked))
        row.addWidget(self.fill)
        for key, label, callback in (('image', tr('이미지 넣기'), self.choose_image),
                                     ('paste', tr('붙여넣기 · Ctrl+V'), self.paste),
                                     ('capture', tr('화면 캡처'), self.capture)):
            button = QPushButton(label)
            button.setAutoDefault(False)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.buttons[key] = button

    def apply_color(self, color):
        if color.isValid():
            self.slides.canvas.ink_color = (color.redF(), color.greenF(), color.blueF())
            self.slides.canvas.custom_ink_color = True

    def choose_color(self):
        self.apply_color(QColorDialog.getColor(QColor.fromRgbF(*self.slides.canvas.ink_color), self, tr('판서 색 선택')))

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('슬라이드에 넣을 이미지 선택'), '', tr('이미지 (*.png *.jpg *.jpeg *.bmp)'))
        if path:
            try:
                if Path(path).stat().st_size > 20 * 1024 * 1024:
                    raise ValueError(tr('20MB 이하의 이미지를 선택해 주세요.'))
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                size = reader.size()
                if size.width() * size.height() > 12_000_000:
                    raise ValueError(tr('이미지는 1200만 픽셀 이하로 선택해 주세요.'))
                self.insert(reader.read())
            except Exception as error:
                self.slides.hint.setText(str(error))

    def insert(self, image):
        try:
            self.slides.canvas.add_picture(image)
            self.slides.ink_tools.setCurrentIndex(self.slides.ink_tools.findData('select'))
            self.slides.ink_button.setChecked(True)
            self.slides.hint.setText(tr('이미지를 끌어 이동하고 오른쪽 아래 모서리로 크기를 조절하세요.'))
            return True
        except Exception as error:
            self.slides.hint.setText(str(error))
            return False

    def paste(self):
        self.insert(QApplication.clipboard().image())

    def capture(self):
        if self.slides.canvas.commit_text():
            self.snipper.start()

    def stop_capture(self, restore=True):
        self.snipper.cancel(restore=restore)
