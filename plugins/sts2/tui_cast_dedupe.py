"""Suppress duplicate STS2 lines in TUI / live spam loops."""

from __future__ import annotations

import hashlib
import time

_RECENT: dict[str, float] = {}

# Shown once at study boot; must not repeat every resume/watchdog tick.
_META_MARKERS = (
    "【代打·模型+规则】",
    "不暂停菜单，但可看思考",
    "【STS2·TUI】代打",
    "【STS2·TUI】代打 study 已挂",
)


def is_meta_banner(text: str) -> bool:
    t = (text or "").strip()
    return any(m in t for m in _META_MARKERS)


def should_deliver(text: str, *, ttl: float = 18.0) -> bool:
    """Return False if this exact payload was delivered recently."""
    t = (text or "").strip()
    if not t:
        return False
    now = time.time()
    if len(_RECENT) > 400:
        cutoff = now - max(ttl, 60.0)
        for k in list(_RECENT.keys()):
            if _RECENT[k] < cutoff:
                del _RECENT[k]
    if is_meta_banner(t):
        key = "meta:" + hashlib.sha256(t.split("\n", 1)[0].encode()).hexdigest()[:16]
        ttl = 600.0
    elif t.startswith("【本局记忆】"):
        key = "mem:" + hashlib.sha256(t[:500].encode()).hexdigest()[:16]
        ttl = 45.0
    else:
        key = "line:" + hashlib.sha256(t[:400].encode()).hexdigest()[:16]
    last = _RECENT.get(key)
    if last is not None and now - last < ttl:
        return False
    _RECENT[key] = now
    return True


def reset_meta_banners() -> None:
    """Call on full stop so next study can show one boot line."""
    drop = [k for k in _RECENT if k.startswith("meta:")]
    for k in drop:
        del _RECENT[k]
