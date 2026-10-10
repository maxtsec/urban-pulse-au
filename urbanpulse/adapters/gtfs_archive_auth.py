"""Explicit keyless identities for cloud checks and operator-run historical seeds."""

import os
import re
import shutil
import subprocess

from google.auth import compute_engine
from google.auth.transport.requests import Request


def seed_user_valid(account: str) -> bool:
    return bool(
        re.fullmatch(r"[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", account)
        and not account.lower().endswith(".gserviceaccount.com")
    )


def access_token(expected_service_account: str, seed_user_account: str | None) -> str:
    if not re.fullmatch(
        r"[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com", expected_service_account
    ):
        raise ValueError("explicit target service account required")
    if seed_user_account is None:
        credentials = compute_engine.Credentials()  # type: ignore[no-untyped-call]
        credentials.refresh(Request())  # type: ignore[no-untyped-call]
        if credentials.service_account_email != expected_service_account:
            raise ValueError("unexpected runtime identity")
        token = credentials.token
    else:
        if not seed_user_valid(seed_user_account):
            raise ValueError("explicit operator user account required")
        executable = shutil.which("gcloud.cmd" if os.name == "nt" else "gcloud")
        if executable is None:
            raise ValueError("gcloud required for local impersonation")
        environment = os.environ.copy()
        for name in (
            "CLOUDSDK_AUTH_ACCESS_TOKEN",
            "CLOUDSDK_AUTH_ACCESS_TOKEN_FILE",
            "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE",
        ):
            environment.pop(name, None)
        environment.update(
            {
                "CLOUDSDK_CORE_LOG_HTTP": "false",
                "CLOUDSDK_CORE_DISABLE_FILE_LOGGING": "true",
            }
        )
        # Never inherit console output, print subprocess errors or pass a token in argv.
        try:
            result = subprocess.run(
                [
                    executable,
                    "auth",
                    "print-access-token",
                    "--account=" + seed_user_account,
                    "--impersonate-service-account=" + expected_service_account,
                    "--lifetime=900",
                    "--quiet",
                    "--verbosity=none",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError):
            raise ValueError("seed impersonation failed") from None
        if result.returncode != 0:
            raise ValueError("seed impersonation failed")
        token = result.stdout.strip()
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9._~-]{1,16384}", token):
        raise ValueError("invalid access token")
    return token
