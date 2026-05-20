"""Ironclad (铁甲战士) deck-building and combat playbooks for STS2 study mode."""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

# --- Anchor cards per archetype (STS2 API ids) ---
_STRENGTH_CORE = frozenset(
    {
        "INFLAME",
        "BURNING",  # 燃烧
        "DEMON_FORM",
        "LIMIT_BREAK",
        "SPOT_WEAKNESS",
        "HEAVY_BLADE",
        "TWIN_STRIKE",
        "SECOND_WIND",
        "REAPER",
        "FEED",
        "SHURIKEN",  # relic synergy — not a card but tagged in guides
    }
)
_BLOCK_CORE = frozenset(
    {
        "BARRICADE",
        "ENTRENCH",
        "METALLICIZE",
        "IMPERVIOUS",
        "FLAME_BARRIER",
        "TRUE_GRIT",
        "SHRUG_OFF",
        "GHOSTLY_ARMOR",
        "POWER_THROUGH",
        "BODY_SLAM",
        "IRON_WAVE",
    }
)
_EXHAUST_CORE = frozenset(
    {
        "FEEL_NO_PAIN",
        "DARK_EMBRACE",
        "CORRUPTION",
        "EXHUME",
        "SECOND_WIND",
        "SENTINEL",
        "EVOLVE",
        "TRUE_GRIT",
    }
)
_TEMPO_UTIL = frozenset(
    {
        "BASH",
        "UPPERCUT",
        "SHOCKWAVE",
        "CLEAVE",
        "THUNDERCLAP",
        "HEADBUTT",
        "ARMAMENTS",
        "BATTLE_TRANCE",
        "SETUP_STRIKE",
        "ONE_TWO_PUNCH",
        "BULLY",
        "SWORD_BOOMERANG",
        "OFFERING",
    }
)
_PERFECT_STRIKE_CORE = frozenset({"PERFECT_STRIKE", "PERFECTED_STRIKE"})

_MUST_PICK = frozenset(
    {
        "DEMON_FORM",
        "BARRICADE",
        "CORRUPTION",
        "OFFERING",
        "FEED",
    }
)
_STRONG_PICK = frozenset(
    {
        "BODY_SLAM",
        "INFLAME",
        "SHRUG_OFF",
        "BATTLE_TRANCE",
        "FEEL_NO_PAIN",
        "DARK_EMBRACE",
        "REAPER",
        "FLAME_BARRIER",
        "IRON_WAVE",
        "BASH",
        "CLEAVE",
        "THUNDERCLAP",
    }
)
_USUALLY_SKIP = frozenset(
    {
        "CONFLICT",
        "WILD_STRIKE",
        "BLOOD_FOR_BLOOD",
        "STRIKE_IRONCLAD",
        "DEFEND_IRONCLAD",
    }
)

_EARLY_PICKS: Dict[str, float] = {}
for cid in _MUST_PICK:
    _EARLY_PICKS[cid] = 95.0
for cid in _STRONG_PICK:
    _EARLY_PICKS.setdefault(cid, 75.0)
_EARLY_PICKS.update(
    {
        "LIMIT_BREAK": 88,
        "HEAVY_BLADE": 72,
        "TWIN_STRIKE": 70,
        "ENTRENCH": 68,
        "METALLICIZE": 66,
        "PERFECT_STRIKE": 85,
        "STRIKE_IRONCLAD": 5,
        "DEFEND_IRONCLAD": 8,
    }
)

_ARCHETYPE_PLAYBOOKS: Dict[str, str] = {
    "early": (
        "【前期通用】Act1 前 8 层：定方向比瞎拿重要。\n"
        "痛击(易伤)优先升级；商店删打击；奖励拿功能牌：耸肩、火焰屏障、顺劈/雷霆、战斗专注、欺凌。\n"
        "见恶魔形态/壁垒/腐化之一 → 立刻按对应流派补件。燃烧之血允许适度换血打精英。"
    ),
    "strength": (
        "【力量成长】燃烧(+2力)、恶魔形态(每回合+力)、极限突破(力量翻倍)、抓弱点。\n"
        "抓牌：多段攻(回旋镖/双连击/旋风斩)、重刀、祭品、收割；少拿纯防除非会死。\n"
        "战斗：先挂能力再输出；易伤/弹珠袋回合集火；有斩杀线别先打防。"
    ),
    "block": (
        "【壁垒全身撞击】壁垒让格挡保留 → 全身撞击(最好升级0费)吃格挡打伤害。\n"
        "抓牌：耸肩、铁波、火焰屏障、金属化、entrech；攻击用铁波/全身撞击。\n"
        "战斗：有格挡的回合再撞击；敌人 Buff 意图日可全力叠防转伤。"
    ),
    "exhaust": (
        "【消耗引擎】腐化(技能0费但消耗)+无痛(消耗得防)+黑暗拥抱(消耗抽牌)。\n"
        "先凑两件再拿第三件；别让坚毅/随机消耗烧掉核心。第二风是应急块。"
    ),
    "perfect": (
        "【完美打击】保留打击类牌组，完美打击按打击数量加伤。\n"
        "少删打击；拿生成打击/0费打击的联动；其余位补抽牌与防。"
    ),
    "tempo": (
        "【节奏功能】痛击易伤链 + AOE 清场 + 铁波/耸肩过渡。\n"
        "每拿一张问：补运转还是污染？拒绝第 3 张雷同打击/防御。"
    ),
}

_ARCHETYPE_EXCERPTS: Dict[str, str] = {
    "strength": "必拿倾向: 恶魔形态、燃烧、极限突破 | 跳过: 冲突、狂乱打击",
    "block": "必拿倾向: 壁垒、全身撞击 | 跳过: 无壁垒时纯堆防",
    "exhaust": "必拿倾向: 腐化+无痛+黑暗拥抱三件套 | 跳过: 无 FNP 时乱拿消耗",
    "perfect": "必拿倾向: 完美打击 | 跳过: 过早删光打击",
    "early": "必拿倾向: 痛击升级、耸肩、顺劈 | 跳过: 基础打击/防御奖励",
    "tempo": "必拿倾向: 痛击、耸肩、顺劈 | 跳过: 冲突、第二张无用打击",
}


@lru_cache(maxsize=1)
def _guide_digest() -> str:
    path = Path(__file__).resolve().parent / "references" / "sts2_ironclad_guide.md"
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8")[:4500]
        except OSError:
            pass
    return ""


def _deck_ids(state: dict) -> Tuple[List[str], Counter[str]]:
    player = state.get("player") or {}
    ids: List[str] = []
    for key in ("deck", "master_deck", "cards", "draw_pile", "discard_pile", "hand"):
        for c in player.get(key) or []:
            if isinstance(c, dict):
                cid = str(c.get("id") or "").strip().upper()
                if cid:
                    ids.append(cid)
    return ids, Counter(ids)


def detect_archetype(state: dict) -> str:
    """early | strength | block | exhaust | perfect | tempo."""
    ids, counts = _deck_ids(state)
    if not ids:
        run = state.get("run") or {}
        try:
            floor = int(run.get("floor") or 0)
        except (TypeError, ValueError):
            floor = 0
        return "early" if floor <= 8 else "tempo"

    def score(core: frozenset) -> int:
        return sum(counts.get(c, 0) for c in core)

    if score(_PERFECT_STRIKE_CORE) >= 1:
        return "perfect"

    ranked = [
        ("strength", score(_STRENGTH_CORE)),
        ("block", score(_BLOCK_CORE)),
        ("exhaust", score(_EXHAUST_CORE)),
        ("tempo", score(_TEMPO_UTIL)),
    ]
    ranked.sort(key=lambda x: x[1], reverse=True)
    best, val = ranked[0]

    run = state.get("run") or {}
    try:
        floor = int(run.get("floor") or 0)
    except (TypeError, ValueError):
        floor = 0

    if floor <= 8 and val < 2:
        return "early"
    if val < 1:
        return "tempo"
    if ranked[1][1] == val:
        return "tempo"
    return best


def archetype_label(key: str) -> str:
    return {
        "early": "前期通用",
        "strength": "力量成长",
        "block": "格挡壁垒",
        "exhaust": "消耗组合",
        "perfect": "完美打击",
        "tempo": "节奏功能",
    }.get(key, key)


def playbook_for_archetype(key: str) -> str:
    return _ARCHETYPE_PLAYBOOKS.get(key, _ARCHETYPE_PLAYBOOKS["tempo"])


def card_tier_hint(card_id: str) -> str:
    cid = str(card_id or "").strip().upper()
    if cid in _MUST_PICK:
        return "必拿级"
    if cid in _STRONG_PICK:
        return "强力"
    if cid in _USUALLY_SKIP:
        return "常跳过"
    return ""


def offer_pick_score(card_id: str, archetype: str, *, floor: int) -> float:
    cid = str(card_id or "").strip().upper()
    if not cid:
        return 0.0
    if cid in _USUALLY_SKIP and archetype != "perfect":
        return -50.0
    base = float(_EARLY_PICKS.get(cid, 42))
    if archetype == "strength":
        if cid in _STRENGTH_CORE:
            base += 28.0
    elif archetype == "block":
        if cid in _BLOCK_CORE:
            base += 30.0
    elif archetype == "exhaust":
        if cid in _EXHAUST_CORE or "EXHAUST" in cid:
            base += 28.0
    elif archetype == "perfect":
        if cid in _PERFECT_STRIKE_CORE or "STRIKE" in cid:
            base += 20.0
    elif archetype == "early":
        if cid in _TEMPO_UTIL or cid in _STRONG_PICK:
            base += 18.0
    if cid in _MUST_PICK:
        base += 15.0
    if floor > 6 and cid in ("STRIKE_IRONCLAD", "DEFEND_IRONCLAD"):
        base -= 35.0
    return base


def build_strategy_brief(state: dict) -> str:
    arch = detect_archetype(state)
    ids, counts = _deck_ids(state)
    run = state.get("run") or {}
    try:
        floor = int(run.get("floor") or 0)
        act = int(run.get("act") or 1)
    except (TypeError, ValueError):
        floor, act = 0, 1

    strike_n = sum(n for k, n in counts.items() if "STRIKE" in k and "PERFECT" not in k)
    lines = [
        f"【构筑诊断】Act{act} 第{floor}层 · 主轴={archetype_label(arch)}",
        playbook_for_archetype(arch),
        _ARCHETYPE_EXCERPTS.get(arch, ""),
    ]
    if strike_n >= 5 and arch != "perfect":
        lines.append(f"⚠ 打击类约{strike_n}张：奖励优先功能/能力，别拿重复打击。")
    cores = [c for c in set(ids) if c in _MUST_PICK | _STRENGTH_CORE | _BLOCK_CORE | _EXHAUST_CORE]
    if cores:
        lines.append("已有核心/锚点: " + ", ".join(sorted(cores)[:10]))
    digest = _guide_digest()
    if digest:
        lines.append("【攻略摘要】\n" + digest[:2200])
    lines.append(
        "抓牌三问：非拿不可？会死吗？补运转还是污染？（参考 slaythespire-2.com 铁甲页 + Wiki）"
    )
    return "\n".join(x for x in lines if x)


def combat_playbook_snippet(state: dict) -> str:
    arch = detect_archetype(state)
    common = (
        "集火最低血；net=max(0,意图伤-格挡)；net≥HP必防；"
        "HP<30%有防必打（含Debuff/Stun回合叠格挡）；Buff 意图且血够才贪输出。"
    )
    extra = {
        "strength": "先能力(燃烧/恶魔形态)再多段攻；极限突破在力量高时用。",
        "block": "叠格挡→全身撞击/铁波；有壁垒时格挡可留到下回合。",
        "exhaust": "腐化+FNP+黑暗拥抱成型后技能白嫖。",
        "perfect": "保留打击；完美打击当终结技。",
        "early": "痛击升级、删打击、拿一张定方向的功能牌。",
        "tempo": "痛击易伤+AOE清场；别安全时浪费防。",
    }.get(arch, "")
    return f"【打法·{archetype_label(arch)}】{extra} {common}"


def bootstrap_build_rules() -> None:
    from plugins.sts2.notes import merge_strategy_rules

    merge_strategy_rules(
        [
            "铁甲：先定流派(力量/壁垒/消耗/完美打击)，再按 Wiki+攻略摘要把牌补进运转。",
            "痛击优先升级；商店优先删打击；奖励是精选池不是三打击。",
            "必拿级：恶魔形态、壁垒、腐化、祭品、狂宴（见攻略摘要）。",
            "力量轴：燃烧/恶魔形态+多段攻+极限突破；壁垒轴：壁垒+全身撞击。",
            "消耗轴：腐化+无痛+黑暗拥抱三件套再扩；完美打击轴保留打击。",
            "战斗：能斩杀先斩杀；net≥HP必防；低血有防必打，禁止 end_turn 留防。",
        ]
    )


def pick_best_offer_index(state: dict, offers: List[dict]) -> int:
    arch = detect_archetype(state)
    run = state.get("run") or {}
    try:
        floor = int(run.get("floor") or 0)
    except (TypeError, ValueError):
        floor = 0
    best_idx = 0
    best_sc = -999.0
    for c in offers:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "")
        try:
            idx = int(c.get("index", 0))
        except (TypeError, ValueError):
            idx = 0
        sc = offer_pick_score(cid, arch, floor=floor)
        try:
            from plugins.sts2.knowledge import card_reward_bonus

            sc += card_reward_bonus(cid)
        except Exception:
            pass
        if sc > best_sc:
            best_sc = sc
            best_idx = idx
    return best_idx
