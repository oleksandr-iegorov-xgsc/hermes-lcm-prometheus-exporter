from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigurationError(ValueError):
    """Raised when exporter database configuration is invalid or ambiguous."""


def _add_database(databases: dict[str, Path], profile: str, path: Path) -> None:
    if not isinstance(profile, str) or not profile or "/" in profile:
        raise ConfigurationError("database profile must be a non-empty single path component")
    if profile in databases:
        raise ConfigurationError(
            f"duplicate profile {profile!r}; each Hermes profile is one agent identity"
        )
    databases[profile] = path


def discover_profiles(profiles_roots: list[Path]) -> dict[str, Path]:
    databases: dict[str, Path] = {}
    for root in profiles_roots:
        if not root.is_dir():
            raise ConfigurationError(f"profiles root does not exist or is not a directory: {root}")
        for path in sorted(root.glob("*/lcm.db")):
            _add_database(databases, path.parent.name, path)
    return databases


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text())
    except OSError as exc:
        raise ConfigurationError(f"cannot read configuration {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"invalid JSON in configuration {path}: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError("configuration root must be a JSON object")
    unknown = set(raw) - {"profiles_roots", "databases"}
    if unknown:
        raise ConfigurationError(f"unknown configuration key(s): {', '.join(sorted(unknown))}")
    return raw


def load_database_config(path: Path) -> dict[str, Path]:
    """Load profile-only source configuration from a structured JSON file."""
    raw = _read_json(path)
    roots = raw.get("profiles_roots", [])
    explicit = raw.get("databases", [])
    if not isinstance(roots, list) or not all(isinstance(item, str) for item in roots):
        raise ConfigurationError("profiles_roots must be an array of paths")
    if not isinstance(explicit, list):
        raise ConfigurationError("databases must be an array")

    databases = discover_profiles([Path(item).expanduser() for item in roots])
    for item in explicit:
        if not isinstance(item, dict) or set(item) != {"profile", "path"}:
            raise ConfigurationError("each databases entry must contain exactly profile and path")
        profile = item["profile"]
        raw_path = item["path"]
        if not isinstance(raw_path, str):
            raise ConfigurationError("database path must be a string")
        _add_database(databases, profile, Path(raw_path).expanduser())
    if not databases:
        raise ConfigurationError("configuration did not resolve any LCM databases")
    return databases
