# Clean-checkout rehearsal

Use this procedure to verify the local baseline from an independent checkout without reusing its virtual environment or database. See [BASE-01 evidence](../evidence/base-01-clean-checkout.md) for the measured run.

Prerequisites: the system tools in the [development guide](../development.md), a running Docker engine, and free ports 8000, 5173, 15432 and 16379. Use a new PowerShell terminal. Compose 2.24.4 or later supports the [port replacement override](https://docs.docker.com/reference/compose-file/merge/#replace-value).

## Restore and check

From a parent directory where `urbanpulse-rehearsal` does not exist:

```powershell
git clone --single-branch --branch main https://github.com/maxtsec/urban-pulse-au.git urbanpulse-rehearsal
if ($LASTEXITCODE -ne 0) { throw 'Clone failed' }
Set-Location urbanpulse-rehearsal
git checkout --detach b2a390bface82a418094d8fcf7843f8bd42796a9
if ($LASTEXITCODE -ne 0) { throw 'Revision checkout failed' }
git status --short
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
if ($LASTEXITCODE -ne 0) { throw 'Setup failed' }
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1
if ($LASTEXITCODE -ne 0) { throw 'Checks failed' }
```

The pinned revision reproduces the recorded baseline. Select a different reviewed revision for a new evidence record. Record dependency-cache and Docker-image availability when measuring time.

## Isolate services

Use a unique Compose project and replacement ports. The project name keeps the new database volume separate; a different folder alone is insufficient because the repository sets a Compose project name.

```powershell
$rehearsalProject = 'urbanpulse-rehearsal-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$env:COMPOSE_PROJECT_NAME = $rehearsalProject
$env:COMPOSE_PATH_SEPARATOR = ';'
New-Item -ItemType Directory -Path .local -Force | Out-Null
@'
services:
  postgres:
    ports: !override ["127.0.0.1:15432:5432"]
  redis:
    ports: !override ["127.0.0.1:16379:6379"]
'@ | Set-Content -Encoding UTF8 .local/rehearsal.compose.yaml
$env:COMPOSE_FILE = 'compose.yaml;' + (Join-Path (Get-Location) '.local/rehearsal.compose.yaml')
$env:DATABASE_URL = 'postgresql://urbanpulse:urbanpulse_local@127.0.0.1:15432/urbanpulse'
$env:REDIS_URL = 'redis://127.0.0.1:16379/0'
$config = docker compose config --format json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Invalid Compose configuration' }
if ($config.name -ne $rehearsalProject) { throw 'Wrong project name' }
if ($config.volumes.postgres_data.name -ne ($rehearsalProject + '_postgres_data')) {
    throw 'Wrong database volume'
}
if (@(docker ps -aq --filter "label=com.docker.compose.project=$rehearsalProject").Count) {
    throw 'Test containers already exist'
}
if (@(docker volume ls -q --filter "label=com.docker.compose.project=$rehearsalProject").Count) {
    throw 'Test volumes already exist'
}
```

## Exercise and clean up

Run this block in the same terminal. Its cleanup applies only to the generated rehearsal project.

```powershell
try {
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/services-smoke.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Service smoke failed' }
    @'
from fastapi.testclient import TestClient
from apps.api.main import app
with TestClient(app) as client:
    response = client.get("/health/ready")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "ok", "postgis": "ok", "redis": "ok", "mode": "fixture"
    }
print("PASS: readiness against isolated PostGIS and Redis")
'@ | uv run --locked python -
    if ($LASTEXITCODE -ne 0) { throw 'Readiness failed' }
    uv run --locked python scripts/smoke.py
    if ($LASTEXITCODE -ne 0) { throw 'HTTP smoke failed' }
} finally {
    if (-not $rehearsalProject -or $env:COMPOSE_PROJECT_NAME -ne $rehearsalProject) {
        throw 'Refusing cleanup of a different project'
    }
    docker compose down --volumes
    if ($LASTEXITCODE -ne 0) { throw 'Cleanup failed' }
}
git status --short
docker ps -a --filter "label=com.docker.compose.project=$rehearsalProject"
docker volume ls --filter "label=com.docker.compose.project=$rehearsalProject"
```

Expect a clean Git status and no remaining rehearsal containers or volumes. Close the dedicated terminal to discard the test environment variables. Retain logs with the tested revision and timing conditions. The HTTP smoke owns and terminates its temporary servers.
