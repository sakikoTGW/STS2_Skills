"""stdio MCP bridge to the STS2MCP in-game HTTP API.



Run: ``python -m plugins.sts2.mcp_server``

Hermes: ``~/.hermes/config.yaml`` → ``mcp_servers.sts2`` (``hermes sts2 setup``).

OpenClaw / AstrBot / other MCP clients: ``python scripts/sts2_mcp_bridge.py``
(see ``hermes sts2 integration-config`` or ``plugins/sts2/integrations/``).



MCP tools expose **readable** action traces (出牌/用药/效果) for agents that only use MCP.

"""



from __future__ import annotations



import argparse

import json

import sys





def _observe_payload() -> dict:

    from plugins.sts2.autoplay import get_controller

    from plugins.sts2.action_trace import read_action_log_tail



    out = get_controller().observe_once()

    st = get_controller().status()

    out["autoplay_running"] = st.get("running")

    out["watch_running"] = st.get("watching")

    out["learn_running"] = st.get("learning")

    out["action_log_tail"] = read_action_log_tail(max_chars=4000)

    return out





def _run() -> None:

    try:

        from mcp.server.fastmcp import FastMCP

    except ImportError as exc:

        sys.stderr.write(

            "sts2 MCP server requires the mcp package. "

            "Install with: pip install 'hermes-agent[mcp]'\n"

        )

        raise SystemExit(1) from exc



    from plugins.sts2 import client as sts2_client

    from plugins.sts2.action_trace import read_action_log_tail

    from plugins.sts2.autoplay import get_controller

    from plugins.sts2.config import load_sts2_config

    from plugins.sts2.visibility import describe_situation



    cfg = load_sts2_config()

    mcp = FastMCP("sts2")



    @mcp.tool()

    def ping_mod() -> str:

        """Check STS2MCP HTTP server health (game running, mod enabled)."""

        return json.dumps(sts2_client.ping(), ensure_ascii=False, indent=2)



    @mcp.tool()

    def get_game_state(

        format: str = "summary",

        include_raw_json: bool = False,

    ) -> str:

        """Current singleplayer state.



        format=summary (default): Chinese snapshot of hand, intents, map, etc.

        format=json|markdown: raw API payload (large).

        Set include_raw_json=true with summary to attach full JSON.

        """

        fmt = format.strip().lower()

        if fmt == "summary":

            status, state = sts2_client.get_singleplayer_state(fmt="json")

            if status != 200 or not isinstance(state, dict):

                return json.dumps(

                    {"success": False, "http_status": status, "body": state},

                    ensure_ascii=False,

                    indent=2,

                )

            obs = get_controller().observe_once()

            payload = {

                "success": True,

                "situation": obs.get("situation") or describe_situation(state),

                "action_trace": obs.get("action_trace", ""),

                "changed": obs.get("changed", False),

                "state_type": state.get("state_type"),

            }

            if include_raw_json:

                payload["state"] = state

            return json.dumps(payload, ensure_ascii=False, indent=2)



        status, payload = sts2_client.get_singleplayer_state(fmt=fmt if fmt != "summary" else "json")

        if fmt == "markdown" and isinstance(payload, dict) and "raw" in payload:

            return str(payload["raw"])

        return json.dumps(

            {"http_status": status, "state": payload},

            ensure_ascii=False,

            indent=2,

        )



    @mcp.tool()

    def observe_player_actions() -> str:

        """Poll once: infer what you just did (cards, potions, map) and combat effects.



        Call every turn while you play manually, or run start_spectate in background.

        Writes to ~/.hermes/sts2/action_log.md.

        """

        return json.dumps(_observe_payload(), ensure_ascii=False, indent=2)



    @mcp.tool()

    def get_action_log(max_chars: int = 6000) -> str:

        """Recent inferred action log (出牌/用药/效果), newest at bottom."""

        tail = read_action_log_tail(max_chars=max(500, min(20000, max_chars)))

        st = get_controller().status()

        return json.dumps(

            {

                "success": True,

                "log": tail or "(empty — play with spectate or call observe_player_actions)",

                "last_action_trace": st.get("last_action_trace", ""),

                "last_situation": st.get("last_situation", ""),

            },

            ensure_ascii=False,

            indent=2,

        )



    @mcp.tool()
    def start_study_autoplay(max_steps: int = 500) -> str:
        """Disabled — use sts2_get_state + sts2_act instead of rule marathon."""
        from plugins.sts2.play_mode import rule_marathon_blocked_message

        return json.dumps(
            {
                "success": False,
                "error": rule_marathon_blocked_message(),
                "rule_marathon": "permanently_disabled",
            },
            ensure_ascii=False,
            indent=2,
        )

    @mcp.tool()

    def start_spectate(mode: str = "watch") -> str:

        """Background poll while YOU play in the game UI (no bot clicks).



        mode=watch: narrate actions/effects to action_log.

        mode=learn: same + ask when confused (answer via provide_spectate_hint).

        """

        ctrl = get_controller()

        mode = mode.strip().lower()

        if mode == "learn":

            out = ctrl.start_learn()

        elif mode == "watch":

            out = ctrl.start_watch()

        else:

            return json.dumps(

                {"success": False, "error": 'mode must be "watch" or "learn"'},

                ensure_ascii=False,

            )

        return json.dumps(out, ensure_ascii=False, indent=2)



    @mcp.tool()

    def stop_spectate() -> str:

        """Stop watch/learn background polling."""

        return json.dumps(get_controller().stop(), ensure_ascii=False, indent=2)



    @mcp.tool()

    def provide_spectate_hint(hint: str) -> str:

        """Answer a learn-mode question (saved to hot_notes + strategy)."""

        ctrl = get_controller()

        ctrl.provide_hint(hint)

        return json.dumps(

            {"success": True, "hint_accepted": True},

            ensure_ascii=False,

        )



    @mcp.tool()

    def perform_action(action: str, parameters: dict | None = None) -> str:

        """Execute one STS2 action (play_card, end_turn, choose_map_node, ...).



        Prefer playing yourself + observe_player_actions when learning style.

        """

        body: dict = {"action": action}

        if parameters:

            body.update({k: v for k, v in parameters.items() if k != "action"})

        status, payload = sts2_client.post_singleplayer_action(body)

        result = {"http_status": status, "result": payload}

        if status == 200:

            try:

                _, fresh = sts2_client.get_singleplayer_state(fmt="json")

                if isinstance(fresh, dict):

                    obs = get_controller().observe_once()

                    result["situation"] = obs.get("situation")

                    result["action_trace"] = obs.get("action_trace")

            except Exception:

                pass

        return json.dumps(result, ensure_ascii=False, indent=2)



    @mcp.tool()

    def search_wiki(query: str, item_type: str = "all", limit: int = 10) -> str:

        """Fuzzy-search discovered cards/relics for the active profile."""

        status, payload = sts2_client.wiki_search(

            query, item_type=item_type, limit=limit

        )

        return json.dumps(

            {"http_status": status, "results": payload},

            ensure_ascii=False,

            indent=2,

        )



    @mcp.tool()

    def get_profile_progress() -> str:

        """Persistent profile progress (discoveries, stats)."""

        status, payload = sts2_client.get_profile()

        return json.dumps(

            {"http_status": status, "profile": payload},

            ensure_ascii=False,

            indent=2,

        )



    @mcp.tool()

    def get_compendium() -> str:

        """Compendium-shaped profile data (cards, relics, run history, ...)."""

        status, payload = sts2_client.get_compendium()

        return json.dumps(

            {"http_status": status, "compendium": payload},

            ensure_ascii=False,

            indent=2,

        )



    parser = argparse.ArgumentParser(description="STS2 MCP bridge")

    parser.add_argument("--host", default="127.0.0.1", help="unused (HTTP target from env)")

    parser.add_argument("--port", type=int, default=15526, help="unused (set STS2_MCP_BASE_URL)")

    parser.parse_args()



    _ = cfg

    mcp.run()





def main() -> None:

    _run()





if __name__ == "__main__":

    main()


