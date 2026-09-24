"""Create a local DPAPI license state for isolated installer smoke tests."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.licensing import LicenseStore


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit('사용법: seed_test_license.py <license-folder>')
    store = LicenseStore(Path(sys.argv[1]))
    store.data.update(key='installer-smoke-test', active=True)
    store.save()
    if not store.valid_session():
        raise SystemExit('테스트 라이선스 저장에 실패했습니다.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
