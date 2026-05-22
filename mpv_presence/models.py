from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class MpvEvent:
    action: str
    path: str = ""
    filename: str = ""
    media_title: str = ""
    duration: float = 0.0
    position: float = 0.0
    pause: bool = False
    playlist_pos: Optional[int] = None
    chapter: Optional[str] = None


@dataclass(slots=True)
class ParsedMedia:
    kind: str = "unknown"  # anime, movie, tv, unknown
    title: str = ""
    raw_title: str = ""
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_end: Optional[int] = None
    episode_title: Optional[str] = None
    release_group: Optional[str] = None
    confidence: float = 0.0
    parser: str = "fallback"
    search_titles: list[str] = field(default_factory=list)
    ids: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResolvedMedia:
    kind: str
    title: str
    original_title: Optional[str] = None
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_title: Optional[str] = None
    overview: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    external_url: Optional[str] = None
    provider: str = "filename"
    ids: dict[str, Any] = field(default_factory=dict)
    parsed: Optional[ParsedMedia] = None

    @property
    def display_title(self) -> str:
        return self.title or (self.parsed.title if self.parsed else "mpv") or "mpv"
