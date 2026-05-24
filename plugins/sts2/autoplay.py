"""Background autoplay controller with per-turn commentary."""

from __future__ import annotations

import importlib
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from plugins.sts2 import client as sts2_client
from plugins.sts2 import decision as _sts2_decision
from plugins.sts2 import driver_lock
from plugins.sts2.action_trace import append_action_log, format_action_trace
from plugins.sts2.config import load_sts2_config
from plugins.sts2.lessons import finalize_trajectory, lessons_summary_for_prompt
from plugins.sts2.reflect import reflect_if_changed
from plugins.sts2.rewards import compute_step_reward
from plugins.sts2.storage import live_feed_path, pending_question_path
from plugins.sts2.trajectory import current_path, log_event, start_session
from plugins.sts2.visibility import (
    describe_situation,
    format_turn_commentary,
    state_fingerprint,
)

logger = logging.getLogger(__name__)

EmitFn = Callable[[str], None]


@dataclass
class AutoplayStatus:
    running: bool = False
    steps: int = 0
    last_commentary: str = ""
    last_situation: str = ""
    last_action_trace: str = ""
    last_state_type: str = ""
    watching: bool = False
    learning: bool = False
    studying: bool = False
    trajectory: str = ""
    paused: bool = False
    pause_reason: str = ""
    errors: list[str] = field(default_factory=list)


class AutoplayController:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._status = AutoplayStatus()
        self._emit: EmitFn | None = None
        self._prev_state: dict[str, Any] | None = None
        self._recent_actions: list[dict[str, Any]] = []
        self._repeat_hash = ""
        self._repeat_count = 0
        self._user_hint = ""
        self._last_observed_state: dict[str, Any] | None = None
        self._last_fingerprint: str = ""
        self._coach = None
        self._consecutive_failures = 0
        self._runs_completed = 0
        self._was_in_run = False
        self._last_restart_fp = ""
        self._menu_stuck_fp = ""
        self._menu_stuck_count = 0
        self._lesson_cast_fps: set[str] = set()
        self._potion_fail_streak = 0

    def set_emit(self, fn: EmitFn | None) -> None:
        self._emit = fn

    def status(self) -> dict[str, Any]:
        with self._lock:
            s = self._status
            return {
                "running": s.running,
                "steps": s.steps,
                "last_commentary": s.last_commentary,
                "last_situation": s.last_situation,
                "last_action_trace": s.last_action_trace,
                "last_state_type": s.last_state_type,
                "watching": s.watching,
                "learning": s.learning,
                "studying": s.studying,
                "paused": s.paused,
                "pause_reason": s.pause_reason,
                "trajectory": s.trajectory,
                "errors": list(s.errors[-5:]),
            }

    def start_study(
        self, *, max_steps: int | None = None, announce: bool = True
    ) -> dict[str, Any]:
        """Study autoplay: LLM decides + rules validate; lessons on death."""
        from plugins.sts2.play_mode import rule_marathon_allowed, rule_marathon_blocked_message

        if not rule_marathon_allowed():
            return {
                "success": False,
                "error": rule_marathon_blocked_message(),
                "rule_marathon": "disabled",
            }

        from plugins.sts2.manual_mode import set_manual_mode
        from plugins.sts2.study_mode import set_study_mode

        set_manual_mode(False)
        cfg = load_sts2_config()
        with self._lock:
            if self._status.running or self._status.watching or self._status.learning:
                return {"success": False, "error": "sts2 session already active"}
        from plugins.sts2.config import enforce_single_driver_enabled

        if enforce_single_driver_enabled(cfg) and not driver_lock.acquire("autoplay"):
            from plugins.sts2.process_lock import live_holder_pid
            from plugins.sts2.storage import sts2_home

            lock_path = sts2_home() / ".autoplay.lock"
            if live_holder_pid(lock_path) is not None:
                return {
                    "success": False,
                    "error": "sts2 driver busy — stop watch/learn/autoplay first",
                }
            # Recover stale in-process / orphaned lock after crashed study thread
            if not self._status.running and not self._status.studying:
                driver_lock.release("autoplay")
                try:
                    from plugins.sts2.process_lock import release as release_pl

                    release_pl()
                    lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
            if not driver_lock.acquire("autoplay"):
                return {
                    "success": False,
                    "error": "sts2 driver busy — stop watch/learn/autoplay first",
                }
        with self._lock:
            self._stop.clear()
            self._status = AutoplayStatus(running=True, studying=True)
            self._prev_state = None
            self._recent_actions = []
            self._repeat_count = 0
            path = start_session()
            self._status.trajectory = str(path)

        set_study_mode(True)
        limit = max_steps or int(cfg.get("max_steps_per_run", 500))

        def _run() -> None:
            set_study_mode(True)
            try:
                self._loop_marathon(limit)
            except Exception as exc:
                self._record_error(exc)
                self._cast(
                    f"【STS2·代打已停】{type(exc).__name__}: {exc}\n"
                    "修复后请 sts2_autoplay action=run 重开，或重启 Hermes。"
                )
                try:
                    from plugins.sts2.mode_display import emit_mode_banner_to_tui

                    emit_mode_banner_to_tui(force=True)
                except Exception:
                    pass
            finally:
                set_study_mode(False)
                with self._lock:
                    self._status.running = False
                    self._status.studying = False
                from plugins.sts2.config import enforce_single_driver_enabled

                if enforce_single_driver_enabled():
                    driver_lock.release("autoplay")

        from plugins.sts2.act1_clear import bootstrap_win_focus_rules
        from plugins.sts2.autonomy import clear_user_wait_state
        from plugins.sts2.evolution_loop import begin_run, bootstrap_evolution_store
        from plugins.sts2.lessons import bootstrap_learning_store
        from plugins.sts2.run_victory import bootstrap_full_run_rules

        clear_user_wait_state()
        bootstrap_learning_store()
        bootstrap_full_run_rules()
        bootstrap_win_focus_rules()
        bootstrap_evolution_store()
        try:
            from plugins.sts2.source_paths import write_source_pointer

            write_source_pointer()
        except Exception:
            pass
        begin_run()
        try:
            from plugins.sts2.coach_channel import ensure_coach_files

            ensure_coach_files()
        except Exception:
            pass
        summary = lessons_summary_for_prompt()
        if announce:
            try:
                from plugins.sts2.mode_display import emit_mode_banner_to_tui

                emit_mode_banner_to_tui(force=True)
            except Exception:
                pass
            self._cast(
                "【STS2·一口气代打】已启动 → FULL_RUN_CLEARED。"
                " pause|resume|stop|hint|status；聊天不打断（手操 sts2_act 会 pause）。"
            )
        self._thread = threading.Thread(target=_run, name="sts2-study", daemon=True)
        self._thread.start()
        return {
            "success": True,
            "studying": True,
            "trajectory": self._status.trajectory,
            "max_steps": limit,
            "lessons_loaded": bool(summary),
        }

    def start(self, *, max_steps: int | None = None, user_hint: str = "") -> dict[str, Any]:
        """Alias for start_study (LLM autoplay until victory)."""
        return self.start_study(max_steps=max_steps, announce=True)

    def _start_rule_loop(self, *, max_steps: int | None = None, user_hint: str = "") -> dict[str, Any]:
        cfg = load_sts2_config()
        with self._lock:
            if self._status.running or self._status.watching or self._status.learning:
                return {"success": False, "error": "sts2 session already active"}
        from plugins.sts2.config import enforce_single_driver_enabled

        if enforce_single_driver_enabled(cfg) and not driver_lock.acquire("autoplay"):
            return {
                "success": False,
                "error": "sts2 driver busy — stop manual sts2_act loops or other autoplay first",
            }
        with self._lock:
            self._stop.clear()
            self._status = AutoplayStatus(running=True)
            self._user_hint = user_hint
            path = start_session()
            self._status.trajectory = str(path)
            self._prev_state = None
            self._recent_actions = []
            self._repeat_count = 0

        cfg = load_sts2_config()
        limit = max_steps or int(cfg.get("max_steps_per_run", 500))

        def _run() -> None:
            try:
                self._loop(limit)
            except Exception as exc:
                self._record_error(exc)
            finally:
                with self._lock:
                    self._status.running = False
                from plugins.sts2.config import enforce_single_driver_enabled

                if enforce_single_driver_enabled():
                    driver_lock.release("autoplay")

        summary = lessons_summary_for_prompt()
        if summary:
            self._cast(f"[STS2] 跨局经验已加载:\n{summary[:600]}")

        self._thread = threading.Thread(target=_run, name="sts2-autoplay", daemon=True)
        self._thread.start()
        out: dict[str, Any] = {
            "success": True,
            "trajectory": self._status.trajectory,
            "max_steps": limit,
        }
        if summary:
            out["lessons_loaded"] = True
        return out

    def pause(self, *, reason: str = "") -> dict[str, Any]:
        with self._lock:
            self._status.paused = True
            if reason:
                self._status.pause_reason = reason[:500]
        try:
            from plugins.sts2.mode_display import emit_mode_banner_to_tui

            emit_mode_banner_to_tui(force=True)
        except Exception:
            pass
        return {"success": True, "paused": True, "pause_reason": self._status.pause_reason}

    def resume(self) -> dict[str, Any]:
        pending_question_path().unlink(missing_ok=True)
        with self._lock:
            self._status.paused = False
            self._status.pause_reason = ""
        try:
            from plugins.sts2.mode_display import emit_mode_banner_to_tui

            emit_mode_banner_to_tui(force=True)
        except Exception:
            pass
        return {"success": True, "paused": False}

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        with self._lock:
            self._status.running = False
            self._status.watching = False
            self._status.learning = False
            self._status.studying = False
            self._status.paused = False
            self._status.pause_reason = ""
        self._coach = None
        from plugins.sts2.study_mode import set_study_mode

        set_study_mode(False)
        try:
            from plugins.sts2.tui_cast_dedupe import reset_meta_banners

            reset_meta_banners()
        except Exception:
            pass
        from plugins.sts2.manual_mode import release_all_driver_locks, set_manual_mode
        from plugins.sts2.play_mode import autopilot_enabled

        release_all_driver_locks()
        if not autopilot_enabled():
            set_manual_mode(True)
        try:
            from plugins.sts2.mode_display import emit_mode_banner_to_tui

            emit_mode_banner_to_tui(force=True)
        except Exception:
            pass
        return {
            "success": True,
            "stopped": True,
            "manual_mode": not autopilot_enabled(),
        }

    def start_learn(self) -> dict[str, Any]:
        """Watch user play; ask at end of turn when confused; save answers as style rules."""
        from plugins.sts2.learn_coach import LearnCoach

        with self._lock:
            if self._status.running or self._status.watching or self._status.learning:
                return {"success": False, "error": "sts2 session already active"}
        with self._lock:
            self._stop.clear()
            self._status = AutoplayStatus(learning=True)
            self._last_observed_state = None
            self._last_fingerprint = ""
            self._coach = LearnCoach()
            path = start_session()
            self._status.trajectory = str(path)

        def _run() -> None:
            try:
                self._learn_loop()
            except Exception as exc:
                self._record_error(exc)
            finally:
                with self._lock:
                    self._status.learning = False
                self._coach = None

        self._thread = threading.Thread(target=_run, name="sts2-learn", daemon=True)
        self._thread.start()
        self._cast(
            "学习模式已开：你在游戏里正常操作即可。\n"
            "每回合结束若我看不懂会提问；在聊天里回答，并执行 "
            "sts2_autoplay action=hint 把你的思路传给我（会写入打法笔记）。"
        )
        return {"success": True, "learning": True, "trajectory": self._status.trajectory}

    def start_watch(self) -> dict[str, Any]:
        """Poll game state and narrate changes (user plays manually; no sts2_act)."""
        with self._lock:
            if self._status.running or self._status.watching or self._status.learning:
                return {"success": False, "error": "sts2 session already active"}
        with self._lock:
            self._stop.clear()
            self._status = AutoplayStatus(watching=True)
            self._last_observed_state = None
            self._last_fingerprint = ""

        def _run() -> None:
            try:
                self._watch_loop()
            except Exception as exc:
                self._record_error(exc)
            finally:
                with self._lock:
                    self._status.watching = False

        self._thread = threading.Thread(target=_run, name="sts2-watch", daemon=True)
        self._thread.start()
        self._cast("旁观模式：会播报你的出牌与运营（不代打）。")
        return {"success": True, "watching": True}

    def provide_hint(self, text: str) -> None:
        from plugins.sts2.learn_coach import absorb_user_answer

        answer = (text or "").strip()
        pending = pending_question_path()
        if pending.is_file() and answer:
            try:
                data = json.loads(pending.read_text(encoding="utf-8"))
                if data.get("mode") == "learn":
                    q = str(data.get("question") or "")
                    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
                    out = absorb_user_answer(q, answer, meta=meta)
                    if out.get("saved"):
                        self._cast(f"已记录你的打法：{answer[:120]}")
            except Exception as exc:
                logger.debug("learn hint: %s", exc)
        self._user_hint = answer
        pending.unlink(missing_ok=True)
        with self._lock:
            self._status.paused = False
            self._status.pause_reason = ""

    def step_once(self, *, user_hint: str = "") -> dict[str, Any]:
        """Single synchronous step (for tool action=step)."""
        if user_hint:
            self._user_hint = user_hint
        return self._single_step()

    def _record_error(self, exc: BaseException) -> None:
        msg = f"{type(exc).__name__}: {exc}"
        logger.warning("sts2 autoplay: %s", msg)
        with self._lock:
            self._status.errors.append(msg)
        try:
            from plugins.sts2.program_health import report_exception

            report_exception(exc, context={"where": "autoplay"})
        except Exception:
            pass

    def _emit_reflection(self, refl: dict[str, Any]) -> None:
        from plugins.sts2.reflection_journal import format_reflection_cast

        line = format_reflection_cast(refl)
        if line:
            self._cast(line)
        elif refl.get("recorded") and refl.get("rule"):
            self._cast(f"【教训已写入】{refl.get('rule', '')[:320]}")

    def _cast(self, text: str) -> None:
        line = text.strip()
        if not line:
            return
        with self._lock:
            if line == self._status.last_commentary:
                return
            if "【本局记忆】" in line and "【本局记忆】" in self._status.last_commentary:
                return
            self._status.last_commentary = line
        try:
            feed = live_feed_path()
            with feed.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass
        delivered = False
        try:
            from plugins.sts2.tui_bridge import deliver_to_tui

            delivered = bool(deliver_to_tui(line))
        except Exception:
            pass
        if self._emit and not delivered:
            try:
                self._emit(f"[STS2] {line}")
            except Exception:
                pass

    def _reload_decision(self) -> None:
        """Reload decision + card_pick_brain modules from disk if changed."""
        import sys
        for modname in ('plugins.sts2.decision', 'plugins.sts2.card_pick_brain'):
            mod = sys.modules.get(modname)
            if not mod:
                continue
            fname = getattr(mod, '__file__', None) or getattr(mod, '_DECISION_FILE', None)
            if not fname:
                continue
            import os
            try:
                mtime = os.path.getmtime(fname)
            except (OSError, TypeError):
                continue
            attr = '_' + modname.replace('.', '_') + '_mtime'
            if mtime > getattr(self, attr, 0.0):
                setattr(self, attr, mtime)
                importlib.reload(mod)

    def _single_step(self) -> dict[str, Any]:
        self._reload_decision()
        cfg = load_sts2_config()
        status, state = sts2_client.get_singleplayer_state(fmt="json")
        if status != 200 or not isinstance(state, dict):
            return {"success": False, "error": f"get_state HTTP {status}", "body": state}

        study = self._status.studying
        state_for_decide = dict(state)
        if study or cfg.get("autopilot_attach_decision_brief", True):
            try:
                from plugins.sts2.decision_context import assemble_play_brief

                state_for_decide["_decision_brief"] = assemble_play_brief(state)
            except Exception:
                pass
        if study or cfg.get("auto_curate_knowledge", True):
            try:
                from plugins.sts2.knowledge_curator import curate_from_state

                cr = curate_from_state(
                    state,
                    use_llm=bool(cfg.get("knowledge_use_llm", True)),
                )
                for rule in (cr.get("rules_added") or [])[:2]:
                    self._cast(f"【自学Wiki】{rule[:280]}")
            except Exception as exc:
                logger.debug("knowledge curate: %s", exc)

        use_llm = bool(study and cfg.get("study_reflect_use_llm", True))
        refl = reflect_if_changed(
            self._prev_state,
            state,
            recent_actions=self._recent_actions,
            use_llm=use_llm,
        )
        self._emit_reflection(refl)

        coach_hint = ""
        if study and cfg.get("study_coach_channel", True):
            try:
                from plugins.sts2.coach_channel import acknowledge_hint, poll_coach_hint

                coach_hint = poll_coach_hint()
                if coach_hint:
                    self._user_hint = (
                        f"{self._user_hint}\n{coach_hint}".strip()
                        if self._user_hint
                        else coach_hint
                    )
                    run = state.get("run") or {}
                    acknowledge_hint(
                        coach_hint,
                        state_type=str(state.get("state_type") or ""),
                        floor=int(run.get("floor") or 0),
                    )
                    self._cast(f"【教练·已读】{coach_hint[:280]}")
            except Exception:
                pass

        commentary, body = _sts2_decision.decide(
            state_for_decide,
            user_hint=self._user_hint,
            recent_actions=self._recent_actions,
        )
        self._user_hint = ""

        from plugins.sts2.action_validate import validate_action

        body = validate_action(state, body)

        if body.get("action") == "__pause__":
            from plugins.sts2.autonomy import autopilot_until_victory, resolve_without_user

            if autopilot_until_victory() or self._status.studying:
                if commentary and commentary.strip():
                    try:
                        from plugins.sts2.thinking_policy import format_feed_thinking

                        self._cast(
                            format_feed_thinking(
                                commentary,
                                "（上一步思考未能执行，改用规则兜底）",
                            )
                        )
                    except Exception:
                        self._cast(commentary[:1200])
                auto_comm, body = resolve_without_user(state)
                body = validate_action(state, body)
                from plugins.sts2.visibility import describe_action

                try:
                    from plugins.sts2.thinking_policy import format_feed_thinking

                    self._cast(
                        format_feed_thinking(
                            f"【规则兜底】{auto_comm}",
                            describe_action(state, body),
                        )
                    )
                except Exception:
                    self._cast(f"【规则兜底】{auto_comm}\n▶ {describe_action(state, body)}")
                log_event(
                    "autopilot_no_ask",
                    {"was_pause": True, "state_type": state.get("state_type"), "action": body.get("action")},
                )
            else:
                self._cast(commentary)
                self._write_pending(commentary, state)
                with self._lock:
                    self._status.paused = True
                    self._status.pause_reason = commentary
                log_event("pause", {"commentary": commentary, "state_type": state.get("state_type")})
                return {
                    "success": True,
                    "paused": True,
                    "commentary": commentary,
                    "state_type": state.get("state_type"),
                }

        st = str(state.get("state_type") or "")
        if body.get("action") in ("__wait__",) or (
            body.get("action") == "proceed" and st in ("monster", "elite", "boss")
        ):
            time.sleep(0.35)
            self._prev_state = state
            return {
                "success": True,
                "skipped": True,
                "commentary": "等待战斗状态刷新…",
                "state_type": st,
            }

        act_status, act_payload, act_ok = self._execute_action(state, body)
        err_msg = ""
        if not act_ok and isinstance(act_payload, dict):
            err_msg = str(act_payload.get("message") or act_payload.get("error") or "")

        post_state: dict[str, Any] | None = None
        if act_ok:
            try:
                _, post_state = sts2_client.get_singleplayer_state(fmt="json")
                if not isinstance(post_state, dict):
                    post_state = None
            except Exception:
                post_state = None

        # Rewards screen: claim can succeed but stay on rewards — chain proceed once.
        if (
            act_ok
            and body.get("action") == "claim_reward"
            and st == "rewards"
            and isinstance(post_state, dict)
            and str(post_state.get("state_type") or "") == "rewards"
        ):
            rw = post_state.get("rewards") or {}
            if rw.get("can_proceed", True):
                proceed_body = {"action": "proceed"}
                p_status, p_payload, p_ok = self._execute_action(post_state, proceed_body)
                if p_ok:
                    try:
                        _, post_state = sts2_client.get_singleplayer_state(fmt="json")
                    except Exception:
                        pass
                    self._recent_actions.append(proceed_body)
                    body = proceed_body
                    act_ok = p_ok
                    act_status = p_status
                    act_payload = p_payload

        try:
            full_commentary = format_turn_commentary(
                state,
                body,
                act_ok=act_ok,
                post_state=post_state,
                err_msg=err_msg,
            )
        except Exception as exc:
            logger.warning("commentary format failed: %s", exc)
            full_commentary = f"【{st}】▶ {body.get('action', '?')}"
        try:
            from plugins.sts2.thinking_policy import format_feed_thinking

            feed_line = format_feed_thinking(commentary, full_commentary)
        except Exception:
            feed_line = full_commentary
            if study and commentary and commentary.strip() not in feed_line:
                feed_line = f"{commentary.strip()}\n\n{full_commentary}"
        self._cast(feed_line)
        if study and cfg.get("study_write_thinking_trace", True):
            try:
                from plugins.sts2.coach_channel import append_thinking

                run = state.get("run") or {}
                append_thinking(
                    commentary=commentary or feed_line,
                    action=body,
                    state_type=st,
                    floor=int(run.get("floor") or 0),
                    act=int(run.get("act") or 1),
                    user_hint=coach_hint,
                )
            except Exception:
                pass
        self._remember_state(post_state or state)
        from plugins.sts2.run_flow import in_run

        if in_run(post_state or state):
            self._was_in_run = True

        if study:
            try:
                from plugins.sts2.agent_learn import tick_after_step

                tick_after_step(post_state or state, action=body)
            except Exception:
                pass

        if not act_ok and err_msg:
            from plugins.sts2.lessons import record_action_failure

            if body.get("action") == "use_potion":
                self._potion_fail_streak += 1
            else:
                self._potion_fail_streak = 0

            fail = record_action_failure(state, body, err_msg)
            if fail and fail.get("promoted"):
                fp = str(fail.get("failure_fingerprint") or fail.get("rule") or "")
                if fp and fp not in self._lesson_cast_fps:
                    self._lesson_cast_fps.add(fp)
                    if len(self._lesson_cast_fps) > 40:
                        self._lesson_cast_fps = set(list(self._lesson_cast_fps)[-20:])
                    self._cast(f"【教训已写入】{fail.get('rule', '')[:280]}")

        effective = post_state if isinstance(post_state, dict) else state
        if effective is not state:
            refl2 = reflect_if_changed(
                state,
                effective,
                recent_actions=self._recent_actions + [body],
                use_llm=use_llm,
            )
            self._emit_reflection(refl2)

        reward = compute_step_reward(self._prev_state, state, act_ok=act_ok)
        try:
            from plugins.sts2.evolution_loop import accumulate_step_reward

            accumulate_step_reward(
                reward,
                post_state if isinstance(post_state, dict) else state,
                act_ok=act_ok,
            )
        except Exception:
            pass
        log_event(
            "step",
            {
                "commentary": commentary,
                "action": body,
                "act_ok": act_ok,
                "reward": reward,
                "state_type": state.get("state_type"),
                "http_status": act_status,
                "result": act_payload,
            },
        )
        self._recent_actions.append(body)
        if len(self._recent_actions) > 24:
            self._recent_actions = self._recent_actions[-24:]
        import copy

        self._prev_state = copy.deepcopy(effective)
        self._track_repeat(effective, act_ok=act_ok, body=body)

        with self._lock:
            self._status.steps += 1
            self._status.last_state_type = str(state.get("state_type") or "")

        return {
            "success": act_ok,
            "commentary": full_commentary,
            "situation": describe_situation(post_state or state),
            "action": body,
            "reward": reward,
            "state_type": (post_state or state).get("state_type"),
            "act_result": act_payload,
        }

    def _remember_state(
        self, state: dict[str, Any], *, action_trace: str = ""
    ) -> None:
        self._last_observed_state = state
        self._last_fingerprint = state_fingerprint(state)
        with self._lock:
            self._status.last_situation = describe_situation(state)
            if action_trace:
                self._status.last_action_trace = action_trace

    def observe_once(self) -> dict[str, Any]:
        """One-shot snapshot + delta (for sts2_observe / sts2_get_state summary)."""
        from plugins.sts2.visibility import describe_delta

        status, state = sts2_client.get_singleplayer_state(fmt="json")
        if status != 200 or not isinstance(state, dict):
            return {"success": False, "error": f"get_state HTTP {status}", "body": state}
        fp = state_fingerprint(state)
        changed = fp != self._last_fingerprint
        action_trace = ""
        if self._last_observed_state:
            action_trace = format_action_trace(self._last_observed_state, state)
            if action_trace:
                append_action_log(action_trace)
        delta = action_trace or (
            describe_delta(self._last_observed_state, state)
            if self._last_observed_state
            else ""
        )
        self._remember_state(state, action_trace=action_trace)
        return {
            "success": True,
            "situation": describe_situation(state),
            "action_trace": action_trace,
            "delta": delta,
            "changed": changed or bool(action_trace),
            "fingerprint": fp,
            "state_type": state.get("state_type"),
        }

    def _watch_loop(self) -> None:
        from plugins.sts2.visibility import describe_delta

        interval = float(load_sts2_config().get("watch_interval_seconds", 0.65))
        prev_state: dict[str, Any] | None = None
        prev_fp = ""
        while not self._stop.is_set():
            status, state = sts2_client.get_singleplayer_state(fmt="json")
            if status != 200 or not isinstance(state, dict):
                time.sleep(interval)
                continue
            fp = state_fingerprint(state)
            if fp != prev_fp:
                trace = (
                    format_action_trace(prev_state, state) if prev_state else ""
                )
                if trace:
                    append_action_log(trace)
                block = describe_situation(state)
                if trace:
                    block = f"{trace}\n\n{block}"
                elif prev_state:
                    delta = describe_delta(prev_state, state)
                    if delta:
                        block = f"【变化】{delta}\n{block}"
                self._cast(block)
                self._remember_state(state, action_trace=trace)
                prev_state = state
                prev_fp = fp
            time.sleep(interval)

    def _track_repeat(
        self, state: dict[str, Any], *, act_ok: bool, body: dict[str, Any] | None = None
    ) -> None:
        cfg = load_sts2_config()
        action = str((body or {}).get("action") or "")
        st = str(state.get("state_type") or "")
        if action in ("__wait__",) or (action == "proceed" and st in ("monster", "elite", "boss")):
            return
        h = json.dumps(
            {"state_type": state.get("state_type"), "run": state.get("run")},
            sort_keys=True,
        )
        if act_ok:
            self._repeat_hash = h
            self._repeat_count = 0
            return
        if h == self._repeat_hash:
            self._repeat_count += 1
        else:
            self._repeat_hash = h
            self._repeat_count = 0
        if self._status.studying and self._repeat_count >= 5:
            self._repeat_count = 2
        limit = int(cfg.get("max_repeat_state", 3))
        if self._status.studying and cfg.get("study_marathon", True):
            if self._repeat_count >= limit:
                self._repeat_count = 0
                self._cast("软锁：跳过本步，继续循环（连打模式不退出）。")
            return
        if self._repeat_count >= limit:
            self._stop.set()
            self._cast("Stopping: repeated state detected (possible soft-lock).")

    def _write_pending(
        self,
        question: str,
        state: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
        mode: str = "",
    ) -> None:
        pending_question_path().write_text(
            json.dumps(
                {
                    "question": question,
                    "state_type": state.get("state_type"),
                    "meta": meta or {},
                    "mode": mode or ("learn" if self._status.learning else "autoplay"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _pause_for_question(
        self,
        question: str,
        state: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self._write_pending(question, state, meta=meta, mode="learn")
        with self._lock:
            self._status.paused = True
            self._status.pause_reason = question
        self._cast(question)
        log_event("learn_ask", {"question": question[:500], "meta": meta or {}})

    def _learn_loop(self) -> None:
        from plugins.sts2.visibility import describe_delta

        interval = float(load_sts2_config().get("watch_interval_seconds", 0.65))
        coach = self._coach
        prev_state: dict[str, Any] | None = None
        prev_fp = ""
        while not self._stop.is_set():
            with self._lock:
                if self._status.paused:
                    time.sleep(0.5)
                    continue
            status, state = sts2_client.get_singleplayer_state(fmt="json")
            if status != 200 or not isinstance(state, dict):
                time.sleep(interval)
                continue

            if coach:
                for ev in coach.tick(prev_state, state):
                    if ev.kind == "ask":
                        self._pause_for_question(ev.text, state, meta=ev.meta)
                        break

            fp = state_fingerprint(state)
            if fp != prev_fp:
                trace = (
                    format_action_trace(prev_state, state) if prev_state else ""
                )
                if trace:
                    append_action_log(trace)
                block = describe_situation(state)
                if trace:
                    block = f"{trace}\n\n{block}"
                elif prev_state:
                    delta = describe_delta(prev_state, state)
                    if delta:
                        block = f"【变化】{delta}\n{block}"
                self._cast(block)
                self._remember_state(state, action_trace=trace)
                prev_state = state
                prev_fp = fp
            elif prev_state is None:
                prev_state = state
                prev_fp = fp

            time.sleep(interval)
        self._cast("学习模式已停止。打法笔记在 hot_notes / strategy.yaml。")

    def _execute_action(
        self, state: dict[str, Any], body: dict[str, Any]
    ) -> tuple[int, Any, bool]:
        from plugins.sts2.action_validate import validate_action

        driver_lock.set_internal_act(True)
        try:
            if str(body.get("action") or "") in ("__wait__", "__pause__"):
                return 200, {"status": "ok", "local_skip": True}, True
            for attempt in range(3):
                body = validate_action(state, body)
                try:
                    act_status, act_payload = sts2_client.post_singleplayer_action(body)
                except ConnectionError as exc:
                    from plugins.sts2.program_health import report_exception

                    report_exception(exc, context={"where": "execute_action", "action": body})
                    return 0, {"error": str(exc)}, False
                act_ok = (
                    act_status == 200
                    and isinstance(act_payload, dict)
                    and act_payload.get("status") == "ok"
                )
                if act_ok or body.get("action") == "__wait__":
                    return act_status, act_payload, act_ok
                status, fresh = sts2_client.get_singleplayer_state(fmt="json")
                if status == 200 and isinstance(fresh, dict):
                    state = fresh
                    commentary, body = _sts2_decision.decide(state)
                    body = validate_action(state, body)
                else:
                    break
            return act_status, act_payload, False
        finally:
            driver_lock.set_internal_act(False)

    def _menu_burst(
        self,
        state: dict[str, Any],
        *,
        max_clicks: int = 12,
        announce: bool = False,
    ) -> bool:
        """Click through menus without counting a finished run."""
        from plugins.sts2.action_validate import validate_action
        from plugins.sts2.run_flow import in_run, menu_fingerprint, next_menu_action

        if in_run(state):
            self._was_in_run = True
            return True
        if announce:
            self._runs_completed += 1
            try:
                from plugins.sts2.evolution_loop import begin_run, finalize_run

                status, st = sts2_client.get_singleplayer_state(fmt="json")
                last = st if status == 200 and isinstance(st, dict) else state
                finalize_run(
                    label="run_end",
                    last_state=last,
                )
                begin_run()
            except Exception:
                pass
            self._cast(f"第 {self._runs_completed} 局结束，自动开新局…")
        for _ in range(max_clicks):
            if self._stop.is_set():
                return False
            status, state = sts2_client.get_singleplayer_state(fmt="json")
            if status != 200 or not isinstance(state, dict):
                time.sleep(0.8)
                continue
            if in_run(state):
                if announce:
                    self._cast("新局已开始。")
                self._was_in_run = True
                self._prev_state = None
                self._last_restart_fp = ""
                self._menu_stuck_fp = ""
                self._menu_stuck_count = 0
                return True
            fp = menu_fingerprint(state)
            if fp == self._menu_stuck_fp:
                self._menu_stuck_count += 1
            else:
                self._menu_stuck_fp = fp
                self._menu_stuck_count = 0
            ruled = next_menu_action(state) or _sts2_decision._rule_action(state)
            if self._menu_stuck_count >= 8 and ruled:
                if str(ruled.get("action")) == "menu_select":
                    ruled = {"action": "proceed"}
            if not ruled:
                ruled = {"action": "proceed"}
            ruled = validate_action(state, ruled)
            if ruled.get("action") == "__wait__":
                time.sleep(0.4)
                continue
            self._execute_action(state, ruled)
            time.sleep(0.55)
        return False

    def _maybe_restart_run(self, state: dict[str, Any]) -> bool:
        """After game_over / post-run menu — click through to a new run (configured character)."""
        from plugins.sts2.run_flow import in_run, menu_fingerprint, run_needs_restart

        st = str(state.get("state_type") or "")
        if st not in ("game_over", "menu") and not in_run(state):
            return False
        if in_run(state):
            self._was_in_run = True
            return True
        if not run_needs_restart(state, was_in_run=self._was_in_run):
            return self._menu_burst(state, max_clicks=14, announce=False)
        fp = menu_fingerprint(state)
        if fp == self._last_restart_fp:
            return self._menu_burst(state, max_clicks=14, announce=False)
        self._last_restart_fp = fp
        ok = self._menu_burst(state, max_clicks=45, announce=True)
        if ok:
            self._was_in_run = False
        return ok

    def _loop_marathon(self, max_steps: int) -> None:
        cfg = load_sts2_config()
        interval = float(cfg.get("step_interval_seconds", 0.55))
        max_fail = int(cfg.get("max_consecutive_failures", 25))
        loop_runs = bool(cfg.get("loop_runs", True))
        step = 0
        try:
            while step < max_steps and not self._stop.is_set():
                with self._lock:
                    if self._status.paused:
                        time.sleep(0.5)
                        continue
                with self._lock:
                    if not self._status.running:
                        break
                result = self._single_step()
                step += 1
                if result.get("paused"):
                    from plugins.sts2.autonomy import autopilot_until_victory

                    if autopilot_until_victory():
                        with self._lock:
                            self._status.paused = False
                            self._status.pause_reason = ""
                        continue
                    time.sleep(0.5)
                    continue
                st = str(result.get("state_type") or "")
                if loop_runs and self._status.studying and st in (
                    "game_over",
                    "menu",
                ):
                    status, state = sts2_client.get_singleplayer_state(fmt="json")
                    if status == 200 and isinstance(state, dict):
                        self._maybe_restart_run(state)
                    time.sleep(interval)
                    continue
                if result.get("success") or result.get("skipped"):
                    self._consecutive_failures = 0
                else:
                    self._consecutive_failures += 1
                    if self._consecutive_failures >= max_fail:
                        self._cast(f"连续失败 {max_fail} 次，暂停（action=stop 可彻底退出）。")
                        self._consecutive_failures = 0
                        time.sleep(2.0)
                time.sleep(interval)
        finally:
            traj = current_path()
            if traj is None and self._status.trajectory:
                from pathlib import Path

                traj = Path(self._status.trajectory)
            fin = finalize_trajectory(traj)
            self._emit_reflection(fin)
            if fin.get("recorded"):
                self._cast(f"[STS2] 本局教训: {fin.get('rule', '')[:200]}")
        self._cast(
            f"代打结束。共 {step} 步，{self._runs_completed} 局。教训见 strategy.yaml"
        )

    def _loop(self, max_steps: int) -> None:
        interval = float(load_sts2_config().get("step_interval_seconds", 0.8))
        try:
            for _ in range(max_steps):
                if self._stop.is_set():
                    break
                with self._lock:
                    if self._status.paused:
                        pass
                    elif not self._status.running:
                        break
                if self._status.paused:
                    time.sleep(0.5)
                    continue
                result = self._single_step()
                if result.get("paused"):
                    from plugins.sts2.autonomy import autopilot_until_victory

                    if autopilot_until_victory():
                        with self._lock:
                            self._status.paused = False
                            self._status.pause_reason = ""
                        continue
                    time.sleep(0.5)
                    continue
                if not result.get("success") and not result.get("paused"):
                    self._record_error(RuntimeError(result.get("error", "step failed")))
                time.sleep(interval)
        finally:
            traj = current_path()
            if traj is None and self._status.trajectory:
                from pathlib import Path

                traj = Path(self._status.trajectory)
            fin = finalize_trajectory(traj)
            self._emit_reflection(fin)
            if fin.get("recorded"):
                self._cast(f"[STS2] 本局教训已写入: {fin.get('rule', '')[:200]}")
        self._cast("Autoplay stopped.")


_controller = AutoplayController()


def get_controller() -> AutoplayController:
    return _controller
