from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Optional

from .cache import JsonCache
from .http_util import ApiError, request_json
from .models import ParsedMedia, ResolvedMedia

log = logging.getLogger(__name__)

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/"


def _year_from_date(value: str | None) -> Optional[int]:
    if not value or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def _poster(path: str | None, size: str = "w780") -> Optional[str]:
    return f"{TMDB_IMAGE_BASE}{size}{path}" if path else None


def _tmdb_url(kind: str, tmdb_id: int | str | None, season: int | None = None, episode: int | None = None) -> Optional[str]:
    if not tmdb_id:
        return None
    if kind == "movie":
        return f"https://www.themoviedb.org/movie/{tmdb_id}"
    if kind in {"tv", "anime"}:
        if season and episode:
            return f"https://www.themoviedb.org/tv/{tmdb_id}/season/{season}/episode/{episode}"
        if season:
            return f"https://www.themoviedb.org/tv/{tmdb_id}/season/{season}"
        return f"https://www.themoviedb.org/tv/{tmdb_id}"
    return None


class AniListProvider:
    API = "https://graphql.anilist.co"

    def __init__(self, cfg: dict[str, Any], cache: JsonCache):
        self.cfg = cfg
        self.cache = cache
        self.timeout = cfg.get("metadata", {}).get("network_timeout_seconds", 8)

    def by_id(self, anilist_id: int, parsed: ParsedMedia) -> Optional[ResolvedMedia]:
        return self._query_media({"id": anilist_id}, parsed)

    def search(self, parsed: ParsedMedia) -> Optional[ResolvedMedia]:
        for title in parsed.search_titles or [parsed.title]:
            if not title:
                continue
            media = self._query_media({"search": title}, parsed)
            if media:
                return media
        return None

    def _query_media(self, variables: dict[str, Any], parsed: ParsedMedia) -> Optional[ResolvedMedia]:
        query = """
        query ($search: String, $id: Int) {
          Media(search: $search, id: $id, type: ANIME) {
            id
            idMal
            title { romaji english native userPreferred }
            coverImage { extraLarge large medium color }
            bannerImage
            siteUrl
            seasonYear
            episodes
            format
            description(asHtml: false)
            startDate { year }
          }
        }
        """
        key = "anilist:" + repr(variables)
        try:
            data = self.cache.get_or_set(key, lambda: request_json(
                self.API,
                method="POST",
                payload={"query": query, "variables": variables},
                timeout=self.timeout,
            ))
        except ApiError as exc:
            log.warning("AniList lookup failed: %s", exc)
            return None

        media = (data or {}).get("data", {}).get("Media")
        if not media:
            return None

        title_obj = media.get("title") or {}
        title = title_obj.get("english") or title_obj.get("userPreferred") or title_obj.get("romaji") or parsed.title
        original = title_obj.get("romaji") or title_obj.get("native")
        cover = media.get("coverImage") or {}
        year = media.get("seasonYear") or ((media.get("startDate") or {}).get("year")) or parsed.year
        ids = {"anilist": media.get("id"), "mal": media.get("idMal")}

        return ResolvedMedia(
            kind="anime",
            title=title,
            original_title=original if original != title else None,
            year=year,
            season=parsed.season,
            episode=parsed.episode,
            episode_title=parsed.episode_title,
            overview=media.get("description"),
            poster_url=cover.get("extraLarge") or cover.get("large") or cover.get("medium"),
            backdrop_url=media.get("bannerImage"),
            external_url=media.get("siteUrl"),
            provider="AniList",
            ids={k: v for k, v in ids.items() if v},
            parsed=parsed,
        )


class TMDBProvider:
    API = "https://api.themoviedb.org/3"

    def __init__(self, cfg: dict[str, Any], cache: JsonCache):
        self.cfg = cfg
        self.meta = cfg.get("metadata", {})
        self.api_key = self.meta.get("tmdb_api_key", "")
        self.cache = cache
        self.timeout = self.meta.get("network_timeout_seconds", 8)
        self.languages = self.meta.get("preferred_languages", ["sk-SK", "cs-CZ", "en-US"])
        self.include_adult = bool(self.meta.get("tmdb_adult", False))
        self.max_candidates = int(self.meta.get("max_candidates", 8))

    def enabled(self) -> bool:
        return bool(self.api_key)

    def by_id(self, kind: str, tmdb_id: int, parsed: ParsedMedia) -> Optional[ResolvedMedia]:
        if not self.enabled():
            return None
        if kind == "movie":
            item = self._get(f"/movie/{tmdb_id}", {"language": self.languages[0]})
            if not item:
                return None
            return self._resolved_movie(item, parsed)
        if kind in {"tv", "anime"}:
            item = self._get(f"/tv/{tmdb_id}", {"language": self.languages[0]})
            if not item:
                return None
            return self._resolved_tv(item, parsed, kind=kind)
        return None

    def search(self, parsed: ParsedMedia) -> Optional[ResolvedMedia]:
        if not self.enabled():
            return None
        search_kinds = []
        if parsed.kind == "movie":
            search_kinds = ["movie", "tv"]
        elif parsed.kind in {"tv", "anime"}:
            search_kinds = ["tv", "movie"]
        else:
            search_kinds = ["movie", "tv"]

        best: Optional[tuple[float, ResolvedMedia]] = None
        for title in parsed.search_titles or [parsed.title]:
            if not title:
                continue
            for kind in search_kinds:
                for lang in self.languages:
                    result = self._search_one(kind, title, parsed, lang)
                    if result:
                        score = self._score_result(result, parsed, title, kind, lang)
                        if not best or score > best[0]:
                            best = (score, result)
                            # Good enough, avoid noisy extra calls.
                            if score >= 92:
                                return result
        return best[1] if best else None

    def _headers(self) -> dict[str, str]:
        # v3 API key query auth is enough and easier for users.
        return {}

    def _get(self, endpoint: str, query: dict[str, Any]) -> Optional[dict[str, Any]]:
        q = dict(query)
        q["api_key"] = self.api_key
        key = "tmdb:get:" + endpoint + ":" + repr(sorted(q.items()))
        try:
            return self.cache.get_or_set(key, lambda: request_json(self.API + endpoint, query=q, headers=self._headers(), timeout=self.timeout))
        except ApiError as exc:
            log.warning("TMDB get failed: %s", exc)
            return None

    def _search_one(self, kind: str, title: str, parsed: ParsedMedia, language: str) -> Optional[ResolvedMedia]:
        endpoint = "/search/movie" if kind == "movie" else "/search/tv"
        query: dict[str, Any] = {
            "api_key": self.api_key,
            "query": title,
            "language": language,
            "include_adult": str(self.include_adult).lower(),
        }
        if parsed.year:
            if kind == "movie":
                query["year"] = parsed.year
                query["primary_release_year"] = parsed.year
            else:
                query["first_air_date_year"] = parsed.year

        key = "tmdb:search:" + kind + ":" + repr(sorted(query.items()))
        try:
            data = self.cache.get_or_set(key, lambda: request_json(self.API + endpoint, query=query, timeout=self.timeout))
        except ApiError as exc:
            log.warning("TMDB search failed: %s", exc)
            return None

        results = (data or {}).get("results") or []
        results = [r for r in results if r.get("poster_path") or r.get("backdrop_path") or r.get("popularity", 0) > 0]
        if not results:
            return None
        results = results[: self.max_candidates]
        results.sort(key=lambda r: self._raw_score(r, parsed, kind), reverse=True)
        item = results[0]
        return self._resolved_movie(item, parsed) if kind == "movie" else self._resolved_tv(item, parsed, kind="tv" if parsed.kind != "anime" else "anime")

    def _raw_score(self, item: dict[str, Any], parsed: ParsedMedia, kind: str) -> float:
        score = float(item.get("popularity") or 0)
        if item.get("poster_path"):
            score += 10
        if parsed.year:
            item_year = _year_from_date(item.get("release_date") or item.get("first_air_date"))
            if item_year == parsed.year:
                score += 30
            elif item_year and abs(item_year - parsed.year) <= 1:
                score += 10
        # Prefer same guessed kind.
        if parsed.kind == kind or (parsed.kind == "anime" and kind == "tv"):
            score += 15
        return score

    def _score_result(self, resolved: ResolvedMedia, parsed: ParsedMedia, title: str, kind: str, lang: str) -> float:
        score = 50.0
        if resolved.poster_url:
            score += 10
        if resolved.year and parsed.year:
            score += 25 if resolved.year == parsed.year else max(0, 12 - abs(resolved.year - parsed.year) * 3)
        if parsed.kind == kind or (parsed.kind == "anime" and kind == "tv"):
            score += 10
        if lang == self.languages[0]:
            score += 3
        if resolved.title.lower() == title.lower():
            score += 20
        return score

    def _resolved_movie(self, item: dict[str, Any], parsed: ParsedMedia) -> ResolvedMedia:
        year = _year_from_date(item.get("release_date")) or parsed.year
        tmdb_id = item.get("id")
        return ResolvedMedia(
            kind="movie",
            title=item.get("title") or item.get("original_title") or parsed.title,
            original_title=item.get("original_title"),
            year=year,
            season=None,
            episode=None,
            overview=item.get("overview"),
            poster_url=_poster(item.get("poster_path")),
            backdrop_url=_poster(item.get("backdrop_path"), "w1280"),
            external_url=_tmdb_url("movie", tmdb_id),
            provider="TMDB",
            ids={"tmdb": tmdb_id} if tmdb_id else {},
            parsed=parsed,
        )

    def _resolved_tv(self, item: dict[str, Any], parsed: ParsedMedia, *, kind: str = "tv") -> ResolvedMedia:
        year = _year_from_date(item.get("first_air_date")) or parsed.year
        tmdb_id = item.get("id")
        return ResolvedMedia(
            kind=kind,
            title=item.get("name") or item.get("original_name") or parsed.title,
            original_title=item.get("original_name"),
            year=year,
            season=parsed.season,
            episode=parsed.episode,
            episode_title=parsed.episode_title,
            overview=item.get("overview"),
            poster_url=_poster(item.get("poster_path")),
            backdrop_url=_poster(item.get("backdrop_path"), "w1280"),
            external_url=_tmdb_url("tv", tmdb_id, parsed.season, parsed.episode),
            provider="TMDB",
            ids={"tmdb": tmdb_id} if tmdb_id else {},
            parsed=parsed,
        )


class RPDBProvider:
    BASE = "https://api.ratingposterdb.com"

    def __init__(self, cfg: dict[str, Any]):
        self.meta = cfg.get("metadata", {})
        self.api_key = self.meta.get("rpdb_api_key", "")
        self.style = self.meta.get("rpdb_style", "poster-default")

    def enabled(self) -> bool:
        return bool(self.api_key)

    def poster_for(self, media: ResolvedMedia) -> Optional[str]:
        if not self.enabled():
            return None
        tmdb_id = media.ids.get("tmdb")
        if not tmdb_id:
            return None
        if media.kind == "movie":
            rpdb_id = f"movie-{tmdb_id}"
        else:
            # RPDB supports series-level posters; episode posters are not worth relying on for Discord.
            rpdb_id = f"series-{tmdb_id}"
        safe_style = urllib.parse.quote(str(self.style), safe="")
        return f"{self.BASE}/{urllib.parse.quote(self.api_key)}/tmdb/{safe_style}/{rpdb_id}.jpg?fallback=true"


class Resolver:
    def __init__(self, cfg: dict[str, Any]):
        ttl = int(cfg.get("metadata", {}).get("cache_ttl_days", 30))
        self.cfg = cfg
        self.cache = JsonCache("api", ttl)
        self.anilist = AniListProvider(cfg, self.cache)
        self.tmdb = TMDBProvider(cfg, self.cache)
        self.rpdb = RPDBProvider(cfg)

    def resolve(self, parsed: ParsedMedia) -> ResolvedMedia:
        forced = self._resolve_forced_id(parsed)
        if forced:
            return self._with_poster(forced)

        result: Optional[ResolvedMedia] = None
        if parsed.kind == "anime" and self.cfg.get("metadata", {}).get("prefer_anilist_for_anime", True):
            result = self.anilist.search(parsed) or self.tmdb.search(parsed)
        elif parsed.kind in {"movie", "tv"}:
            result = self.tmdb.search(parsed)
        elif self.cfg.get("matching", {}).get("unknown_to_tmdb", True):
            result = self.tmdb.search(parsed)

        if not result:
            result = ResolvedMedia(kind=parsed.kind, title=parsed.title, year=parsed.year, season=parsed.season, episode=parsed.episode, episode_title=parsed.episode_title, provider="filename", parsed=parsed)
        return self._with_poster(result)

    def _resolve_forced_id(self, parsed: ParsedMedia) -> Optional[ResolvedMedia]:
        ids = parsed.ids or {}
        if ids.get("anilist"):
            return self.anilist.by_id(int(ids["anilist"]), parsed)
        if ids.get("tmdb"):
            kind = parsed.kind if parsed.kind in {"movie", "tv", "anime"} else "movie"
            return self.tmdb.by_id(kind, int(ids["tmdb"]), parsed)
        return None

    def _with_poster(self, media: ResolvedMedia) -> ResolvedMedia:
        priority = self.cfg.get("metadata", {}).get("poster_priority", ["rpdb", "metadata"])
        for source in priority:
            if source == "rpdb":
                rpdb = self.rpdb.poster_for(media)
                if rpdb:
                    media.poster_url = rpdb
                    media.provider = f"{media.provider}+RPDB"
                    return media
            elif source == "metadata" and media.poster_url:
                return media
        return media
