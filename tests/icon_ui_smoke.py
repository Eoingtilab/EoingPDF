"""Validate line icons on this test's own Windows widgets and screenshots."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scale', type=float, choices=(1.25, 1.5), required=True)
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise SystemExit('This gate requires the Windows Qt platform.')
    # Use a separate process per scale. Screen-scale override makes the check
    # independent of the operator's configured Windows display scaling.
    os.environ['QT_QPA_PLATFORM'] = 'windows'
    os.environ['QT_SCALE_FACTOR'] = '1'
    os.environ['QT_SCREEN_SCALE_FACTORS'] = str(args.scale)
    os.environ['QT_SCALE_FACTOR_ROUNDING_POLICY'] = 'PassThrough'

    import pymupdf as pdf
    from PIL import Image, ImageDraw
    from PySide6.QtCore import QPoint, QSize, QSettings, Qt
    from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QImage, QPalette
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (QApplication, QMessageBox, QPushButton,
                                   QStyle, QStyleOptionButton)
    from eoingpdf.app import STYLE
    from eoingpdf.capture_ui import CaptureDialog, session
    from eoingpdf.localization import install_language
    from eoingpdf.sdk_theme import apply_style, install_theme
    from eoingpdf.stamp_editor import StampEditor
    from eoingpdf.tool_browser import ToolBrowser
    from eoingpdf.viewer import PdfViewer, SlideShow
    from eoingpdf.viewer_workspace import HistoryDialog

    app = QApplication.instance() or QApplication([])
    assert app.platformName() == 'windows'
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
    app.setFont(QFont('Pretendard', 10))
    folder = ROOT / 'temp/icon-ui-validation' / str(args.scale)
    folder.mkdir(parents=True, exist_ok=True)
    theme = install_theme(app, QSettings(str(folder / 'theme.ini'), QSettings.IniFormat))
    apply_style(app, STYLE)
    source, seal = folder / 'icon-office.pdf', folder / 'seal.jpg'
    with pdf.open() as document:
        for number in range(2):
            page = document.new_page(width=595, height=842)
            page.insert_font(fontname='sample', fontfile=str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
            page.insert_text((45, 70), 'PDF 작업 공간', fontname='sample', fontsize=26)
            page.insert_text((45, 115), '익숙한 작업을 한 화면에서 편하게', fontname='sample', fontsize=14)
            page.draw_rect(pdf.Rect(45, 250, 550, 450), color=(.7, .75, .8))
            page.insert_text((60, 295), f'검토 자료 {number + 1}', fontname='sample', fontsize=18)
        document.save(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    image = Image.new('RGB', (90, 90), 'white')
    ImageDraw.Draw(image).ellipse((9, 9, 81, 81), outline='red', width=5)
    image.save(seal)
    report = {'platform': app.platformName(), 'requested_scale': args.scale,
              'scope': 'Generated PDF/JPEG; QWidget.grab only on this test owned windows.',
              'cases': [], 'icon_checks': [],
              'exceptions': ['▲', '▼', 'thumbnailPage', 'deleteThumbnail', 'color swatches']}

    def rgb(color):
        return color.red(), color.green(), color.blue()

    def luminance(color):
        channels = [value / 255 for value in rgb(color)]
        channels = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(channels, (.2126, .7152, .0722)))

    def contrast(first, second):
        values = sorted((luminance(first), luminance(second)))
        return (values[1] + .05) / (values[0] + .05)

    def contained(widget, window):
        point = widget.mapTo(window, QPoint())
        assert window.rect().contains(point), (widget.objectName(), widget.text())
        assert window.rect().contains(point + QPoint(widget.width() - 1, widget.height() - 1)), widget.text()
        option = QStyleOptionButton()
        option.initFrom(widget)
        option.text, option.icon, option.iconSize = widget.text(), widget.icon(), widget.iconSize()
        contents = widget.style().subElementRect(QStyle.SE_PushButtonContents, option, widget)
        needed = widget.fontMetrics().horizontalAdvance(widget.text()) + widget.iconSize().width() + 4
        assert contents.width() + 2 >= needed, (widget.text(), contents.width(), needed)

    def icon_raster(icon, owner, mode=QIcon.Normal):
        ratio = owner.devicePixelRatioF()
        pixmap = icon.pixmap(QSize(16, 16), ratio, mode, QIcon.Off)
        assert not pixmap.isNull()
        assert abs(pixmap.devicePixelRatioF() - ratio) < .01
        assert abs(pixmap.width() - 16 * ratio) < 1.1
        raster = pixmap.toImage()
        group = QPalette.Disabled if mode == QIcon.Disabled else QPalette.Active
        foreground = owner.palette().color(group, QPalette.ButtonText)
        pixels = [raster.pixelColor(x, y) for y in range(raster.height()) for x in range(raster.width())]
        opaque = [pixel for pixel in pixels if pixel.alpha() >= 180]
        assert len(opaque) >= 6, (owner.objectName(), mode, len(opaque))
        assert sum(pixel.alpha() < 10 for pixel in pixels) >= len(pixels) * .2, (
            owner.objectName(), owner.property('actionIcon'), mode, sum(pixel.alpha() < 10 for pixel in pixels), len(pixels))
        assert max(max(abs(channel - expected) for channel, expected in zip(rgb(pixel), rgb(foreground)))
                   for pixel in opaque) <= 3, (owner.objectName(), rgb(foreground), rgb(opaque[0]))
        assert any(pixel.alpha() == 0 for pixel in pixels[:raster.width()])
        background = owner.palette().color(group, QPalette.Button)
        inactive = mode == QIcon.Disabled or not owner.isEnabled()
        assert contrast(foreground, background) >= (1.4 if inactive else 3), (
            owner.objectName(), rgb(foreground), rgb(background))
        return {'foreground': rgb(foreground), 'dpr': ratio, 'physical_size': pixmap.width(),
                'opaque_pixels': len(opaque), 'contrast': round(contrast(foreground, background), 2)}

    def actions(window):
        found = []
        for button in window.findChildren(QPushButton):
            if not button.isVisibleTo(window) or button.text() in ('▲', '▼') or button.objectName() in ('thumbnailPage', 'deleteThumbnail'):
                continue
            assert button.property('actionIcon'), ('Missing line action icon', type(window).__name__, button.text(), button.objectName())
            assert button.iconSize() == QSize(16, 16), button.text()
            contained(button, window)
            normal = icon_raster(button.icon(), button, QIcon.Normal)
            disabled = icon_raster(button.icon(), button, QIcon.Disabled)
            report['icon_checks'].append({'window': type(window).__name__, 'text': button.text(),
                                          'icon': button.property('actionIcon'), 'normal': normal, 'disabled': disabled})
            found.append(button.property('actionIcon'))
        return found

    def neutral_workspace(viewer):
        base = viewer.open_button.palette()
        buttons = [viewer.slideshow_button, viewer.stamp_button]
        if viewer.save_button.isEnabled():
            buttons.append(viewer.save_button)
        for button in buttons:
            for role in (QPalette.Button, QPalette.ButtonText):
                assert button.palette().color(QPalette.Active, role) == base.color(QPalette.Active, role), button.text()
            assert button.font().weight() == viewer.open_button.font().weight(), button.text()
        assert viewer.save_button.objectName() != 'primary'

    def show_on_test_screen(window):
        window.winId()
        window.windowHandle().setScreen(app.primaryScreen())
        window.move(app.primaryScreen().availableGeometry().topLeft() + QPoint(30, 30))
        window.show()

    def selected_menus(viewer, mode):
        for name, button in (('pages', viewer.page_tools_button), ('copy-view', viewer.view_tools_button),
                              ('settings', viewer.settings_button)):
            menu = button.menu()
            visible = [action for action in menu.actions() if action.isVisible() and not action.isSeparator()]
            assert visible and all(not action.icon().isNull() for action in visible)
            selected = next(action for action in visible if action.isEnabled())
            original_flags = menu.windowFlags()
            try:
                # Packaging gates launch other native windows concurrently.
                # A real Popup disappears when any such window takes focus;
                # that lifecycle is unrelated to this pixel/contrast check.
                # Keep the same QMenu, actions and QStyle painting, temporarily
                # showing it as a focusless tool window and restoring its flags.
                menu.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
                menu.winId()
                menu.windowHandle().setScreen(viewer.screen())
                menu.ensurePolished()
                menu.adjustSize()
                available = viewer.screen().availableGeometry()
                requested = button.mapToGlobal(QPoint(0, button.height()))
                anchor = QPoint(max(available.left(), min(requested.x(), available.right() - menu.width() + 1)),
                                max(available.top(), min(requested.y(), available.bottom() - menu.height() + 1)))
                menu.move(anchor)
                menu.show()
                menu.setActiveAction(selected)
                QTest.qWait(30)
                assert menu.isVisible()
                assert available.contains(menu.geometry()), (name, available, menu.geometry())
                captured = menu.grab()
                assert captured.save(str(folder / f'menu-{name}-{mode}.png'))
                row = menu.actionGeometry(selected)
                ratio = captured.devicePixelRatioF()
                raster = captured.toImage()
                background = raster.pixelColor(round((row.right() - 4) * ratio),
                                                round(row.center().y() * ratio))
                # Inspect the actual icon gutter, rather than assuming which
                # QIcon mode a platform style requests for a selected action.
                counts = Counter(rgb(raster.pixelColor(x, y))
                    for y in range(round((row.top() + 2) * ratio), round((row.bottom() - 2) * ratio))
                    for x in range(round((row.left() + 4) * ratio), round((row.left() + 27) * ratio))
                    if max(abs(value - target) for value, target in
                           zip(rgb(raster.pixelColor(x, y)), rgb(background))) > 60)
                assert counts, (name, mode, 'Selected icon gutter is blank')
                foreground = QColor(*counts.most_common(1)[0][0])
                measured = contrast(foreground, background)
                report.setdefault('selected_menus', []).append({'name': name, 'theme': mode,
                    'foreground': rgb(foreground), 'background': rgb(background), 'contrast': round(measured, 2),
                    'window_policy': 'Focusless Tool temporarily; same QMenu/QStyle, original Popup flags restored',
                    'requested_anchor': [requested.x(), requested.y()], 'captured_anchor': [anchor.x(), anchor.y()]})
                assert measured >= 3, (name, mode, rgb(foreground), rgb(background), measured)
            finally:
                menu.hide()
                menu.setWindowFlags(original_flags)
                assert menu.windowFlags() == original_flags

    with patch('eoingpdf.license_ui.ensure_license', return_value=True), \
            patch('eoingpdf.sniffer_ui.MicroSniffer.start'), \
            patch('eoingpdf.capture_ui.CaptureSession.capture'), \
            patch('eoingpdf.viewer.QMessageBox.question', return_value=QMessageBox.Discard):
        for locale in ('ko-KR', 'en-US', 'ja-JP'):
            install_language(app, locale)
            viewer = PdfViewer(source)
            show_on_test_screen(viewer)
            assert abs(viewer.devicePixelRatioF() - args.scale) < .01, viewer.devicePixelRatioF()
            previous_color = None
            try:
                for mode in ('light', 'dark'):
                    theme.set_preference(mode)
                    QTest.qWait(50)
                    color = icon_raster(viewer.open_button.icon(), viewer.open_button)['foreground']
                    if previous_color is not None:
                        assert color != previous_color, 'Existing icon did not repaint for the new theme'
                    previous_color = color
                    for width, height in ((960, 820), (680, 480)):
                        viewer.resize(width, height)
                        QTest.qWait(50)
                        assert viewer.width() == width and viewer.height() == height
                        assert viewer.scroll.height() > 100
                        neutral_workspace(viewer)
                        found = actions(viewer)
                        viewer.grab().save(str(folder / f'workspace-{locale}-{mode}-{width}.png'))
                        report['cases'].append({'locale': locale, 'theme': mode, 'size': [width, height],
                                                'actions': found, 'foreground': color})
                    viewer.move_current_page(1)
                    assert viewer.undo_button.isEnabled()
                    neutral_workspace(viewer)
                    viewer.undo_button.click()
                    assert viewer.pages == [0, 1] and viewer.redo_button.isEnabled()
                    viewer.redo_button.click()
                    if locale == 'ko-KR' and args.scale == 1.5:
                        selected_menus(viewer, mode)
                    history = HistoryDialog(viewer)
                    show_on_test_screen(history)
                    QTest.qWait(30)
                    actions(history)
                    history.grab().save(str(folder / f'history-{locale}-{mode}.png'))
                    history.reject()
                    tools = ToolBrowser(viewer)
                    tools.resize(480, 380)
                    show_on_test_screen(tools)
                    QTest.qWait(30)
                    actions(tools)
                    for index in range(tools.results.count()):
                        icon = tools.results.item(index).icon()
                        assert not icon.isNull(), tools.results.item(index).text()
                        icon_raster(icon, tools.results)
                    tools.grab().save(str(folder / f'tools-{locale}-{mode}.png'))
                    tools.reject()
                    captures = []
                    for color in (0xff416ae6, 0xff32947c):
                        capture = QImage(90, 60, QImage.Format_RGB32)
                        capture.fill(color)
                        assert session().add_image(capture)
                        captures.append(capture)
                    viewer.resize(960, 820)
                    QTest.qWait(20)
                    assert viewer.capture_chip.isVisible()
                    actions(viewer)
                    captures_dialog = CaptureDialog(captures, viewer)
                    show_on_test_screen(captures_dialog)
                    QTest.qWait(30)
                    actions(captures_dialog)
                    captures_dialog.grab().save(str(folder / f'captures-{locale}-{mode}.png'))
                    captures_dialog.reject()
                    session().clear()
                    viewer.resize(680, 480)
                    viewer.reset_edits()
                    if viewer.stamp_editor is None:
                        viewer.stamp_editor = StampEditor(viewer)
                    viewer.stamp_editor.add_image(seal)
                    QTest.qWait(30)
                    viewer.grab().save(str(folder / f'stamp-{locale}-{mode}-680.png'))
                    assert viewer.size() == QSize(680, 480)
                    assert viewer.scroll.height() > 100, ('Stamp controls consume the document viewport',
                        locale, mode, viewer.scroll.height(), viewer.stamp_editor.panel.height(), viewer.stamp_editor.hint.height())
                    for control in (viewer.stamp_editor.panel, viewer.stamp_editor.width):
                        point = control.mapTo(viewer, QPoint())
                        assert viewer.rect().contains(point)
                        assert viewer.rect().contains(point + QPoint(control.width() - 1, control.height() - 1))
                    actions(viewer)
                    report['cases'].append({'locale': locale, 'theme': mode, 'size': [680, 480],
                                            'stamp_panel_height': viewer.stamp_editor.panel.height(),
                                            'stamp_viewport_height': viewer.scroll.height()})
                    if locale == 'ko-KR' and mode == 'dark' and args.scale == 1.5:
                        viewer.resize(960, 820)
                        QTest.qWait(50)
                        actions(viewer)
                        neutral_workspace(viewer)
                        assert viewer.save_button.isEnabled() and viewer.undo_button.isEnabled()
                        viewer.feedback_timer.stop()
                        viewer.restore_status()
                        assert viewer.workspace_header.grab().save(str(folder.parent / 'workspace-toolbar-final.png'))
                        assert viewer.grab().save(str(folder.parent / 'workspace-final.png'))
                    viewer.reset_edits()
                    slides = SlideShow(source, parent=viewer)
                    slides.resize(960, 820)
                    show_on_test_screen(slides)
                    QTest.qWait(50)
                    actions(slides)
                    for index in range(slides.ink_tools.count()):
                        assert not slides.ink_tools.itemIcon(index).isNull()
                        icon_raster(slides.ink_tools.itemIcon(index), slides.ink_tools)
                    slides.grab().save(str(folder / f'ink-{locale}-{mode}.png'))
                    slides.reject()
            finally:
                viewer.close()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    report['source_preserved'] = True
    (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'PASS icons Windows: {args.scale * 100:.0f}% DPR; three languages, two themes, two sizes; palette, contrast, disabled states and draft behavior', flush=True)


if __name__ == '__main__':
    main()
