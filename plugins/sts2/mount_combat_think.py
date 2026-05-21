"""挂载模式：状态机触发时的辅脑深度思考（主 Agent 决策，此处仅出参考分析）。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _parse_json(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def run_mount_deep_think(
    state: dict,
    *,
    zone_note: str,
    changed_zones: list[str],
    memory_prefix: str = "",
) -> dict[str, Any]:
    """Auxiliary deep think for mount mode — reference only, not auto-execute."""
    from plugins.sts2.config import load_sts2_config
    from plugins.sts2.play_mode import llm_play_enabled

    if not llm_play_enabled():
        return {"skipped": True, "reason": "HERMES_STS2_LLM_PLAY=0"}

    cfg = load_sts2_config()
    hand = list((state.get("player") or {}).get("hand") or [])

    from plugins.sts2.knowledge_pack import assemble_combat_pack
    from plugins.sts2.run_objective import llm_run_objective_system
    from plugins.sts2.thinking_policy import combat_system_append

    system = (
        "你是 STS2 挂载模式的【辅脑·战斗分析】。主 Hermes Agent 会读你的 commentary 后自行 sts2_act。\n"
        "你只输出分析参考，不会自动执行；禁止空话。\n"
        + llm_run_objective_system()
        + combat_system_append()
        + "\nJSON: {\"commentary\":\"...\",\"action\":\"play_card|end_turn|use_potion\","
        '"card_index":0,"target":"ENTITY_ID"}'
    )
    user = assemble_combat_pack(state, hand, memory=memory_prefix)
    fsm = state.get("combat_fsm") or {}
    snap = str(fsm.get("snapshot_text") or "").strip()
    if snap:
        user = f"{snap}\n\n{user}"
    user += (
        f"\n\n[状态机变化] {', '.join(changed_zones)}\n{zone_note}\n"
        "commentary 须含：意图、净入伤、行为循环 T+1/T+2、本动计划、取舍、构筑主轴。"
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        from plugins.sts2.llm_util import sts2_call_llm
        from plugins.sts2.thinking_policy import commentary_substantive, llm_retry_user

        max_tok = int(cfg.get("mount_think_max_tokens", 1400))
        temp = float(cfg.get("mount_think_temperature", 0.32))
        raw = sts2_call_llm(messages, max_tokens=max_tok, temperature=temp)
        parsed = _parse_json(raw)
        comm = str((parsed or {}).get("commentary") or "").strip()
        if parsed and not commentary_substantive(comm, combat=True):
            raw2 = sts2_call_llm(
                messages
                + [
                    {"role": "assistant", "content": raw[:900]},
                    {
                        "role": "user",
                        "content": llm_retry_user("挂载辅脑 commentary 过短"),
                    },
                ],
                max_tokens=max_tok,
                temperature=temp,
            )
            if raw2:
                raw = raw2
                parsed = _parse_json(raw)
                comm = str((parsed or {}).get("commentary") or "").strip()
        if not parsed:
            return {"ok": False, "error": "json_parse_failed", "raw": raw[:400]}
        body = {k: v for k, v in parsed.items() if k != "commentary"}
        return {
            "ok": True,
            "trigger": "mount_fsm_zone_change",
            "changed_zones": changed_zones,
            "commentary": comm,
            "suggested_action": body,
            "reference_only": True,
        }
    except Exception as exc:
        logger.warning("mount deep think failed: %s", exc)
        return {"ok": False, "error": str(exc)}
