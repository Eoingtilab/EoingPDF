from pathlib import Path
import sys
from unittest.mock import Mock
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.hwp_pdf import export_pdf


@pytest.mark.parametrize('previous_method', range(11))
def test_every_inherited_layout_is_reset_to_single_page(tmp_path, monkeypatch, previous_method):
    target = tmp_path / 'out.pdf'
    values = {}
    parameters = Mock()
    parameters.SetItem.side_effect = lambda key, value: values.update({key: value})
    action = Mock()
    action.CreateSet.return_value = parameters
    action.GetDefault.side_effect = lambda unused: values.update(PrintMethod=previous_method, NumCopy=4, Range=3, ReverseOrder=1)
    def execute(unused):
        assert values['PrintMethod'] == 0
        assert values['Range'] == 0 and values['NumCopy'] == 1
        assert values['ReverseOrder'] == 0 and values['UserOrder'] == 0
        assert values['PrinterName'] == 'Hancom PDF'
        with pdf.open() as document:
            for index in range(4):
                document.new_page().insert_text((50, 50), f'PAGE {index + 1}')
            document.save(values['FileName'])
        return True
    action.Execute.side_effect = execute
    app = Mock(PageCount=4)
    app.CreateAction.return_value = action
    monkeypatch.setattr('win32print.EnumPrinters', lambda flags: [(0, '', 'Hancom PDF', '')])
    export_pdf(app, target)
    app.CreateAction.assert_called_once_with('PrintToPDFEx')
    app.SaveAs.assert_not_called()


def test_no_pdf_driver_never_uses_default_physical_printer(tmp_path, monkeypatch):
    app = Mock()
    monkeypatch.setattr('win32print.EnumPrinters', lambda flags: [(0, '', 'Office physical printer', '')])
    with pytest.raises(ValueError, match='한컴 PDF'):
        export_pdf(app, tmp_path / 'out.pdf')
    app.CreateAction.assert_not_called()


def test_grouped_output_is_never_accepted_as_success(tmp_path, monkeypatch):
    target = tmp_path / 'out.pdf'
    app = Mock(PageCount=4)
    action = app.CreateAction.return_value
    def execute(parameters):
        with pdf.open() as document:
            document.new_page()
            document.new_page()
            document.save(target)
        return True
    action.Execute.side_effect = execute
    monkeypatch.setattr('win32print.EnumPrinters', lambda flags: [(0, '', 'Hancom PDF', '')])
    with pytest.raises(ValueError, match='페이지 수'):
        export_pdf(app, target)


def test_failed_action_and_existing_target_do_not_report_success(tmp_path, monkeypatch):
    app = Mock(PageCount=4)
    app.CreateAction.return_value.Execute.return_value = False
    monkeypatch.setattr('win32print.EnumPrinters', lambda flags: [(0, '', 'Hancom PDF', '')])
    target = tmp_path / 'out.pdf'
    with pytest.raises(ValueError, match='실행하지'):
        export_pdf(app, target)
    assert not target.exists()
    target.write_bytes(b'preserve')
    app.reset_mock()
    with pytest.raises(ValueError, match='이미'):
        export_pdf(app, target)
    assert target.read_bytes() == b'preserve'
    app.CreateAction.assert_not_called()
