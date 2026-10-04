$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
uv run --locked pytest -m integration -q
if ($LASTEXITCODE -ne 0) { throw 'PostGIS integration tests failed; start local services first' }
Push-Location apps/web
try {
    npx.cmd playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed' }
    npm.cmd run test:e2e
    if ($LASTEXITCODE -ne 0) { throw 'City browser tests failed' }
} finally { Pop-Location }
