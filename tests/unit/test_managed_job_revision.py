"""Keep deployment revision pins aligned with executable schema/access policy."""

import re

import pytest
from alembic.script import ScriptDirectory

from urbanpulse.adapters.demo_database import EXPECTED_REVISION
from urbanpulse.application.city import MAX_SECONDS
from urbanpulse.config import ROOT


@pytest.mark.parametrize("root", ["demo-jobs", "demo-serving"])
def test_managed_resources_pin_the_reviewed_image_revision(root):
    variables = (ROOT / "infra" / root / "variables.tf").read_text(encoding="utf-8")
    block = variables.split('variable "schema_revision" {', 1)[1].split("\nvariable ", 1)[0]
    default = re.search(r'default\s*=\s*"([^"]+)"', block)
    gate = re.search(r'var\.schema_revision\s*==\s*"([^"]+)"', block)
    assert default and gate
    assert default[1] == gate[1] == EXPECTED_REVISION
    assert ScriptDirectory(str(ROOT / "migrations")).get_current_head() == EXPECTED_REVISION


def test_managed_worker_target_matches_the_fixture_clock():
    configuration = (ROOT / "infra/demo-jobs/main.tf").read_text(encoding="utf-8")
    worker = configuration.split("worker = [", 1)[1].split("]", 1)[0]
    target = re.search(r'"--seconds",\s*"([0-9]+)"', worker)
    assert target
    assert int(target[1]) == MAX_SECONDS


def test_offline_identity_argument_preserves_legacy_powershell_quoting():
    runbook = (ROOT / "docs/runbooks/managed-demo-jobs.md").read_text(encoding="utf-8")
    command = re.search(r"docker run [^\n]+ -c '([^'\n]+)'", runbook)
    assert command
    # PowerShell 5.1 removes embedded double quotes when passing native arguments.
    assert '"' not in command[1]
    compile(command[1], "offline-identity-command", "exec")
