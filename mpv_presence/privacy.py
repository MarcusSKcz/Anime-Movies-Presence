from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def should_ignore(path: str, cfg: dict[str, Any]) -> bool:
    privacy = cfg.get("privacy", {})
    if not privacy.get("enabled", True):
        return False
    p = str(Path(path).expanduser())
    low = p.lower()
    for prefix in privacy.get("ignore_paths", []):
        if prefix and low.startswith(str(Path(prefix).expanduser()).lower()):
            return True
    for pat in privacy.get("ignore_patterns", []):
        if not pat:
            continue
        try:
            if re.search(str(pat), p, re.I):
                return True
        except re.error:
            if str(pat).lower() in low:
                return True
    return False
