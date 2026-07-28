# Critical bug inspection playbook

Automated daily patrol for **P0 correctness** issues in STS2_Skills.

## Scope (in)

- Data loss, silent truncation, false success on game actions
- Cross-process driver lock races (dual autoplay / stolen locks)
- Auth/permission bypasses in host setup
- Crashes or infinite loops on critical paths

## Out of scope

- Style, docs-only changes, minor UX degradation
- Theoretical issues without a concrete trigger scenario
- Install probe version skew (tracked as non-P0 until version markers exist)

## Scan checklist

1. `git log main -15 --oneline` — focus behavioral diffs in `plugins/sts2/`, `scripts/install_stub/`.
2. **`handle_sts2_act` / `_action_http_ok`** — HTTP 200 + `status:error` must not return `success=True`.
3. **`.autoplay.lock`** — never `unlink` when a foreign live PID holds the file; use `clear_if_stale` / `foreign_holder_pid`.
4. **`manual_act_blocked`** — must check file lock, not only in-process `_mode`.
5. **`mcp_server.perform_action`** — consider unifying with `_action_http_ok` (follow-up).
6. **Installer `EnvironmentProbe.CheckPip`** — Python unset returns `PipReady=true` (false positive; non-P0).
7. **`Deployer.DeployAll` skip path** — `AllReady` skips deploy without version check (upgrade risk; non-P0).
8. Run `python3 -m pytest tests/ -q` after any fix.

## Known non-P0 risks

| Area | Risk |
|------|------|
| Install probe | Skip deploy when markers match; upgrades need `--force` |
| CheckPip | Reports ready when Python path missing |
| perform_action MCP tool | Does not expose `success` field; callers must read `result.status` |

## Merge hygiene

- Land `cursor/critical-bug-inspection-*` branches promptly to avoid duplicate patrol PRs.
- Before re-landing, grep main for `_action_http_ok` and `foreign_holder_pid`.
