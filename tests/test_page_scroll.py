import sys
from pathlib import Path
import pymupdf as pdf
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from eoingpdf.viewer import PdfViewer


def wheel(viewer, amount=-120, *, pixels=0, phase=Qt.NoScrollPhase, modifiers=Qt.NoModifier, x=0):
    area=viewer.scroll.viewport()
    position=QPointF(area.rect().center())
    event=QWheelEvent(position, QPointF(area.mapToGlobal(position.toPoint())),
                      QPoint(0,pixels), QPoint(x,amount), Qt.NoButton, modifiers, phase, False)
    QApplication.sendEvent(area,event)
    QApplication.processEvents()


@pytest.fixture
def viewer(tmp_path):
    source=tmp_path/'scroll.pdf'
    with pdf.open() as doc:
        for height in (1200,1000,150):
            doc.new_page(width=400,height=height)
        doc.save(source)
    window=PdfViewer(source)
    window.resize(1000,700)
    window.show()
    QTest.qWait(80)
    yield window
    window.close()
    QApplication.processEvents()


def test_end_scroll_next_and_top_scroll_previous(viewer):
    bar=viewer.scroll.verticalScrollBar()
    assert bar.maximum()>0
    wheel(viewer)
    assert viewer.page.value()==1 and bar.value()>0
    bar.setValue(bar.maximum())
    wheel(viewer)
    assert viewer.page.value()==2
    assert bar.value()==0
    QTest.qWait(200)
    wheel(viewer,120)
    assert viewer.page.value()==1
    assert bar.value()==bar.maximum()
    QTest.qWait(60)
    assert bar.value()==bar.maximum()


def test_small_page_last_page_modifiers_and_horizontal(viewer):
    viewer.page.setValue(3)
    QTest.qWait(50)
    bar=viewer.scroll.verticalScrollBar()
    assert bar.maximum()==0
    wheel(viewer)
    assert viewer.page.value()==3
    QTest.qWait(200)
    wheel(viewer,120,modifiers=Qt.ControlModifier)
    assert viewer.page.value()==3
    wheel(viewer,0,x=120)
    assert viewer.page.value()==3
    wheel(viewer,120)
    assert viewer.page.value()==2
    assert bar.value()==bar.maximum()


def test_pixel_accumulation_and_momentum_do_not_skip_pages(viewer):
    bar=viewer.scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    wheel(viewer,0,pixels=-20,phase=Qt.ScrollUpdate)
    assert viewer.page.value()==1
    wheel(viewer,0,pixels=-30,phase=Qt.ScrollUpdate)
    assert viewer.page.value()==2
    bar.setValue(bar.maximum())
    QTest.qWait(200)
    wheel(viewer,0,pixels=-200,phase=Qt.ScrollMomentum)
    assert viewer.page.value()==2
    wheel(viewer,-120)
    assert viewer.page.value()==3


def test_first_page_and_pending_deleted_page_order(viewer):
    wheel(viewer,120)
    assert viewer.page.value()==1
    viewer.pages=[0,2]
    viewer.count=2
    viewer.page.setMaximum(2)
    viewer.render()
    viewer.scroll.verticalScrollBar().setValue(viewer.scroll.verticalScrollBar().maximum())
    QTest.qWait(200)
    wheel(viewer)
    assert viewer.page.value()==2 and viewer.pages[viewer.page.value()-1]==2
