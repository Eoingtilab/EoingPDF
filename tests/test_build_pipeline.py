from pathlib import Path


def test_release_pipeline_contains_all_distribution_gates():
    script = (Path(__file__).resolve().parents[1] / 'build_release.ps1').read_text(encoding='utf-8-sig')
    required = (
        "Get-ChildItem tests -Filter 'test_*.py'",
        'PyInstaller',
        'ShellBridge.cs',
        'InnoSetup\\ISCC.exe',
        'EoingPDF-$version-Setup-x64.exe',
        'tests\\frozen_smoke.py',
        'scripts\\package_source.py',
        'tests\\source_package_smoke.py',
    )
    missing = [item for item in required if item not in script]
    assert not missing, f'배포 파이프라인 단계가 없습니다: {missing}'


def test_winget_submission_template_is_present_and_explicitly_unfinalized():
    root = Path(__file__).resolve().parents[1]
    manifest = root / 'packaging' / 'winget' / 'manifest.yaml'
    text = manifest.read_text(encoding='utf-8')
    for required in ('PackageIdentifier: Eoingtilab.EoingPDF',
                     'PackageVersion: 2.2.0',
                     'InstallerType: exe',
                     'InstallerUrl:',
                     'InstallerSha256: REPLACE_WITH_64_HEX_SHA256'):
        assert required in text

