from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Snapshot:
    profile: str
    database_size_bytes: int
    messages_total: int = 0
    message_tokens: int = 0
    messages_by_role: dict[str, int] = field(default_factory=dict)
    latest_message_timestamp: float = 0.0
    summary_nodes_total: int = 0
    summary_tokens: int = 0
    summary_source_tokens: int = 0
    summary_nodes_by_depth: dict[int, int] = field(default_factory=dict)
    latest_summary_timestamp: float = 0.0
    lifecycle_conversations: int = 0
    lifecycle_debt_conversations: int = 0
    lifecycle_debt_tokens: int = 0
    error: str | None = None


def _scalar(connection: sqlite3.Connection, query: str) -> int | float:
    value = connection.execute(query).fetchone()[0]
    return 0 if value is None else value


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def collect_database(path: Path, profile: str) -> Snapshot:
    """Return a point-in-time, read-only snapshot of a single LCM database."""
    size = path.stat().st_size if path.exists() else 0
    try:
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, timeout=2)
        try:
            tables = _table_names(connection)
            required = {"messages", "summary_nodes", "lcm_lifecycle_state"}
            missing = sorted(required - tables)
            if missing:
                raise RuntimeError(f"required LCM tables missing: {', '.join(missing)}")

            messages_by_role = {
                str(role): int(count)
                for role, count in connection.execute(
                    "SELECT role, COUNT(*) FROM messages GROUP BY role"
                )
            }
            summary_nodes_by_depth = {
                int(depth): int(count)
                for depth, count in connection.execute(
                    "SELECT depth, COUNT(*) FROM summary_nodes GROUP BY depth"
                )
            }
            return Snapshot(
                profile=profile,
                database_size_bytes=size,
                messages_total=int(_scalar(connection, "SELECT COUNT(*) FROM messages")),
                message_tokens=int(
                    _scalar(connection, "SELECT COALESCE(SUM(token_estimate), 0) FROM messages")
                ),
                messages_by_role=messages_by_role,
                latest_message_timestamp=float(
                    _scalar(connection, "SELECT MAX(timestamp) FROM messages")
                ),
                summary_nodes_total=int(_scalar(connection, "SELECT COUNT(*) FROM summary_nodes")),
                summary_tokens=int(
                    _scalar(connection, "SELECT COALESCE(SUM(token_count), 0) FROM summary_nodes")
                ),
                summary_source_tokens=int(
                    _scalar(
                        connection, "SELECT COALESCE(SUM(source_token_count), 0) FROM summary_nodes"
                    )
                ),
                summary_nodes_by_depth=summary_nodes_by_depth,
                latest_summary_timestamp=float(
                    _scalar(connection, "SELECT MAX(created_at) FROM summary_nodes")
                ),
                lifecycle_conversations=int(
                    _scalar(connection, "SELECT COUNT(*) FROM lcm_lifecycle_state")
                ),
                lifecycle_debt_conversations=int(
                    _scalar(
                        connection,
                        "SELECT COUNT(*) FROM lcm_lifecycle_state WHERE debt_kind IS NOT NULL",
                    )
                ),
                lifecycle_debt_tokens=int(
                    _scalar(
                        connection,
                        "SELECT COALESCE(SUM(debt_size_estimate), 0) FROM lcm_lifecycle_state",
                    )
                ),
            )
        finally:
            connection.close()
    except (OSError, RuntimeError, sqlite3.Error) as exc:
        return Snapshot(profile=profile, database_size_bytes=size, error=str(exc))


def _label_value(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _sample(name: str, value: float, **labels: object) -> str:
    label_text = ",".join(f'{key}="{_label_value(labels[key])}"' for key in sorted(labels))
    return f"{name}{{{label_text}}} {value}\n" if label_text else f"{name} {value}\n"


def render_metrics(snapshots: Iterable[Snapshot]) -> str:
    """Render Prometheus text exposition without paths, sessions, or message content."""
    lines = [
        "# HELP hermes_lcm_exporter_up Whether the LCM database was read successfully.\n",
        "# TYPE hermes_lcm_exporter_up gauge\n",
    ]
    metric_types = {
        "hermes_lcm_database_size_bytes": "gauge",
        "hermes_lcm_messages_total": "gauge",
        "hermes_lcm_message_tokens_estimate": "gauge",
        "hermes_lcm_messages_by_role": "gauge",
        "hermes_lcm_summary_nodes_total": "gauge",
        "hermes_lcm_summary_tokens_total": "gauge",
        "hermes_lcm_summary_source_tokens_total": "gauge",
        "hermes_lcm_summary_compression_ratio": "gauge",
        "hermes_lcm_summary_nodes_by_depth": "gauge",
        "hermes_lcm_latest_message_timestamp_seconds": "gauge",
        "hermes_lcm_latest_summary_timestamp_seconds": "gauge",
        "hermes_lcm_lifecycle_conversations_total": "gauge",
        "hermes_lcm_lifecycle_debt_conversations": "gauge",
        "hermes_lcm_lifecycle_debt_tokens": "gauge",
    }
    for metric, kind in metric_types.items():
        lines.append(f"# TYPE {metric} {kind}\n")

    for snapshot in snapshots:
        labels = {"profile": snapshot.profile}
        lines.append(_sample("hermes_lcm_exporter_up", int(snapshot.error is None), **labels))
        lines.append(
            _sample("hermes_lcm_database_size_bytes", snapshot.database_size_bytes, **labels)
        )
        if snapshot.error is not None:
            continue
        lines.extend(
            [
                _sample("hermes_lcm_messages_total", snapshot.messages_total, **labels),
                _sample("hermes_lcm_message_tokens_estimate", snapshot.message_tokens, **labels),
                _sample("hermes_lcm_summary_nodes_total", snapshot.summary_nodes_total, **labels),
                _sample("hermes_lcm_summary_tokens_total", snapshot.summary_tokens, **labels),
                _sample(
                    "hermes_lcm_summary_source_tokens_total",
                    snapshot.summary_source_tokens,
                    **labels,
                ),
                _sample(
                    "hermes_lcm_latest_message_timestamp_seconds",
                    snapshot.latest_message_timestamp,
                    **labels,
                ),
                _sample(
                    "hermes_lcm_latest_summary_timestamp_seconds",
                    snapshot.latest_summary_timestamp,
                    **labels,
                ),
                _sample(
                    "hermes_lcm_lifecycle_conversations_total",
                    snapshot.lifecycle_conversations,
                    **labels,
                ),
                _sample(
                    "hermes_lcm_lifecycle_debt_conversations",
                    snapshot.lifecycle_debt_conversations,
                    **labels,
                ),
                _sample(
                    "hermes_lcm_lifecycle_debt_tokens", snapshot.lifecycle_debt_tokens, **labels
                ),
            ]
        )
        if snapshot.summary_tokens:
            lines.append(
                _sample(
                    "hermes_lcm_summary_compression_ratio",
                    snapshot.summary_source_tokens / snapshot.summary_tokens,
                    **labels,
                )
            )
        for role, count in sorted(snapshot.messages_by_role.items()):
            lines.append(_sample("hermes_lcm_messages_by_role", count, role=role, **labels))
        for depth, count in sorted(snapshot.summary_nodes_by_depth.items()):
            lines.append(_sample("hermes_lcm_summary_nodes_by_depth", count, depth=depth, **labels))
    return "".join(lines)
