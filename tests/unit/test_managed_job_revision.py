"""Keep deployment revision pins aligned with executable schema/access policy."""

import re

from alembic.script import ScriptDirectory

from urbanpulse.adapters.demo_database import EXPECTED_REVISION
from urbanpulse.config import ROOT


def test_managed_jobs_pin_the_reviewed_image_revision():
    variables = (ROOT / "infra/demo-jobs/variables.tf").read_text(encoding="utf-8")
    block = variables.split('variable "schema_revision" {', 1)[1].split("\nvariable ", 1)[0]
    default = re.search(r'default\s*=\s*"([^"]+)"', block)
    gate = re.search(r'var\.schema_revision\s*==\s*"([^"]+)"', block)
    assert default and gate
    assert default[1] == gate[1] == EXPECTED_REVISION
    assert ScriptDirectory(str(ROOT / "migrations")).get_current_head() == EXPECTED_REVISION
