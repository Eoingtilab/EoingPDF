"""Optional isolated LibreOffice conversion, without changing the user's profile."""
from .localization import tr
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from .core import Cancelled, open_pdf


def find_executable():
    candidates = []
    for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
        base = os.environ.get(variable)
        if base:
            candidates.extend((Path(base) / 'LibreOffice/program/soffice.com',
                               Path(base) / 'Programs/LibreOffice/program/soffice.com'))
    for name in ('soffice.com', 'libreoffice', 'soffice'):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    return next((path.resolve() for path in candidates if path.is_file()), None)


def convert(source, target, cancelled=lambda: False, timeout=90, executable=None):
    executable = executable or find_executable()
    if not executable:
        raise ValueError(tr('Microsoft Office/한글 또는 LibreOffice를 설치한 뒤 다시 시도해 주세요.'))
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError(tr('원본 파일을 덮어쓸 수 없습니다.'))
    if target.exists():
        raise ValueError(tr('기존 파일을 덮어쓸 수 없습니다. 다른 이름을 선택해 주세요.'))
    if cancelled():
        raise Cancelled(tr('작업을 취소했습니다.'))
    with tempfile.TemporaryDirectory(prefix='eoing-lo-') as temporary:
        folder = Path(temporary)
        profile = folder / 'profile'
        user = profile / 'user'
        user.mkdir(parents=True)
        (user / 'registrymodifications.xcu').write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
            '<prop oor:name="SecureURL" oor:op="fuse"><value/></prop>'
            '</item></oor:items>', encoding='utf-8')
        output = folder / 'output'
        output.mkdir()
        command = [str(executable), '-env:UserInstallation=' + profile.as_uri(), '--headless',
                   '--nologo', '--nodefault', '--norestore', '--convert-to', 'pdf',
                   '--outdir', str(output), str(source)]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancelled():
                    raise Cancelled(tr('작업을 취소했습니다.'))
                if time.monotonic() - started > timeout:
                    raise ValueError(tr('LibreOffice 변환 시간이 초과되었습니다. 암호와 문서 손상 여부를 확인해 주세요.'))
                time.sleep(.1)
            result = output / (source.stem + '.pdf')
            if process.returncode != 0 or not result.is_file():
                raise ValueError(tr('LibreOffice에서 이 문서를 변환하지 못했습니다. 이 형식에 맞는 Office/한글 프로그램이 필요할 수 있습니다.'))
            with open_pdf(result):
                if cancelled():
                    raise Cancelled(tr('작업을 취소했습니다.'))
            with tempfile.TemporaryDirectory(prefix='.eoing-lo-output-', dir=target.parent) as publication:
                staged = Path(publication) / 'result.pdf'
                shutil.copyfile(result, staged)
                if cancelled():
                    raise Cancelled(tr('작업을 취소했습니다.'))
                if os.name == 'nt':
                    os.rename(staged, target)
                else:
                    os.link(staged, target)
        finally:
            if process.poll() is None:
                # Only this invocation and its isolated-profile descendants.
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=10, check=False)
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
