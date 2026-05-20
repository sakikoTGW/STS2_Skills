"""Console entrypoint for the standalone ``sts2`` CLI (``pip install hermes-sts2``)."""

from __future__ import annotations

import argparse
import sys

from plugins.sts2.cli import register_cli, sts2_command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sts2",
        description="Slay the Spire 2 — STS2MCP bridge (Hermes / OpenClaw / AstrBot)",
    )
    register_cli(parser)
    args = parser.parse_args(argv)
    return sts2_command(args)


if __name__ == "__main__":
    raise SystemExit(main())
