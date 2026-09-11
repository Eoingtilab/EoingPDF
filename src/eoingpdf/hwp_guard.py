from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile
import winreg
import time
import logging
import os

REGISTRY = r'Software\HNC\HwpAutomation\Modules'


def revoke_job(directory):
    directory = Path(directory)
    # Parent and helper use the same unique name, so cancellation can revoke
    # access even when the helper is blocked inside a COM call.
    name = 'EoingPDF_' + directory.name
    (directory / 'allowed.txt').unlink(missing_ok=True)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        pass


@contextmanager
def job_directory():
    with tempfile.TemporaryDirectory(prefix='eoing-hwp-', ignore_cleanup_errors=True) as temporary:
        try:
            yield Path(temporary)
        finally:
            revoke_job(temporary)


@contextmanager
def allow_job(app, source, target):
    from .convert import ROOT
    from contextlib import nullcontext
    inherited = os.environ.get('EOINGPDF_HWP_JOB')
    with nullcontext(inherited) if inherited else job_directory() as temporary:
        directory = Path(temporary)
        name = 'EoingPDF_' + directory.name
        (directory / 'allowed.txt').write_text(f'{Path(source).resolve()}\n{Path(target).resolve()}\n', encoding='utf-16-le')
        registered = False
        try:
            for arch in ('x86', 'x64'):
                module = directory / f'guard-{arch}.dll'
                shutil.copyfile(ROOT / 'assets' / f'hwp-{arch}.dll', module)
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, str(module))
                if app.RegisterModule('FilePathCheckDLL', name):
                    registered = True
                    break
            if not registered:
                raise ValueError('한글 파일 접근 모듈을 연결하지 못했습니다. 한컴 한글 버전을 확인해 주세요.')
            yield
        finally:
            # Revoke paths before cleanup; a still-loaded DLL must allow nothing.
            revoke_job(directory)
            try:
                app.RegisterModule('FilePathCheckDLL', '')
            except Exception:
                pass
            try:
                app.Quit()
            except Exception:
                logging.exception('한글 변환 인스턴스 종료 실패')
            # The caller still holds this wrapper. Release its owned COM pointer
            # so HWP can unload the DLL before TemporaryDirectory removes it.
            if hasattr(app, '_oleobj_'):
                app._oleobj_ = None
            for _ in range(10):
                try:
                    shutil.rmtree(directory)
                    break
                except FileNotFoundError:
                    break
                except PermissionError:
                    time.sleep(.1)
