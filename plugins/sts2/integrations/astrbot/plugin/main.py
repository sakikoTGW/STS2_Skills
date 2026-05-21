"""
AstrBot 插件：通过 STS2_Skills + STS2MCP 自动玩杀戮尖塔 2。
命令：/sts2ai ping | state | step [llm] | auto [llm] | stop | status | setup
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, List, Union

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .runner import STS2Runner
from .sts2_skills_bridge import (
    _ASTRBOT_DATA,
    _FALLBACK_SRC,
    mcp_server_block,
    skills_root_from_cfg,
    sync_vendor_from_source,
    write_astrbot_sts2_config,
)

_MCP_JSON = _ASTRBOT_DATA / "mcp_server.json"
_SKILL_SRC = (
    skills_root_from_cfg({})
    / "plugins"
    / "sts2"
    / "integrations"
    / "astrbot"
    / "skills"
    / "slay-the-spire-2"
)
_SKILL_DST = Path(__file__).resolve().parent / "skills" / "slay-the-spire-2"


def _parse_subcommand(event: AstrMessageEvent) -> tuple[str, bool]:
    raw = (event.message_str or "").strip()
    parts = [p for p in raw.split() if p]
    if parts and parts[0].lower().replace("/", "") in ("sts2ai", "sts2", "塔2"):
        parts = parts[1:]
    use_llm = any(p.lower() in ("llm", "大模型", "ai") for p in parts)
    cmd_parts = [p for p in parts if p.lower() not in ("llm", "大模型", "ai")]
    sub = cmd_parts[0].lower() if cmd_parts else "help"
    return sub, use_llm


@register(
    "astrbot_plugin_sts2_agent",
    "Patchouli",
    "STS2 AI — STS2_Skills + STS2MCP（15526）",
    "1.0.4",
)
class Sts2AgentPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        cfg = self.context.get_config() or {}
        plugin_cfg = cfg.get("astrbot_plugin_sts2_agent", {}) if isinstance(cfg, dict) else {}
        self._plugin_cfg = plugin_cfg
        self.runner = STS2Runner(
            plugin_cfg,
            interval=float(plugin_cfg.get("interval", 0.7)),
            llm_min_interval=float(plugin_cfg.get("llm_min_interval", 4.0)),
            llm_post_think_delay=float(plugin_cfg.get("llm_post_think_delay", 1.2)),
        )

    async def initialize(self) -> None:
        logger.info(
            "[STS2] v2 STS2_Skills + STS2MCP — /sts2ai setup | ping | auto llm"
        )

    async def _resolve_provider_id(self, event: AstrMessageEvent) -> str:
        configured = (self._plugin_cfg.get("llm_provider_id") or "").strip()
        if configured:
            return configured
        umo = getattr(event, "unified_msg_origin", None)
        if umo is not None:
            pid = await self.context.get_current_chat_provider_id(umo=umo)
            if pid:
                return pid
        get_using = getattr(self.context, "get_using_provider", None)
        if callable(get_using):
            prov = get_using()
            if prov is not None:
                return str(
                    getattr(prov, "id", None)
                    or getattr(prov, "provider_id", None)
                    or prov
                )
        return ""

    def _extract_llm_text(self, resp: Any) -> str:
        if resp is None:
            return ""
        if isinstance(resp, str):
            return resp
        for attr in ("completion_text", "text", "content", "result", "message"):
            val = getattr(resp, attr, None)
            if isinstance(val, str) and val.strip():
                return val
        if isinstance(resp, dict):
            for key in ("completion_text", "text", "content", "message"):
                val = resp.get(key)
                if isinstance(val, str) and val.strip():
                    return val
        return str(resp)

    def _bind_llm(self, event: AstrMessageEvent) -> None:
        plugin = self

        async def _llm(
            messages: Union[str, List[dict]],
            *,
            max_tokens: int = 720,
            temperature: float = 0.3,
        ) -> str:
            provider_id = await plugin._resolve_provider_id(event)
            if not provider_id:
                raise RuntimeError(
                    "未找到 LLM Provider：请在插件配置填写 llm_provider_id，"
                    "或确保当前会话已选择聊天模型"
                )

            system_prompt = ""
            user_prompt = ""
            if isinstance(messages, list):
                sys_parts: list[str] = []
                usr_parts: list[str] = []
                for m in messages:
                    role = str(m.get("role") or "user")
                    text = str(m.get("content") or "")
                    if role == "system":
                        sys_parts.append(text)
                    else:
                        usr_parts.append(text)
                system_prompt = "\n\n".join(sys_parts).strip()
                user_prompt = "\n\n".join(usr_parts).strip()
            else:
                user_prompt = str(messages)

            if not system_prompt:
                system_prompt = (
                    "You control Slay the Spire 2 via HTTP API. "
                    "Reply with ONE JSON object only, no markdown. "
                    'Format: {"commentary":"Chinese reasoning",'
                    '"action":"...", optional params}. '
                    "On card_reward use action select_card_reward with card_index. "
                    "On card_select use select_card then confirm_selection when can_confirm."
                )

            kwargs: dict[str, Any] = {
                "chat_provider_id": provider_id,
                "prompt": user_prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
            }
            logger.info("[STS2] LLM (%s chars sys, %s chars user)…", len(system_prompt), len(user_prompt))
            resp = await plugin.context.llm_generate(**kwargs)
            text = plugin._extract_llm_text(resp)
            logger.info("[STS2] LLM: %s", text[:120])
            return text

        self.runner.llm_generate = _llm

    async def _run_setup(self) -> str:
        lines: list[str] = []
        try:
            vend = await asyncio.to_thread(sync_vendor_from_source, _FALLBACK_SRC)
            lines.append(f"已复制 STS2_Skills → {vend}")
            self._plugin_cfg.setdefault("skills_root", str(vend))
        except Exception as e:
            lines.append(f"复制 vendor 跳过/失败: {e}")

        root = skills_root_from_cfg(self._plugin_cfg)
        if not root.is_dir():
            return "\n".join(lines) + f"\nSTS2_Skills 目录不存在: {root}"

        cfg_path = write_astrbot_sts2_config(self._plugin_cfg, use_llm=True)
        lines.append(f"配置: {cfg_path} (pause_on_ask=false)")

        py = self._plugin_cfg.get("mcp_python") or ""
        if not py:
            import sys

            py = sys.executable
        lines.append(f"Skills: {root}")
        lines.append(f"Python: {py}")

        try:
            proc = await asyncio.create_subprocess_exec(
                py,
                "-m",
                "pip",
                "install",
                "-e",
                f"{root}[mcp]",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            out, _ = await proc.communicate()
            lines.append(f"pip: exit {proc.returncode}")
            if out:
                tail = out.decode("utf-8", errors="replace")[-600:]
                lines.append(tail)
        except Exception as e:
            lines.append(f"pip 失败: {e}")

        game_dir = (self._plugin_cfg.get("game_dir") or "").strip()
        if not game_dir:
            import os
            import sys

            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            try:
                from plugins.sts2.paths import find_game_dir

                found = find_game_dir()
                if found:
                    game_dir = str(found)
            except Exception:
                pass
            if not game_dir:
                game_dir = (os.environ.get("STS2_GAME_DIR") or "").strip()
        script = root / "scripts" / "install_sts2_mcp_mod.py"
        if script.is_file():
            import os

            if not game_dir:
                lines.append(
                    "install-mod 跳过: 未配置 game_dir，且未检测到游戏目录。"
                    "请在插件配置填写路径，或设置环境变量 STS2_GAME_DIR。"
                )
            else:
                env = {**os.environ, "STS2_GAME_DIR": game_dir}
                try:
                    proc2 = await asyncio.create_subprocess_exec(
                        py,
                        str(script),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                        env=env,
                    )
                    out2, _ = await proc2.communicate()
                    lines.append(f"install-mod: exit {proc2.returncode}")
                    if out2:
                        lines.append(out2.decode("utf-8", errors="replace")[-500:])
                except Exception as e:
                    lines.append(f"install-mod 失败: {e}")

        if _SKILL_SRC.is_dir():
            _SKILL_DST.parent.mkdir(parents=True, exist_ok=True)
            if _SKILL_DST.exists():
                shutil.rmtree(_SKILL_DST)
            shutil.copytree(_SKILL_SRC, _SKILL_DST)
            lines.append(f"Skill 已复制到 {_SKILL_DST}")

        block = mcp_server_block(self._plugin_cfg)
        block["command"] = py
        try:
            data = json.loads(_MCP_JSON.read_text(encoding="utf-8")) if _MCP_JSON.is_file() else {}
        except json.JSONDecodeError:
            data = {}
        servers = data.setdefault("mcpServers", {})
        servers["sts2"] = block
        _MCP_JSON.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        lines.append(f"MCP 已写入 {_MCP_JSON}")
        lines.append("请在 WebUI 重载 MCP，游戏内启用 STS2 MCP 模组后 /sts2ai ping")

        return "\n".join(lines)

    @filter.command("sts2ai", alias={"sts2", "塔2"})
    async def sts2ai(self, event: AstrMessageEvent) -> Any:
        sub, use_llm = _parse_subcommand(event)

        if sub in ("help", "h", "?", ""):
            yield event.plain_result(
                "STS2 Agent v2（STS2_Skills + STS2MCP :15526）\n"
                "/sts2ai setup — 安装依赖、STS2MCP 模组、写入 MCP 配置\n"
                "/sts2ai ping — 检测游戏 API\n"
                "/sts2ai state — 当前局面摘要\n"
                "/sts2ai step [llm] — 走一步（llm=中文思考+决策）\n"
                "/sts2ai auto [llm] — 后台自动\n"
                "/sts2ai stop — 停止\n"
                "/sts2ai status — 状态\n"
                "旧版 sts2_ai_proxy(:9876) 已停用，请用游戏内 STS2 MCP 模组。"
            )
            return

        if sub == "setup":
            msg = await self._run_setup()
            yield event.plain_result(msg)
            return

        if sub == "ping":
            r = await self.runner.ping()
            yield event.plain_result(str(r))
            return

        if sub == "state":
            st = await self.runner.get_state()
            summary = st.get("summary") or st.get("error") or str(st)[:2000]
            yield event.plain_result(summary)
            return

        if sub == "status":
            ctrl_st = {}
            try:
                ctrl_st = self.runner._ensure_ctrl().status()  # noqa: SLF001
            except Exception:
                pass
            yield event.plain_result(
                f"running={self.runner._running} steps={self.runner.steps}\n"
                f"use_llm={self.runner.use_llm} backend=STS2MCP\n"
                f"interval={self.runner._step_interval()}s\n"
                f"source={self.runner.last_decision_source}\n"
                f"think={self.runner.last_think!r}\n"
                f"llm_preview={self.runner.last_llm_preview!r}\n"
                f"last_err={self.runner.last_error}\n"
                f"last={self.runner.last_action}\n"
                f"autoplay={ctrl_st}"
            )
            return

        if sub == "stop":
            await self.runner.stop()
            yield event.plain_result("STS2 自动已停止。")
            return

        if sub == "step":
            if use_llm:
                self._bind_llm(event)
            else:
                self.runner.llm_generate = None
            self.runner.use_llm = use_llm
            r = await self.runner.step_once()
            think = self.runner.last_think
            body = f"think:\n{think}\n\n" if think else ""
            yield event.plain_result(body + str(r))
            return

        if sub == "auto":
            if self.runner._running:
                await self.runner.stop()
            if use_llm:
                self._bind_llm(event)
            else:
                self.runner.llm_generate = None
            self.runner.start(use_llm=use_llm)
            if not self.runner._running:
                err = self.runner.last_error or self.runner._start_result.get("error")
                yield event.plain_result(f"启动失败: {err}\n请先 /sts2ai setup")
                return
            if use_llm:
                mode = "原项目 study 代打线程（选牌/奖励不暂停）"
            else:
                mode = "原项目 rule 代打线程"
            prov = await self._resolve_provider_id(event) if use_llm else ""
            extra = f"\nProvider: {prov}" if prov else ""
            yield event.plain_result(
                f"STS2 自动已开始（{mode}）。\n"
                f"/sts2ai status 查看 think=\n"
                f"/sts2ai stop 停止{extra}"
            )
            return

        yield event.plain_result(f"未知子命令: {sub}\n发送 /sts2ai help")

    async def terminate(self) -> None:
        await self.runner.stop()
