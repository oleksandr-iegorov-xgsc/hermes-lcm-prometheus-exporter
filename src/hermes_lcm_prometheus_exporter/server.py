from __future__ import annotations

import argparse
from collections.abc import Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from .collector import Snapshot, collect_database, render_metrics


def discover_databases(profiles_roots: Sequence[Path], explicit: Sequence[str]) -> dict[str, Path]:
    databases: dict[str, Path] = {}
    for root in profiles_roots:
        if root.is_dir():
            for path in root.glob("*/lcm.db"):
                databases.setdefault(path.parent.name, path)
    for item in explicit:
        profile, separator, raw_path = item.partition("=")
        if not separator or not profile or not raw_path:
            raise ValueError("--database must be PROFILE=PATH")
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
        if self.path == "/metrics":
            body = render_metrics(snapshots).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        elif self.path == "/healthz":
            body = (
                "ok\n" if all(s.error is None for s in snapshots) else "database read failure\n"
            ).encode()
            self.send_response(
                HTTPStatus.OK
                if all(s.error is None for s in snapshots)
                else HTTPStatus.SERVICE_UNAVAILABLE
            )
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
    parser.add_argument("--profiles-root", type=Path, action="append", default=[])
    parser.add_argument("--database", action="append", default=[], metavar="PROFILE=PATH")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9476)
    args = parser.parse_args()
    databases = discover_databases(args.profiles_root, args.database)
    if not databases:
        parser.error("provide --profiles-root and/or --database PROFILE=PATH")
    handler = type("ConfiguredMetricsHandler", (MetricsHandler,), {"databases": databases})
    server = ThreadingHTTPServer((args.listen, args.port), handler)
    print(f"serving {len(databases)} LCM database(s) on http://{args.listen}:{args.port}/metrics")
    server.serve_forever()


if __name__ == "__main__":
    main()
