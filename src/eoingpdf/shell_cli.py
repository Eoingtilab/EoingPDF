"""Noninteractive shell registration entry point for installers and scripts."""
from .localization import tr
import argparse
import json
import os
from pathlib import Path
import sys


def main(arguments):
    # The action names begin with '--'; parse it independently of optional args.
    action, *options = arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--shell-result', type=Path)
    args = parser.parse_args(options)
    code, message = 0, tr('Windows 셸 설정을 완료했습니다.')
    try:
        from .shell import install, uninstall, open_default_settings
        if action == '--uninstall-menu':
            uninstall()
        elif action in ('--install-menu', '--register-shell'):
            install()
            if action == '--install-menu':
                open_default_settings()
        else:
            raise ValueError(tr('지원하지 않는 셸 명령입니다.'))
    except PermissionError:
        code = 2
        message = tr('Windows 셸 설정 권한이 없습니다. 사용자 계정 정책을 확인해 주세요.')
    except Exception as error:
        code = 1
        message = tr('Windows 셸 설정 실패: {v0}', v0=error)
    result = {'action': action, 'exit_code': code, 'message': message}
    report = args.shell_result
    if report is None and os.environ.get('LOCALAPPDATA'):
        report = Path(os.environ['LOCALAPPDATA']) / 'EoingPDF' / 'logs' / 'shell-result.json'
    if report is not None:
        try:
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8-sig')
        except OSError:
            # A denied diagnostics directory must not open UI or hide the
            # registration result from the calling installer.
            pass
    if code and sys.stderr is not None:
        try:
            print(message, file=sys.stderr)
        except (OSError, UnicodeError):
            pass
    return code
