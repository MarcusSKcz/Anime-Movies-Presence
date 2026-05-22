from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any, Optional

from .models import ParsedMedia
from .parsing import clean_query_title, normalize_spaces


class OverrideMatcher:
    def __init__(self, data: dict[str, Any], strip_terms: list[str] | None = None):
        self.overrides = data.get("overrides", []) if isinstance(data, dict) else []
        self.strip_terms = strip_terms or []

    def apply(self, parsed: ParsedMedia, path: str, filename: str) -> ParsedMedia:
        item = self.match(path, filename, parsed)
        if not item:
            return parsed

        out = ParsedMedia(**{field: getattr(parsed, field) for field in parsed.__dataclass_fields__})
        if item.get("type"):
            out.kind = str(item["type"])
        if item.get("title"):
            out.title = normalize_spaces(str(item["title"]))
        if item.get("search_title"):
            st = normalize_spaces(str(item["search_title"]))
            out.search_titles = [st] + [t for t in out.search_titles if t != st]
        if item.get("year"):
            out.year = int(item["year"])
        if item.get("season") is not None:
            out.season = int(item["season"])
        if item.get("episode") is not None:
            out.episode = int(item["episode"])
        if item.get("episode_title"):
            out.episode_title = str(item["episode_title"])

        ids = dict(out.ids)
        if item.get("tmdb_id"):
            ids["tmdb"] = int(item["tmdb_id"])
        if item.get("anilist_id"):
            ids["anilist"] = int(item["anilist_id"])
        if item.get("mal_id"):
            ids["mal"] = int(item["mal_id"])
        out.ids = ids
        out.parser = f"override+{out.parser}"
        out.confidence = 1.0
        if not out.search_titles:
            out.search_titles = [out.title]
        return out

    def match(self, path: str, filename: str, parsed: ParsedMedia) -> Optional[dict[str, Any]]:
        blob = f"{path}\n{filename}\n{parsed.title}\n{clean_query_title(filename, self.strip_terms)}".lower()
        for item in self.overrides:
            if not isinstance(item, dict):
                continue
            if item.get("enabled") is False:
                continue
            if "path_contains" in item and str(item["path_contains"]).lower() in path.lower():
                return item
            if "filename_contains" in item and str(item["filename_contains"]).lower() in filename.lower():
                return item
            if "contains" in item and str(item["contains"]).lower() in blob:
                return item
            if "glob" in item and fnmatch.fnmatch(filename.lower(), str(item["glob"]).lower()):
                return item
            if "regex" in item:
                try:
                    if re.search(str(item["regex"]), blob, re.I):
                        return item
                except re.error:
                    continue
        return None
