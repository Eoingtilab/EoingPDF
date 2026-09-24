import sys
from pathlib import Path
import pymupdf as pdf
import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QListWidget, QRadioButton
from PySide6.QtTest import QTest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.forms import choice_selection
from eoingpdf.form_ui import FormDialog
from eoingpdf.advanced import transform


def fixture(path):
    with pdf.open() as doc:
        page = doc.new_page()
        for name, kind, flags in [('combo', pdf.PDF_WIDGET_TYPE_COMBOBOX, 0),
                                  ('multi', pdf.PDF_WIDGET_TYPE_LISTBOX, pdf.PDF_CH_FIELD_IS_MULTI_SELECT),
                                  ('editable', pdf.PDF_WIDGET_TYPE_COMBOBOX, pdf.PDF_CH_FIELD_IS_EDIT)]:
            field = pdf.Widget()
            field.field_name, field.field_type, field.field_flags = name, kind, flags
            field.choice_values = [('A', 'Alpha'), ('B', 'Beta'), ('C', 'Gamma')]
            field.rect = pdf.Rect(40, 40 + len(list(page.widgets() or []))*100, 240, 130 + len(list(page.widgets() or []))*100)
            page.add_widget(field)
        radios=[]
        for index, value in enumerate(('A', 'B')):
            field = pdf.Widget();field.field_name='radio'+value
            field.field_type=pdf.PDF_WIDGET_TYPE_CHECKBOX
            field.rect=pdf.Rect(300,40+40*index,320,60+40*index)
            page.add_widget(field)
            widget=list(page.widgets())[-1]
            radios.append(widget.xref)
            on=doc.xref_get_key(widget.xref,'AP/N/Yes')[1]
            off=doc.xref_get_key(widget.xref,'AP/N/Off')[1]
            doc.xref_set_key(widget.xref,'AP/N',f'<</{value} {on} /Off {off}>>')
            doc.xref_set_key(widget.xref,'T','null')
            doc.xref_set_key(widget.xref,'V','null')
            doc.xref_set_key(widget.xref,'Ff','32768')
        parent=doc.get_new_xref()
        doc.update_object(parent, '<</FT /Btn /Ff 32768 /T (group) /Kids ['+' '.join(f'{x} 0 R' for x in radios)+'] /V /Off>>')
        for x in radios:doc.xref_set_key(x,'Parent',f'{parent} 0 R')
        refs=[w.xref for w in page.widgets() if w.xref not in radios]+[parent]
        doc.xref_set_key(doc.pdf_catalog(),'AcroForm/Fields','['+' '.join(f'{x} 0 R' for x in refs)+']')
        doc.save(path)


def test_ui_selection_to_pdf_roundtrip(tmp_path, monkeypatch):
    app=QApplication.instance() or QApplication([])
    source=tmp_path/'source.pdf';target=tmp_path/'out.pdf';fixture(source)
    original=source.read_bytes()
    dialog=FormDialog(source,0)
    for editor in dialog.fields.values():
        if isinstance(editor,QComboBox):
            if editor.isEditable():editor.setEditText('Custom')
            else:editor.setCurrentIndex(editor.findData('B'))
        elif isinstance(editor,QListWidget):
            editor.item(0).setSelected(True);editor.item(2).setSelected(True)
        elif isinstance(editor,QRadioButton):editor.setChecked(editor.text()=='B')
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda *args: True)
    monkeypatch.setattr('eoingpdf.form_ui.QFileDialog.getSaveFileName', lambda *args: (str(target), 'PDF'))
    saved = []
    dialog.saved.connect(saved.append)
    dialog.show()
    dialog.save.click()
    for _ in range(500):
        if saved or dialog.worker and not dialog.worker.isRunning():
            break
        QTest.qWait(20)
    assert saved == [str(target)], dialog.status.text()
    with pdf.open(target) as doc:
        page=doc[0]
        fields=list(page.widgets())
        assert next(w for w in fields if w.field_name=='combo').field_value=='B'
        assert next(w for w in fields if w.field_name=='editable').field_value=='Custom'
        assert choice_selection(next(w for w in fields if w.field_name=='multi'))==['A','C']
        radio=[w for w in fields if w.field_type==pdf.PDF_WIDGET_TYPE_RADIOBUTTON]
        assert [doc.xref_get_key(w.xref,'AS')[1] for w in radio]==['/Off','/B']
        assert [w.field_value for w in radio] == ['Off', 'B']
        assert doc.xref_get_key(radio[0].xref, 'Parent/V')[1] == 'B'
        assert page.get_pixmap().width>0
    reopened=FormDialog(target,0)
    assert sum(e.isChecked() for e in reopened.fields.values() if isinstance(e,QRadioButton))==1
    multi=next(e for e in reopened.fields.values() if isinstance(e,QListWidget))
    assert [i.text() for i in multi.selectedItems()]==['Alpha','Gamma']
    assert source.read_bytes()==original
    dialog.close();reopened.close()


@pytest.mark.parametrize('case',['invalid','duplicate','readonly','empty_multi'])
def test_validation_and_clear(tmp_path,case):
    source=tmp_path/'source.pdf';fixture(source)
    with pdf.open(source) as doc:
        page=doc[0];fields=list(page.widgets());combo=fields[0];multi=fields[1]
        radio=[w for w in fields if w.field_type==pdf.PDF_WIDGET_TYPE_RADIOBUTTON]
        if case=='readonly':
            doc.xref_set_key(radio[0].xref,'Ff','32769')
            changed=tmp_path/'locked.pdf';doc.save(changed);source=changed
        values=({str(combo.xref):'Not an option'} if case=='invalid' else
                {str(w.xref):True for w in radio} if case=='duplicate' else
                {str(radio[1].xref):True} if case=='readonly' else {str(multi.xref):[]})
    target=tmp_path/'out.pdf'
    if case=='empty_multi':
        transform(source,target,'fill_forms',form_values=values)
        with pdf.open(target) as doc:
            page=doc[0];assert choice_selection(list(page.widgets())[1])==[]
    else:
        with pytest.raises(ValueError):transform(source,target,'fill_forms',form_values=values)
        assert not target.exists()
