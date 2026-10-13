"""Reorder/delete viewer pages without discarding the canonical AcroForm tree."""
from .localization import tr


def apply_page_order(document, pages):
    pages = list(pages)
    count = len(document)
    if not pages or any(type(index) is not int or not 0 <= index < count for index in pages):
        raise ValueError(tr('페이지 순서가 올바르지 않습니다.'))
    if len(set(pages)) != len(pages):
        raise ValueError(tr('같은 페이지를 중복해서 선택할 수 없습니다.'))
    if pages == list(range(count)):
        return
    # Document.select() removes /AcroForm even when widgets remain on pages.
    # Delete each removed widget explicitly so its field is not left orphaned,
    # then move the retained page objects instead of rebuilding their page tree.
    retained = set(pages)
    for index in reversed(range(count)):
        if index not in retained:
            page = document[index]
            for widget in list(page.widgets() or ()):
                page.delete_widget(widget)
            document.delete_page(index)
    current = sorted(pages)
    for target, identifier in enumerate(pages):
        source = current.index(identifier)
        if source != target:
            document.move_page(source, target)
            current.insert(target, current.pop(source))
