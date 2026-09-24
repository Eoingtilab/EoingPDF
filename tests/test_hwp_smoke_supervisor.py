"""Check timeout revocation without starting Hancom or modifying its registry."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import subprocess

import pytest


def load_driver():
    spec = importlib.util.spec_from_file_location('hwp_smoke_driver', Path(__file__).with_name('hwp_one_page_smoke.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('failure', [None, 'timeout', 'failed'])
def test_worker_timeout_and_failure_revoke_grant(tmp_path, monkeypatch, failure):
    driver = load_driver()
    released = []
    calls = []

    @contextmanager
    def grant():
        try:
            yield tmp_path
        finally:
            released.append(True)

    def run(command, **options):
        calls.append(command[-1])
        assert options['env']['EOINGPDF_HWP_JOB'] == str(tmp_path)
        assert options['timeout'] == 3 and options['check']
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(command, 3)
        if failure == 'failed':
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(driver, 'job_directory', grant)
    monkeypatch.setattr(driver.subprocess, 'run', run)
    if failure:
        error = RuntimeError if failure == 'timeout' else subprocess.CalledProcessError
        with pytest.raises(error):
            driver.main(timeout=3)
        assert calls == ['hwp'] and len(released) == 1
    else:
        driver.main(timeout=3)
        assert calls == ['hwp', 'hwpx'] and len(released) == 2
