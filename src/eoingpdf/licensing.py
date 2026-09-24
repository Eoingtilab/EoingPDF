"""EDD desktop licensing; keys are encrypted for the current Windows user."""
from .localization import tr
import json
import os
import re
import uuid
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlencode
from urllib.error import URLError
import win32crypt
import pywintypes

STORE_URL = 'https://app.nal.la/'
ITEM_ID = 26818
ERRORS = {
    'expired': '라이선스가 만료되었습니다.',
    'disabled': '중지된 라이선스입니다.',
    'revoked': '취소된 라이선스입니다.',
    'missing': '등록되지 않은 라이선스입니다.',
    'invalid': '유효하지 않은 라이선스입니다.',
    'site_inactive': '이 PC에서 활성화되지 않았습니다.',
    'no_activations_left': '활성화 가능한 기기 수를 초과했습니다. 다른 PC에서 비활성화한 뒤 다시 시도하세요.',
    'item_name_mismatch': '다른 상품의 라이선스입니다.',
    'invalid_item_id': '상품 설정을 확인해 주세요.',
}


class LicenseError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LicenseError(tr('라이선스 서버 주소가 변경되었습니다. 관리자에게 문의해 주세요.'))


def request(action, key, device):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', key):
        raise LicenseError(tr('라이선스 키 형식을 확인해 주세요.'))
    data = urlencode({'edd_action': action, 'item_id': ITEM_ID, 'license': key, 'url': device}).encode()
    req = Request(STORE_URL, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'EoingPDF'})
    try:
        with build_opener(NoRedirect()).open(req, timeout=12) as response:
            result = json.loads(response.read(65537))
    except LicenseError:
        raise
    except (URLError, OSError, ValueError):
        raise LicenseError(tr('라이선스 서버에 연결할 수 없습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.')) from None
    if not isinstance(result, dict):
        raise LicenseError(tr('라이선스 서버 응답을 확인할 수 없습니다.'))
    if result.get('item_id') not in (None, False, ITEM_ID, str(ITEM_ID)):
        raise LicenseError(tr('다른 상품의 라이선스 응답입니다.'))
    return result


class LicenseStore:
    def __init__(self, folder=None, transport=request):
        self.folder = Path(folder) if folder else Path(os.environ['LOCALAPPDATA']) / 'EoingPDF/license'
        self.transport = transport
        self.data = self.load()
        self.verified_until = 0

    def load(self):
        try:
            raw = (self.folder / 'license.dat').read_bytes()
            data = json.loads(win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1])
            if not isinstance(data, dict) or not isinstance(data.get('device'), str):
                raise ValueError('Invalid license state')
            if not data['device'].startswith('eoingpdf-') or not isinstance(data.get('key'), str):
                raise ValueError('Invalid license identity')
            if type(data.get('active')) is not bool:
                raise ValueError('Invalid activation state')
            return data
        except (OSError, ValueError, pywintypes.error):
            return {'device': 'eoingpdf-' + str(uuid.uuid4()), 'key': '', 'active': False}

    def save(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        blob = win32crypt.CryptProtectData(json.dumps(self.data).encode(), 'EoingPDF', None, None, None, 0)
        target = self.folder / 'license.dat'
        temporary = self.folder / ('license-' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_bytes(blob)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def perform(self, action, key=None):
        if action not in {'activate_license', 'check_license', 'deactivate_license'}:
            raise LicenseError(tr('지원하지 않는 라이선스 작업입니다.'))
        key = (key if key is not None else self.data.get('key', '')).strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', key):
            raise LicenseError(tr('라이선스 키 형식을 확인해 주세요.'))
        if self.data.get('active') and key != self.data.get('key'):
            raise LicenseError(tr('기존 라이선스를 먼저 비활성화해 주세요.'))
        if action == 'activate_license':
            if self.data.get('active') and key != self.data.get('key'):
                raise LicenseError(tr('기존 라이선스를 먼저 비활성화해 주세요.'))
            # Persist device identity before a request whose result might time out.
            self.data['key'] = key
            self.save()
        result = self.transport(action, key, self.data['device'])
        status = result.get('license', '')
        if action == 'deactivate_license':
            if result.get('success') is not True or status not in ('deactivated', 'inactive', 'site_inactive'):
                raise LicenseError(tr(ERRORS.get(result.get('error') or status, '비활성화하지 못했습니다. 다시 시도해 주세요.')))
            self.data['active'] = False
            self.verified_until = 0
        elif status == 'valid' and result.get('success') is not False and (action != 'activate_license' or result.get('success') is True):
            self.data.update(key=key, active=True)
        else:
            self.data['active'] = False
            self.verified_until = 0
            self.save()
            raise LicenseError(tr(ERRORS.get(result.get('error') or status, '라이선스를 확인하지 못했습니다. 상품과 키를 확인해 주세요.')))
        self.save()
        return self.data['active']

    def valid_session(self):
        # A DPAPI-protected successful activation survives process restarts.
        # Network errors never grant activation or revoke an existing grant.
        # Explicit server rejection and successful deactivation revoke it.
        return self.data.get('active') is True and bool(self.data.get('key'))


_store = None


def store():
    global _store
    if _store is None:
        _store = LicenseStore()
    return _store
