"""Compatibility entry for private operator scripts; SQL policy lives in its adapter."""

from urbanpulse.adapters.demo_database import (
    APPLICATION_TABLES,
    EVENT_TABLES,
    EXPECTED_REVISION,
    INPUT_TABLES,
    MUTABLE_EVENT_TABLES,
    ROLE_LIMITS,
    activate_roles,
    bootstrap,
    configure_defaults,
    grant_access,
    require_database,
    require_migrator,
    role_names,
)

__all__ = [
    "EXPECTED_REVISION",
    "ROLE_LIMITS",
    "INPUT_TABLES",
    "EVENT_TABLES",
    "MUTABLE_EVENT_TABLES",
    "APPLICATION_TABLES",
    "role_names",
    "require_database",
    "bootstrap",
    "activate_roles",
    "require_migrator",
    "configure_defaults",
    "grant_access",
]
