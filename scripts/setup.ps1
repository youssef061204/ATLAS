$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 and retry.' }
}
& .venv/Scripts/python -m pip install -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Push-Location frontend
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
} finally { Pop-Location }
& .venv/Scripts/atlas demo --cached
if ($LASTEXITCODE -ne 0) { throw 'Sample download/cache initialization failed; upload your own traffic footage instead.' }
Write-Host 'Ready. Run: .venv/Scripts/python scripts/dev.py'
