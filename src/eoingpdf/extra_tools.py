"""Extended local PDF utilities matching full workbench and Stirling-class workflows."""
from __future__ import annotations

import html
import io
import json
import math
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pymupdf as pdf
from PIL import Image

from .core import Cancelled, open_pdf, pages_from_text
from .distribution import resource_root
from .localization import tr

PAPER_SIZES = {
    'A4': (595.0, 842.0),
    'A4_LANDSCAPE': (842.0, 595.0),
    'A3': (842.0, 1191.0),
    'LETTER': (612.0, 792.0),
    'B5': (499.0, 709.0),
}


def extract_images_zip(document, target, cancelled=lambda: False, progress=lambda value: None):
    seen_xrefs = set()
    extracted = 0
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        total = max(1, len(document))
        for page_index, page in enumerate(document):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            for item in page.get_images(full=True):
                xref = item[0]
                if not xref or xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                info = document.extract_image(xref)
                if not info or not info.get('image'):
                    continue
                ext = info.get('ext') or 'png'
                extracted += 1
                archive.writestr(f'image_{extracted:04d}_p{page_index + 1}.{ext}', info['image'])
            progress(int((page_index + 1) / total * 90))
    if not extracted:
        raise ValueError(tr('문서 안에서 추출할 수 있는 이미지를 찾지 못했습니다.'))
    return extracted


def pdf_to_html(document, target, source_name, cancelled=lambda: False, progress=lambda value: None):
    sections = []
    total = max(1, len(document))
    for index, page in enumerate(document):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        body = page.get_text('html')
        sections.append(
            f'<section class="eoing-page" data-page="{index + 1}">'
            f'<div class="eoing-page-badge">{index + 1} / {len(document)}</div>'
            f'{body}</section>'
        )
        progress(int((index + 1) / total * 90))
    title = html.escape(source_name)
    doc_html = (
        '<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
        f'<title>{title}</title>\n'
        '<style>'
        'body{font-family:Pretendard,system-ui,sans-serif;background:#f4f6fb;color:#1d2a3f;margin:0;padding:24px;}'
        '.eoing-page{background:#fff;border:1px solid #dce3f0;border-radius:10px;padding:28px;margin:0 auto 20px;max-width:900px;overflow-x:auto;}'
        '.eoing-page-badge{font-size:12px;color:#657187;margin-bottom:12px;border-bottom:1px solid #eef2f8;padding-bottom:6px;}'
        '</style>\n</head>\n<body>\n' + '\n'.join(sections) + '\n</body>\n</html>\n'
    )
    Path(target).write_text(doc_html, encoding='utf-8')
    return len(document)


def pdf_to_json(document, target, source_name, cancelled=lambda: False, progress=lambda value: None):
    pages_data = []
    total = max(1, len(document))
    for index, page in enumerate(document):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        pages_data.append({
            'page': index + 1,
            'width': round(page.rect.width, 2),
            'height': round(page.rect.height, 2),
            'rotation': page.rotation,
            'text': page.get_text('text'),
            'image_count': len(page.get_images(full=True)),
            'link_count': len(page.get_links()),
        })
        progress(int((index + 1) / total * 90))
    payload = {
        'file': source_name,
        'page_count': len(document),
        'metadata': document.metadata or {},
        'toc': [{'level': lvl, 'title': title, 'page': pg} for lvl, title, pg in document.get_toc()],
        'pages': pages_data,
    }
    Path(target).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return len(document)


def pdf_to_xml(document, target, source_name, cancelled=lambda: False, progress=lambda value: None):
    root = ET.Element('document', name=source_name, pageCount=str(len(document)))
    meta_el = ET.SubElement(root, 'metadata')
    for key, value in (document.metadata or {}).items():
        if value:
            item = ET.SubElement(meta_el, 'entry', key=str(key))
            item.text = str(value)
    pages_el = ET.SubElement(root, 'pages')
    total = max(1, len(document))
    for index, page in enumerate(document):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        page_el = ET.SubElement(
            pages_el,
            'page',
            number=str(index + 1),
            width=str(round(page.rect.width, 2)),
            height=str(round(page.rect.height, 2)),
            rotation=str(page.rotation),
        )
        page_el.text = page.get_text('text')
        progress(int((index + 1) / total * 90))
    tree = ET.ElementTree(root)
    ET.indent(tree, space='  ')
    tree.write(target, encoding='utf-8', xml_declaration=True)
    return len(document)


def html_to_pdf(source, target, cancelled=lambda: False, progress=lambda value: None):
    if cancelled():
        raise Cancelled(tr('작업을 취소했습니다.'))
    source = Path(source)
    raw = source.read_text(encoding='utf-8', errors='replace')
    if source.suffix.lower() == '.md':
        lines = []
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith('### '):
                lines.append(f'<h3>{html.escape(stripped[4:])}</h3>')
            elif stripped.startswith('## '):
                lines.append(f'<h2>{html.escape(stripped[3:])}</h2>')
            elif stripped.startswith('# '):
                lines.append(f'<h1>{html.escape(stripped[2:])}</h1>')
            elif stripped.startswith(('- ', '* ')):
                lines.append(f'<p>&bull; {html.escape(stripped[2:])}</p>')
            elif stripped:
                lines.append(f'<p>{html.escape(line)}</p>')
        html_body = '<div class="eoing-doc">' + '\n'.join(lines or ['<p></p>']) + '</div>'
    else:
        html_body = raw

    font_path = (resource_root() / 'assets/fonts/Pretendard-Regular.ttf').resolve()
    css = ''
    if font_path.is_file():
        font_uri = font_path.as_uri()
        css = (
            f"@font-face {{ font-family: 'Pretendard'; src: url('{font_uri}'); }}\n"
            "body, p, div, h1, h2, h3, li, td, th, span { font-family: 'Pretendard', sans-serif; line-height: 1.5; }\n"
        )
    story = pdf.Story(html=html_body, user_css=css)
    mediabox = pdf.Rect(0, 0, 595, 842)
    where = pdf.Rect(42, 46, 553, 796)
    writer = pdf.DocumentWriter(str(target))
    more = True
    pages = 0
    while more:
        if cancelled():
            writer.close()
            raise Cancelled(tr('작업을 취소했습니다.'))
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev, None)
        writer.end_page()
        pages += 1
        if pages >= 500:
            break
    writer.close()
    progress(90)
    return pages


def scale_pages(document, target, paper_size='A4', cancelled=lambda: False, progress=lambda value: None):
    key = str(paper_size or 'A4').upper()
    if key not in PAPER_SIZES:
        raise ValueError(tr('지원하지 않는 용지 규격입니다.'))
    target_w, target_h = PAPER_SIZES[key]
    total = max(1, len(document))
    with pdf.open() as output:
        for index, page in enumerate(document):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            src_rect = page.rect
            scale = min(target_w / max(src_rect.width, 1), target_h / max(src_rect.height, 1))
            draw_w = src_rect.width * scale
            draw_h = src_rect.height * scale
            dx = (target_w - draw_w) / 2
            dy = (target_h - draw_h) / 2
            new_page = output.new_page(width=target_w, height=target_h)
            if page.get_contents() or page.get_images():
                new_page.show_pdf_page(pdf.Rect(dx, dy, dx + draw_w, dy + draw_h), document, index)
            progress(int((index + 1) / total * 90))
        output.save(target, garbage=4, deflate=True)
        return len(output)


def insert_blank_pages(document, after_page=1, count=1, paper_size='MATCH', cancelled=lambda: False, progress=lambda value: None):
    if cancelled():
        raise Cancelled(tr('작업을 취소했습니다.'))
    if type(count) is not int or not 1 <= count <= 100:
        raise ValueError(tr('삽입할 빈 페이지 수는 1~100 사이로 입력해 주세요.'))
    if type(after_page) is not int or not 0 <= after_page <= len(document):
        raise ValueError(tr('삽입할 페이지 위치가 올바르지 않습니다.'))
    if str(paper_size).upper() == 'MATCH' and len(document) > 0:
        ref = document[max(0, min(after_page - 1, len(document) - 1))].rect
        width, height = ref.width, ref.height
    else:
        width, height = PAPER_SIZES.get(str(paper_size).upper(), (595.0, 842.0))
    for i in range(count):
        document.new_page(pno=after_page + i, width=width, height=height)
    progress(90)
    return count


def overlay_pdf(document, overlay_path, overlay_password='', overlay_foreground=True,
                cancelled=lambda: False, progress=lambda value: None):
    overlay_path = Path(overlay_path)
    if not overlay_path.is_file():
        raise ValueError(tr('겹쳐 넣을 PDF 파일을 선택해 주세요.'))
    total = max(1, len(document))
    with open_pdf(overlay_path, overlay_password) as over:
        over_count = len(over)
        for index, page in enumerate(document):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            over_idx = index if index < over_count else over_count - 1
            page.show_pdf_page(page.rect, over, over_idx, overlay=bool(overlay_foreground))
            progress(int((index + 1) / total * 90))
    return len(document)


def split_by_size_zip(document, target, max_mb=5.0, cancelled=lambda: False, progress=lambda value: None):
    if not isinstance(max_mb, (int, float)) or isinstance(max_mb, bool) or not math.isfinite(max_mb) or not 0.1 <= max_mb <= 500:
        raise ValueError(tr('분할 기준 용량은 0.1MB부터 500MB 사이로 입력해 주세요.'))
    limit_bytes = int(max_mb * 1024 * 1024)
    total = len(document)
    chunks: list[tuple[str, bytes]] = []
    current_pages: list[int] = []

    def build_bytes(pages: list[int]) -> bytes:
        with pdf.open() as part:
            for p in pages:
                part.insert_pdf(document, from_page=p, to_page=p)
            return part.tobytes(garbage=4, deflate=True)

    for index in range(total):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        candidate = current_pages + [index]
        raw = build_bytes(candidate)
        if current_pages and len(raw) > limit_bytes:
            prev_raw = build_bytes(current_pages)
            label = f'{current_pages[0] + 1}-{current_pages[-1] + 1}'
            chunks.append((f'part_{len(chunks) + 1:03d}_p{label}.pdf', prev_raw))
            current_pages = [index]
        else:
            current_pages = candidate
        progress(int((index + 1) / max(1, total) * 85))

    if current_pages:
        raw = build_bytes(current_pages)
        label = f'{current_pages[0] + 1}-{current_pages[-1] + 1}'
        chunks.append((f'part_{len(chunks) + 1:03d}_p{label}.pdf', raw))

    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for name, data in chunks:
            archive.writestr(name, data)
    progress(95)
    return len(chunks)


def auto_rotate_pages(document, cancelled=lambda: False, progress=lambda value: None):
    changed = 0
    total = max(1, len(document))
    for index, page in enumerate(document):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        info = page.get_text('dict', flags=pdf.TEXTFLAGS_DICT & ~pdf.TEXT_PRESERVE_IMAGES)
        votes = {0: 0, 90: 0, 180: 0, 270: 0}
        for block in info.get('blocks', ()):
            for line in block.get('lines', ()):
                text = ''.join(span.get('text', '') for span in line.get('spans', ())).strip()
                if not text:
                    continue
                dx, dy = line.get('dir', (1, 0))
                angle = round(math.degrees(math.atan2(-dy, dx)) / 90) * 90 % 360
                # Map baseline vector to clockwise correction needed to make text upright (dx=1, dy=0).
                correction = {0: 0, 90: 90, 180: 180, 270: 270}.get(angle, 0)
                votes[correction] += len(text)
        best = max(votes, key=votes.get)
        if votes[best] > 0 and best != 0:
            page.set_rotation((page.rotation + best) % 360)
            changed += 1
        progress(int((index + 1) / total * 90))
    return changed


def change_permissions(document, user_password='', owner_password='', allow_print=True, allow_copy=False,
                       allow_edit=False, allow_annotate=False, cancelled=lambda: False, progress=lambda value: None):
    if cancelled():
        raise Cancelled(tr('작업을 취소했습니다.'))
    if not owner_password:
        raise ValueError(tr('권한 변경에는 소유자 암호가 필요합니다.'))
    if user_password and user_password == owner_password:
        raise ValueError(tr('열기 암호와 소유자 암호를 다르게 설정해 주세요.'))
    permissions = pdf.PDF_PERM_ACCESSIBILITY
    if allow_print:
        permissions |= pdf.PDF_PERM_PRINT | pdf.PDF_PERM_PRINT_HQ
    if allow_copy:
        permissions |= pdf.PDF_PERM_COPY
    if allow_edit:
        permissions |= pdf.PDF_PERM_MODIFY
    if allow_annotate:
        permissions |= pdf.PDF_PERM_ANNOTATE
    progress(90)
    return permissions


def unlock_forms(document, cancelled=lambda: False, progress=lambda value: None):
    unlocked = 0
    total = max(1, len(document))
    for index, page in enumerate(document):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        for widget in page.widgets() or ():
            if widget.field_flags & pdf.PDF_FIELD_IS_READ_ONLY:
                widget.field_flags &= ~pdf.PDF_FIELD_IS_READ_ONLY
                widget.update()
                unlocked += 1
        progress(int((index + 1) / total * 90))
    if not unlocked:
        raise ValueError(tr('잠금 해제할 읽기 전용 양식 필드가 없습니다.'))
    return unlocked


def manage_attachments(document, target, mode='extract', attachment_path='', cancelled=lambda: False, progress=lambda value: None):
    if cancelled():
        raise Cancelled(tr('작업을 취소했습니다.'))
    if mode == 'extract':
        names = list(document.embfile_names())
        if not names:
            raise ValueError(tr('PDF에 포함된 첨부 파일이 없습니다.'))
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for i, name in enumerate(names, 1):
                safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(name).name) or f'attachment_{i}'
                archive.writestr(f'{i:03d}_{safe}', document.embfile_get(name))
        progress(90)
        return len(names)
    if mode == 'add':
        src = Path(attachment_path)
        if not src.is_file():
            raise ValueError(tr('첨부할 파일을 선택해 주세요.'))
        data = src.read_bytes()
        if len(data) > 50 * 1024 * 1024:
            raise ValueError(tr('첨부 파일은 50MB 이하만 지원합니다.'))
        document.embfile_add(src.name, data, filename=src.name)
        progress(90)
        return 1
    if mode == 'remove':
        names = list(document.embfile_names())
        for name in names:
            document.embfile_del(name)
        progress(90)
        return len(names)
    raise ValueError(tr('지원하지 않는 첨부 파일 작업입니다.'))


def edit_bookmarks(document, toc_text='', auto_toc=False, cancelled=lambda: False, progress=lambda value: None):
    if cancelled():
        raise Cancelled(tr('작업을 취소했습니다.'))
    if auto_toc:
        entries = []
        for idx, page in enumerate(document):
            blocks = page.get_text('dict', flags=pdf.TEXTFLAGS_DICT & ~pdf.TEXT_PRESERVE_IMAGES).get('blocks', ())
            candidates = []
            for block in blocks:
                for line in block.get('lines', ()):
                    spans = [s for s in line.get('spans', ()) if s.get('text', '').strip()]
                    if not spans:
                        continue
                    size = max(s.get('size', 0) for s in spans)
                    text = ' '.join(s['text'].strip() for s in spans).strip()
                    if size >= 14 and 2 <= len(text) <= 80:
                        candidates.append((size, text))
            if candidates:
                candidates.sort(key=lambda item: -item[0])
                entries.append([1, candidates[0][1], idx + 1])
            elif idx == 0:
                entries.append([1, tr('{page}페이지', page=1), 1])
        if not entries:
            raise ValueError(tr('자동 생성할 제목 후보를 찾지 못했습니다.'))
        document.set_toc(entries)
        progress(90)
        return len(entries)

    toc = []
    for raw in (toc_text or '').splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) == 2:
            level, title, page_num = 1, parts[0], int(parts[1])
        elif len(parts) >= 3:
            level, title, page_num = int(parts[0]), '|'.join(parts[1:-1]).strip(), int(parts[-1])
        else:
            raise ValueError(tr('목차 형식은 "제목 | 페이지" 또는 "단계 | 제목 | 페이지"로 입력해 주세요.'))
        if not 1 <= level <= 6 or not title or not 1 <= page_num <= len(document):
            raise ValueError(tr('목차 단계(1~6)와 페이지 범위를 확인해 주세요.'))
        toc.append([level, title, page_num])
    document.set_toc(toc)
    progress(90)
    return len(toc)


def add_qr_stamp(document, qr_text, pages='1', x_mm=15.0, y_mm=15.0, width_mm=28.0,
                 cancelled=lambda: False, progress=lambda value: None):
    from .qr_code import make_qr_png
    from .stamping import place_prepared

    stream = make_qr_png(qr_text)
    selected = list(range(len(document))) if not str(pages).strip() else list(dict.fromkeys(pages_from_text(pages, len(document))))
    total = max(1, len(selected))
    for step, index in enumerate(selected):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        place_prepared(document[index], stream, 1.0, x_mm, y_mm, width_mm)
        progress(int((step + 1) / total * 90))
    return len(selected)


def convert_to_pdfa(document, target, cancelled=lambda: False, progress=lambda value: None):
    # Clean active scripts/actions and store clean subsetted fonts + archival metadata intent.
    from .sanitize import sanitize_active_content
    sanitize_active_content(document, remove_scripts=True, remove_attachments=False, cancelled=cancelled, progress=lambda v: progress(v // 2))
    metadata = dict(document.metadata or {})
    metadata.setdefault('title', Path(target).stem)
    document.set_metadata(metadata)
    document.subset_fonts()
    document.save(target, garbage=4, deflate=True, encryption=pdf.PDF_ENCRYPT_NONE)
    progress(95)
    return len(document)


def inspect_pdf_report(path, password=''):
    path = Path(path).resolve()
    info = {
        'file_name': path.name,
        'file_size_bytes': path.stat().st_size,
        'encrypted': False,
        'page_count': 0,
        'pdf_version': '',
        'page_sizes': [],
        'mixed_page_sizes': False,
        'fonts': [],
        'unembedded_fonts': [],
        'image_count': 0,
        'attachment_count': 0,
        'has_javascript': False,
        'has_forms': False,
        'annotation_count': 0,
        'permissions': {},
        'metadata': {},
    }
    with open_pdf(path, password) as doc:
        info['encrypted'] = bool(doc.is_encrypted)
        info['page_count'] = len(doc)
        info['pdf_version'] = str(doc.metadata.get('format', '') or '')
        info['metadata'] = {k: v for k, v in (doc.metadata or {}).items() if v}
        info['attachment_count'] = len(doc.embfile_names())
        info['has_forms'] = bool(doc.is_form_pdf)
        perms = doc.permissions
        info['permissions'] = {
            'print': bool(perms & pdf.PDF_PERM_PRINT),
            'copy': bool(perms & pdf.PDF_PERM_COPY),
            'modify': bool(perms & pdf.PDF_PERM_MODIFY),
            'annotate': bool(perms & pdf.PDF_PERM_ANNOTATE),
        }
        sizes = set()
        fonts = set()
        unembedded = set()
        images = 0
        annots = 0
        has_js = False
        for page in doc:
            sizes.add((round(page.rect.width * 25.4 / 72, 1), round(page.rect.height * 25.4 / 72, 1)))
            for f in page.get_fonts(full=True):
                name = f[3] or f[4] or 'Font'
                fonts.add(name)
                if not f[0]:
                    unembedded.add(name)
            images += len(page.get_images(full=True))
            annots += sum(1 for _ in page.annots() or ())
        for xref in range(1, min(doc.xref_length(), 5000)):
            try:
                obj = doc.xref_object(xref, compressed=False)
                if '/JS' in obj or '/JavaScript' in obj or '/Launch' in obj:
                    has_js = True
                    break
            except Exception:
                continue
        info['page_sizes'] = [f'{w} x {h} mm' for w, h in sorted(sizes)]
        info['mixed_page_sizes'] = len(sizes) > 1
        info['fonts'] = sorted(fonts)[:30]
        info['unembedded_fonts'] = sorted(unembedded)[:20]
        info['image_count'] = images
        info['annotation_count'] = annots
        info['has_javascript'] = has_js
    return info


def export_document(source, target, export_format, password='', pages='', dpi=150, quality=90,
                    cancelled=lambda: False, progress=lambda value: None):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError(tr('원본을 덮어쓸 수 없습니다. 다른 파일명을 선택해 주세요.'))
    fmt = str(export_format or 'pdf').lower()
    with open_pdf(source, password) as doc:
        selected = pages_from_text(pages, len(doc)) if str(pages or '').strip() else list(range(len(doc)))
        if fmt == 'pdf':
            from .page_copy import copy_pages
            with copy_pages(doc, selected) as out:
                out.save(target, garbage=4, deflate=True, encryption=pdf.PDF_ENCRYPT_KEEP)
            progress(95)
            return len(selected)
        if fmt == 'pdfa':
            return convert_to_pdfa(doc, target, cancelled, progress)
        if fmt in ('png_zip', 'jpg_zip', 'png', 'jpg'):
            img_fmt = 'PNG' if 'png' in fmt else 'JPEG'
            ext = 'png' if img_fmt == 'PNG' else 'jpg'
            scale = min(4.0, max(0.5, dpi / 72.0))
            if fmt in ('png', 'jpg') and len(selected) == 1:
                page = doc[selected[0]]
                pix = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                if ext == 'png':
                    Path(target).write_bytes(pix.tobytes('png'))
                else:
                    Image.frombytes('RGB', (pix.width, pix.height), pix.samples).save(target, format='JPEG', quality=quality, optimize=True)
                progress(95)
                return 1
            with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for i, p in enumerate(selected):
                    if cancelled():
                        raise Cancelled(tr('작업을 취소했습니다.'))
                    pix = doc[p].get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                    if ext == 'png':
                        data = pix.tobytes('png')
                    else:
                        buf = io.BytesIO()
                        Image.frombytes('RGB', (pix.width, pix.height), pix.samples).save(buf, format='JPEG', quality=quality, optimize=True)
                        data = buf.getvalue()
                    archive.writestr(f'{i + 1:04d}_page-{p + 1}.{ext}', data)
                    progress(int((i + 1) / len(selected) * 90))
            return len(selected)
        if fmt in ('long_png', 'long_jpg'):
            scale = min(3.0, max(0.5, dpi / 72.0))
            images = []
            total_h = 0
            max_w = 0
            for i, p in enumerate(selected):
                if cancelled():
                    raise Cancelled(tr('작업을 취소했습니다.'))
                pix = doc[p].get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                images.append(img)
                max_w = max(max_w, img.width)
                total_h += img.height
                if max_w * total_h > 80_000_000:
                    raise ValueError(tr('이미지 총 해상도가 너무 큽니다. 페이지 범위를 줄이거나 DPI를 낮춰 주세요.'))
                progress(int((i + 1) / len(selected) * 70))
            canvas = Image.new('RGB', (max_w, total_h), 'white')
            y = 0
            for img in images:
                canvas.paste(img, ((max_w - img.width) // 2, y))
                y += img.height
            if fmt == 'long_png':
                canvas.save(target, format='PNG')
            else:
                canvas.save(target, format='JPEG', quality=quality, optimize=True)
            progress(95)
            return len(selected)
        if fmt == 'txt':
            from .ocr import page_text
            parts = []
            for i, p in enumerate(selected):
                if cancelled():
                    raise Cancelled(tr('작업을 취소했습니다.'))
                text, used_ocr = page_text(doc[p], cancelled)
                parts.append(tr('--- {v0}페이지{v1} ---\n{v2}', v0=p + 1, v1=' (OCR)' if used_ocr else '', v2=text))
                progress(int((i + 1) / len(selected) * 90))
            Path(target).write_text('\n'.join(parts), encoding='utf-8-sig')
            return len(selected)
        if fmt == 'md':
            from .markdown_export import export as md_export
            return md_export(doc, target, source.name, cancelled, progress)
        if fmt == 'html':
            return pdf_to_html(doc, target, source.name, cancelled, progress)
        if fmt == 'json':
            return pdf_to_json(doc, target, source.name, cancelled, progress)
        if fmt == 'xml':
            return pdf_to_xml(doc, target, source.name, cancelled, progress)
        if fmt == 'svg':
            from .svg_export import export as svg_export
            return svg_export(doc, target, cancelled, progress)
        if fmt == 'dxf':
            from .dxf_export import export as dxf_export
            return dxf_export(doc, target, cancelled, progress)
    raise ValueError(tr('지원하지 않는 저장 형식입니다.'))


def rotate_pages(document, rotation=90, pages='', cancelled=lambda: False, progress=lambda value: None):
    if rotation not in (90, 180, 270):
        raise ValueError(tr('회전 각도는 90°, 180°, 270°만 선택할 수 있습니다.'))
    selected = list(dict.fromkeys(pages_from_text(pages, len(document)))) if str(pages or '').strip() else list(range(len(document)))
    for i, p in enumerate(selected):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        document[p].set_rotation((document[p].rotation + rotation) % 360)
        progress(int((i + 1) / max(1, len(selected)) * 90))
    return len(selected)


def add_page_numbers(document, pages='', start=1, position='bottom-center', cancelled=lambda: False, progress=lambda value: None):
    from .pdf_fonts import text_font
    selected = list(dict.fromkeys(pages_from_text(pages, len(document)))) if str(pages or '').strip() else list(range(len(document)))
    font = text_font('0123456789 /')
    total = len(document)
    for i, p in enumerate(selected):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        page = document[p]
        old_rot = page.rotation
        page.set_rotation(0)
        rect = page.rect
        label = f'{start + i} / {total}'
        align = 0 if 'left' in position else 2 if 'right' in position else 1
        y0, y1 = (10, 29) if position.startswith('top') else (rect.height - 29, rect.height - 10)
        page.insert_font(fontname='EoingNum', fontbuffer=font.buffer)
        page.insert_textbox(pdf.Rect(18, y0, rect.width - 18, y1), label, fontname='EoingNum',
                            fontsize=9.5, align=align, color=(0.35, 0.4, 0.5))
        page.set_rotation(old_rot)
        progress(int((i + 1) / max(1, len(selected)) * 90))
    return len(selected)
