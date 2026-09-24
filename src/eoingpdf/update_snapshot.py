"""Verified snapshots of packaged application files, excluding user data."""
from .localization import tr
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

MANAGED = frozenset({'EoingPDF.exe', 'EoingPDF.Shell.exe', 'EoingPDF.Explorer.dll', 'VERSION', '_internal', 'docs',
                     'README.md', 'CHANGELOG.md', 'THIRD_PARTY.md',
                     'install-context-menu.cmd', 'uninstall-context-menu.cmd'})


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def safe_path(root, relative):
    part = Path(relative)
    if part.is_absolute() or not part.parts or part.parts[0] not in MANAGED or any(x in ('..', '.') or ':' in x for x in part.parts):
        raise ValueError(tr('백업 경로가 올바르지 않습니다.'))
    path = root / part
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(tr('백업 경로가 폴더 밖을 가리킵니다.'))
    for current in [path, *path.parents]:
        if current == root:
            break
        if current.is_symlink() or current.is_junction():
            raise ValueError(tr('연결된 파일은 업데이트 백업에서 지원하지 않습니다.'))
    return path


def create(install, folder, version):
    install, folder = Path(install).resolve(), Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='snapshot-', dir=folder))
    try:
        files = {}
        size = 0
        for name in sorted(MANAGED):
            entry = safe_path(install, name)
            if not entry.exists():
                continue
            paths = entry.rglob('*') if entry.is_dir() else [entry]
            for path in paths:
                relative = path.relative_to(install).as_posix()
                path = safe_path(install, relative)
                if not path.is_file():
                    continue
                size += path.stat().st_size
                if size > 3 * 1024**3 or len(files) >= 20000:
                    raise ValueError(tr('업데이트 백업 크기 제한을 초과했습니다.'))
                expected = digest(path)
                target = safe_path(backup, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                if digest(target) != expected or digest(path) != expected:
                    raise ValueError(tr('백업 중 설치 파일이 변경되었습니다.'))
                files[relative] = expected
        if 'EoingPDF.exe' not in files:
            raise ValueError(tr('백업할 실행 파일이 없습니다.'))
        manifest = {'schema': 2, 'source': str(install), 'version': version,
                    'sha256': files['EoingPDF.exe'], 'files': files}
        (backup / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
        validate(backup, install)
        return backup
    except Exception:
        shutil.rmtree(backup)
        raise


def validate(backup, install):
    backup = Path(backup).resolve()
    manifest = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 2 or manifest.get('source') != str(Path(install).resolve()):
        raise ValueError(tr('현재 설치 폴더의 전체 백업이 아닙니다.'))
    files = manifest.get('files')
    if not isinstance(files, dict) or not 1 <= len(files) <= 20000 or 'EoingPDF.exe' not in files:
        raise ValueError(tr('백업 파일 목록이 올바르지 않습니다.'))
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError(tr('백업 파일 정보가 올바르지 않습니다.'))
        source = safe_path(backup, relative)
        if not source.is_file() or digest(source) != expected:
            raise ValueError(tr('업데이트 백업이 손상되었습니다.'))
    return manifest


def restore(backup, install):
    install = Path(install).resolve()
    manifest = validate(backup, install)
    staging = Path(tempfile.mkdtemp(prefix='.eoing-restore-', dir=install))
    applied, moved = [], []
    completed = False
    try:
        payload, old = staging / 'payload', staging / 'previous'
        payload.mkdir(); old.mkdir()
        for relative, expected in manifest['files'].items():
            target = safe_path(payload, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(safe_path(Path(backup), relative), target)
            if digest(target) != expected:
                raise ValueError(tr('복원 파일 검증에 실패했습니다.'))
        # A newer release may add a managed root file absent from this snapshot.
        # Move it aside too, so rollback cannot mix old EXE and new shell DLLs.
        names = sorted(MANAGED, key=lambda name: (name != 'EoingPDF.exe', name))
        for name in names:
            target = safe_path(install, name)
            if target.exists():
                os.replace(target, old / name)
                moved.append(name)
            if (payload / name).exists():
                os.replace(payload / name, target)
                applied.append(name)
        completed = True
    except Exception:
        for name in reversed(applied):
            os.replace(install / name, payload / name)
        for name in reversed(moved):
            os.replace(old / name, install / name)
        raise
    finally:
        # If compensating restoration fails, retain the staged previous files
        # instead of deleting the only remaining copy.
        if not (staging / 'previous').exists() or not any((staging / 'previous').iterdir()) or completed:
            shutil.rmtree(staging)
    return install / 'EoingPDF.exe'
