# Changelog

All notable changes to [STS2_Skills](https://github.com/sakikoTGW/STS2_Skills) are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning: [Semantic Versioning](https://semver.org/) on the `1.0.x` line (see [VERSION_MIGRATION.md](VERSION_MIGRATION.md)).

## [Unreleased]

## [1.0.6] - 2026-05-21

### Added

- `sts2 doctor` — install/API/MCP diagnostics; `sts2 status` includes doctor summary
- [docs/QUICKSTART.md](docs/QUICKSTART.md) — three-minute setup guide
- GitHub Issue templates: feature request, host integration; `config.yml` links
- Release workflow: push tag `v*` → ruff, pytest, version check, source zip, GitHub Release

### Changed

- CI: `ruff check plugins/sts2 scripts tests` (full `plugins/sts2` tree)
- README / README.en: link QUICKSTART; document `doctor` CLI

## [1.0.5] - 2026-05-21

### Fixed

- Paths/config: centralize `resolve_astrbot_data_dir`, `resolve_game_dir`, `save_game_dir_hint`, and multi-host `game_dir.txt` / `config.yaml` discovery (Hermes, OpenClaw, AstrBot)
- AstrBot bridge: remove hardcoded user profile paths; MCP JSON and vendor sync use plugin config + env + repo auto-detect
- `host_config`, `auto_repair`, `program_health`, `install_sts2_mcp_mod`: dynamic paths instead of fixed `E:\Hermes\...` strings
- AstrBot `/sts2ai setup`: use `resolve_game_dir()` / `STS2_GAME_DIR` instead of hardcoded `D:\SteamLibrary\...` when `game_dir` is unset

- `character_choice`: break `normalize_character` / `character_index` infinite recursion (Chinese aliases and menu pick)
- `auto_repair`: default fallbacks align with config (`False`, not `True`)
- `enforce_single_driver`: single helper `enforce_single_driver_enabled()`; `sts2_act` checks lock before `_prepare_manual_act` clears it
- `lessons.run_history_path`: resolve under current `STS2_HOME` (fixes cross-test / multi-host pollution)
- `lessons.finalize_trajectory`: record `stalled_run` when repeated `act_ok: false`
- `action_validate`: debuff/non-attack turns allow explicit `end_turn`; `hand_select` removed from combat frozenset
- `combat_state_machine.reset`: clear debounce timestamp

### Changed

- GUI installer (`sts2skill.exe`): host setup via `scripts/sts2_host_setup_cli.py` (same logic as `host_setup` / wizard)
- Host integrations: `host_setup` module — `sts2 setup --host …`, wizard + `integration-config --install`; OpenClaw auto-merge `openclaw.json` / `openclaw mcp set`; per-host `enforce_single_driver` defaults
- Host integrations: unified `platform_home` / MCP env (`STS2_CONFIG_PATH`, `STS2_CHARACTER`); standalone `~/.config/sts2` fallback; `STS2_*` aliases for play-mode flags; AstrBot bridge no longer sets `HERMES_HOME`
- Docs: tighten README / CONTRIBUTING / integration guides; drop internal or preachy wording
- Tests: Hermes `agent` stub, MCP config assertion, reward-skip policy expectations; doc phrase guard in `test_repo_meta`

## [1.0.4] - 2026-05-21

### Added

- GitHub Actions CI (pytest, ruff, version alignment check)
- `compat.yaml` matrix with pinned STS2MCP `0.4.0`
- `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`
- `scripts/sync-version.ps1` and `scripts/release.ps1` (maintainer release via `gh`)
- Dependabot for pip and GitHub Actions

### Changed

- PyPI package renamed to **`sts2-skills`** (was `hermes-sts2`); repository URLs corrected
- `auto_repair` / `hermes_may_patch_code` default to **off** (opt-in for agent code patch)
- `enforce_single_driver` default **on** (AstrBot integration still documents explicit override)
- `max_steps_per_run` single default (`8000`); removed duplicate config key
- `sts2 install-mod` uses pinned STS2MCP tag from `compat.yaml` (`--tag` to override)

### Deprecated

- `scripts/publish_release_api.py` — prefer `scripts/release.ps1` + `gh release create`

## [1.0.3]

Prior release notes: [RELEASE_NOTES_v1.0.3.md](RELEASE_NOTES_v1.0.3.md).

## [1.2.0] / [1.3.0] (legacy tags)

Historical tags only; see [VERSION_MIGRATION.md](VERSION_MIGRATION.md). Do not create new `v1.2.x` / `v1.3.x` tags.
