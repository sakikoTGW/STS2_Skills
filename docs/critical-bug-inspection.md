# Critical Bug Inspection Playbook

Automated daily scan for high-severity correctness bugs. Only P0 issues (data loss, crashes, security, dual-driver races, silent false success) should trigger fix PRs.

## Scan checklist

1. **Recent commits on `main`** (last 5–10): trace caller chains for behavioral changes.
2. **`handle_sts2_act` / `_http_result`**: HTTP 200 + `status: "error"` must return `success=False` (`_action_http_ok`).
3. **Single-driver lock**: `manual_act_blocked()` must check foreign `.autoplay.lock` holder; `release_all_driver_locks()` must use `clear_if_stale`, not blind `unlink`.
4. **Installer probe** (`install_probe.py`, `Deployer.cs`): skip-deploy when markers match — upgrades need `--force` (non-P0 unless silent corruption).
5. **Autoplay internal paths**: ensure `post_singleplayer_action` responses use same error semantics as `handle_sts2_act`.

## Known non-P0 risks

- **CheckPip false positive** (C# `EnvironmentProbe`): returns ready when Python unset.
- **Install skip without version check**: `ba8df63` skips deploy when file markers match; user must force reinstall for upgrades.

## Validation

```bash
python3 -m pytest tests/plugins/test_sts2_plugin.py tests/plugins/test_sts2_process_lock.py -q
python3 -m pytest tests/ -q
```

## Merge hygiene

Cherry-pick or merge `cursor/critical-bug-inspection-*` branches promptly to avoid duplicate patrol work re-landing the same fixes.
