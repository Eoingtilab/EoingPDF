"""Conservative vector/text form candidates and real AcroForm fields."""
from .localization import tr
import re
import pymupdf as pdf
from .core import Cancelled


def candidates(page):
    visible = pdf.Rect(0, 0, page.cropbox.width, page.cropbox.height)
    existing = [widget.rect for widget in page.widgets() or ()]
    words = page.get_text('words')
    found = []

    def add(rect, kind, allow_marks=False):
        rect = pdf.Rect(rect) & visible
        if rect.is_empty or rect.width < 6 or rect.height < 6:
            return
        if any(rect.intersects(other) for other in existing):
            return
        if any((rect & other).get_area() > min(rect.get_area(), other.get_area()) * .5 for other, _ in found):
            return
        if not allow_marks and any(rect.contains((pdf.Rect(word[:4]).tl + pdf.Rect(word[:4]).br) / 2)
                                   for word in words if word[4].strip('_[] ')):
            return
        found.append((rect, kind))

    for drawing in page.get_drawings():
        if drawing.get('fill') not in (None, (1, 1, 1)):
            continue
        for item in drawing['items']:
            if item[0] == 're':
                rect = pdf.Rect(item[1])
                if 8 <= rect.width <= 26 and 8 <= rect.height <= 26 and .75 <= rect.width / rect.height <= 1.33:
                    add(rect, 'checkbox')
                elif 36 <= rect.width <= 600 and 12 <= rect.height <= 72:
                    add(rect, 'text')
            elif item[0] == 'l':
                first, last = item[1:3]
                if abs(first.y - last.y) <= .5 and abs(first.x - last.x) >= 36:
                    add(pdf.Rect(min(first.x, last.x), first.y - 16, max(first.x, last.x), first.y), 'text')
    for block in page.get_text('blocks'):
        if block[6] != 0:
            continue
        for match in re.finditer(r'_{3,}|\[\s{0,8}\]', block[4]):
            for rect in page.search_for(match.group()):
                kind = 'checkbox' if match.group().startswith('[') else 'text'
                add(rect, kind, allow_marks=True)
    return found


def create_fields(document, cancelled=lambda: False, progress=lambda value: None, reviewed=None):
    selected = None
    if reviewed is not None:
        if not isinstance(reviewed, list) or not 1 <= len(reviewed) <= 2000:
            raise ValueError(tr('생성할 입력 칸을 1개 이상 선택해 주세요.'))
        selected = {}
        for item in reviewed:
            if not isinstance(item, dict) or item.get('kind') not in ('text', 'checkbox'):
                raise ValueError(tr('검토한 입력 칸 정보가 올바르지 않습니다.'))
            index = item.get('page')
            if type(index) is not int or not 0 <= index < len(document):
                raise ValueError(tr('입력 칸 페이지가 올바르지 않습니다.'))
            rect = item.get('rect')
            if not isinstance(rect, list) or len(rect) != 4 or any(type(value) not in (int, float) for value in rect):
                raise ValueError(tr('입력 칸 좌표가 올바르지 않습니다.'))
            selected.setdefault(index, []).append((pdf.Rect(rect), item['kind']))
    names = {widget.field_name for page in document for widget in page.widgets() or ()}
    count = 0
    for page_index, page in enumerate(document):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        detected = candidates(page)
        requested = detected if selected is None else selected.get(page_index, [])
        if selected is not None:
            seen = set()
            for rect, kind in requested:
                key = tuple(rect)
                if key in seen or not any(all(abs(a - b) < .01 for a, b in zip(rect, other)) for other, _ in detected):
                    raise ValueError(tr('감지 결과가 변경되었습니다. 양식을 다시 검토해 주세요.'))
                seen.add(key)
        for rect, kind in requested:
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            if count >= 2000:
                raise ValueError(tr('감지된 입력 칸이 2,000개를 초과합니다. 문서를 나누어 처리해 주세요.'))
            number = count + 1
            name = f'EoingField_{page_index + 1}_{number}'
            while name in names:
                number += 1
                name = f'EoingField_{page_index + 1}_{number}'
            names.add(name)
            field = pdf.Widget()
            field.field_name = name
            field.field_label = tr('{v0}페이지 입력 칸 {v1}', v0=page_index + 1, v1=number)
            field.field_type = pdf.PDF_WIDGET_TYPE_CHECKBOX if kind == 'checkbox' else pdf.PDF_WIDGET_TYPE_TEXT
            field.rect = rect
            field.field_value = 'Off' if kind == 'checkbox' else ''
            field.border_width = 0
            field.text_font = 'ZaDb' if kind == 'checkbox' else 'Helv'
            field.text_fontsize = 0
            field.text_color = (0, 0, 0)
            page.add_widget(field)
            count += 1
        progress(int((page_index + 1) / len(document) * 90))
    if not count and not names:
        raise ValueError(tr('빈 입력 칸을 찾지 못했습니다. 스캔 이미지는 아직 자동 양식 감지 대상이 아닙니다.'))
    return count


def fill_fields(document, values, cancelled=lambda: False, progress=lambda value: None):
    if not isinstance(values, dict) or len(values) > 2000:
        raise ValueError(tr('입력 필드 데이터가 올바르지 않습니다.'))
    remaining = set(values)
    selected_groups = set()
    # Reject conflicting requests before any widget is changed.
    for page in document:
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        for field in page.widgets() or ():
            if field.field_type == pdf.PDF_WIDGET_TYPE_RADIOBUTTON and str(field.xref) in values:
                if values[str(field.xref)] is not True:
                    raise ValueError(tr('라디오 버튼은 선택할 항목 하나만 지정해 주세요.'))
                group = radio_group(document, field)
                if group in selected_groups:
                    raise ValueError(tr('같은 라디오 그룹에서 여러 항목을 선택할 수 없습니다.'))
                selected_groups.add(group)
    for page in document:
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        for field in page.widgets() or ():
            if (field.field_type == pdf.PDF_WIDGET_TYPE_RADIOBUTTON and
                    radio_group(document, field) in selected_groups and field.field_flags & pdf.PDF_FIELD_IS_READ_ONLY):
                raise ValueError(tr('읽기 전용 라디오 그룹은 변경할 수 없습니다.'))
    changed = 0
    for page_index, page in enumerate(document):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        for field in page.widgets() or ():
            key = str(field.xref)
            if key not in values:
                continue
            if field.field_flags & pdf.PDF_FIELD_IS_READ_ONLY:
                raise ValueError(tr('읽기 전용 필드는 변경할 수 없습니다.'))
            value = values[key]
            if field.field_type == pdf.PDF_WIDGET_TYPE_CHECKBOX:
                if not isinstance(value, bool):
                    raise ValueError(tr('체크 필드 값이 올바르지 않습니다.'))
                field.field_value = field.on_state() if value else 'Off'
            elif field.field_type == pdf.PDF_WIDGET_TYPE_RADIOBUTTON:
                field.field_value = field.on_state()
                if not field.field_value:
                    raise ValueError(tr('라디오 버튼의 선택 상태를 읽을 수 없습니다.'))
            elif field.field_type in (pdf.PDF_WIDGET_TYPE_COMBOBOX, pdf.PDF_WIDGET_TYPE_LISTBOX):
                set_choice(document, field, value)
                remaining.remove(key)
                changed += 1
                continue
            elif field.field_type == pdf.PDF_WIDGET_TYPE_TEXT:
                if not isinstance(value, str) or len(value) > 10000 or '\x00' in value:
                    raise ValueError(tr('입력 문자열이 올바르지 않습니다.'))
                if field.text_maxlen and len(value) > field.text_maxlen:
                    raise ValueError(tr('필드의 최대 글자 수를 초과했습니다.'))
                field.field_value = value
            else:
                raise ValueError(tr('이 입력 필드 종류는 아직 지원하지 않습니다.'))
            field.update()
            remaining.remove(key)
            changed += 1
        progress(int((page_index + 1) / len(document) * 90))
    if remaining:
        raise ValueError(tr('원본의 입력 필드가 변경되었습니다. 문서를 다시 열어 주세요.'))
    return changed


def choice_options(field):
    return [(str(item[0]), str(item[1])) if isinstance(item, (list, tuple)) else (str(item), str(item))
            for item in field.choice_values or ()]


def radio_group(document, field):
    kind, parent = document.xref_get_key(field.xref, 'Parent')
    return ('parent', parent) if kind == 'xref' else ('name', field.field_name)


def choice_selection(field):
    # Widget.field_value is scalar even when the PDF /V is an array.
    api = pdf.mupdf
    obj = api.pdf_annot_obj(field._annot.this)
    value = api.pdf_dict_get_inheritable(obj, api.pdf_new_name('V'))
    if api.pdf_is_array(value):
        return [api.pdf_to_text_string(api.pdf_array_get(value, i)) for i in range(api.pdf_array_len(value))]
    return [field.field_value] if field.field_value not in (None, '') else []


def set_choice(document, field, values):
    options = choice_options(field)
    exports = [item[0] for item in options]
    multi = bool(field.field_flags & pdf.PDF_CH_FIELD_IS_MULTI_SELECT)
    editable = field.field_type == pdf.PDF_WIDGET_TYPE_COMBOBOX and field.field_flags & pdf.PDF_CH_FIELD_IS_EDIT
    selected = values if isinstance(values, list) else [values]
    if (not multi and len(selected) != 1 or len(selected) > 2000 or
            any(not isinstance(value, str) or len(value) > 10000 or '\x00' in value for value in selected)):
        raise ValueError(tr('선택 목록 값이 올바르지 않습니다.'))
    if len(set(selected)) != len(selected) or any(value not in exports and not editable and (multi or value != '') for value in selected):
        raise ValueError(tr('선택 목록에 없는 값입니다.'))
    if multi:
        selected = sorted(selected, key=lambda value: exports.index(value))
    field.field_value = selected[0] if selected else ''
    field.update()
    document.xref_set_key(field.xref, 'V',
                          '[' + ' '.join(pdf.get_pdf_str(value) for value in selected) + ']' if multi
                          else pdf.get_pdf_str(selected[0]))
    indices = [exports.index(value) for value in selected if value in exports]
    document.xref_set_key(field.xref, 'I', '[' + ' '.join(map(str, indices)) + ']' if indices else 'null')
    # Rebuild the actual appearance from /V and /I without scalar Widget.update
    # overwriting a multi-selection array.
    api = pdf.mupdf
    api.pdf_dirty_annot(field._annot.this)
    api.pdf_update_annot(field._annot.this)
