"""LLM vs rule-based STS2 decisions — on-demand autopilot + interactive agent."""



from __future__ import annotations

from contextlib import contextmanager

from plugins.sts2.host_env import env_disabled, env_flag
from plugins.sts2.study_mode import is_study_mode, set_study_mode


def marathon_forbidden() -> bool:

    """Block background marathon unless user explicitly allows autopilot."""

    if env_flag("HERMES_STS2_NO_MARATHON", "STS2_NO_MARATHON"):
        return True
    if env_flag("HERMES_STS2_MANUAL", "STS2_MANUAL"):
        return True
    return False





def mount_mode() -> bool:
    """挂载模式：主 Agent 边聊边打至通关，无后台 autopilot。"""

    return env_flag(
        "HERMES_STS2_MOUNT_MODE",
        "STS2_MOUNT_MODE",
        "HERMES_STS2_CHAT_THROUGH",
        "STS2_CHAT_THROUGH",
        "HERMES_STS2_CHAT_MARATHON",
        "STS2_CHAT_MARATHON",
    )


def chat_through_mode() -> bool:
    """Deprecated alias — use mount_mode()."""

    return mount_mode()


def chat_marathon_mode() -> bool:
    return mount_mode()


def agent_play_mode() -> bool:
    """Interactive TUI: user chats with main agent; may start on-demand autopilot."""

    if mount_mode():
        return True
    return env_flag("HERMES_STS2_AGENT_PLAY", "STS2_AGENT_PLAY")





def llm_play_enabled() -> bool:

    """Auxiliary LLM for plugin brains when needed."""

    if env_disabled("HERMES_STS2_LLM_PLAY", "STS2_LLM_PLAY"):
        return False
    return True





def use_llm_decision() -> bool:

    return is_study_mode() or llm_play_enabled()





def llm_marathon_allowed() -> bool:

    """User-invoked LLM autopilot until victory (study/run/start)."""

    if marathon_forbidden() or mount_mode():

        return False

    if env_flag("HERMES_STS2_LLM_AUTOPILOT", "STS2_LLM_AUTOPILOT"):
        return True

    try:

        from plugins.sts2.config import load_sts2_config



        if load_sts2_config().get("llm_autopilot_enabled", True):

            return True

    except Exception:

        pass

    return not agent_play_mode()





def autopilot_enabled() -> bool:

    """Background bot env flag (legacy)."""

    if marathon_forbidden():

        return False

    return env_flag("HERMES_STS2_AUTOPILOT", "STS2_AUTOPILOT")





def win_rate_mode() -> bool:

    return False





def rule_marathon_allowed() -> bool:

    return llm_marathon_allowed()





def autopilot_active() -> bool:

    try:

        from plugins.sts2.autoplay import get_controller



        st = get_controller().status()

        return bool(st.get("studying") or st.get("running"))

    except Exception:

        return False





def marathon_blocked_message() -> str:

    if mount_mode():

        return (
            "当前为【挂载模式】：禁止后台 sts2_autoplay run。\n"
            "请在同一轮对话内连续 sts2_get_state → sts2_act，直到 FULL_RUN_CLEARED。\n"
            "可闲聊，但不要问「继续吗」；用户说「停」才停。"
        )

    return (
        "后台代打未启用。\n"
        "请说「开始代打」或执行 sts2_autoplay action=run（等同 study/start）。\n"
        "代打中：action=pause|resume|stop；action=hint 传战术；你可随时聊天。\n"
        "手操接管：sts2_act 会先暂停代打（可配置），或 action=stop 彻底停止。"
    )





rule_marathon_blocked_message = marathon_blocked_message





@contextmanager

def llm_step_context():

    """One-shot internal step when marathon is allowed."""

    if marathon_forbidden() and not llm_marathon_allowed():

        yield

        return

    prev = is_study_mode()

    set_study_mode(True)

    try:

        yield

    finally:

        if not prev:

            set_study_mode(False)


