$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
uv sync --locked
if ($LASTEXITCODE -ne 0) { throw 'Python dependency sync failed' }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Push-Location apps/web
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
} finally { Pop-Location }
Write-Output 'Dependencies ready. Start Docker Desktop, then docker compose up -d --wait.'
