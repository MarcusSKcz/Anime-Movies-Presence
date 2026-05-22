from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .models import MpvEvent, ResolvedMedia

log = logging.getLogger(__name__)


def _trim(text: str, n: int = 128) -> str:
    text = str(text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


class DiscordPresence:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.discord = cfg.get("discord", {})
        self.rpc = None
        self.last_payload: dict[str, Any] | None = None
        self.last_connect_attempt = 0.0

    def _connect(self):
        client_id = str(self.discord.get("client_id") or "").strip()
        if not client_id or client_id == "PUT_DISCORD_CLIENT_ID_HERE":
            raise RuntimeError("Discord client_id is not configured in ~/.config/mpv-presence/config.json")

        now = time.time()
        if self.rpc is not None:
            return self.rpc

        if now - self.last_connect_attempt < 5:
            raise RuntimeError("Skipping Discord reconnect cooldown")
        self.last_connect_attempt = now

        from pypresence import Presence  # type: ignore
        rpc = Presence(client_id)
        try:
            rpc.connect()
        except Exception:
            self.rpc = None
            raise

        self.rpc = rpc
        log.info("Connected to Discord RPC")
        return self.rpc

    def clear(self) -> None:
        try:
            rpc = self._connect()
            rpc.clear()
            self.last_payload = None
            log.info("Cleared Discord presence")
        except Exception as exc:
            log.debug("Could not clear Discord presence: %s", exc)

    def update(self, media: ResolvedMedia, event: MpvEvent) -> None:
        rpc = self._connect()
        payload = self._payload(media, event)
        # Avoid sending identical payloads every 15 seconds. Timestamps are allowed to differ only when not paused.
        comparable = dict(payload)
        comparable.pop("start", None)
        comparable.pop("end", None)
        if self.last_payload:
            old = dict(self.last_payload)
            old.pop("start", None)
            old.pop("end", None)
            if old == comparable and not event.pause:
                return
        import inspect
        sig = inspect.signature(rpc.update)
        if not any(param.kind == param.VAR_KEYWORD for param in sig.parameters.values()):
            payload = {k: v for k, v in payload.items() if k in sig.parameters}
        try:
            rpc.update(**payload)
        except Exception:
            self.rpc = None
            raise
        self.last_payload = payload
        log.info("Presence: %s — %s", payload.get("details"), payload.get("state"))

    def _payload(self, media: ResolvedMedia, event: MpvEvent) -> dict[str, Any]:
        details = self._details(media)
        state = self._state(media)
        if event.pause and self.discord.get("show_paused", True):
            state = self.cfg.get("presence_text", {}).get("paused_prefix", "Paused • ") + state

        payload: dict[str, Any] = {
            "details": _trim(details),
            "state": _trim(state),
            "large_text": _trim(media.provider or "mpv"),
            "instance": False,
        }

        # Optional enum support; older pypresence versions may not have it.
        if str(self.discord.get("activity_type", "watching")).lower() == "watching":
            try:
                from pypresence.types import ActivityType  # type: ignore
                payload["activity_type"] = ActivityType.WATCHING
            except Exception:
                pass

        try:
            from pypresence.types import StatusDisplayType  # type: ignore
            status = str(self.discord.get("status_display", "details")).lower()
            if status == "state":
                payload["status_display_type"] = StatusDisplayType.STATE
            elif status == "details":
                payload["status_display_type"] = StatusDisplayType.DETAILS
        except Exception:
            pass

        image = media.poster_url or self.discord.get("large_image_fallback")
        if image:
            payload["large_image"] = image
        small = self.discord.get("small_image")
        if small:
            payload["small_image"] = small
            payload["small_text"] = self.discord.get("small_text") or "mpv"

        if media.external_url:
            payload["large_url"] = media.external_url
            payload["details_url"] = media.external_url
            if self.discord.get("show_buttons", True):
                label = "Open on AniList" if "AniList" in media.provider else "Open on TMDB"
                payload["buttons"] = [{"label": label, "url": media.external_url}]

        if self.discord.get("show_timestamps", True) and not event.pause and event.duration > 0:
            pos = max(0.0, float(event.position or 0.0))
            dur = max(0.0, float(event.duration or 0.0))
            now = int(time.time())
            # Discord timestamps are the cleanest progress indicator.
            payload["start"] = now - int(pos)
            if dur > pos:
                payload["end"] = now + int(dur - pos)

        return payload

    def _details(self, media: ResolvedMedia) -> str:
        if media.title:
            return media.title
        if self.cfg.get("privacy", {}).get("show_filename_when_unmatched", False) and media.parsed:
            return media.parsed.raw_title
        return self.cfg.get("presence_text", {}).get("unknown_details", "Watching via mpv")

    def _state(self, media: ResolvedMedia) -> str:
        text_cfg = self.cfg.get("presence_text", {})
        year_suffix = f" • {media.year}" if media.year else ""
        if media.kind == "anime":
            if media.season is not None and media.episode is not None:
                base = text_cfg.get("anime_state", "Season {season} • Episode {episode}").format(season=media.season, episode=media.episode)
            elif media.episode is not None:
                base = text_cfg.get("anime_state_no_season", "Episode {episode}").format(episode=media.episode)
            else:
                base = "Anime" + year_suffix
        elif media.kind == "tv":
            if media.season is not None and media.episode is not None:
                base = text_cfg.get("tv_state", "Season {season} • Episode {episode}").format(season=media.season, episode=media.episode)
            elif media.episode is not None:
                base = f"Episode {media.episode}"
            else:
                base = "TV Series" + year_suffix
        elif media.kind == "movie":
            base = text_cfg.get("movie_state", "Movie{year_suffix}").format(year_suffix=year_suffix)
        else:
            base = text_cfg.get("unknown_state", "Unknown media")
        if media.episode_title and media.episode is not None:
            base += f" • {media.episode_title}"
        return base
