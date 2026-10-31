"""Command-line entry point: ``imagetoolbox-mcp`` or ``python -m imagetoolbox_mcp``.

Runs the MCP server over stdio. An input folder is mandatory: pass ``--root DIR`` or set
``IMAGETOOLBOX_MCP_ROOT``. The server can only read image files inside that folder and
only creates new files in the output folder (``--out``; default ``<root>/imagetoolbox-out``).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

from . import __version__

ROOT_ENV = "IMAGETOOLBOX_MCP_ROOT"
ISOLATE_ENV = "IMAGETOOLBOX_MCP_ISOLATE"


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line: ts, level, logger, msg. Messages are already path-free."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str, fmt: str) -> None:
    handler = logging.StreamHandler(sys.stderr)  # stdout is the MCP channel
    if fmt == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


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
    parser.add_argument(
        "--log-format",
        default="text",
        choices=["text", "json"],
        help="stderr log format: 'text' (default) or 'json' (one object per line).",
    )
    parser.add_argument(
        "--isolate",
        type=float,
        metavar="SECONDS",
        default=float(os.environ[ISOLATE_ENV]) if os.environ.get(ISOLATE_ENV) else None,
        help="Run every image operation in a child process that is stopped after SECONDS "
        f"(1-600; or set {ISOLATE_ENV}). Off by default: slower, but protects against "
        "a decoder hanging or crashing.",
    )
    parser.add_argument(
        "--max-megapixels",
        type=float,
        metavar="MP",
        default=None,
        help="Refuse images (and results) larger than this many megapixels (1-64, default 64). "
        "Lower it on phones with little memory.",
    )
    parser.add_argument(
        "--sbom",
        action="store_true",
        help="Print a CycloneDX 1.5 SBOM (JSON) of this install and exit. No network.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Check this install (versions, codecs, every tool on generated images, a stdio "
        "child process) in a temporary folder, print PASS/FAIL lines and exit. No --root needed.",
    )
    args = parser.parse_args(argv)

    if args.sbom:
        from .sbom import dump

        sys.stdout.write(dump())
        return 0

    if args.self_test:
        from .selftest import run_self_test

        return run_self_test()

    if not args.root:
        print(
            f"imagetoolbox-mcp: an input folder is required: --root DIR or {ROOT_ENV}=DIR",
            file=sys.stderr,
        )
        return 2

    if args.isolate is not None and not 1 <= args.isolate <= 600:
        print("imagetoolbox-mcp: --isolate must be between 1 and 600 seconds", file=sys.stderr)
        return 2

    if args.max_megapixels is not None and not 1 <= args.max_megapixels <= 64:
        print("imagetoolbox-mcp: --max-megapixels must be between 1 and 64", file=sys.stderr)
        return 2

    # stdout is the MCP channel; all logging must go to stderr.
    configure_logging(args.log_level, args.log_format)

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
    from .engine import DEFAULT_LIMITS, Limits

    limits = DEFAULT_LIMITS
    if args.max_megapixels is not None:
        limits = Limits(max_pixels=int(args.max_megapixels * 1_000_000))
    run_stdio(root, limits, log_level=args.log_level, out=out, isolate_seconds=args.isolate)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
