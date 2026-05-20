"""Push STS2 live commentary into the Hermes TUI (activity feed)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def emit_sts2_to_tui(text: str) -> bool:
    """Emit ``sts2.commentary`` to all connected TUI sessions. Returns True if sent."""
    line = (text or "").strip()
    if not line:
        return False
    try:
        from tui_gateway import server as gw

        sids = list(getattr(gw, "_sessions", {}).keys())
        if sids:
            payload = {"text": line[:2000]}
            for sid in sids:
                gw._emit("sts2.commentary", sid, payload)  # noqa: SLF001
            return True
    except Exception as exc:
        logger.debug("sts2 tui emit: %s", exc)
    try:
        from plugins.sts2.tui_bridge import broadcast_to_tui

        return broadcast_to_tui(line)
    except Exception:
        return False
