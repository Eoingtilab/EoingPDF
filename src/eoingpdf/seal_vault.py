"""Windows account-bound encrypted seal storage. No plaintext image files."""
from .localization import tr
import base64
import io
import json
import os
import re
import uuid
from pathlib import Path

MAX_BLOB = 30 * 1024 * 1024


def read_seal(path):
    import win32crypt
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_BLOB:
        raise ValueError(tr('도장 보관 파일이 없거나 허용 크기를 초과합니다.'))
    try:
        plain = win32crypt.CryptUnprotectData(path.read_bytes(), None, None, None, 1)[1]
        item = json.loads(plain)
        if item.get('version') != 1 or not isinstance(item.get('name'), str) or not 1 <= len(item['name']) <= 80:
            raise ValueError()
        stream = base64.b64decode(item['png'], validate=True)
        from PIL import Image
        with Image.open(io.BytesIO(stream)) as image:
            if image.format != 'PNG' or image.width * image.height > 40_000_000:
                raise ValueError()
            image.verify()
        return item['name'], stream
    except Exception:
        raise ValueError(tr('도장을 열 수 없습니다. 저장한 Windows 계정인지 확인해 주세요. 파일이 손상되었을 수도 있습니다.')) from None


class SealVault:
    def __init__(self, folder=None):
        self.folder = Path(folder) if folder is not None else Path(os.environ['LOCALAPPDATA']) / 'EoingPDF/seals'

    def entries(self):
        result = []
        for path in sorted(self.folder.glob('*.eoseal')):
            if len(result) >= 100:
                break
            try:
                name, _ = read_seal(path)
                result.append((path, name, True))
            except ValueError:
                result.append((path, tr('열 수 없는 도장'), False))
        return result

    def add(self, image_path, name):
        import win32crypt
        from .stamping import prepare_image
        name = name.strip()
        if not 1 <= len(name) <= 80 or any(ord(char) < 32 for char in name):
            raise ValueError(tr('도장 이름은 줄바꿈 없이 1~80자로 입력해 주세요.'))
        if len(list(self.folder.glob('*.eoseal'))) >= 100:
            raise ValueError(tr('도장은 최대 100개까지 보관할 수 있습니다.'))
        stream, _ = prepare_image(image_path)
        plain = json.dumps(dict(version=1, name=name, png=base64.b64encode(stream).decode('ascii'))).encode('utf-8')
        blob = win32crypt.CryptProtectData(plain, 'EoingPDF seal', None, None, None, 1)
        if len(blob) > MAX_BLOB:
            raise ValueError(tr('도장이 너무 큽니다. 이미지 크기를 줄여 주세요.'))
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / (uuid.uuid4().hex + '.eoseal')
        created = False
        try:
            with path.open('xb') as output:
                created = True
                output.write(blob)
                output.flush()
                os.fsync(output.fileno())
        except Exception:
            if created and path.exists():
                path.unlink()
            raise
        return path

    def remove(self, path):
        path = Path(path)
        if path.resolve().parent != self.folder.resolve() or not re.fullmatch(r'[a-f0-9]{32}\.eoseal', path.name):
            raise ValueError(tr('보관함 안의 도장만 삭제할 수 있습니다.'))
        path.unlink()
