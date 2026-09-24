import sys
from pathlib import Path
from dataclasses import replace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf import windows_effects as effects


@pytest.fixture
def enabled():
    return effects.Policy(build=22621, transparency=True, composition=True)


@pytest.mark.parametrize('override', [
    {'build': 19045}, {'build': 22000}, {'high_contrast': True},
    {'transparency': False}, {'remote': True}, {'battery_saver': True},
    {'composition': False},
])
def test_unsupported_or_accessibility_settings_always_use_solid(enabled, override):
    policy = replace(enabled, **override)
    assert policy.material() == policy.material(transient=True) == 1


def test_live_preference_change_resets_material_and_dark_titlebar(monkeypatch, enabled):
    calls = []
    monkeypatch.setattr(effects, 'set_attribute', lambda *args: calls.append(args) or True)
    assert effects.apply_frame(123, 'dark', enabled) == 'mica'
    assert calls[-2:] == [(123, 20, 1), (123, 38, 2)]
    assert effects.apply_frame(123, 'light', enabled, transient=True) == 'acrylic'
    assert calls[-2:] == [(123, 20, 0), (123, 38, 3)]
    assert effects.apply_frame(123, 'dark', replace(enabled, high_contrast=True)) == 'solid'
    assert calls[-2:] == [(123, 20, 0), (123, 38, 1)]
    assert effects.apply_frame(123, 'dark', enabled, audience=True) == 'solid'


def test_failed_dwm_material_request_resets_to_solid(monkeypatch, enabled):
    calls = []
    monkeypatch.setattr(effects, 'set_attribute', lambda *args: calls.append(args) or False)
    assert effects.apply_frame(123, 'dark', enabled) == 'solid'
    assert calls[-1] == (123, 38, 1)
    calls.clear()
    assert effects.apply_frame(123, 'dark', replace(enabled, build=19045)) == 'unsupported'
    assert calls == []
