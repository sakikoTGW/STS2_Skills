"""STS2_Skills native autoplay (same as原项目) for AstrBot."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from .card_pick_force import is_card_flow_state, run_card_flow_until_clear
from .sts2_skills_bridge import (
    apply_astrbot_runtime,
    ensure_skills,
    force_unpause_controller,
    get_controller,
    patch_llm,
    set_play_mode,
)

LlmGenerateFn = Callable[..., Awaitable[str]]


class STS2Runner:
    """Delegates to plugins.sts2.autoplay.AutoplayController (study / rule loops)."""

    def __init__(
        self,
        plugin_cfg: dict[str, Any],
        *,
        interval: float = 0.7,
        llm_min_interval: float = 4.0,
        llm_post_think_delay: float = 1.2,
    ) -> None:
        self._plugin_cfg = dict(plugin_cfg)
        self._plugin_cfg["interval"] = interval
        self.interval = interval
        self.llm_min_interval = llm_min_interval
        self.llm_post_think_delay = llm_post_think_delay
        self._ctrl: Any = None
        self._running = False
        self.use_llm = False
        self.llm_generate: LlmGenerateFn | None = None
        self.last_error: str | None = None
        self.last_action: dict[str, Any] | None = None
        self.last_decision_source: str = "none"
        self.last_llm_preview: str = ""
        self.last_think: str = ""
        self.steps = 0
        self._start_result: dict[str, Any] = {}

    def _ensure_ctrl(self):
        self._plugin_cfg["_runtime_use_llm"] = self.use_llm
        ensure_skills(self._plugin_cfg, base_url=self._plugin_cfg.get("base_url"))
        if self._ctrl is None:
            self._ctrl = get_controller(self._plugin_cfg)
        return self._ctrl

    def _bind_sync_llm(self) -> None:
        if not self.llm_generate:
            return
        llm_async = self.llm_generate

        def sync_fn(
            messages: list,
            *,
            max_tokens: int = 500,
            temperature: float = 0.3,
        ) -> str:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                raw = asyncio.run(
                    llm_async(
                        messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                )
            else:
                raw = asyncio.run_coroutine_threadsafe(
                    llm_async(
                        messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    ),
                    loop,
                ).result(timeout=180)
            self.last_llm_preview = (raw or "")[:300]
            return raw if isinstance(raw, str) else str(raw)

        patch_llm(sync_fn)

    def _sync_from_step(self, out: dict[str, Any]) -> None:
        if out.get("paused"):
            self.last_decision_source = "paused"
            self.last_think = str(out.get("commentary") or out.get("pause_reason") or "")[:800]
            return
        if not out.get("success") and not out.get("skipped"):
            self.last_error = str(out.get("error") or out.get("body") or "")
            return
        self.last_error = None
        self.steps += 1
        comm = str(out.get("commentary") or "")
        self.last_think = comm[:800]
        act = out.get("action")
        if isinstance(act, dict):
            self.last_action = act
        else:
            self.last_action = {
                k: out[k]
                for k in ("action", "index", "card_index", "target_index")
                if k in out
            }
        st = str(out.get("state_type") or "")
        if out.get("skipped"):
            self.last_decision_source = "wait"
        elif self.use_llm:
            self.last_decision_source = f"skills_{st or 'llm'}"
        else:
            self.last_decision_source = f"rule_{st or 'ok'}"

    async def ping(self) -> dict[str, Any]:
        ensure_skills(self._plugin_cfg, base_url=self._plugin_cfg.get("base_url"))
        from plugins.sts2 import client as sts2_client  # noqa: WPS433

        try:
            payload = await asyncio.to_thread(sts2_client.ping)
            return {"ok": True, "backend": "STS2MCP", **payload}
        except Exception as e:
            return {"ok": False, "error": str(e), "backend": "STS2MCP"}

    async def get_state(self) -> dict[str, Any]:
        ensure_skills(self._plugin_cfg, base_url=self._plugin_cfg.get("base_url"))
        from plugins.sts2 import client as sts2_client  # noqa: WPS433
        from plugins.sts2.visibility import describe_situation  # noqa: WPS433

        try:
            status, payload = await asyncio.to_thread(
                sts2_client.get_singleplayer_state, fmt="json"
            )
        except Exception as e:
            return {"error": str(e)}
        if status != 200 or not isinstance(payload, dict):
            return {"error": f"HTTP {status}", "body": payload}
        payload["summary"] = describe_situation(payload)
        return payload

    async def step_once(self) -> dict[str, Any]:
        ctrl = self._ensure_ctrl()
        apply_astrbot_runtime(self._plugin_cfg, use_llm=self.use_llm)
        set_play_mode(use_llm=self.use_llm, plugin_cfg=self._plugin_cfg)
        if self.use_llm:
            self._bind_sync_llm()
        force_unpause_controller(ctrl)

        forced = await run_card_flow_until_clear(self._plugin_cfg)
        if forced and forced.get("success"):
            self._sync_from_step(forced)
            self.last_decision_source = "forced_card_pick"
            return forced

        try:
            out = await asyncio.to_thread(ctrl.step_once)
        except Exception as e:
            self.last_error = str(e)
            return {"acted": False, "error": str(e)}

        post = await self.get_state()
        if isinstance(post, dict) and is_card_flow_state(post):
            forced2 = await run_card_flow_until_clear(self._plugin_cfg)
            if forced2:
                out = forced2
                self.last_decision_source = "forced_card_pick_after"

        st = str(out.get("state_type") or "")
        if out.get("paused") and st in ("card_reward", "card_select", "relic_select", "relic_select_boss"):
            force_unpause_controller(ctrl)
            try:
                from plugins.sts2 import client as sts2_client  # noqa: WPS433
                from plugins.sts2.action_validate import validate_action  # noqa: WPS433
                from plugins.sts2.decision import decide  # noqa: WPS433

                status, state = await asyncio.to_thread(
                    sts2_client.get_singleplayer_state, fmt="json"
                )
                if status == 200 and isinstance(state, dict):
                    _comm, body = await asyncio.to_thread(decide, state)
                    body = validate_action(state, body)
                    if body.get("action") not in ("__pause__", "__wait__", ""):
                        act_status, act_payload = await asyncio.to_thread(
                            sts2_client.post_singleplayer_action, body
                        )
                        out = {
                            "success": act_status == 200,
                            "commentary": _comm,
                            "action": body,
                            "state_type": st,
                            "http_status": act_status,
                            "body": act_payload,
                            "recovered_from_pause": True,
                        }
            except Exception as e:
                out["recover_error"] = str(e)

        self._sync_from_step(out)
        if self.use_llm and self.llm_post_think_delay > 0 and out.get("success"):
            await asyncio.sleep(self.llm_post_think_delay)
        return out

    def start(self, use_llm: bool = False) -> None:
        self.use_llm = use_llm
        self._plugin_cfg["_runtime_use_llm"] = use_llm
        apply_astrbot_runtime(self._plugin_cfg, use_llm=use_llm)
        set_play_mode(use_llm=use_llm, plugin_cfg=self._plugin_cfg)
        if use_llm:
            self._bind_sync_llm()

        ctrl = self._ensure_ctrl()
        force_unpause_controller(ctrl)

        if ctrl.status().get("running") or ctrl.status().get("studying"):
            self._running = True
            return

        if use_llm:
            self._start_result = ctrl.start_study(announce=False)
        else:
            self._start_result = ctrl._start_rule_loop()  # noqa: SLF001

        self._running = bool(self._start_result.get("success"))
        if not self._running:
            self.last_error = str(self._start_result.get("error") or "start failed")

    async def stop(self) -> None:
        self._running = False
        try:
            ctrl = self._ensure_ctrl()
            await asyncio.to_thread(ctrl.stop)
        except Exception:
            pass
        set_play_mode(use_llm=False, plugin_cfg=self._plugin_cfg)
