"""Create a private initial delivery record from approved serving inputs; no cloud calls."""

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from scripts.demo_delivery import require


def seed(
    inputs: dict[str, Any], evidence: str, previous_inputs: dict[str, Any] | None = None
) -> dict[str, Any]:
    require(bool(evidence.strip()), "Retain an operator acceptance reference")
    revision = f"{inputs['name_prefix']}-{inputs['release_id']}"
    require(inputs["serving_revision"] == revision, "Seed only a fully promoted serving revision")
    require(
        bool(inputs.get("iap_members") and inputs.get("custom_oauth_client_id")),
        "Protected named-user bootstrap must be complete",
    )
    require(
        all("@sha256:" in inputs[f"{c}_image"] for c in ("api", "web")), "Images must be immutable"
    )
    previous = None
    if previous_inputs is not None:
        require(
            all(
                previous_inputs[k] == inputs[k]
                for k in (
                    "project_id",
                    "name_prefix",
                    "schema_revision",
                    "import_id",
                    "runtime_secret_version",
                )
            ),
            "Previous inputs must belong to a compatible accepted deployment",
        )
        previous = seed(previous_inputs, evidence)["serving"]
        require(previous["revision"] != revision, "Previous revision must be distinct")
    return {
        "schema_version": 1,
        "inputs": deepcopy(inputs),
        "serving": {
            "revision": revision,
            "inputs": deepcopy(inputs),
            "accepted": True,
            "acceptance_reference": evidence,
        },
        "candidate": None,
        "previous": previous,
        "in_progress": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acceptance-reference", required=True)
    parser.add_argument("--previous-inputs", type=Path)
    args = parser.parse_args()
    result = seed(
        json.loads(args.inputs.read_text(encoding="utf-8")),
        args.acceptance_reference,
        json.loads(args.previous_inputs.read_text(encoding="utf-8"))
        if args.previous_inputs
        else None,
    )
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print("Private initial delivery record created; nothing uploaded or deployed.")


if __name__ == "__main__":
    main()
