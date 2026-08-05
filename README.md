# Hermes LCM Prometheus Exporter

A dependency-light, read-only Prometheus exporter for one or more Hermes LCM SQLite databases. It is intentionally separate from `hermes-lcm`: no plugin code or database schema changes are required.

A Hermes profile is the agent identity in this deployment. Every metric has a bounded `profile` label. Database paths, session IDs, prompts, and message content are never emitted as labels or metric values.

## Metrics

- `hermes_lcm_messages_total`, `hermes_lcm_message_tokens_estimate`
- `hermes_lcm_messages_by_role`
- `hermes_lcm_summary_nodes_total`, `hermes_lcm_summary_tokens_total`, `hermes_lcm_summary_source_tokens_total`, `hermes_lcm_summary_compression_ratio`
- `hermes_lcm_summary_nodes_by_depth`
- `hermes_lcm_lifecycle_conversations_total`, `hermes_lcm_lifecycle_debt_conversations`, `hermes_lcm_lifecycle_debt_tokens`
- `hermes_lcm_latest_message_timestamp_seconds`, `hermes_lcm_latest_summary_timestamp_seconds`
- `hermes_lcm_database_size_bytes`, `hermes_lcm_exporter_up`

These are point-in-time database gauges. The current LCM schema does not retain per-compaction duration or pre/post token-event records, so the exporter does not fabricate them.

## Source configuration

The host layout is normally:

```text
$HERMES_HOME/profiles/<profile>/lcm.db
```

For example, the local source root is:

```text
/home/aimachine2/.hermes/profiles
```

Use a structured JSON configuration file. `profiles_roots` is an array so one exporter can scan several read-only mounted roots, provided every profile name is unique. A duplicate profile is rejected rather than silently dropping a database.

```json
{
  "profiles_roots": ["/lcm/profiles"],
  "databases": [
    {"profile": "exceptional_profile", "path": "/lcm/exceptional/lcm.db"}
  ]
}
```

`databases` is optional. Each explicit entry must have exactly `profile` and `path`.

## Run directly

```bash
uv run hermes-lcm-prometheus-exporter \
  --config examples/sources.json \
  --listen 127.0.0.1 --port 9476
```

For legacy local operation, `--profiles-root /path/to/profiles` remains available.

Endpoints:

- `/metrics` — Prometheus/OpenMetrics text exposition
- `/healthz` — reports 200 only when every configured database can be read

SQLite connections use `mode=ro`; the exporter never writes to LCM databases.

## Container image

Build the OCI/Docker-compatible image:

```bash
podman build -t hermes-lcm-prometheus-exporter:local .
```

Run it with the entire profile root mounted read-only. Mount the directory, rather than only `lcm.db`, so SQLite can consistently access any sibling WAL or shared-memory files.

```bash
podman run --rm \
  --network host --userns keep-id --user "$(id -u):$(id -g)" \
  --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  -v "$HERMES_HOME/profiles:/lcm/profiles:ro,Z" \
  -v "$PWD/examples/sources.json:/etc/hermes-lcm-exporter/sources.json:ro,Z" \
  hermes-lcm-prometheus-exporter:local \
  --config /etc/hermes-lcm-exporter/sources.json \
  --listen 127.0.0.1 --port 9476
```

The image runs as an unprivileged user. With host networking, bind to `127.0.0.1` so the endpoint stays local to the host.

## Prometheus

```yaml
- job_name: hermes_lcm
  static_configs:
    - targets: ["127.0.0.1:9476"]
```

One Prometheus target is sufficient; the exporter exposes every configured profile under its `profile` label.

## Development

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```
