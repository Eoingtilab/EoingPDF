param(
	[Parameter(Mandatory=$true)][string]$PackageName,
	[Parameter(Mandatory=$true)][string]$Publisher,
	[Parameter(Mandatory=$true)][string]$PublisherDisplayName
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot '.venv_d\Scripts\python.exe'
if (-not (Test-Path $python)) {
	$python = 'python'
}

$version = (Get-Content VERSION -Raw).Trim()
$output = Join-Path $PSScriptRoot "release\EoingPDF-$version-Store-x64.msix"
$arguments = @(
	'scripts\package_store_msix.py',
	'--package-name', $PackageName,
	'--publisher', $Publisher,
	'--publisher-display-name', $PublisherDisplayName,
	'--output', $output
)

& $python @arguments
if ($LASTEXITCODE -ne 0) {
	throw 'Microsoft Store MSIX package build failed'
}

Get-FileHash $output -Algorithm SHA256
