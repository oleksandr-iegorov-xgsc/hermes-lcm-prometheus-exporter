from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_lcm_prometheus_exporter.config import ConfigurationError, load_database_config


def make_lcm_db(profiles_root: Path, profile: str) -> Path:
    path = profiles_root / profile / "lcm.db"
    path.parent.mkdir(parents=True)
    path.touch()
    return path


def test_config_discovers_unique_profiles_from_multiple_roots(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    everyday = make_lcm_db(first, "everyday_assistant")
    research = make_lcm_db(second, "research_assistant")
    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"profiles_roots": [str(first), str(second)]}))

    databases = load_database_config(config)

    assert databases == {
        "everyday_assistant": everyday,
        "research_assistant": research,
    }


def test_config_rejects_duplicate_profile_names_across_roots(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    make_lcm_db(first, "everyday_assistant")
    make_lcm_db(second, "everyday_assistant")
    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"profiles_roots": [str(first), str(second)]}))

    with pytest.raises(ConfigurationError, match="duplicate profile"):
        load_database_config(config)


def test_config_accepts_explicit_profile_database(tmp_path: Path) -> None:
    database = tmp_path / "standalone.db"
    database.touch()
    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"databases": [{"profile": "standalone", "path": str(database)}]}))

    assert load_database_config(config) == {"standalone": database}
