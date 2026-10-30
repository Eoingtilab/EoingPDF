param(
    [Parameter(Mandatory=$true)][string]$PythonPath
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python virtual environment was not found: $PythonPath"
}
$version = (Get-Content VERSION -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid source version' }

$finalFolder = Join-Path $PSScriptRoot 'release\EoingPDF'
$stagedFolder = Join-Path $PSScriptRoot 'build\store-staging\EoingPDF'
if (Test-Path -LiteralPath $finalFolder) {
    throw "Existing release folder must be reviewed before rebuilding: $finalFolder"
}
if (Test-Path -LiteralPath $stagedFolder) {
    throw "Existing staging folder must be reviewed before rebuilding: $stagedFolder"
}
if (-not (Test-Path 'assets\EoingPDF.Explorer.dll' -PathType Leaf)) {
    throw 'Verified Explorer COM DLL is missing'
}

& $PythonPath -m pyflakes src\eoingpdf\package_context.py scripts\package_store_msix.py src\eoingpdf\updates.py src\eoingpdf\app.py src\eoingpdf\settings_ui.py
if ($LASTEXITCODE -ne 0) { throw 'Store source static checks failed' }
& $PythonPath scripts\package_search_model.py --verify
if ($LASTEXITCODE -ne 0) { throw 'Search model integrity check failed' }

# Build only the self-contained Win32 folder. Do not rebuild the old installer or mutate GitHub releases.
$env:EOINGPDF_BUILD_ONEFILE = '0'
& $PythonPath -m PyInstaller --noconfirm --clean --distpath build\store-staging --workpath build\store-work packaging\EoingPDF.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller Store folder build failed' }
if (-not (Test-Path (Join-Path $stagedFolder 'EoingPDF.exe'))) { throw 'Frozen EXE is missing' }

$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64/v4.0.30319/csc.exe'
if (-not (Test-Path $csc)) { throw 'Windows .NET C# compiler is missing' }
& $csc /nologo /target:winexe /platform:x64 /out:"$stagedFolder\EoingPDF.Shell.exe" /reference:System.Windows.Forms.dll native\ShellBridge.cs
if ($LASTEXITCODE -ne 0) { throw 'Explorer helper build failed' }
Copy-Item -LiteralPath assets\EoingPDF.Explorer.dll -Destination $stagedFolder
Copy-Item -Path README.md,CHANGELOG.md,VERSION,LICENSE,PRIVACY.md,docs\THIRD_PARTY.md -Destination $stagedFolder
Copy-Item -LiteralPath docs -Destination $stagedFolder -Recurse

New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'temp') | Out-Null
# Verify the exact Store-aware frozen application before moving the folder into the MSIX input location.
& $PythonPath tests\frozen_smoke.py --exe "$stagedFolder\EoingPDF.exe"
if ($LASTEXITCODE -ne 0) { throw 'Frozen application smoke test failed' }
& $PythonPath tests\frozen_form_smoke.py --exe "$stagedFolder\EoingPDF.exe"
if ($LASTEXITCODE -ne 0) { throw 'Frozen form smoke test failed' }
& $PythonPath tests\frozen_localization_smoke.py --exe "$stagedFolder\EoingPDF.exe"
if ($LASTEXITCODE -ne 0) { throw 'Frozen localization smoke test failed' }
& $PythonPath tests\frozen_update_smoke.py --folder $stagedFolder
if ($LASTEXITCODE -ne 0) { throw 'Frozen update smoke test failed' }

New-Item -Path (Split-Path -Parent $finalFolder) -ItemType Directory -Force | Out-Null
Move-Item -LiteralPath $stagedFolder -Destination $finalFolder
Write-Output "STORE_FOLDER_READY=$finalFolder"
Write-Output "STORE_FOLDER_VERSION=$version"
Get-FileHash -LiteralPath (Join-Path $finalFolder 'EoingPDF.exe') -Algorithm SHA256 | Format-List