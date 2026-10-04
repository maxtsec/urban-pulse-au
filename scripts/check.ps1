$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
uv run --locked ruff check .
if ($LASTEXITCODE -ne 0) { throw 'Ruff lint failed' }
uv run --locked ruff format --check .
if ($LASTEXITCODE -ne 0) { throw 'Python format check failed' }
uv run --locked mypy
if ($LASTEXITCODE -ne 0) { throw 'Python type check failed' }
uv run --locked pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Python tests failed' }
Push-Location apps/web
try {
    npm.cmd run lint
    if ($LASTEXITCODE -ne 0) { throw 'Frontend lint failed' }
    npm.cmd run format:check
    if ($LASTEXITCODE -ne 0) { throw 'Frontend format check failed' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
