# Hermes LCM Prometheus Exporter

A dependency-light, read-only Prometheus exporter for one or more Hermes LCM SQLite databases. It is intentionally separate from `hermes-lcm`: no plugin code or database schema changes are required.

The exporter discovers each `lcm.db` below a profiles directory and assigns its parent directory name as the bounded `profile` label. It never emits database paths, session IDs, prompts, or message content as labels or metric values.

## Metrics

- `hermes_lcm_messages_total`, `hermes_lcm_message_tokens_estimate`
- `hermes_lcm_messages_by_role`
- `hermes_lcm_summary_nodes_total`, `hermes_lcm_summary_tokens_total`, `hermes_lcm_summary_source_tokens_total`, `hermes_lcm_summary_compression_ratio`
- `hermes_lcm_summary_nodes_by_depth`
- `hermes_lcm_lifecycle_conversations_total`, `hermes_lcm_lifecycle_debt_conversations`, `hermes_lcm_lifecycle_debt_tokens`
- `hermes_lcm_latest_message_timestamp_seconds`, `hermes_lcm_latest_summary_timestamp_seconds`
- `hermes_lcm_database_size_bytes`, `hermes_lcm_exporter_up`

These are point-in-time database gauges. The current LCM schema does not retain per-compaction duration or pre/post token-event records, so the exporter does not fabricate them.

## Run

```bash
uv run hermes-lcm-prometheus-exporter \
  --profiles-root /home/aimachine2/.hermes/profiles \
  --listen 127.0.0.1 --port 9476
```

Endpoints:

- `/metrics` — Prometheus/OpenMetrics text exposition
- `/healthz` — reports 200 only when every configured database was read successfully

The SQLite connections use `mode=ro`; the exporter never writes to LCM databases.

## Prometheus

```yaml
- job_name: hermes-lcm
  static_configs:
    - targets: ["127.0.0.1:9476"]
```

## Development

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```
