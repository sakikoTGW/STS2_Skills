"""Rule-based combat for STS2 — intent-aware; tuned for Act1 / Ascension 0."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_POWER_IDS = frozenset({
    "INFLAME", "DEMON_FORM", "SPOT_WEAKNESS", "FEEL_NO_PAIN", "DARK_EMBRACE",
    "CORRUPTION", "BATTLE_TRANCE", "COMBUSTION", "RUPTURE", "BRUTALITY",
    "BARRICADE", "ENTRENCH", "METALLICIZE", "EVOLVE", "FIRE_BREATHING",
    "DEMONIC_SHIELD", "AFTERIMAGE", "FOOTWORK", "NOXIOUS_FUMES", "PHANTASMAL",
    "BLUR", "FLAME_BARRIER",
})

_BLOCK_IDS = frozenset({
    "DEFEND_IRONCLAD", "DEFEND", "SHRUG_OFF", "IRON_WAVE", "TRUE_GRIT",
    "GHOSTLY_ARMOR", "FLAME_BARRIER", "SURVIVOR", "DEFLECT", "BLOOD_WALL",
    "POWER_THROUGH", "DODGE_AND_ROLL", "BACKFLIP", "PREPARED",
})

_ATTACK_IDS = frozenset({
    "STRIKE_IRONCLAD", "STRIKE", "ANGER", "BASH", "CLEAVE", "TWIN_STRIKE",
    "HEADBUTT", "SEVER_SOUL", "BLOOD_FOR_BLOOD", "HEMOKINESIS", "RAMPAGE",
    "BLADE_DANCE", "SHIV", "FLECHETTES", "SUCKER_PUNCH", "NEUTRALIZE",
    "SETUP_STRIKE", "BREAKTHROUGH", "WHIRLWIND", "POMMEL_STRIKE", "CLASH",
})


def _cost(card: dict) -> int:
    c = str(card.get("cost", "99"))
    if c.upper() == "X":
        return 99
    try:
        return int(c)
    except ValueError:
        return 99


def _run_floor(state: dict) -> int:
    run = state.get("run") or {}
    try:
        return int(run.get("floor") or 0)
    except (TypeError, ValueError):
        return 0


def _parse_intent_damage(intent: dict) -> int:
    hits = 1
    for hkey in ("hits", "count", "repeat"):
        if hkey not in intent or intent.get(hkey) is None:
            continue
        try:
            hits = max(1, int(intent.get(hkey) or 1))
        except (TypeError, ValueError):
            continue
    for key in ("damage", "base_damage", "min_damage", "max_damage"):
        try:
            d = int(intent.get(key) or 0)
            if d > 0:
                return d * hits if hits > 1 else d
        except (TypeError, ValueError):
            continue
    label = str(intent.get("label", "")).strip()
    low = label.lower()
    if "x" in low:
        parts = low.replace(" ", "").split("x")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]) * int(parts[1])
    digits = re.findall(r"\d+", label)
    if digits:
        return max(int(d) for d in digits)
    desc = str(intent.get("description", "")).lower()
    for pat in (r"(\d+)\s*damage", r"deals\s+(\d+)", r"attack.*?(\d+)"):
        m = re.search(pat, desc)
        if m:
            return int(m.group(1))
    return 0


_NON_ATTACK_INTENTS = frozenset({
    "buff", "debuff", "defend", "block", "sleep", "stun", "escape",
    "heal", "card", "magic", "none", "unknown",
})


def net_incoming_damage(incoming: int, block: int) -> int:
    """Damage that actually hits HP after current block."""
    try:
        return max(0, int(incoming) - int(block))
    except (TypeError, ValueError):
        return max(0, incoming)


def is_safe_from_incoming(incoming: int, block: int, hp: int) -> bool:
    """True when this turn's attacks cannot kill us (STS2: compare to HP, not +1 block)."""
    try:
        hp_i = int(hp)
    except (TypeError, ValueError):
        hp_i = 0
    return net_incoming_damage(incoming, block) < hp_i


def estimate_block_gain(card: dict, player: dict | None = None) -> int:
    """Best-effort block; with player applies mechanics_kb (dex + frail)."""
    if player:
        try:
            from plugins.sts2.combat_damage import compute_block_from_card

            return compute_block_from_card(card, player)
        except Exception:
            pass
    for key in ("block", "base_block", "display_block"):
        if card.get(key) is not None:
            try:
                return max(0, int(card[key]))
            except (TypeError, ValueError):
                pass
    desc = str(card.get("description", "") or "")
    for pat in (
        r"获得\s*(\d+)\s*点?格挡",
        r"(\d+)\s*点?格挡",
        r"block\s+(\d+)",
        r"gain\s+(\d+)\s+block",
    ):
        m = re.search(pat, desc, re.I)
        if m:
            return int(m.group(1))
    cid = str(card.get("id", "")).upper()
    if "DEFEND" in cid or "SHRUG" in cid:
        return 5
    return 4


def _player_combat_stats(state: dict) -> tuple[int, int, int, int, int, int]:
    """hp, max_hp, block, energy, incoming, net_damage."""
    player = state.get("player") or {}
    try:
        hp = int(player.get("hp", player.get("current_hp", 1)))
        max_hp = int(player.get("max_hp", hp) or hp or 1)
        block = int(player.get("block", 0))
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        hp, max_hp, block, energy = 1, 1, 0, 0
    enemies = (state.get("battle") or {}).get("enemies") or []
    incoming = incoming_attack_damage(enemies)
    net = net_incoming_damage(incoming, block)
    return hp, max_hp, block, energy, incoming, net


def block_play_is_urgent(state: dict) -> bool:
    """Must play block now — only when this hit would actually kill (not on Buff/Debuff turns)."""
    if combat_should_wait(state):
        return False
    hp, max_hp, block, energy, incoming, net = _player_combat_stats(state)
    if energy <= 0 or incoming <= 0:
        return False
    hand = (state.get("player") or {}).get("hand") or []
    playable = _affordable(hand, energy)
    if not any(_card_is_block(c) for c in playable):
        return False
    return net >= hp


def prefer_block_play(state: dict) -> Optional[dict]:
    """Play block only when incoming damage would kill this turn."""
    if combat_should_wait(state) or not block_play_is_urgent(state):
        return None
    if not block_play_is_urgent(state) and try_lethal_attack(state):
        return None

    player = state.get("player") or {}
    hp, max_hp, block, energy, incoming, net = _player_combat_stats(state)
    hand = player.get("hand") or []
    playable = _affordable(hand, energy)
    blocks = [c for c in playable if _card_is_block(c)]
    if not blocks:
        return None

    enemies = (state.get("battle") or {}).get("enemies") or []
    target = _target_entity_id(enemies)
    blocks.sort(
        key=lambda c: (-estimate_block_gain(c), _cost(c), c.get("index", 0))
    )
    return _play_card(blocks[0], target)


def player_attack_damage_multiplier(state: dict | None) -> float:
    """Outgoing mult from mechanics_kb (虚弱/缩小/双倍等) — 用于战报提示。"""
    if not state:
        return 1.0
    from plugins.sts2.mechanics_kb.damage_engine import (
        outgoing_special_multiplier,
        weak_multiplier,
    )
    from plugins.sts2.mechanics_kb.power_parse import collect_powers

    player = state.get("player") or {}
    pp = collect_powers(player)
    mult = weak_multiplier(pp, player)
    mult *= outgoing_special_multiplier(pp, player, attacks_played=0, pen_nib_triggers=False)
    return mult


def enemy_vulnerable_stacks(enemy: dict) -> int:
    """易伤持续回合数（STS2 Duration，非 STS1 每层+50%伤害）。"""
    from plugins.sts2.combat_damage import vulnerable_turns

    return vulnerable_turns(enemy)


def vulnerable_damage_multiplier(stacks: int, **kwargs) -> float:
    """有易伤时 ×1.5（层数只表示剩余回合，不叠乘倍率）。见 wiki.gg Vulnerable。"""
    if int(stacks or 0) <= 0:
        return 1.0
    if kwargs.get("enemy") is not None or kwargs.get("player") is not None:
        from plugins.sts2.combat_damage import vulnerable_damage_multiplier as _m

        return _m(
            kwargs.get("enemy") or {"vulnerable": stacks},
            player=kwargs.get("player"),
            state=kwargs.get("state"),
        )
    return 1.5


def card_applies_vulnerable(card: dict) -> int:
    """本牌施加的易伤回合数（痛击 2 / 痛击+ 3）。"""
    from plugins.sts2.combat_damage import card_applies_vulnerable_turns

    return card_applies_vulnerable_turns(card)


def focus_enemy(state: dict) -> dict | None:
    """Default single-target focus: lowest HP living enemy."""
    living = [
        e
        for e in (state.get("battle") or {}).get("enemies") or []
        if isinstance(e, dict) and int(e.get("hp", 0) or 0) > 0
    ]
    if not living:
        return None
    return min(living, key=lambda e: int(e.get("hp", 9999)))


def vuln_stacks_when_playing_card(
    state: dict, hand: list, card: dict, *, enemy: dict | None = None
) -> int:
    """打出本牌前，目标身上易伤回合数（含手牌低 index 先打的痛击等）。"""
    from plugins.sts2.combat_damage import projected_vulnerable_turns_after_prior_cards

    return projected_vulnerable_turns_after_prior_cards(
        state, hand, card, enemy=enemy
    )


def estimate_card_damage(
    card: dict,
    player: dict,
    *,
    state: dict | None = None,
    enemy: dict | None = None,
    vuln_stacks: int | None = None,
    apply_vulnerable: bool = True,
) -> int:
    """Wiki STS2: floor((base+str)×易伤)；易伤层数=回合数，倍率固定×1.5。"""
    from plugins.sts2.combat_damage import estimate_attack_damage

    turns = vuln_stacks
    if turns is None and enemy is not None:
        turns = enemy_vulnerable_stacks(enemy)
    if turns is None and state is not None:
        hand = list((player.get("hand") or []))
        turns = vuln_stacks_when_playing_card(state, hand, card, enemy=enemy)

    return estimate_attack_damage(
        card,
        player,
        state=state,
        enemy=enemy,
        vulnerable_turns_when_hit=turns,
        apply_vulnerable=apply_vulnerable,
    )


def format_hand_damage_ledger(state: dict) -> str:
    from plugins.sts2.combat_damage import format_hand_damage_ledger as _ledger

    return _ledger(state)


def format_attack_damage_hint(card: dict, player: dict, state: dict) -> str:
    from plugins.sts2.combat_damage import format_attack_damage_hint as _hint

    return _hint(card, player, state)


def next_turn_incoming_from_loops(state: dict) -> int:
    """Enemy attack damage on the turn after end_turn (KB loop T+1)."""
    total = 0
    try:
        from plugins.sts2.huiji_kb.loops import forecast_enemy
        from plugins.sts2.huiji_kb.store import lookup_enemy
        from plugins.sts2.wiki_enemy import normalize_enemy_wiki_id
    except Exception:
        return 0

    for e in (state.get("battle") or {}).get("enemies") or []:
        if not isinstance(e, dict) or int(e.get("hp", 0) or 0) <= 0:
            continue
        wid = normalize_enemy_wiki_id(e)
        kb = lookup_enemy(wid) if wid else None
        if not kb:
            continue
        fc = forecast_enemy(kb, e, horizon=2)
        rows = fc.get("horizon") or []
        if len(rows) >= 2:
            total += int(rows[1].get("damage_est") or 0)
    return total


def try_lethal_attack(state: dict) -> Optional[dict]:
    """If affordable attacks can kill the lowest-HP enemy, play the best kill card."""
    if combat_should_wait(state):
        return None
    player = state.get("player") or {}
    try:
        energy = int(player.get("energy", 0) or 0)
    except (TypeError, ValueError):
        energy = 0
    hand = player.get("hand") or []
    playable = _affordable(hand, energy)
    attacks = [c for c in playable if _card_is_attack(c)]
    if not attacks:
        return None
    enemies = (state.get("battle") or {}).get("enemies") or []
    living = [e for e in enemies if int(e.get("hp", 0) or 0) > 0]
    if not living:
        return None
    focus = min(living, key=lambda e: int(e.get("hp", 9999)))
    need = int(focus.get("hp", 0) or 0)
    eid = focus.get("entity_id")
    hand = list((player.get("hand") or []))
    total = sum(
        estimate_card_damage(
            c,
            player,
            state=state,
            vuln_stacks=vuln_stacks_when_playing_card(state, hand, c, enemy=focus),
        )
        for c in attacks
    )
    if total < need:
        return None
    attacks.sort(
        key=lambda c: (
            -estimate_card_damage(
                c,
                player,
                state=state,
                vuln_stacks=vuln_stacks_when_playing_card(state, hand, c, enemy=focus),
            ),
            _cost(c),
            c.get("index", 0),
        )
    )
    return _play_card(attacks[0], eid)


def incoming_attack_damage_for_enemy(enemy: dict) -> int:
    """Attack intent damage from one living enemy (T+0 slots)."""
    if int(enemy.get("hp", 0) or 0) <= 0:
        return 0
    total = 0
    for intent in enemy.get("intents") or []:
        itype = str(intent.get("type", "")).lower()
        if itype in _NON_ATTACK_INTENTS:
            continue
        if itype in ("attack", "multi_attack", "debuff_attack"):
            dmg = _parse_intent_damage(intent)
            if dmg > 0:
                total += dmg
            continue
        label = str(intent.get("label", "")).strip()
        if label.isdigit() and int(label) > 0:
            total += int(label)
    return total


def incoming_attack_damage(enemies: list) -> int:
    """Only count real attack intents — ignore Buff/Debuff (fixes defend-fest on buff turns)."""
    total = 0
    for enemy in enemies:
        total += incoming_attack_damage_for_enemy(enemy)
    return total


def incoming_attack_damage_excluding(enemies: list, exclude_entity_id: str) -> int:
    """Total incoming if one enemy is removed (killed this turn)."""
    ex = str(exclude_entity_id or "")
    total = 0
    for enemy in enemies:
        if int(enemy.get("hp", 0) or 0) <= 0:
            continue
        eid = str(enemy.get("entity_id") or enemy.get("id") or "")
        if ex and eid == ex:
            continue
        total += incoming_attack_damage_for_enemy(enemy)
    return total


def _target_entity_id(enemies: list) -> Optional[str]:
    living = [e for e in enemies if int(e.get("hp", 0)) > 0]
    if not living:
        return None
    return min(living, key=lambda e: int(e.get("hp", 9999))).get("entity_id")


def combat_should_wait(state: dict) -> bool:
    """Enemy turn or between phases — never end_turn/proceed."""
    battle = state.get("battle") or {}
    turn = str(battle.get("turn", "")).lower()
    if turn == "enemy":
        return True
    if not battle.get("is_play_phase", False):
        return True
    return False


def combat_should_end_turn(state: dict) -> bool:
    """Player phase but nothing left to do."""
    if combat_should_wait(state):
        return False
    player = state.get("player") or {}
    hand = player.get("hand") or []
    try:
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        energy = 0
    playable = _affordable(hand, energy)
    if not hand:
        return energy <= 0
    if not playable:
        return True
    return False


def _play_card(card: dict, target: Optional[str]) -> dict:
    body: dict = {"action": "play_card", "card_index": card["index"]}
    tt = str(card.get("target_type") or "").lower()
    if tt in ("anyenemy", "enemy", "singleenemy") and target:
        body["target"] = target
    return body


def _card_is_block(card: dict) -> bool:
    cid = str(card.get("id", "")).upper()
    if cid in _BLOCK_IDS or "DEFEND" in cid:
        return True
    name = str(card.get("name", "")).lower()
    if "defend" in name or "防御" in name or "格挡" in name:
        return True
    desc = str(card.get("description", "")).lower()
    return "block" in desc or "格挡" in desc or "获得" in desc and "格挡" in desc


def _card_is_power(card: dict) -> bool:
    if str(card.get("type", "")).lower() == "power":
        return True
    return str(card.get("id", "")) in _POWER_IDS


def _card_is_attack(card: dict) -> bool:
    if str(card.get("type", "")).lower() == "attack":
        return True
    cid = str(card.get("id", "")).upper()
    return cid in _ATTACK_IDS or "STRIKE" in cid


def _affordable(hand: list, energy: int) -> list:
    out = []
    for c in hand:
        if not c.get("can_play", False):
            continue
        if _cost(c) > energy:
            continue
        out.append(c)
    return out


def _lessons_want_caution(state: dict) -> bool:
    """Apply strategy.yaml combat lessons (deaths → block more)."""
    try:
        from plugins.sts2.lessons import lessons_for_combat

        rules = lessons_for_combat(state)
    except Exception:
        return False
    if not rules:
        return False
    text = " ".join(rules).lower()
    return any(k in text for k in ("阵亡", "格挡", "防", "block", "精英", "低层", "act1"))


def decide_combat(state: dict, *, apply_lessons: bool = True) -> dict:
    """One legal combat action; scored engine or legacy rules."""
    try:
        from plugins.sts2.config import load_sts2_config

        if load_sts2_config().get("use_combat_scorer", True):
            from plugins.sts2.combat_scorer import decide_combat_scored

            return decide_combat_scored(state)
    except Exception:
        pass

    if combat_should_wait(state):
        return {"action": "__wait__"}
    if combat_should_end_turn(state):
        return {"action": "end_turn"}

    battle = state.get("battle") or {}

    player = state.get("player") or {}
    hand = player.get("hand") or []
    try:
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        energy = 0
    try:
        hp = int(player.get("hp", player.get("current_hp", 1)))
        max_hp = int(player.get("max_hp", hp) or hp or 1)
    except (TypeError, ValueError):
        hp, max_hp = 1, 1
    try:
        block = int(player.get("block", 0))
    except (TypeError, ValueError):
        block = 0

    enemies = battle.get("enemies") or []
    target = _target_entity_id(enemies)
    incoming = incoming_attack_damage(enemies)
    playable = _affordable(hand, energy)

    # Draw animation — hand not dealt yet
    if not hand and energy > 0 and not playable:
        return {"action": "__wait__"}
    floor = _run_floor(state)
    early_act = floor <= 8
    cautious = apply_lessons and _lessons_want_caution(state)
    rnd = int(battle.get("round", 1) or 1)

    from plugins.sts2.combat_resources import prefer_bloodletting_play, prefer_potion_play

    potion = prefer_potion_play(state)
    if potion:
        return potion

    bleed = prefer_bloodletting_play(state)
    if bleed:
        return bleed

    # --- 0-cost first (Anger, etc.) ---
    for c in sorted(playable, key=lambda x: x.get("index", 0)):
        if _cost(c) == 0:
            return _play_card(c, target)

    # --- Armaments / key setup skills early ---
    for c in sorted(playable, key=lambda x: _cost(x)):
        cid = str(c.get("id", "")).upper()
        name = str(c.get("name", ""))
        if cid == "ARMAMENTS" or "武装" in name:
            return _play_card(c, target)

    # --- Powers (turn 1-2) ---
    if rnd <= 2:
        for c in sorted(playable, key=lambda x: _cost(x)):
            if _card_is_power(c):
                return _play_card(c, target)

    # Enough block already — press attacks (don't Defend on Buff turns)
    if incoming > 0 and incoming <= block:
        attacks = [c for c in playable if _card_is_attack(c)]
        if attacks:
            attacks.sort(key=lambda c: (-_cost(c), c.get("index", 0)))
            return _play_card(attacks[0], target)

    # --- Lethal before block (10 HP gremlin: don't Defend for 5 block) ---
    lethal = try_lethal_attack(state)
    if lethal:
        return lethal

    urgent_block = prefer_block_play(state)
    if urgent_block:
        return urgent_block

    net = net_incoming_damage(incoming, block)
    # --- Block only when we would actually lose HP ---
    if is_safe_from_incoming(incoming, block, hp):
        need_block = False
    elif net >= hp:
        need_block = True
    elif hp < max_hp * 0.2 and net > 0:
        need_block = True
    elif cautious:
        need_block = net > max(3, hp // 4) or (incoming >= 10 and hp < max_hp * 0.5)
    else:
        need_block = net > max(5, hp // 3)

    if need_block:
        for c in playable:
            if _card_is_block(c):
                return _play_card(c, target)

    # --- No / low threat → kill (Buff intent → incoming 0) ---
    if incoming <= block + 2:
        attacks = [c for c in playable if _card_is_attack(c)]
        if attacks:
            attacks.sort(key=lambda c: (-_cost(c), c.get("index", 0)))
            return _play_card(attacks[0], target)

    # --- Setup debuffs when safe ---
    if energy > 0 and incoming <= block + 6:
        for c in playable:
            cid = str(c.get("id", ""))
            if cid in ("BASH", "TREMBLE", "SHOCKWAVE", "UPPERCUT", "NEUTRALIZE", "SUCKER_PUNCH"):
                return _play_card(c, target)

    # --- Default: attacks then other skills ---
    attacks = [c for c in playable if _card_is_attack(c)]
    if attacks:
        attacks.sort(key=lambda c: (-_cost(c), c.get("index", 0)))
        return _play_card(attacks[0], target)

    for c in playable:
        if not _card_is_block(c):
            return _play_card(c, target)

    # Last resort: block even if not ideal
    for c in playable:
        if _card_is_block(c):
            return _play_card(c, target)

    urgent_block = prefer_block_play(state)
    if urgent_block:
        return urgent_block

    if not playable and energy > 0:
        return {"action": "end_turn"}

    return {"action": "end_turn"}
