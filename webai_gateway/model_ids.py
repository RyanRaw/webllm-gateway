from __future__ import annotations

import re
from typing import Any


_ANSI_ESCAPE_RE = re.compile(r"(?:\x1b\[[0-?]*[ -/]*[@-~]|\x9b[0-?]*[ -/]*[@-~])")
_SGR_FRAGMENT_RE = r"\[(?:\d{1,3})(?:;\d{1,3})*m\]?"
_LEADING_SGR_FRAGMENT_RE = re.compile(rf"^(?:{_SGR_FRAGMENT_RE})+")
_TRAILING_SGR_FRAGMENT_RE = re.compile(rf"(?:{_SGR_FRAGMENT_RE})+$")


def normalize_model_id(value: Any, default: str = "") -> str:
    """Normalize model IDs at protocol boundaries while keeping provider names intact.

    ds2api accepts broad client input and resolves it to canonical model IDs. Claude Code on
    Windows can leak rendered ANSI style fragments such as "[1m" into env-provided model IDs;
    strip those transport artifacts before route matching or upstream dispatch.
    """
    raw = str(value or default or "")
    normalized = _ANSI_ESCAPE_RE.sub("", raw).strip()
    previous = None
    while normalized != previous:
        previous = normalized
        normalized = _LEADING_SGR_FRAGMENT_RE.sub("", normalized)
        normalized = _TRAILING_SGR_FRAGMENT_RE.sub("", normalized)
        normalized = _ANSI_ESCAPE_RE.sub("", normalized).strip()
    return normalized


def normalize_model_body(body: dict[str, Any], *, default_model: str = "") -> dict[str, Any]:
    model = normalize_model_id(body.get("model"), default_model)
    if not model:
        return dict(body)
    if body.get("model") == model:
        return body
    return {**body, "model": model}
