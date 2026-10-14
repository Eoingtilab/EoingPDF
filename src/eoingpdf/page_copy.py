"""Copy page selections without rebuilding genuine AcroForm parent trees."""
import pymupdf as pdf
from .page_edits import apply_page_order


def copy_pages(source, pages, before_page=lambda index, page: None, snapshot=None):
    pages = list(pages)
    output = None
    try:
        # Ordinary documents keep the fast page-copy path. An interactive form
        # must retain its canonical parent tree; page-by-page insert_pdf splits
        # a field displayed on several pages into unrelated renamed fields.
        if source.is_form_pdf and len(set(pages)) == len(pages):
            for index, page in enumerate(pages):
                before_page(index, page)
            output = pdf.open(stream=snapshot if snapshot is not None else
                              source.tobytes(encryption=pdf.PDF_ENCRYPT_NONE), filetype='pdf')
            apply_page_order(output, pages)
        else:
            output = pdf.open()
            for index, page in enumerate(pages):
                before_page(index, page)
                output.insert_pdf(source, from_page=page, to_page=page)
        return output
    except BaseException:
        if output is not None:
            output.close()
        raise
