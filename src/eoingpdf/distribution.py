"""Runtime layout and persistent shell resources for single-file distribution."""
from .localization import tr
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))


def is_onefile():
    return bool(getattr(sys, 'frozen', False) and (resource_root() / 'onefile.marker').is_file())


@dataclass(frozen=True)
class ShellLayout:
    executable: Path
    bridge: Path
    icon: Path
    portable: bool = False

    def command(self, action):
        command = f'"{self.bridge}" {action}'
        return command + f' --app "{self.executable}"' if self.portable else command


def _hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _safe_folder(folder):
    # Do not follow a user-created junction into an unrelated directory.
    folder = Path(folder).absolute()
    for part in (folder, *folder.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError(tr('연결된 폴더에는 포터블 셸 파일을 보관할 수 없습니다.'))
    return folder


def _portable_base(executable):
    local = Path(os.environ.get('LOCALAPPDATA', ''))
    if not local.is_absolute():
        raise ValueError(tr('Windows 사용자 데이터 폴더를 찾지 못했습니다.'))
    identity = hashlib.sha256(str(executable.resolve()).casefold().encode('utf-8')).hexdigest()[:24]
    return _safe_folder(local / 'EoingPDF' / 'portable-shell' / identity)


def shell_layout(folder=None, *, prepare=False):
    if folder is not None or not is_onefile():
        folder = Path(folder or (Path(sys.executable).parent if getattr(sys, 'frozen', False)
                                  else Path(__file__).resolve().parents[2] / 'release/EoingPDF')).resolve()
        return ShellLayout(folder / 'EoingPDF.exe', folder / 'EoingPDF.Shell.exe',
                           folder / '_internal/assets/pdf_icon.ico')
    executable = Path(sys.executable).resolve()
    sources = {'EoingPDF.Shell.exe': resource_root() / 'portable_tools/EoingPDF.Shell.exe',
               'pdf_icon.ico': resource_root() / 'assets/pdf_icon.ico'}
    hashes = {name: _hash(path) for name, path in sources.items()}
    revision = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:24]
    cache = _safe_folder(_portable_base(executable) / revision)
    if prepare:
        cache.mkdir(parents=True, exist_ok=True)
        for name, source in sources.items():
            target = cache / name
            _safe_folder(target)
            if target.is_file() and _hash(target) == hashes[name]:
                continue
            with tempfile.NamedTemporaryFile(dir=cache, prefix='publish-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(source.read_bytes())
            try:
                if _hash(temporary) != hashes[name]:
                    raise ValueError(tr('포터블 셸 파일 검증에 실패했습니다.'))
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        owner = cache / 'owner.json'
        _safe_folder(owner)
        owner.write_text(json.dumps({'executable': str(executable), 'files': hashes}), encoding='utf-8')
    return ShellLayout(executable, cache / 'EoingPDF.Shell.exe', cache / 'pdf_icon.ico', True)


def cleanup_portable_shell():
    """Remove only intact, owned helper artifacts; retain unknown or locked files."""
    if not is_onefile():
        return
    executable = Path(sys.executable).resolve()
    base = _portable_base(executable)
    if not base.is_dir():
        return
    for cache in base.iterdir():
        if not cache.is_dir() or cache.is_symlink() or cache.is_junction():
            continue
        try:
            owner = _safe_folder(cache / 'owner.json')
            metadata = json.loads(owner.read_text(encoding='utf-8'))
            if not isinstance(metadata, dict):
                continue
            if metadata.get('executable') != str(executable):
                continue
            files = metadata.get('files', {})
            if not isinstance(files, dict) or set(files) != {'EoingPDF.Shell.exe', 'pdf_icon.ico'}:
                continue
            for name, digest in files.items():
                target = _safe_folder(cache / name)
                if target.is_file() and _hash(target) == digest:
                    target.unlink()
            # Keep ownership metadata if a file was changed or could not be removed.
            if not any((cache / name).exists() for name in files):
                owner.unlink()
            if not any(cache.iterdir()):
                cache.rmdir()
        except (OSError, ValueError, TypeError):
            continue
    if not any(base.iterdir()):
        base.rmdir()
