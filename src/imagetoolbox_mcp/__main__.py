"""Command-line entry point: ``imagetoolbox-mcp`` or ``python -m imagetoolbox_mcp``.

The MCP stdio server is added in milestone M2; until then only ``--version`` works.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="imagetoolbox-mcp",
        description="Local MCP server for safe image operations (work in progress).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args(argv)
    msg = "imagetoolbox-mcp: the MCP server is not implemented yet (milestone M2)."
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
