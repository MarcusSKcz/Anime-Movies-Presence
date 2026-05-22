from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import CONFIG_PATH, load_config, load_overrides, write_default_files
from .models import MpvEvent
from .overrides import OverrideMatcher
from .parsing import MediaParser
from .presence import DiscordPresence
from .privacy import should_ignore
from .providers import Resolver

log = logging.getLogger(__name__)


def setup_logging(cfg: dict[str, Any], verbose: bool = False) -> None:
    level_name = "DEBUG" if verbose else cfg.get("logging", {}).get("level", "INFO")
    logging.basicConfig(
        level=getattr(logging, str(level_name).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def mpv_event_from_dict(data: dict[str, Any]) -> MpvEvent:
    def fnum(x) -> float:
        try:
            return float(x or 0)
        except Exception:
            return 0.0

    return MpvEvent(
        action=str(data.get("action") or "update"),
        path=str(data.get("path") or ""),
        filename=str(data.get("filename") or Path(str(data.get("path") or "")).name),
        media_title=str(data.get("media_title") or data.get("title") or ""),
        duration=fnum(data.get("duration")),
        position=fnum(data.get("position")),
        pause=bool(data.get("pause", False)),
        playlist_pos=data.get("playlist_pos"),
        chapter=data.get("chapter"),
    )


class PresenceDaemon:
    def __init__(self, cfg: dict[str, Any], overrides: dict[str, Any]):
        self.cfg = cfg
        self.parser = MediaParser(cfg)
        self.override_matcher = OverrideMatcher(overrides, cfg.get("matching", {}).get("strip_terms", []))
        self.resolver = Resolver(cfg)
        self.discord = DiscordPresence(cfg)
        self.last_media_key: str | None = None
        self.last_resolved = None

    def handle_event(self, event: MpvEvent) -> None:
        if event.action in {"end", "shutdown", "stop"}:
            self.last_media_key = None
            self.last_resolved = None
            try:
                self.discord.clear()
            except Exception as exc:
                log.debug("Discord clear failed: %s", exc)
            return

        if not event.path:
            return
        if should_ignore(event.path, self.cfg):
            log.info("Ignored by privacy rules")
            try:
                self.discord.clear()
            except Exception as exc:
                log.debug("Discord clear failed: %s", exc)
            return

        key = event.path
        if key != self.last_media_key:
            parsed = self.parser.parse(event.path, event.filename)
            parsed = self.override_matcher.apply(parsed, event.path, event.filename)
            resolved = self.resolver.resolve(parsed)
            self.last_media_key = key
            self.last_resolved = resolved
            log.info(
                "Resolved: %s -> %s / %s / S%sE%s via %s",
                event.filename if self.cfg.get("privacy", {}).get("show_path_in_logs", False) else Path(event.filename).name,
                resolved.title,
                resolved.kind,
                resolved.season,
                resolved.episode,
                resolved.provider,
            )
        else:
            resolved = self.last_resolved

        if resolved:
            try:
                self.discord.update(resolved, event)
            except Exception as exc:
                log.warning("Discord update failed: %s", exc)


def make_handler(app: PresenceDaemon, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "mpv-presence/0.1"

        def _send(self, status: int, payload: dict[str, Any] | None = None) -> None:
            body = b"" if payload is None else json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self):
            if self.path.rstrip("/") in {"", "/", "/health"}:
                self._send(200, {"ok": True})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if token and self.headers.get("X-MPV-Presence-Token") != token:
                self._send(403, {"error": "bad token"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 65536:
                    self._send(413, {"error": "payload too large"})
                    return
                raw = self.rfile.read(length).decode("utf-8")
                data = json.loads(raw) if raw else {}
                event = mpv_event_from_dict(data)
                app.handle_event(event)
                self._send(204)
            except Exception as exc:
                log.exception("event handling failed")
                self._send(500, {"error": str(exc)})

        def log_message(self, fmt, *args):
            log.debug("http: " + fmt, *args)

    return Handler


def run_server(cfg: dict[str, Any], verbose: bool = False) -> None:
    setup_logging(cfg, verbose)
    overrides = load_overrides()
    app = PresenceDaemon(cfg, overrides)
    srv_cfg = cfg.get("server", {})
    host = srv_cfg.get("host", "127.0.0.1")
    port = int(srv_cfg.get("port", 47230))
    token = str(srv_cfg.get("token") or "")
    httpd = ThreadingHTTPServer((host, port), make_handler(app, token))

    def stop(*_):
        log.info("Stopping daemon")
        try:
            app.discord.clear()
        finally:
            httpd.shutdown()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("Listening on http://%s:%s", host, port)
    httpd.serve_forever()


def print_status(cfg: dict[str, Any]) -> None:
    server = cfg.get("server", {})
    print(f"Config: {CONFIG_PATH}")
    print(f"Server: http://{server.get('host')}:{server.get('port')}")
    print("Discord client id:", "set" if str(cfg.get("discord", {}).get("client_id", "")).isdigit() else "NOT SET")
    print("TMDB API key:", "set" if cfg.get("metadata", {}).get("tmdb_api_key") else "not set")
    print("RPDB API key:", "set" if cfg.get("metadata", {}).get("rpdb_api_key") else "not set")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MPV Discord Rich Presence daemon")
    parser.add_argument("--init", action="store_true", help="create default config files and exit")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="config file path")
    parser.add_argument("--status", action="store_true", help="print config status and exit")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    if args.init:
        write_default_files()
        print(f"Wrote config files under {CONFIG_PATH.parent}")
        return 0

    cfg = load_config(args.config)
    if args.status:
        print_status(cfg)
        return 0
    run_server(cfg, args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
