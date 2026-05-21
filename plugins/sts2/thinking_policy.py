"""Require visible step-by-step reasoning before autoplay actions."""

from __future__ import annotations

import re

_THINK_MARKERS = (
    "意图",
    "净入",
    "伤害",
    "格挡",
    "本动",
    "本回合",
    "计划",
    "取舍",
    "wiki",
    "Wiki",
    "构筑",
    "主轴",
    "流派",
    "抓牌",
    "因为",
    "所以",
    "否则",
    "T+",
)

_COMBAT_THINK_APPEND = (
    "\n\n【思考格式·必填】commentary 用中文写满至少 6 句，且必须显式包含："
    "①【意图】敌人本回合/下回合意图与关键机制（引用 Wiki 行为若已给出）；"
    "②【算数】净入伤、有效HP、能量与手牌费；"
    "③【本动】这一步要完成什么；"
    "④【取舍】为什么不选另一张牌/为什么不 end_turn；"
    "⑤【构筑】本动如何服务当前流派主轴（力量/壁垒/消耗等）。"
    "须引用上文【Wiki·战斗必读】或怪物机制一句。"
    "禁止只写「出牌」「防御」「继续」等空话。"
)

_MAP_THINK_APPEND = (
    "\n\n【思考格式·必填】commentary 至少 5 句，含："
    "①【路线】本幕目标与当前层风险；"
    "②【选项】各路径利弊；"
    "③【本动】选哪格及理由；"
    "④【构筑】与当前主轴/缺件的关系。"
    "选牌/营火/遗物屏须引用 Wiki 候选卡摘要。"
)


def commentary_substantive(text: str, *, combat: bool = False) -> bool:
    t = (text or "").strip()
    hits = sum(1 for m in _THINK_MARKERS if m in t)
    min_len = 48 if combat else 56
    if len(t) < min_len:
        return False
    if combat and hits < 2:
        return False
    if hits < 1 and len(t) < 100:
        return False
    if re.fullmatch(r"[\s▶·\-—规则战斗模型兜底暂停\.]+", t):
        return False
    return True


def combat_system_append() -> str:
    return _COMBAT_THINK_APPEND


def map_system_append() -> str:
    return _MAP_THINK_APPEND


def format_feed_thinking(commentary: str, action_block: str) -> str:
    """TUI/live_feed: thinking first, then board+action."""
    think = (commentary or "").strip()
    act = (action_block or "").strip()
    if not think:
        return act
    if not act:
        return f"━━ 思考 ━━\n{think}"
    if think in act:
        return act
    return f"━━ 思考 ━━\n{think}\n\n━━ 执行 ━━\n{act}"


def llm_retry_user(reason: str) -> str:
    return (
        f"上次回复不合格：{reason}。"
        "请重新输出完整 JSON，commentary 必须按【思考格式·必填】写满。"
    )
