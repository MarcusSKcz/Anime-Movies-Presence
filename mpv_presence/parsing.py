from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Optional

from .models import ParsedMedia

log = logging.getLogger(__name__)

VIDEO_EXTS = {".mkv", ".mp4", ".webm", ".avi", ".mov", ".m4v", ".ts", ".wmv", ".flv"}


def _first_number(items: Any) -> Optional[int]:
    if items is None:
        return None
    if isinstance(items, (int, float)):
        return int(items)
    if isinstance(items, str):
        m = re.search(r"\d+", items)
        return int(m.group(0)) if m else None
    if isinstance(items, dict):
        for key in ("number", "start", "episode", "season", "year"):
            if key in items:
                n = _first_number(items[key])
                if n is not None:
                    return n
    if isinstance(items, list) and items:
        return _first_number(items[0])
    return None


def _episode_end(items: Any) -> Optional[int]:
    if isinstance(items, dict):
        return _first_number(items.get("end"))
    if isinstance(items, list) and items:
        return _episode_end(items[0])
    return None


def _first_str(items: Any, *keys: str) -> Optional[str]:
    if items is None:
        return None
    if isinstance(items, str):
        return items
    if isinstance(items, dict):
        for key in keys:
            val = items.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        for key in keys:
            val = _first_str(items.get(key), *keys)
            if val:
                return val
    if isinstance(items, list):
        for item in items:
            val = _first_str(item, *keys)
            if val:
                return val
    return None


def strip_extension(filename: str) -> str:
    p = Path(filename)
    return p.stem if p.suffix.lower() in VIDEO_EXTS else filename


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ._-—–")


def remove_diacritics(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def clean_query_title(text: str, strip_terms: list[str] | None = None) -> str:
    strip_terms = strip_terms or []
    s = strip_extension(text)
    s = s.replace("_", " ").replace(".", " ")

    # Keep a possible title inside normal parentheses, but drop checksum/codec/resolution groups.
    s = re.sub(r"\[[^\]]*(?:1080|720|2160|x264|x265|HEVC|AV1|AAC|FLAC|[A-Fa-f0-9]{8})[^\]]*\]", " ", s)
    s = re.sub(r"\[[^\]]{1,24}\]", " ", s)  # usually fansub/release tags
    s = re.sub(r"\([^)]*(?:1080|720|2160|x264|x265|HEVC|AV1|AAC|FLAC|WEB|BluRay|BD)[^)]*\)", " ", s, flags=re.I)

    s = re.sub(r"\bS\d{1,2}E\d{1,4}\b", " ", s, flags=re.I)
    s = re.sub(r"\bSeason\s*\d{1,2}\b", " ", s, flags=re.I)
    s = re.sub(r"\b(?:Episode|Ep)\s*\d{1,4}\b", " ", s, flags=re.I)
    s = re.sub(r"\s+-\s+\d{1,4}(?:v\d+)?(?:\s|$).*", " ", s)
    s = re.sub(r"\b(?:19|20)\d{2}\b", " ", s)

    for term in strip_terms:
        if not term:
            continue
        s = re.sub(rf"\b{re.escape(term)}\b", " ", s, flags=re.I)

    s = re.sub(r"\b(SK|CZ|EN|JP|JPN|ENG|SUB|DUB|DAB|DABING|TITULKY)\b", " ", s, flags=re.I)
    return normalize_spaces(s)


def find_year(text: str) -> Optional[int]:
    years = [int(m.group(0)) for m in re.finditer(r"\b(19\d{2}|20\d{2})\b", text)]
    years = [y for y in years if 1900 <= y <= 2099]
    return years[-1] if years else None


def folder_season(path: str) -> Optional[int]:
    p = str(Path(path).parent)
    patterns = [
        r"(?:^|[/\\])Season\s*(\d{1,2})(?:[/\\]|$)",
        r"(?:^|[/\\])S(\d{1,2})(?:[/\\]|$)",
        r"(?:^|[/\\])(\d{1,2})(?:st|nd|rd|th)?\s+Season(?:[/\\]|$)",
        r"(?:^|[/\\])Part\s*(\d{1,2})(?:[/\\]|$)",
    ]
    for pat in patterns:
        m = re.search(pat, p, re.I)
        if m:
            return int(m.group(1))
    return None


def path_contains(path: str, keywords: list[str]) -> bool:
    low = remove_diacritics(path.lower())
    return any(remove_diacritics(k.lower()) in low for k in keywords if k)


class MediaParser:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.matching = config.get("matching", {})
        self.strip_terms = self.matching.get("strip_terms", [])

    def parse(self, path: str, filename: str = "") -> ParsedMedia:
        filename = filename or Path(path).name
        full = f"{path} {filename}"

        guess = self._parse_guessit(path, filename)
        anime = self._parse_aniparse(path, filename)
        regex = self._parse_regex(path, filename)

        candidates = [p for p in [anime, guess, regex] if p and p.title]
        if not candidates:
            title = clean_query_title(filename, self.strip_terms) or clean_query_title(Path(path).parent.name, self.strip_terms)
            return ParsedMedia(kind="unknown", title=title, raw_title=filename, year=find_year(full), parser="fallback", confidence=0.2, search_titles=[title])

        # Strongly prefer anime parser when the path/release looks anime-ish or it found episode syntax.
        animeish = self._looks_anime(path, filename) or (anime and anime.confidence >= self.matching.get("anime_confidence_threshold", 0.55))
        if animeish and anime and anime.title:
            chosen = anime
        else:
            # GuessIt is usually safer for movies/Western TV, but keep anime if it is clearly high confidence.
            if guess and guess.kind in {"movie", "tv"} and not self._looks_anime(path, filename):
                chosen = guess
            else:
                chosen = max(candidates, key=lambda c: c.confidence)

        # Folder season can rescue episode-only files in Season folders.
        if chosen.season is None and self.matching.get("season_folder_patterns", True):
            chosen.season = folder_season(path)

        chosen.year = chosen.year or find_year(full)
        chosen.search_titles = self._make_search_titles(chosen, path, filename)
        return chosen

    def _looks_anime(self, path: str, filename: str) -> bool:
        full = f"{path} {filename}"
        if path_contains(full, self.matching.get("anime_path_keywords", [])):
            return True
        if re.search(r"^\[[^\]]+\]", filename):
            return True
        if re.search(r"\s-\s\d{1,4}(?:v\d+)?(?:\s|$|\[|\()", filename):
            return True
        if re.search(r"\b(SubsPlease|Erai[- ]Raws|Judas|EMBER|Anime Time|NCED|NCOP)\b", filename, re.I):
            return True
        return False

    def _make_search_titles(self, parsed: ParsedMedia, path: str, filename: str) -> list[str]:
        titles: list[str] = []
        for t in [parsed.title, parsed.raw_title, Path(path).parent.name if self.matching.get("use_folder_name", True) else "", clean_query_title(filename, self.strip_terms)]:
            t = normalize_spaces(str(t or ""))
            if t and t not in titles:
                titles.append(t)
        # For Slovak/Czech titles with diacritics, also try ASCII fallback.
        for t in list(titles):
            ascii_t = normalize_spaces(remove_diacritics(t))
            if ascii_t and ascii_t != t and ascii_t not in titles:
                titles.append(ascii_t)
        return titles[:6]

    def _parse_aniparse(self, path: str, filename: str) -> Optional[ParsedMedia]:
        try:
            import aniparse  # type: ignore
        except Exception:
            return None

        try:
            data = aniparse.parse(filename, path=path) or {}
        except TypeError:
            try:
                data = aniparse.parse(filename) or {}
            except Exception as exc:
                log.debug("aniparse failed: %s", exc)
                return None
        except Exception as exc:
            log.debug("aniparse failed: %s", exc)
            return None

        series = data.get("series") or []
        if not series:
            return None
        s = series[0]
        title = s.get("title") if isinstance(s, dict) else None
        if not title:
            return None

        ep = s.get("episode") if isinstance(s, dict) else None
        season = s.get("season") if isinstance(s, dict) else None
        year = s.get("year") if isinstance(s, dict) else None
        kind = "anime"
        anime_type = _first_str(s.get("type") if isinstance(s, dict) else None, "type")
        if anime_type and anime_type.lower() == "movie":
            kind = "anime"

        release_group = _first_str(data.get("release_group"), "name", "title")
        episode_title = _first_str(ep, "title")
        parsed = ParsedMedia(
            kind=kind,
            title=normalize_spaces(title),
            raw_title=filename,
            year=_first_number(year),
            season=_first_number(season),
            episode=_first_number(ep),
            episode_end=_episode_end(ep),
            episode_title=episode_title,
            release_group=release_group,
            confidence=0.72 if _first_number(ep) is not None else 0.55,
            parser="aniparse",
            extra={"aniparse": data},
        )
        return parsed

    def _parse_guessit(self, path: str, filename: str) -> Optional[ParsedMedia]:
        try:
            from guessit import guessit  # type: ignore
        except Exception:
            return None
        try:
            data = dict(guessit(filename))
        except Exception as exc:
            log.debug("guessit failed: %s", exc)
            return None

        title = data.get("title")
        if isinstance(title, list):
            title = " ".join(str(x) for x in title)
        if not title:
            return None

        gtype = str(data.get("type") or "").lower()
        if gtype == "episode":
            kind = "tv"
        elif gtype == "movie":
            kind = "movie"
        else:
            kind = "unknown"

        # Path/fansub hints can upgrade GuessIt output to anime.
        if self._looks_anime(path, filename):
            kind = "anime"

        parsed = ParsedMedia(
            kind=kind,
            title=normalize_spaces(str(title)),
            raw_title=filename,
            year=_first_number(data.get("year")),
            season=_first_number(data.get("season")),
            episode=_first_number(data.get("episode")),
            episode_title=_first_str(data.get("episode_title"), "title"),
            release_group=_first_str(data.get("release_group"), "name", "title"),
            confidence=0.68 if kind in {"movie", "tv"} else 0.45,
            parser="guessit",
            extra={"guessit": data},
        )
        return parsed

    def _parse_regex(self, path: str, filename: str) -> Optional[ParsedMedia]:
        raw = strip_extension(filename)
        title = clean_query_title(filename, self.strip_terms)
        season = None
        episode = None
        episode_end = None
        episode_title = None

        m = re.search(r"\bS(\d{1,2})E(\d{1,4})(?:\s*[-–—]\s*([^\[\]()]+))?", raw, re.I)
        if m:
            season = int(m.group(1))
            episode = int(m.group(2))
            episode_title = normalize_spaces(m.group(3) or "") or None
            title = normalize_spaces(raw[:m.start()]) or title
            kind = "anime" if self._looks_anime(path, filename) else "tv"
        else:
            # Anime convention: [Group] Title - 04v2 - Episode Name [1080p]
            m = re.search(r"^(?:\[[^\]]+\]\s*)?(.*?)\s+-\s+(\d{1,4})(?:v\d+)?(?:\s*[-–—]\s*([^\[\]()]+))?", raw)
            if m:
                title = normalize_spaces(m.group(1))
                episode = int(m.group(2))
                episode_title = normalize_spaces(m.group(3) or "") or None
                kind = "anime"
            else:
                m = re.search(r"\b(?:Ep(?:isode)?\.?\s*)(\d{1,4})\b", raw, re.I)
                if m:
                    episode = int(m.group(1))
                    kind = "anime" if self._looks_anime(path, filename) else "tv"
                else:
                    kind = "movie" if path_contains(path, self.matching.get("movie_path_keywords", [])) else "unknown"

        if not title:
            return None

        return ParsedMedia(
            kind=kind,
            title=title,
            raw_title=filename,
            year=find_year(raw),
            season=season,
            episode=episode,
            episode_end=episode_end,
            episode_title=episode_title,
            confidence=0.6 if episode is not None else 0.35,
            parser="regex",
        )
