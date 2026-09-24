import sys
from pathlib import Path
import pymupdf as pdf
import pytest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import Cancelled


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_outlined_pdf_visual_and_font_independence(tmp_path, rotation):
    source, target = tmp_path/'source.pdf', tmp_path/'out.pdf'
    with pdf.open() as doc:
        page = doc.new_page(width=500,height=400)
        page.insert_font(fontname='custom',fontfile='assets/fonts/Pretendard-Regular.ttf')
        page.insert_text((70,100),'어잉PDF 인쇄용 ABC 012',fontname='custom',fontsize=22)
        page.draw_circle((150,190),35,color=(.2,.5,.9),fill=(.8,.9,1))
        page.draw_rect(pdf.Rect(200,160,280,220),fill=(1,.2,.1),fill_opacity=.4)
        image=pdf.Pixmap(pdf.csRGB,pdf.IRect(0,0,20,20),False)
        image.clear_with(95)
        page.insert_image(pdf.Rect(300,180,350,230),pixmap=image)
        page.set_cropbox(pdf.Rect(20,20,460,380))
        page.set_rotation(rotation)
        doc.set_toc([[1,'Print',1]])
        doc.save(source)
    original=source.read_bytes()
    assert transform(source,target,'outlines')==1
    with pdf.open(source) as before, pdf.open(target) as after:
        assert after[0].rect==before[0].rect
        assert not after[0].get_fonts(full=True)
        assert not after[0].get_text().strip()
        assert len(after[0].get_drawings()) > len(before[0].get_drawings()) + 8
        assert after[0].get_images()
        assert after.get_toc()==before.get_toc()
        a=before[0].get_pixmap(matrix=pdf.Matrix(2,2),alpha=False)
        b=after[0].get_pixmap(matrix=pdf.Matrix(2,2),alpha=False)
        first=np.frombuffer(a.samples,dtype=np.uint8).astype(float)
        second=np.frombuffer(b.samples,dtype=np.uint8).astype(float)
        assert np.abs(first-second).mean()<1.0
        assert (np.abs(first-second)>40).mean()<.005
    assert source.read_bytes()==original


def test_outlines_cancel_does_not_publish(tmp_path):
    source,target=tmp_path/'source.pdf',tmp_path/'out.pdf'
    with pdf.open() as doc:
        doc.new_page().insert_text((30,30),'Test')
        doc.save(source)
    with pytest.raises(Cancelled):
        transform(source,target,'outlines',cancelled=lambda:True)
    assert not target.exists()
    assert not list(tmp_path.glob('.eoing-*'))



def test_outlines_encrypted_widgets_and_annotations(tmp_path):
    source, target = tmp_path/'locked.pdf', tmp_path/'print.pdf'
    with pdf.open() as doc:
        page = doc.new_page(width=400,height=300)
        field = pdf.Widget()
        field.field_type = pdf.PDF_WIDGET_TYPE_TEXT
        field.field_name = 'Name'
        field.field_value = 'Print form'
        field.rect = pdf.Rect(30,40,220,80)
        page.add_widget(field)
        annotation = page.add_freetext_annot(pdf.Rect(30,100,220,150),'Visible note',fontsize=14)
        annotation.update()
        doc.save(source,encryption=pdf.PDF_ENCRYPT_AES_256,user_pw='test-password',owner_pw='owner')
    original=source.read_bytes()
    transform(source,target,'outlines',password='test-password')
    with pdf.open(source) as before, pdf.open(target) as after:
        before.authenticate('test-password')
        assert not after.needs_pass
        assert not list(after[0].widgets() or ())
        assert not list(after[0].annots() or ())
        assert not after[0].get_fonts(full=True)
        a=before[0].get_pixmap(matrix=pdf.Matrix(2,2),alpha=False)
        b=after[0].get_pixmap(matrix=pdf.Matrix(2,2),alpha=False)
        diff=np.abs(np.frombuffer(a.samples,dtype=np.uint8).astype(float)-np.frombuffer(b.samples,dtype=np.uint8).astype(float))
        assert diff.mean()<1
    assert source.read_bytes()==original
