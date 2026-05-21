"""Hermes tools for Slay the Spire 2 (STS2MCP bridge)."""

from __future__ import annotations

from typing import Any

from plugins.sts2 import client as sts2_client

try:
    from tools.registry import tool_error, tool_result
except ImportError:  # standalone sts2-skills without hermes-agent on PYTHONPATH

    def tool_result(**kwargs: Any) -> str:
        import json

        return json.dumps(kwargs, ensure_ascii=False, default=str)

    def tool_error(message: str, **kwargs: Any) -> str:
        import json

        payload = {"success": False, "error": message, **kwargs}
        return json.dumps(payload, ensure_ascii=False, default=str)

_PLAY_LOOP = (
    "On-demand LLM autopilot: sts2_autoplay action=run (until FULL_RUN_CLEARED). "
    "While chatting: pause|resume|stop|hint|status. Manual override: sts2_act (pauses autopilot). "
    "Or hand-play loop: sts2_get_state(summary=true) → think → sts2_act."
)


def _check_sts2_available() -> bool:
    try:
        sts2_client.ping()
        return True
    except Exception:
        return False


def _attach_play_context(payload: dict, *, action: dict | None = None) -> dict:
    """Add play_brief coaching block for the agent."""
    from plugins.sts2.play_brief import build_play_brief

    if isinstance(payload, dict) and payload.get("state_type"):
        from plugins.sts2.crystal_sphere import annotate_state

        payload = annotate_state(dict(payload))
        payload["play_brief"] = build_play_brief(payload)
        try:
            from plugins.sts2.combat_survival_gate import attach_survival_fields

            payload = attach_survival_fields(payload)
        except Exception:
            pass
        try:
            from plugins.sts2.manual_act import attach_manual_act_fields

            payload = attach_manual_act_fields(payload)
        except Exception:
            pass
        try:
            from plugins.sts2.agent_contract import attach_agent_contract_fields

            payload = attach_agent_contract_fields(payload)
        except Exception:
            pass
        try:
            from plugins.sts2.combat_state_machine import attach_combat_fsm

            payload["combat_fsm"] = attach_combat_fsm(payload)
        except Exception:
            pass
        try:
            from plugins.sts2.manual_learn import tick

            learn_meta = tick(payload, action=action)
            if learn_meta.get("reflect", {}).get("reflected"):
                payload["learn_reflect"] = learn_meta["reflect"]
        except Exception:
            pass
    return payload


def _http_result(status: int, payload: Any, *, ok_statuses: tuple[int, ...] = (200,)) -> str:
    if status in ok_statuses:
        if isinstance(payload, dict):
            return tool_result(success=True, http_status=status, **payload)
        return tool_result(success=True, http_status=status, data=payload)
    if isinstance(payload, dict) and payload.get("message"):
        return tool_error(payload.get("message"), http_status=status, **payload)
    return tool_error(f"STS2MCP request failed (HTTP {status})", http_status=status, body=payload)


def handle_sts2_ping(args: dict[str, Any], **kwargs: Any) -> str:
    try:
        payload = sts2_client.ping()
    except ConnectionError as exc:
        return tool_error(str(exc))
    except Exception as exc:
        return tool_error(f"sts2_ping failed: {type(exc).__name__}: {exc}")
    try:
        from plugins.sts2.mode_display import ensure_autoplay_running, structured_mode_status

        ar = ensure_autoplay_running(reason="ping")
        mode = structured_mode_status()
    except Exception:
        ar, mode = {}, {}
    return tool_result(success=True, sts2_mode=mode, auto_run=ar, **payload)


def handle_sts2_get_state(args: dict[str, Any], **kwargs: Any) -> str:
    fmt = str(args.get("format") or "json").strip().lower()
    if fmt not in ("json", "markdown"):
        return tool_error('format must be "json" or "markdown"')
    want_summary = bool(args.get("summary") or args.get("view") == "summary")
    try:
        status, payload = sts2_client.get_singleplayer_state(fmt=fmt)
    except ConnectionError as exc:
        return tool_error(str(exc))
    except Exception as exc:
        return tool_error(f"sts2_get_state failed: {type(exc).__name__}: {exc}")

    if fmt == "markdown" and isinstance(payload, dict) and "raw" in payload:
        return tool_result(success=status == 200, http_status=status, markdown=payload["raw"])

    if status == 409:
        return tool_error(
            "Singleplayer endpoint unavailable (HTTP 409). "
            "You may be in multiplayer — use multiplayer API or return to singleplayer.",
            http_status=status,
            body=payload,
        )
    if isinstance(payload, dict) and payload.get("state_type"):
        payload = _attach_play_context(payload)
    try:
        from plugins.sts2.mode_display import ensure_autoplay_running, structured_mode_status

        ensure_autoplay_running(reason="get_state")
        mode_info = structured_mode_status()
    except Exception:
        mode_info = {}

    if want_summary and isinstance(payload, dict):
        from plugins.sts2.autoplay import get_controller
        from plugins.sts2.visibility import describe_situation

        ctrl = get_controller()
        obs = ctrl.observe_once()
        fsm = payload.get("combat_fsm") or {}
        sit = obs.get("situation") or describe_situation(payload)
        alert = payload.get("survival_alert") or ""
        if alert and alert not in sit:
            sit = f"{alert}\n{sit}"
        decision_ctx = {}
        try:
            from plugins.sts2.decision_context import structured_context

            decision_ctx = structured_context(payload)
        except Exception:
            pass
        from plugins.sts2.play_mode import marathon_forbidden

        thinking_tpl = ""
        try:
            from plugins.sts2.decision_context import thinking_checklist

            thinking_tpl = thinking_checklist(payload)
        except Exception:
            pass

        return tool_result(
            success=status == 200,
            http_status=status,
            situation=sit,
            survival_alert=alert,
            sts2_mode=mode_info,
            mode_banner=mode_info.get("banner_compact") or mode_info.get("banner", ""),
            agent_contract=payload.get("agent_contract"),
            sole_decider=payload.get("sole_decider"),
            coach_hint=payload.get("coach_hint"),
            mandatory_next_action=payload.get("mandatory_next_action"),
            survival_snapshot=payload.get("survival_snapshot"),
            decision_context=decision_ctx,
            marathon_forbidden=marathon_forbidden(),
            legal_actions=payload.get("legal_actions"),
            manual_contract=payload.get("manual_contract"),
            play_brief=payload.get("play_brief", ""),
            thinking_checklist=thinking_tpl,
            delta=obs.get("delta", ""),
            changed=obs.get("changed", False) or fsm.get("changed", False),
            combat_fsm=fsm,
            think_required=fsm.get("think_required", False),
            combat_think=fsm.get("think"),
            fsm_think_ran=fsm.get("think_ran", False),
            state_type=payload.get("state_type"),
            state=payload,
        )
    if isinstance(payload, dict):
        return tool_result(
            success=status == 200,
            http_status=status,
            sts2_mode=mode_info,
            play_brief=payload.get("play_brief", ""),
            **payload,
        )
    return _http_result(status, payload)


def handle_sts2_observe(args: dict[str, Any], **kwargs: Any) -> str:
    """Readable snapshot + what changed since last observe (user or bot plays)."""
    from plugins.sts2.autoplay import get_controller

    try:
        out = get_controller().observe_once()
    except ConnectionError as exc:
        return tool_error(str(exc))
    except Exception as exc:
        return tool_error(f"sts2_observe failed: {type(exc).__name__}: {exc}")
    st = get_controller().status()
    return tool_result(
        **out,
        autoplay_running=st.get("running"),
        watch_running=st.get("watching"),
    )


def _prepare_manual_act() -> str | None:
    """Pause or stop background autopilot before manual sts2_act."""
    from plugins.sts2 import driver_lock

    if driver_lock.is_internal_act():
        return None
    from plugins.sts2.autoplay import get_controller
    from plugins.sts2.config import load_sts2_config
    from plugins.sts2.manual_mode import release_all_driver_locks, set_manual_mode
    from plugins.sts2.play_mode import agent_play_mode

    ctrl = get_controller()
    st = ctrl.status()
    cfg = load_sts2_config()
    if st.get("watching"):
        ctrl.stop()
        release_all_driver_locks()
    elif st.get("studying") or st.get("running"):
        if cfg.get("pause_autopilot_on_manual_act", True):
            ctrl.pause(reason="用户/主 Agent 手操接管")
        else:
            ctrl.stop()
            release_all_driver_locks()
    else:
        release_all_driver_locks()
    set_manual_mode(not agent_play_mode())
    return None


def handle_sts2_act(args: dict[str, Any], **kwargs: Any) -> str:
    from plugins.sts2 import driver_lock
    from plugins.sts2.config import enforce_single_driver_enabled

    if enforce_single_driver_enabled():
        blocked = driver_lock.manual_act_blocked()
        if blocked:
            return tool_error(blocked)

    err = _prepare_manual_act()
    if err:
        return tool_error(err)

    action = str(args.get("action") or "").strip()
    if not action:
        return tool_error('Missing required "action" (e.g. play_card, end_turn, menu_select)')

    params = args.get("parameters")
    body: dict[str, Any] = {"action": action}
    if params is not None:
        if not isinstance(params, dict):
            return tool_error('"parameters" must be a JSON object')
        for key, value in params.items():
            if key != "action":
                body[key] = value

    # Flatten common top-level aliases for ergonomics
    for key in (
        "card_index",
        "target",
        "index",
        "slot",
        "option",
        "seed",
        "x",
        "y",
        "tool",
    ):
        if key in args and args[key] is not None and key not in body:
            body[key] = args[key]

    requested_action = action
    body_before_validate = dict(body)
    live_state: dict[str, Any] | None = None
    corrected = False
    try:
        _st, live_state = sts2_client.get_singleplayer_state(fmt="json")
        if isinstance(live_state, dict) and live_state.get("state_type"):
            from plugins.sts2 import action_validate as av_mod

            fixed = av_mod.validate_action(live_state, body)
            if fixed != body:
                corrected = True
                body = fixed
    except Exception:
        pass

    final_action = str(body.get("action") or "")
    if final_action in ("__wait__", "__pause__"):
        return tool_error(
            f"未向游戏发送动作：请求 {requested_action!r} 被校验为 {final_action!r}（本地跳过）。"
            " 手牌打完后请 sts2_act action=end_turn；若在武装/选牌界面请先 combat_confirm_selection。",
            requested_action=requested_action,
            executed_action=body,
            state_type=(live_state or {}).get("state_type") if live_state else None,
        )

    correction_policy = "ok"
    try:
        from plugins.sts2.manual_mode import manual_mode_enabled
        from plugins.sts2.play_mode import agent_play_mode

        _manual = manual_mode_enabled()
        _agent = agent_play_mode()
    except Exception:
        _manual = False
        _agent = False
    if corrected and isinstance(live_state, dict) and final_action == "play_card":
        if _agent or _manual:
            try:
                from plugins.sts2.manual_act import target_only_correction

                if not target_only_correction(body_before_validate, body):
                    correction_policy = "index_drift"
                    body = body_before_validate
            except Exception:
                correction_policy = "index_drift"
        else:
            try:
                from plugins.sts2.combat_survival_gate import resolve_play_card_correction

                correction_policy, body = resolve_play_card_correction(
                    live_state, body_before_validate, body
                )
            except Exception:
                correction_policy = "ok"
    if correction_policy in ("block_post", "index_drift") and not _agent:
        from plugins.sts2.visibility import describe_situation

        st_attached = _attach_play_context(dict(live_state or {}))
        msg = (
            "未向游戏发送 play_card：card_index 与校验结果不一致或会送死。"
            " 必须先 sts2_get_state(summary=true)，读 survival_alert / 手牌 index，再出牌。"
        )
        if correction_policy == "block_post":
            msg = (
                "未向游戏发送 play_card：必死线回合禁止打出攻击牌。"
                " 请先 sts2_get_state，按 mandatory_next_action 或 survival_alert 叠防/用药。"
            )
        return tool_error(
            msg,
            success=False,
            action_blocked=True,
            correction_policy=correction_policy,
            requested_action=body_before_validate,
            validated_action=body,
            survival_alert=st_attached.get("survival_alert"),
            mandatory_next_action=st_attached.get("mandatory_next_action"),
            play_brief=st_attached.get("play_brief", ""),
            situation=describe_situation(st_attached),
        )

    if (
        not _agent
        and isinstance(live_state, dict)
        and final_action == "play_card"
        and correction_policy == "ok"
    ):
        try:
            from plugins.sts2.combat_survival_gate import (
                play_card_would_lethal,
                potion_required_before_play,
            )

            pot_first = potion_required_before_play(live_state)
            if pot_first:
                from plugins.sts2.visibility import describe_situation

                st_attached = _attach_play_context(dict(live_state))
                return tool_error(
                    "未向游戏发送 play_card：必死线须先 use_potion（叠防不够）。",
                    success=False,
                    action_blocked=True,
                    correction_policy="potion_first",
                    requested_action=body_before_validate,
                    validated_action=body,
                    survival_alert=st_attached.get("survival_alert"),
                    mandatory_next_action=st_attached.get("mandatory_next_action"),
                    play_brief=st_attached.get("play_brief", ""),
                    situation=describe_situation(st_attached),
                )
        except Exception:
            pass

    if (
        not _agent
        and isinstance(live_state, dict)
        and final_action == "play_card"
        and correction_policy == "ok"
    ):
        try:
            from plugins.sts2.combat_survival_gate import play_card_would_lethal

            if play_card_would_lethal(live_state, body):
                from plugins.sts2.visibility import describe_situation

                st_attached = _attach_play_context(dict(live_state))
                return tool_error(
                    "未向游戏发送 play_card：必死线回合禁止打出攻击牌。"
                    " 请先 sts2_get_state，按 mandatory_next_action 叠防/用药。",
                    success=False,
                    action_blocked=True,
                    correction_policy="lethal_play",
                    requested_action=body_before_validate,
                    validated_action=body,
                    survival_alert=st_attached.get("survival_alert"),
                    mandatory_next_action=st_attached.get("mandatory_next_action"),
                    play_brief=st_attached.get("play_brief", ""),
                    situation=describe_situation(st_attached),
                )
        except Exception:
            pass

    try:
        status, payload = sts2_client.post_singleplayer_action(body)
    except ConnectionError as exc:
        return tool_error(str(exc))
    except ValueError as exc:
        return tool_error(str(exc))
    except Exception as exc:
        return tool_error(f"sts2_act failed: {type(exc).__name__}: {exc}")


    extra: dict[str, Any] = {}
    dict(body)
    if corrected:
        extra["requested_action"] = requested_action
        extra["action_corrected"] = True
        extra["executed_action"] = body
        req_idx = args.get("card_index", body_before_validate.get("card_index"))
        exec_idx = body.get("card_index")
        if (
            requested_action == "play_card"
            and req_idx is not None
            and exec_idx is not None
            and int(req_idx) != int(exec_idx)
        ):
            extra["correction_severity"] = "critical"
            extra["mandatory_next_step"] = (
                "你请求的 card_index 与系统校正后不同（常因未 get_state 或 index 漂移）。"
                "禁止继续 end_turn：立即 sts2_get_state(summary=true)，按新手牌 index 重规划。"
            )

    if status == 200:
        try:
            from plugins.sts2.state_settle import wait_for_settled_state

            fresh, settle_meta = wait_for_settled_state(
                live_state, final_action or requested_action
            )
            if isinstance(fresh, dict) and fresh.get("state_type"):
                fresh = _attach_play_context(fresh, action=body)
                if final_action == "select_card_reward" and isinstance(fresh, dict):
                    try:
                        from plugins.sts2.build_knowledge import record_card_pick
                        from plugins.sts2.reward_cards import offer_reward_cards

                        ix = int(body.get("card_index", 0))
                        offers = offer_reward_cards(fresh) or offer_reward_cards(
                            live_state or {}
                        )
                        picked = next(
                            (
                                c
                                for c in offers
                                if isinstance(c, dict) and c.get("index") == ix
                            ),
                            {},
                        )
                        record_card_pick(
                            fresh,
                            str(picked.get("id") or ""),
                            index=ix,
                        )
                    except Exception:
                        pass
                if fresh.get("learn_reflect"):
                    extra["learn_reflect"] = fresh["learn_reflect"]
                try:
                    from plugins.sts2.combat_turn_plan import check_after_action

                    warns = check_after_action(live_state or {}, fresh, body)
                    if warns:
                        extra["combat_plan_warnings"] = warns
                        pb = str(fresh.get("play_brief") or "")
                        fresh["play_brief"] = (
                            pb
                            + "\n\n【上一步提醒】"
                            + " | ".join(warns)
                        )
                except Exception:
                    pass
                extra["_fresh_state"] = fresh
                extra["play_brief"] = fresh.get("play_brief", "")
                fsm_fresh = fresh.get("combat_fsm") or {}
                extra["combat_fsm"] = fsm_fresh
                extra["think_required"] = fsm_fresh.get("think_required", False)
                extra["combat_think"] = fsm_fresh.get("think")
                extra["state_settle"] = settle_meta
                if not settle_meta.get("settled"):
                    extra["play_brief"] = (
                        str(extra.get("play_brief") or "")
                        + "\n\n【注意】"
                        + str(settle_meta.get("note") or "状态可能未刷新完。")
                    )
        except Exception:
            pass

    if isinstance(payload, dict):
        return tool_result(
            success=True,
            http_status=status,
            **payload,
            **extra,
        )
    return tool_result(success=status == 200, http_status=status, data=payload, **extra)


def handle_sts2_wiki_search(args: dict[str, Any], **kwargs: Any) -> str:
    query = str(args.get("query") or "").strip()
    if not query:
        return tool_error('Missing required "query"')
    item_type = str(args.get("item_type") or "all").strip().lower()
    try:
        limit = int(args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(25, limit))

    try:
        status, payload = sts2_client.wiki_search(
            query, item_type=item_type, limit=limit
        )
    except ConnectionError as exc:
        return tool_error(str(exc))
    except Exception as exc:
        return tool_error(f"sts2_wiki_search failed: {type(exc).__name__}: {exc}")
    return _http_result(status, payload)


def handle_sts2_setup_status(args: dict[str, Any], **kwargs: Any) -> str:
    from plugins.sts2.config import load_sts2_config
    from plugins.sts2.paths import find_game_dir, mods_dir

    cfg = load_sts2_config()
    game = find_game_dir()
    mod_ok = False
    if game:
        mdir = mods_dir(game)
        mod_ok = (mdir / "STS2_MCP.dll").is_file() or any(
            mdir.glob("*MCP*.dll")
        )

    ping_ok = False
    ping_message = ""
    try:
        payload = sts2_client.ping()
        ping_ok = True
        ping_message = str(payload.get("message", payload))
    except Exception as exc:
        ping_message = str(exc)

    mcp_configured = False
    try:
        from hermes_cli.config import load_config

        mcp_configured = bool((load_config().get("mcp_servers") or {}).get("sts2"))
    except Exception:
        pass

    try:
        from plugins.sts2.mode_display import structured_mode_status

        mode_info = structured_mode_status()
    except Exception:
        mode_info = {}

    from plugins.sts2.platform_home import detect_runtime_host, resolve_sts2_home

    host = detect_runtime_host()
    sts2_home = resolve_sts2_home(config_log_dir=str(cfg.get("log_dir") or ""))
    integration_hints = {
        "hermes": "hermes sts2 setup && hermes sts2 install-mod",
        "openclaw": "sts2 integration-config --platform openclaw",
        "astrbot": "sts2 integration-config --platform astrbot --json-only",
        "standalone": "sts2 integration-config --platform generic",
    }

    out: dict[str, Any] = dict(
        success=True,
        base_url=cfg.get("base_url"),
        commentary=cfg.get("commentary"),
        autoplay=cfg.get("autoplay"),
        runtime_host=host,
        sts2_home=str(sts2_home),
        sts2_mode=mode_info,
        mode_banner=mode_info.get("banner", ""),
        game_dir=str(game) if game else None,
        mods_dir=str(mods_dir(game)) if game else None,
        mod_dll_installed=mod_ok,
        http_ping_ok=ping_ok,
        http_ping_message=ping_message,
        mcp_server_configured=mcp_configured,
        skill="slay-the-spire-2",
        cli_hint=integration_hints.get(host, integration_hints["standalone"]),
    )
    try:
        from plugins.sts2.play_mode import mount_mode

        if mount_mode():
            out["mount_mode"] = True
            out["next_tools"] = [
                "sts2_ping",
                "sts2_get_state(summary=true)",
                "sts2_act",
            ]
            out["forbidden"] = (
                "sts2_autoplay run, terminal, search_files, read_file, Python HTTP"
            )
            if ping_ok:
                out["hint"] = "Mod 已连通：立刻 sts2_get_state(summary=true) 然后 sts2_act。"
            else:
                out["hint"] = (
                    "请先启动 Slay the Spire 2 并启用 STS2_MCP 模组，"
                    "然后 sts2_ping；不要用 terminal 写脚本连游戏。"
                )
    except Exception:
        pass
    return tool_result(**out)


def handle_sts2_get_profile(args: dict[str, Any], **kwargs: Any) -> str:
    try:
        status, payload = sts2_client.get_profile()
    except ConnectionError as exc:
        return tool_error(str(exc))
    except Exception as exc:
        return tool_error(f"sts2_get_profile failed: {type(exc).__name__}: {exc}")
    return _http_result(status, payload)


def handle_sts2_get_compendium(args: dict[str, Any], **kwargs: Any) -> str:
    try:
        status, payload = sts2_client.get_compendium()
    except ConnectionError as exc:
        return tool_error(str(exc))
    except Exception as exc:
        return tool_error(f"sts2_get_compendium failed: {type(exc).__name__}: {exc}")
    return _http_result(status, payload)


def handle_sts2_autoplay(args: dict[str, Any], **kwargs: Any) -> str:
    from plugins.sts2.autoplay import get_controller
    from plugins.sts2.play_mode import llm_step_context, marathon_blocked_message, mount_mode

    action = str(args.get("action") or "status").strip().lower()
    if mount_mode():
        if action in ("run", "study", "start", "step", "watch", "learn"):
            return tool_error(
                marathon_blocked_message(),
                mount_mode=True,
                use_instead=["sts2_ping", "sts2_get_state", "sts2_act"],
            )
        if action == "status":
            return tool_result(
                success=True,
                mount_mode=True,
                background_autopilot=False,
                hint=(
                    "挂载模式：请 sts2_ping → sts2_get_state(summary=true) → sts2_act，"
                    "不要用 sts2_autoplay。"
                ),
            )
    ctrl = get_controller()
    try:
        if action in ("run", "study", "start"):
            from plugins.sts2.play_mode import llm_marathon_allowed, marathon_blocked_message

            if not llm_marathon_allowed():
                return tool_error(
                    marathon_blocked_message(),
                    marathon_disabled=True,
                )
        if action in ("run", "study", "start"):
            from plugins.sts2.mode_display import ensure_autoplay_running

            out = ensure_autoplay_running(reason="user_run")
            if not out.get("started") and not out.get("running"):
                out = ctrl.start_study()
        elif action == "step":
            from plugins.sts2.play_mode import llm_marathon_allowed, marathon_blocked_message

            if not llm_marathon_allowed():
                return tool_error(marathon_blocked_message())
            with llm_step_context():
                out = ctrl.step_once()
        elif action == "pause":
            out = ctrl.pause(reason=str(args.get("reason") or ""))
        elif action == "resume":
            out = ctrl.resume()
        elif action == "stop":
            from plugins.sts2.manual_mode import release_all_driver_locks, set_manual_mode
            from plugins.sts2.play_mode import agent_play_mode

            out = ctrl.stop()
            release_all_driver_locks()
            if not agent_play_mode():
                set_manual_mode(True)
            else:
                set_manual_mode(False)
            out = dict(out) if isinstance(out, dict) else {"success": True}
            out["hint"] = (
                "代打已停止。手操：get_state → 思考 → sts2_act；"
                "再开代打：sts2_autoplay action=run"
            )
        elif action == "hint":
            hint = str(args.get("user_hint") or args.get("hint") or "").strip()
            if not hint:
                return tool_error("hint action requires user_hint")
            ctrl.provide_hint(hint)
            out = {"success": True, "hint_accepted": True}
        elif action == "watch":
            out = ctrl.start_watch()
        elif action == "learn":
            out = ctrl.start_learn()
        elif action == "status":
            from plugins.sts2.mode_display import structured_mode_status

            out = {"success": True, **ctrl.status(), "sts2_mode": structured_mode_status()}
        else:
            return tool_error(
                "action must be run | start | study | stop | pause | resume | "
                "step | status | hint | watch | learn"
            )
    except ConnectionError as exc:
        return tool_error(str(exc))
    except Exception as exc:
        return tool_error(f"sts2_autoplay failed: {type(exc).__name__}: {exc}")
    return tool_result(**out) if isinstance(out, dict) else tool_result(success=True, data=out)


def handle_sts2_recall(args: dict[str, Any], **kwargs: Any) -> str:
    from plugins.sts2.autoplay import get_controller
    from plugins.sts2.notes import recall_block
    from plugins.sts2.storage import live_feed_path

    block = recall_block()
    feed_tail = ""
    feed = live_feed_path()
    if feed.is_file():
        text = feed.read_text(encoding="utf-8")
        feed_tail = text[-4000:] if text else ""
    st = get_controller().status()
    from plugins.sts2.action_trace import read_action_log_tail

    return tool_result(
        success=True,
        memory=block or "(empty)",
        live_feed_tail=feed_tail,
        action_log_tail=read_action_log_tail(max_chars=4000),
        last_situation=st.get("last_situation") or "",
        last_action_trace=st.get("last_action_trace") or "",
        last_commentary=st.get("last_commentary") or "",
        autoplay_running=st.get("running"),
        watch_running=st.get("watching"),
        learn_running=st.get("learning"),
    )


def handle_sts2_learn(args: dict[str, Any], **kwargs: Any) -> str:
    from plugins.sts2.evolution_loop import (
        approve_pending_rules,
        evolution_summary_for_status,
        read_pending,
        reject_pending_rules,
    )
    from plugins.sts2.manual_learn import build_learn_context

    act = str(args.get("action") or "pending").strip().lower()
    if act == "status":
        return tool_result(
            success=True,
            summary=evolution_summary_for_status(),
            learn_context=build_learn_context(),
        )
    if act == "pending":
        pending = read_pending()
        return tool_result(
            success=True,
            pending=pending,
            hint="采纳: sts2_learn action=approve index=1 或聊天「采纳规则1」",
        )
    if act == "approve":
        if args.get("all"):
            return tool_result(success=True, **approve_pending_rules(all=True))
        idx = args.get("index")
        if idx is None:
            return tool_error("approve needs index (1-based) or all=true")
        return tool_result(
            success=True,
            **approve_pending_rules(indices=[int(idx) - 1]),
        )
    if act == "reject":
        if args.get("all"):
            return tool_result(success=True, **reject_pending_rules(all=True))
        idx = args.get("index")
        if idx is None:
            return tool_error("reject needs index (1-based) or all=true")
        return tool_result(
            success=True,
            **reject_pending_rules(indices=[int(idx) - 1]),
        )
    if act == "refresh_builds":
        from plugins.sts2.build_knowledge import refresh_web_build_cache

        return tool_result(success=True, **refresh_web_build_cache())
    if act == "build_profile":
        from plugins.sts2.build_analyzer import format_build_journal_tail
        from plugins.sts2.build_knowledge import _load_profile

        return tool_result(
            success=True,
            profile=_load_profile(),
            journal_tail=format_build_journal_tail(),
        )
    return tool_error(
        "action must be pending, approve, reject, status, refresh_builds, or build_profile"
    )


def handle_sts2_note(args: dict[str, Any], **kwargs: Any) -> str:
    from plugins.sts2.notes import append_hot_note, merge_strategy_rules, read_hot_notes

    mode = str(args.get("mode") or "append").strip().lower()
    if mode == "read":
        return tool_result(success=True, notes=read_hot_notes())
    body = str(args.get("body") or "").strip()
    section = str(args.get("section") or "note").strip()
    if not body:
        return tool_error("body required for append mode")
    append_hot_note(section, body)
    rules = args.get("rules")
    if isinstance(rules, list) and rules:
        merge_strategy_rules([str(r) for r in rules])
    return tool_result(success=True, appended=True, section=section)


STS2_PING_SCHEMA = {
    "name": "sts2_ping",
    "description": (
        "Check STS2MCP mod connectivity (Slay the Spire 2 must be running with mod enabled). "
        f"{_PLAY_LOOP}"
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}

STS2_GET_STATE_SCHEMA = {
    "name": "sts2_get_state",
    "description": (
        "OBSERVE only — YOU are the sole decider. summary=true returns agent_contract, "
        "play_brief (facts/wiki/math), combat_fsm snapshots (think_required=you must rethink), "
        "survival_snapshot, legal_actions. No background autoplay; no substitute LLM in agent mode. "
        f"{_PLAY_LOOP}"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "enum": ["json", "markdown"],
                "description": "Response format (default json).",
            },
            "summary": {
                "type": "boolean",
                "description": "Required for play: situation + play_brief + delta (default on).",
                "default": True,
            },
        },
        "additionalProperties": False,
    },
}

STS2_OBSERVE_SCHEMA = {
    "name": "sts2_observe",
    "description": (
        "Readable board snapshot and what changed since last observe "
        "(your manual plays or bot autoplay). Use while chatting to see 出牌/运营."
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}

STS2_ACT_SCHEMA = {
    "name": "sts2_act",
    "description": (
        "Execute YOUR chosen action. Agent mode: no card_index substitution, no survival veto. "
        "Returns fresh state + play_brief after animation settle. "
        "Combat: one action per call; same turn = multiple calls until energy gone. "
        "Event: choose_event_option or advance_dialogue (not menu_select). "
        "Crystal sphere: crystal_sphere_click_cell(x,y), crystal_sphere_set_tool(tool), "
        "crystal_sphere_proceed (not proceed/divine/big). "
        f"{_PLAY_LOOP}"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action name from API docs (play_card, end_turn, proceed, ...).",
            },
            "parameters": {
                "type": "object",
                "description": "Optional extra fields merged into the POST body.",
            },
            "card_index": {"type": "integer"},
            "target": {
                "type": "string",
                "description": "Combat target entity_id when required.",
            },
            "index": {"type": "integer"},
            "slot": {"type": "integer"},
            "option": {"type": "string"},
            "seed": {"type": "string"},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "tool": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}

STS2_WIKI_SEARCH_SCHEMA = {
    "name": "sts2_wiki_search",
    "description": (
        "Search STS2 in-game wiki (cards/relics/enemies). Use item_type=enemy for elites "
        "e.g. query='Phantasmal Gardener'. Required when 【怪物Wiki】 is empty. "
        "Use when you need card/relic rules text outside the current combat hand."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search text."},
            "item_type": {
                "type": "string",
                "enum": ["all", "card", "relic"],
                "description": "Filter (default all).",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (1-25, default 10).",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

STS2_SETUP_STATUS_SCHEMA = {
    "name": "sts2_setup_status",
    "description": (
        "Diagnose STS2 integration: game path, mod files, HTTP ping, MCP config. "
        "Works without an active run; use before first autoplay session."
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}

STS2_GET_PROFILE_SCHEMA = {
    "name": "sts2_get_profile",
    "description": "Read STS2 profile progress (discoveries, stats) via STS2MCP.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}

STS2_GET_COMPENDIUM_SCHEMA = {
    "name": "sts2_get_compendium",
    "description": (
        "Read Compendium-shaped profile data (cards, relics, run history) via STS2MCP."
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}

STS2_AUTOPLAY_SCHEMA = {
    "name": "sts2_autoplay",
    "description": (
        "STS2 LLM autopilot until FULL_RUN_CLEARED. action=run|study|start begins background "
        "play; pause|resume|stop|hint|status control it. sts2_act pauses autopilot for manual moves."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "run",
                    "start",
                    "study",
                    "stop",
                    "pause",
                    "resume",
                    "step",
                    "status",
                    "hint",
                    "watch",
                    "learn",
                ],
                "description": (
                    "run|study|start=LLM autopilot until victory; pause|resume; stop=halt; "
                    "hint=user tactic; status; step=one LLM step; watch/learn=spectate only."
                ),
            },
            "max_steps": {
                "type": "integer",
                "description": "Max steps when action=start (default from config).",
            },
            "user_hint": {
                "type": "string",
                "description": "User instruction or answer to resume after pause.",
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}

STS2_RECALL_SCHEMA = {
    "name": "sts2_recall",
    "description": (
        "Load hot_notes, strategy, live_feed (recent 出牌/运营解说), and last_situation."
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}

STS2_LEARN_SCHEMA = {
    "name": "sts2_learn",
    "description": (
        "Manual-play evolution: list/approve/reject pending rules learned from runs. "
        "Rules enter strategy only after you approve (or chat 采纳规则1 / 采纳全部)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["pending", "approve", "reject", "status"],
                "description": "pending=list; approve/reject with index or all=true.",
            },
            "index": {
                "type": "integer",
                "description": "1-based rule index for approve/reject.",
            },
            "all": {
                "type": "boolean",
                "description": "Approve or reject all pending rules.",
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}

STS2_NOTE_SCHEMA = {
    "name": "sts2_note",
    "description": "Append or read STS2 hot_notes; optional rules merge into strategy.yaml.",
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["append", "read"]},
            "section": {"type": "string"},
            "body": {"type": "string"},
            "rules": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    },
}
