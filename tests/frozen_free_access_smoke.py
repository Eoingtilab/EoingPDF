"""Check a fresh frozen app starts without contacting the licensing store."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True)
    executable = Path(parser.parse_args().exe).resolve()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='free-frozen-', dir=root / 'temp') as tmp:
        folder = Path(tmp)
        env = os.environ.copy()
        for key, name in [('APPDATA', 'roaming'), ('LOCALAPPDATA', 'local')]:
            (folder / name).mkdir()
            env[key] = str(folder / name)
        env['QT_QPA_PLATFORM'] = 'offscreen'
        screenshot = folder / 'startup.png'
        result = subprocess.run([str(executable), '--screenshot', str(screenshot), '--skip-update-once'],
                                env=env, capture_output=True, timeout=75)
        assert result.returncode == 0, result.stderr.decode(errors='replace')
        assert screenshot.is_file() and screenshot.stat().st_size > 0
        assert not (folder / 'local' / 'EoingPDF' / 'license').exists()
        legacy = subprocess.run([str(executable), '--license'], env=env, capture_output=True, timeout=30)
        assert legacy.returncode == 0
        assert not (folder / 'local' / 'EoingPDF' / 'license').exists()
    print('PASS: first launch and legacy license entry require no license and create no license state')


if __name__ == '__main__':
    main()
