import hashlib
import sys
from pathlib import Path
import pymupdf as pdf
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.viewer import SlideShow


def wait_for(condition, timeout=1000):
    deadline = __import__('time').monotonic() + timeout / 1000
    while not condition() and __import__('time').monotonic() < deadline:
        QTest.qWait(20)
    return condition()

app = QApplication.instance() or QApplication([])
folder = ROOT / 'temp/presenter-ui'
folder.mkdir(parents=True, exist_ok=True)
source = folder / 'presentation.pdf'
with pdf.open() as document:
    for index in range(3):
        page = document.new_page(width=960, height=540)
        page.insert_text((30, 80), f'Slide {index + 1}')
        page.add_text_annot((100, 100), f'Private script {index + 1}')
    document.save(source)
before = hashlib.sha256(source.read_bytes()).hexdigest()
slides = SlideShow(source, pages=[0, 2])
slides.showFullScreen()
slides.show_presenter()
QTest.qWait(80)
hud = slides.presenter
assert hud.isVisible() and hud.timer.isActive()
assert 'Private script 1' in hud.notes.toPlainText()
assert not hud.current.pixmap().isNull() and not hud.next.pixmap().isNull()
QTest.keyClick(hud, Qt.Key_S)
assert slides.canvas.spotlight
QTest.mouseMove(hud.current, hud.current.rect().center())
# Offscreen full-screen windows overlap; platform cursor routing can deliver
# QTest.mouseMove to the audience instead. Send the HUD event explicitly to
# exercise its preview-to-audience coordinate mapping deterministically.
position = QPointF(hud.current.rect().center())
app.sendEvent(hud.current, QMouseEvent(QEvent.MouseMove, position, position,
                                     Qt.NoButton, Qt.NoButton, Qt.NoModifier))
assert abs(slides.canvas.pointer.x() - .5) < .01
assert abs(slides.canvas.pointer.y() - .5) < .01
spot = slides.canvas.grab().toImage()
assert spot.pixelColor(spot.width() // 2, spot.height() // 2).lightness() > 200
assert spot.pixelColor(5, 5).lightness() < 100
QTest.keyClick(hud, Qt.Key_S)
QTest.keyClick(hud, Qt.Key_L, Qt.ControlModifier)
QTest.mouseMove(hud.current, hud.current.rect().center() + QPoint(10, 10))
position = QPointF(hud.current.rect().center() + QPoint(10, 10))
app.sendEvent(hud.current, QMouseEvent(QEvent.MouseMove, position, position,
                                     Qt.NoButton, Qt.NoButton, Qt.NoModifier))
QTest.qWait(30)
assert slides.canvas.laser and slides.canvas.trail and slides.canvas.fade_timer.isActive()
laser_image = slides.canvas.grab().toImage()
laser_point = slides.canvas.pointer
color = laser_image.pixelColor(round(laser_point.x() * laser_image.width()),
                               round(laser_point.y() * laser_image.height()))
assert color.red() > color.green() + 80
# Allow Windows' full-screen paint scheduling more than one timer interval.
assert wait_for(lambda: not slides.canvas.trail and not slides.canvas.fade_timer.isActive()), list(slides.canvas.trail)
QTest.keyClick(hud, Qt.Key_L, Qt.ControlModifier)
assert not slides.canvas.laser
QTest.keyClick(hud, Qt.Key_Right)
assert slides.index == 1 and 'Private script 3' in hud.notes.toPlainText()
assert hud.next.text() == '마지막 페이지입니다'
QTest.keyClick(hud, Qt.Key_B)
assert slides.blank == 'black'
assert slides.canvas.pixmap().toImage().pixelColor(10, 10) == Qt.black
QTest.keyClick(hud, Qt.Key_W)
assert slides.blank == 'white'
assert slides.canvas.pixmap().toImage().pixelColor(10, 10) == Qt.white
QTest.keyClick(hud, Qt.Key_W)
assert slides.blank is None
QTest.keyClick(hud, Qt.Key_Left)
assert slides.index == 0
QTest.keyClick(hud, Qt.Key_G)
QTest.qWait(100)
grid = slides.grid
assert grid.isVisible() and grid.list.count() == 2
assert grid.loaded == {0, 1}
assert '원본 3쪽' in grid.list.item(1).text()
QTest.mouseClick(grid.list.viewport(), Qt.LeftButton,
                 pos=grid.list.visualItemRect(grid.list.item(1)).center())
assert slides.index == 1 and not grid.isVisible() and not grid.loaded
slides.show_grid()
QTest.qWait(40)
QTest.keyClick(grid, Qt.Key_Escape)
assert slides.index == 1 and not grid.isVisible() and not grid.timer.isActive()
slides.show_grid()
hud.grab().save(str(folder / 'hud.png'))
slides.canvas.toggle_laser()
slides.canvas.move_pointer(QPointF(100, 100))
assert slides.canvas.fade_timer.isActive()
hud.close()
app.processEvents()
assert not hud.isVisible() and not slides.isVisible() and not hud.timer.isActive()
assert not grid.isVisible() and not grid.timer.isActive()
assert not slides.canvas.fade_timer.isActive() and not slides.canvas.trail
assert hashlib.sha256(source.read_bytes()).hexdigest() == before
large = folder / 'large.pdf'
with pdf.open() as document:
    for index in range(200):
        document.new_page().insert_text((30, 80), f'Page {index + 1}')
    document.save(large)
large_slides = SlideShow(large)
large_slides.show()
large_slides.show_grid()
large_grid = large_slides.grid
QTest.qWait(150)
first_loaded = set(large_grid.loaded)
assert first_loaded and len(first_loaded) < 30
large_grid.list.scrollToItem(large_grid.list.item(199))
assert wait_for(lambda: 199 in large_grid.loaded), large_grid.loaded
assert len(large_grid.loaded) < 30
assert not first_loaded.intersection(large_grid.loaded)
assert all(large_grid.list.item(index).icon().isNull() for index in first_loaded)
large_slides.reject()
assert not large_grid.timer.isActive()
print('PASS: presenter previews, draft mapping, private notes, blackout toggles, paired close and timer shutdown; source preserved')
print('PASS: G grid, click selection, Escape, bounded thumbnail retention across 200 pages')
curtain_file = folder / 'curtain.pdf'
with pdf.open() as document:
    page = document.new_page(width=600, height=600)
    page.insert_text((40, 80), 'First paragraph')
    page.insert_text((40, 400), 'Second paragraph')
    document.new_page()
    document.save(curtain_file)
curtain = SlideShow(curtain_file)
curtain.resize(800, 800)
curtain.show()
QTest.qWait(50)
assert len(curtain.reveal_steps) == 2
QTest.keyClick(curtain, Qt.Key_Space)
assert curtain.index == 0 and 0 < curtain.canvas.reveal_fraction < .5
image = curtain.canvas.grab().toImage()
assert image.pixelColor(image.width() // 2, image.height() // 2) == Qt.black
QTest.keyClick(curtain, Qt.Key_W)
image = curtain.canvas.grab().toImage()
assert image.pixelColor(image.width() // 2, image.height() // 2) == Qt.white
QTest.keyClick(curtain, Qt.Key_W)
assert curtain.canvas.reveal_fraction < .5
QTest.keyClick(curtain, Qt.Key_Space)
assert curtain.index == 0 and curtain.canvas.reveal_fraction == 1
QTest.keyClick(curtain, Qt.Key_Space)
assert curtain.index == 1 and curtain.reveal_index == -1
curtain.reject()
print('PASS: Space paragraph reveal, actual curtain pixels, whiteout priority and navigation reset')
