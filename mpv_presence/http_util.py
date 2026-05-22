from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Optional


class ApiError(RuntimeError):
    pass


def request_json(
    url: str,
    *,
    method: str = "GET",
    query: Optional[dict[str, Any]] = None,
    payload: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 8.0,
) -> Any:
    if query:
        q = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{q}"

    body = None
    h = {
        "User-Agent": "mpv-discord-presence/0.1 (+local mpv discord presence)",
        "Accept": "application/json",
    }
    if headers:
        h.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        h["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return None
            return json.loads(raw)
    except Exception as exc:
        raise ApiError(f"{method} {url} failed: {exc}") from exc
