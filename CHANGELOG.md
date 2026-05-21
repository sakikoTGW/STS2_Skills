# Changelog

All notable changes to [STS2_Skills](https://github.com/sakikoTGW/STS2_Skills) are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning: [Semantic Versioning](https://semver.org/) on the `1.0.x` line (see [VERSION_MIGRATION.md](VERSION_MIGRATION.md)).

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
