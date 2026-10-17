"""Command-line entry point: ``imagetoolbox-mcp`` or ``python -m imagetoolbox_mcp``.

Runs the MCP server over stdio. An input folder is mandatory: pass ``--root DIR`` or set
``IMAGETOOLBOX_MCP_ROOT``. The server can only read image files inside that folder and
only creates new files in the output folder (``--out``; default ``<root>/imagetoolbox-out``).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from . import __version__

ROOT_ENV = "IMAGETOOLBOX_MCP_ROOT"
OUT_ENV = "IMAGETOOLBOX_MCP_OUT"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="imagetoolbox-mcp",
        description="Local MCP server (stdio) for safe image operations.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--root",
        default=os.environ.get(ROOT_ENV),
        help=f"Folder the server may read images from (or set {ROOT_ENV}). Required.",
    )
    parser.add_argument(
        "--out",
        default=os.environ.get(OUT_ENV),
        help=f"Folder for new files (or set {OUT_ENV}). Default: <root>/imagetoolbox-out.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log verbosity on stderr (default WARNING). Logs never include image bytes.",
    )
    args = parser.parse_args(argv)

    if not args.root:
        print(
            f"imagetoolbox-mcp: an input folder is required: --root DIR or {ROOT_ENV}=DIR",
            file=sys.stderr,
        )
        return 2

    # stdout is the MCP channel; all logging must go to stderr.
    logging.basicConfig(level=args.log_level, stream=sys.stderr, format="%(levelname)s %(message)s")

    # Imported lazily so `--version` and argument errors work without the MCP SDK loaded.
    from .output import DEFAULT_DIRNAME, OutputDir
    from .sandbox import InputRoot
    from .server import run_stdio

    try:
        root = InputRoot(args.root)
        out = OutputDir(args.out if args.out else root.path / DEFAULT_DIRNAME)
    except ValueError as exc:
        print(f"imagetoolbox-mcp: {exc}", file=sys.stderr)
        return 2
    run_stdio(root, log_level=args.log_level, out=out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
