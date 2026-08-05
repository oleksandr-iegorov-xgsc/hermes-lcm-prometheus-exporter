from __future__ import annotations

import argparse
from collections.abc import Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from .collector import Snapshot, collect_database, render_metrics
from .config import ConfigurationError, discover_profiles, load_database_config


def discover_databases(profiles_roots: Sequence[Path], explicit: Sequence[str]) -> dict[str, Path]:
    """Compatibility path for CLI flags; JSON config is preferred for containers."""
    databases = discover_profiles(list(profiles_roots))
    for item in explicit:
        profile, separator, raw_path = item.partition("=")
        if not separator or not profile or not raw_path:
            raise ConfigurationError("--database must be PROFILE=PATH")
        if profile in databases:
            raise ConfigurationError(
                f"duplicate profile {profile!r}; each Hermes profile is one agent identity"
            )
        databases[profile] = Path(raw_path).expanduser()
    return databases


class MetricsHandler(BaseHTTPRequestHandler):
    databases: ClassVar[dict[str, Path]] = {}

    def log_message(self, format: str, *args: object) -> None:
        return

    def _snapshots(self) -> list[Snapshot]:
        return [collect_database(path, profile) for profile, path in sorted(self.databases.items())]

    def do_GET(self) -> None:
        snapshots = self._snapshots()
        healthy = all(snapshot.error is None for snapshot in snapshots)
        if self.path == "/metrics":
            body = render_metrics(snapshots).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        elif self.path == "/healthz":
            body = ("ok\n" if healthy else "database read failure\n").encode()
            self.send_response(HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        else:
            body = b"not found\n"
            self.send_response(HTTPStatus.NOT_FOUND)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only Prometheus exporter for Hermes LCM SQLite databases"
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--config", type=Path, help="JSON profile database configuration")
    source_group.add_argument("--profiles-root", type=Path, action="append", default=[])
    parser.add_argument("--database", action="append", default=[], metavar="PROFILE=PATH")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9476)
    args = parser.parse_args()
    try:
        databases = (
            load_database_config(args.config)
            if args.config
            else discover_databases(args.profiles_root, args.database)
        )
    except ConfigurationError as exc:
        parser.error(str(exc))
    if not databases:
        parser.error("no LCM databases were discovered")
    handler = type("ConfiguredMetricsHandler", (MetricsHandler,), {"databases": databases})
    server = ThreadingHTTPServer((args.listen, args.port), handler)
    print(f"serving {len(databases)} LCM database(s) on http://{args.listen}:{args.port}/metrics")
    server.serve_forever()


if __name__ == "__main__":
    main()
