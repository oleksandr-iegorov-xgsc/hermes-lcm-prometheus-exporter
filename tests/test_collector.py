from __future__ import annotations

import sqlite3
from pathlib import Path

from hermes_lcm_prometheus_exporter.collector import collect_database, render_metrics


def make_database(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE messages (
            store_id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            timestamp REAL NOT NULL,
            token_estimate INTEGER DEFAULT 0
        );
        CREATE TABLE summary_nodes (
            node_id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            depth INTEGER NOT NULL,
            token_count INTEGER DEFAULT 0,
            source_token_count INTEGER DEFAULT 0,
            created_at REAL NOT NULL
        );
        CREATE TABLE lcm_lifecycle_state (
            conversation_id TEXT PRIMARY KEY,
            debt_kind TEXT,
            debt_size_estimate INTEGER NOT NULL DEFAULT 0
        );
        INSERT INTO messages VALUES
            (1, 'one', 'user', 1000, 10),
            (2, 'one', 'assistant', 1010, 20),
            (3, 'two', 'tool', 1020, 30);
        INSERT INTO summary_nodes VALUES
            (1, 'one', 0, 5, 100, 1030),
            (2, 'two', 1, 10, 200, 1040);
        INSERT INTO lcm_lifecycle_state VALUES
            ('one', NULL, 0),
            ('two', 'maintenance', 7);
        """
    )
    db.commit()
    db.close()


def test_collects_profile_scoped_state_from_read_only_database(tmp_path: Path) -> None:
    path = tmp_path / "lcm.db"
    make_database(path)

    snapshot = collect_database(path, "everyday_assistant")

    assert snapshot.profile == "everyday_assistant"
    assert snapshot.messages_total == 3
    assert snapshot.message_tokens == 60
    assert snapshot.summary_nodes_total == 2
    assert snapshot.summary_tokens == 15
    assert snapshot.summary_source_tokens == 300
    assert snapshot.lifecycle_conversations == 2
    assert snapshot.lifecycle_debt_conversations == 1
    assert snapshot.lifecycle_debt_tokens == 7
    assert snapshot.messages_by_role == {"assistant": 1, "tool": 1, "user": 1}
    assert snapshot.summary_nodes_by_depth == {0: 1, 1: 1}


def test_rendered_metrics_are_prometheus_text_with_profile_label(tmp_path: Path) -> None:
    path = tmp_path / "lcm.db"
    make_database(path)

    rendered = render_metrics([collect_database(path, "everyday_assistant")])

    assert "# TYPE hermes_lcm_messages_total gauge" in rendered
    assert 'hermes_lcm_messages_total{profile="everyday_assistant"} 3' in rendered
    assert 'hermes_lcm_messages_by_role{profile="everyday_assistant",role="tool"} 1' in rendered
    assert 'hermes_lcm_summary_compression_ratio{profile="everyday_assistant"} 20' in rendered
    assert "hermes_lcm_exporter_up" in rendered


def test_missing_required_schema_is_reported_without_crashing(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()

    snapshot = collect_database(path, "broken")

    assert snapshot.error is not None
    assert "messages" in snapshot.error
