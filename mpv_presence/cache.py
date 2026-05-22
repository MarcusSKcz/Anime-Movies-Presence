from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

from .config import CACHE_DIR


class JsonCache:
    def __init__(self, namespace: str, ttl_days: int = 30):
        self.dir = CACHE_DIR / namespace
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl = max(1, ttl_days) * 86400

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()
        return self.dir / f"{digest}.json"

    def get(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            if time.time() - float(data.get("created", 0)) > self.ttl:
                return None
            return data.get("value")
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        path = self._path(key)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"created": time.time(), "value": value}, ensure_ascii=False))
        tmp.replace(path)

    def get_or_set(self, key: str, fn):
        cached = self.get(key)
        if cached is not None:
            return cached
        value = fn()
        self.set(key, value)
        return value
