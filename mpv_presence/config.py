from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_NAME = "mpv-presence"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / APP_NAME
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_NAME
CONFIG_PATH = CONFIG_DIR / "config.json"
OVERRIDES_PATH = CONFIG_DIR / "overrides.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "server": {
        "host": "127.0.0.1",
        "port": 47230,
        "token": "",
    },
    "discord": {
        "client_id": "PUT_DISCORD_CLIENT_ID_HERE",
        "activity_type": "watching",
        "large_image_fallback": "",
        "small_image": "",
        "small_text": "mpv",
        "show_buttons": True,
        "show_timestamps": True,
        "show_paused": True,
        "status_display": "details"
    },
    "metadata": {
        "tmdb_api_key": "",
        "rpdb_api_key": "",
        "preferred_languages": ["sk-SK", "cs-CZ", "en-US"],
        "prefer_anilist_for_anime": True,
        "tmdb_adult": False,
        "poster_priority": ["rpdb", "metadata"],
        "rpdb_style": "poster-default",
        "cache_ttl_days": 30,
        "network_timeout_seconds": 8,
        "max_candidates": 8
    },
    "matching": {
        "anime_path_keywords": ["anime", "ani", "subsplease", "erai-raws"],
        "movie_path_keywords": ["movies", "films", "filmy", "movie"],
        "tv_path_keywords": ["series", "shows", "serialy", "tv"],
        "use_folder_name": True,
        "anime_confidence_threshold": 0.55,
        "unknown_to_tmdb": True,
        "season_folder_patterns": True,
        "strip_terms": [
            "1080p", "720p", "2160p", "480p", "4k", "uhd", "hdr", "hdr10", "dv", "dolby vision",
            "bluray", "blu-ray", "bdrip", "web-dl", "webrip", "web", "hdtv", "remux",
            "x264", "x265", "h264", "h265", "hevc", "av1", "aac", "ac3", "eac3", "dts", "flac",
            "10bit", "8bit", "multi", "dual audio", "sk dabing", "cz dabing", "dabing", "titulky"
        ]
    },
    "privacy": {
        "enabled": True,
        "ignore_paths": [],
        "ignore_patterns": [
            "private", "nsfw", "hentai", "18+"
        ],
        "show_filename_when_unmatched": False,
        "show_path_in_logs": False
    },
    "presence_text": {
        "anime_state": "Season {season} • Episode {episode}",
        "anime_state_no_season": "Episode {episode}",
        "movie_state": "Movie{year_suffix}",
        "tv_state": "Season {season} • Episode {episode}",
        "paused_prefix": "Paused • ",
        "unknown_details": "Watching via mpv",
        "unknown_state": "Unknown media"
    },
    "logging": {
        "level": "INFO"
    }
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def write_default_files() -> None:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False) + "\n")
    if not OVERRIDES_PATH.exists():
        OVERRIDES_PATH.write_text(json.dumps({"overrides": []}, indent=2, ensure_ascii=False) + "\n")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    write_default_files()
    user_cfg = json.loads(path.read_text()) if path.exists() else {}
    return deep_merge(DEFAULT_CONFIG, user_cfg)


def load_overrides(path: Path = OVERRIDES_PATH) -> dict[str, Any]:
    write_default_files()
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"overrides": []}
