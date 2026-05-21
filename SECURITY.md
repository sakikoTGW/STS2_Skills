# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |
| &lt; 1.0.0 / legacy v1.2–v1.3 tags | No |

## Reporting a vulnerability

Please **do not** open a public issue for security-sensitive reports.

1. Open a [private security advisory](https://github.com/sakikoTGW/STS2_Skills/security/advisories/new) on GitHub, or
2. Contact the repository owner via GitHub with a minimal repro and impact description.

## Scope notes

- This project talks to a **local** game API (`127.0.0.1:15526` by default). It should not be exposed to the public internet.
- `auto_repair` and `hermes_may_patch_code` default to **off**; turning them on may let a local agent edit plugin code on disk.
- Do not commit `.env`, wiki cookies (`*.cookies.txt`), or API keys. See `.gitignore`.
- `sts2 install-mod` downloads binaries from [Gennadiyev/STS2MCP](https://github.com/Gennadiyev/STS2MCP); pinned version is in `compat.yaml`.
