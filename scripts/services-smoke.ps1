$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop after reboot before running this script.' }
docker compose up -d --wait
if ($LASTEXITCODE -ne 0) { throw 'Local service startup failed' }
docker compose exec -T postgres psql -U urbanpulse -d urbanpulse -c 'SELECT PostGIS_Version();'
if ($LASTEXITCODE -ne 0) { throw 'PostGIS check failed' }
docker compose exec -T redis redis-cli ping
if ($LASTEXITCODE -ne 0) { throw 'Redis check failed' }
Write-Output 'PostGIS and Redis smoke checks passed. Services are running on loopback.'
