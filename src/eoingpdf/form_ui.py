"""Local form entry, with values passed only to the owned worker's stdin."""
from .localization import tr
from pathlib import Path
import pymupdf as pdf
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QCheckBox, QPushButton, QScrollArea, QWidget, QFileDialog,
                               QComboBox, QListWidget, QListWidgetItem, QAbstractItemView, QRadioButton, QButtonGroup)
from .core import open_pdf
from .forms import choice_options, choice_selection, radio_group
from .transform_process import TransformWorker


class FormDialog(QDialog):
    saved = Signal(str)

    def __init__(self, path, page_index, parent=None, password=''):
        super().__init__(parent)
        self.path = Path(path)
        self.password = password
        self.worker = None
        self.success = False
        self.target = None
        self.fields = {}
        self.radio_groups = {}
        self.setWindowTitle(tr('양식 입력 · {v0}페이지', v0=page_index + 1))
        self.resize(580, 580)
        layout = QVBoxLayout(self)
        notice = QLabel(tr('현재 페이지의 입력 칸입니다. 저장하면 원본을 유지한 암호 없는 새 사본을 만듭니다.'))
        notice.setWordWrap(True)
        layout.addWidget(notice)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        with open_pdf(self.path, self.password) as document:
            readonly_groups = {radio_group(document, field) for item in document for field in item.widgets() or ()
                               if field.field_type == pdf.PDF_WIDGET_TYPE_RADIOBUTTON and field.field_flags & pdf.PDF_FIELD_IS_READ_ONLY}
            page = document[page_index]
            for number, field in enumerate(page.widgets() or (), 1):
                if field.field_type not in (pdf.PDF_WIDGET_TYPE_TEXT, pdf.PDF_WIDGET_TYPE_CHECKBOX,
                                           pdf.PDF_WIDGET_TYPE_RADIOBUTTON, pdf.PDF_WIDGET_TYPE_COMBOBOX, pdf.PDF_WIDGET_TYPE_LISTBOX):
                    form.addRow(QLabel(tr('{v0}번 칸: 지원하지 않는 필드 종류', v0=number)))
                    continue
                if field.field_type == pdf.PDF_WIDGET_TYPE_CHECKBOX:
                    editor = QCheckBox(tr('선택'))
                    editor.setChecked(field.field_value not in (False, None, '', 'Off'))
                elif field.field_type == pdf.PDF_WIDGET_TYPE_RADIOBUTTON:
                    editor = QRadioButton(str(field.on_state() or tr('선택')))
                    group_key = radio_group(document, field)
                    if group_key not in self.radio_groups:
                        self.radio_groups[group_key] = QButtonGroup(self)
                    self.radio_groups[group_key].addButton(editor)
                    editor.setChecked(field.field_value == field.on_state())
                elif field.field_type in (pdf.PDF_WIDGET_TYPE_COMBOBOX, pdf.PDF_WIDGET_TYPE_LISTBOX):
                    options = choice_options(field)
                    selected = choice_selection(field)
                    if field.field_flags & pdf.PDF_CH_FIELD_IS_MULTI_SELECT:
                        editor = QListWidget()
                        editor.setSelectionMode(QAbstractItemView.MultiSelection)
                        editor.setMaximumHeight(160)
                        for value, label in options:
                            item = QListWidgetItem(label, editor)
                            item.setData(Qt.UserRole, value)
                            item.setSelected(value in selected)
                    else:
                        editor = QComboBox()
                        editor.addItem(tr('선택 안 함'), '')
                        for value, label in options:
                            editor.addItem(label, value)
                        editable = field.field_type == pdf.PDF_WIDGET_TYPE_COMBOBOX and field.field_flags & pdf.PDF_CH_FIELD_IS_EDIT
                        editor.setEditable(bool(editable))
                        current = str(field.field_value or '')
                        index = editor.findData(current)
                        if index >= 0:
                            editor.setCurrentIndex(index)
                        elif editable:
                            editor.setEditText(current)
                        else:
                            editor.addItem(current, current)
                            editor.setCurrentIndex(editor.count() - 1)
                else:
                    if field.field_flags & pdf.PDF_TX_FIELD_IS_MULTILINE and not field.field_flags & pdf.PDF_TX_FIELD_IS_PASSWORD:
                        editor = QPlainTextEdit(str(field.field_value or ''))
                        editor.setMaximumHeight(140)
                    else:
                        editor = QLineEdit(str(field.field_value or ''))
                        editor.setMaxLength(min(field.text_maxlen or 10000, 10000))
                        if field.field_flags & pdf.PDF_TX_FIELD_IS_PASSWORD:
                            editor.setEchoMode(QLineEdit.Password)
                readonly = bool(field.field_flags & pdf.PDF_FIELD_IS_READ_ONLY)
                if field.field_type == pdf.PDF_WIDGET_TYPE_RADIOBUTTON:
                    readonly = readonly or radio_group(document, field) in readonly_groups
                editor.setEnabled(not readonly)
                form.addRow(field.field_label or field.field_name or tr('{v0}번 입력 칸', v0=number), editor)
                if not readonly:
                    self.fields[str(field.xref)] = editor
        self.status = QLabel(tr('입력 가능한 칸이 없습니다.') if not self.fields else '')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.save = QPushButton(tr('입력 내용 새 PDF로 저장'))
        self.save.setEnabled(bool(self.fields))
        self.save.clicked.connect(self.start)
        layout.addWidget(self.save)
        self.close_button = QPushButton(tr('닫기'))
        self.close_button.clicked.connect(self.reject)
        layout.addWidget(self.close_button)

    def input_values(self):
        values = {}
        for key, editor in self.fields.items():
            if isinstance(editor, QRadioButton):
                if editor.isChecked():
                    values[key] = True
            elif isinstance(editor, QCheckBox):
                values[key] = editor.isChecked()
            elif isinstance(editor, QListWidget):
                values[key] = [item.data(Qt.UserRole) for item in editor.selectedItems()]
            elif isinstance(editor, QComboBox):
                values[key] = (editor.currentText() if editor.isEditable() and
                               editor.currentText() != editor.itemText(editor.currentIndex()) else editor.currentData())
            elif isinstance(editor, QPlainTextEdit):
                values[key] = editor.toPlainText()
            else:
                values[key] = editor.text()
        return values

    def start(self):
        from .license_ui import ensure_license
        if self.worker and self.worker.isRunning() or not ensure_license(self):
            return
        name, _ = QFileDialog.getSaveFileName(self, tr('입력 결과 저장'),
                                             str(self.path.with_name(self.path.stem + tr('_입력.pdf'))), 'PDF (*.pdf)')
        if not name:
            return
        values = self.input_values()
        self.target = name
        self.success = False
        self.worker = TransformWorker(dict(source=str(self.path), target=name,
                                          operation='fill_forms', form_values=values, password=self.password), self)
        self.worker.result.connect(self.completed)
        self.worker.finished.connect(self.worker_finished)
        self.save.setEnabled(False)
        for field in self.fields.values():
            field.setEnabled(False)
        self.status.setText(tr('입력 내용을 저장하고 있습니다.'))
        self.worker.start()

    def completed(self, success, message):
        self.success = success
        self.status.setText(message)

    def worker_finished(self):
        if self.success:
            self.saved.emit(self.target)
            self.accept()
        else:
            self.save.setEnabled(True)
            for field in self.fields.values():
                field.setEnabled(True)

    def reject(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.status.setText(tr('저장을 취소하고 있습니다.'))
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.reject()
            event.ignore()
        else:
            event.accept()
