"""Install self-check: ``imagetoolbox-mcp --self-test``.

Meant for a phone (Termux) or any fresh install: one command that tells the owner whether
the server will work, without an MCP client app. It

1. reports Python, Pillow and MCP SDK versions and which image codecs Pillow was built with;
2. creates a throw-away folder with two small generated images (nothing of the user's is
   touched or read);
3. calls every tool through an in-process MCP client (exercises the SDK, pydantic schemas,
   the sandbox and the engine);
4. launches the real stdio server as a child process, the way an agent CLI does, and calls
   one tool over it;
5. checks the generated originals were not modified.

Output is plain text on stdout, one line per check (``PASS``/``WARN``/``FAIL``), then a
summary. Exit code 0 when nothing failed (warnings allowed), 1 otherwise. No absolute paths
are printed.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import platform
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from . import __version__

EXPECTED_TOOLS = (
    "image_adjust",
    "image_batch",
    "image_compress",
    "image_convert",
    "image_crop",
    "image_inspect",
    "image_recipe",
    "image_resize",
    "image_rotate_flip",
    "image_tag",
    "image_watermark",
)

# Codecs the tools need. JPEG and zlib (PNG) are required; WebP is used by `format: webp`.
REQUIRED_CODECS = ("jpg", "zlib")
OPTIONAL_CODECS = ("webp",)


@dataclass
class Report:
    stream: TextIO
    lines: list[tuple[str, str, str]] = field(default_factory=list)

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.lines.append((status, name, detail))
        text = f"{status:<4}  {name}"
        if detail:
            text += f" — {detail}"
        print(text, file=self.stream, flush=True)

    def ok(self, name: str, detail: str = "") -> None:
        self.add("PASS", name, detail)

    def warn(self, name: str, detail: str) -> None:
        self.add("WARN", name, detail)

    def fail(self, name: str, detail: str) -> None:
        self.add("FAIL", name, detail)

    @property
    def failed(self) -> int:
        return sum(1 for s, _, _ in self.lines if s == "FAIL")

    @property
    def warned(self) -> int:
        return sum(1 for s, _, _ in self.lines if s == "WARN")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)[:200]


def _check_environment(rep: Report) -> bool:
    """Versions and codecs. Returns False if the remaining checks cannot run."""
    rep.ok("imagetoolbox-mcp", __version__)
    py = sys.version_info
    detail = f"{platform.python_version()} on {platform.system() or 'unknown'} {platform.machine()}"
    if py < (3, 10):
        rep.fail("python", detail + " (3.10 or newer required)")
        return False
    rep.ok("python", detail)

    try:
        import PIL
        from PIL import features
    except Exception as exc:  # noqa: BLE001 - report any import failure
        rep.fail("pillow", f"cannot import ({type(exc).__name__}); install python-pillow")
        return False
    rep.ok("pillow", PIL.__version__)
    usable = True
    for codec in REQUIRED_CODECS:
        if features.check(codec):
            rep.ok(f"codec {codec}")
        else:
            rep.fail(f"codec {codec}", "missing in this Pillow build")
            usable = False
    for codec in OPTIONAL_CODECS:
        if features.check(codec):
            rep.ok(f"codec {codec}")
        else:
            rep.warn(f"codec {codec}", "missing: format 'webp' will not work (pkg install libwebp)")

    try:
        from importlib.metadata import version

        mcp_version = version("mcp")
    except Exception:  # noqa: BLE001
        mcp_version = "unknown version"
    try:
        import mcp  # noqa: F401
        import pydantic
    except Exception as exc:  # noqa: BLE001
        rep.fail("mcp sdk", f"cannot import ({type(exc).__name__}: {exc})"[:200])
        return False
    rep.ok("mcp sdk", f"{mcp_version}, pydantic {pydantic.VERSION}")
    return usable


def _make_fixtures(root: Path) -> dict[str, Path]:
    from PIL import Image

    (root / "set").mkdir()
    jpg = root / "set" / "photo.jpg"
    im = Image.new("RGB", (64, 48), (200, 80, 40))
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90 CW to display -> upright 48x64
    im.save(jpg, "JPEG", quality=90, exif=exif)
    png = root / "set" / "logo.png"
    Image.new("RGBA", (40, 30), (0, 120, 255, 128)).save(png)
    return {"jpg": jpg, "png": png}


async def _in_process(rep: Report, root: Path, webp: bool) -> None:
    from mcp import Client

    from .sandbox import InputRoot
    from .server import build_server

    async with Client(build_server(InputRoot(root)), raise_exceptions=False) as c:
        names = sorted(t.name for t in (await c.list_tools()).tools)
        if tuple(names) == EXPECTED_TOOLS:
            rep.ok("tools listed", f"{len(names)} tools")
        else:
            rep.fail("tools listed", f"unexpected tool list: {', '.join(names)}")

        calls = [
            (
                "image_inspect",
                {"path": "set/photo.jpg"},
                lambda d: f"{d['format']} {d['width']}x{d['height']}",
            ),
            ("image_convert", {"path": "set/photo.jpg", "format": "png"}, lambda d: d["output"]),
            ("image_resize", {"path": "set/logo.png", "width": 20}, lambda d: d["output"]),
            ("image_compress", {"path": "set/photo.jpg", "quality": 60}, lambda d: d["output"]),
            ("image_rotate_flip", {"path": "set/logo.png", "rotate": 90}, lambda d: d["output"]),
            ("image_crop", {"path": "set/photo.jpg", "aspect": "1:1"}, lambda d: d["output"]),
            ("image_adjust", {"path": "set/photo.jpg", "contrast": 1.2}, lambda d: d["output"]),
            ("image_watermark", {"path": "set/logo.png", "text": "test"}, lambda d: d["output"]),
            (
                "image_recipe",
                {"path": "set/photo.jpg", "steps": [{"op": "resize", "width": 24}]},
                lambda d: d["output"],
            ),
            ("image_tag", {"path": "set/photo.jpg", "artist": "test"}, lambda d: d["output"]),
            (
                "image_batch",
                {"operation": "convert", "options": {"format": "png"}, "folder": "set"},
                lambda d: f"{d['succeeded']} of {d['matched']} files",
            ),
        ]
        if webp:
            calls.append(
                ("image_convert", {"path": "set/logo.png", "format": "webp"}, lambda d: d["output"])
            )
        for name, args, show in calls:
            label = f"tool {name}" + (" (webp)" if args.get("format") == "webp" else "")
            try:
                r = await c.call_tool(name, args)
            except Exception as exc:  # noqa: BLE001
                rep.fail(label, f"client error {type(exc).__name__}")
                continue
            if r.is_error:
                rep.fail(label, _text(r))
                continue
            data = r.structured_content or {}
            if name == "image_inspect" and (data.get("width"), data.get("height")) != (64, 48):
                rep.fail(label, f"unexpected size {data.get('width')}x{data.get('height')}")
                continue
            if name == "image_batch" and data.get("succeeded") != 2:
                rep.fail(label, f"expected 2 files converted, got {data.get('succeeded')}")
                continue
            rep.ok(label, str(show(data)))

        bad = await c.call_tool("image_inspect", {"path": "../outside.png"})
        if bad.is_error and "[outside_root]" in _text(bad):
            rep.ok("sandbox", "path outside the folder refused")
        else:
            rep.fail("sandbox", "a path outside the folder was not refused")


async def _stdio(rep: Report, root: Path) -> None:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    env = dict(os.environ)
    pkg_parent = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = pkg_parent + os.pathsep + env.get("PYTHONPATH", "")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "imagetoolbox_mcp", "--root", str(root)],
        env=env,
    )
    async with Client(params, read_timeout_seconds=60) as c:
        r = await c.call_tool("image_inspect", {"path": "set/logo.png"})
    if r.is_error:
        rep.fail("stdio server", _text(r))
    else:
        rep.ok("stdio server", "child process answered image_inspect")


def run_self_test(stream: TextIO | None = None, *, stdio: bool = True) -> int:
    """Run all checks; return the process exit code (0 = usable)."""
    rep = Report(stream or sys.stdout)
    print(f"imagetoolbox-mcp self-test ({__version__})", file=rep.stream, flush=True)
    if _check_environment(rep):
        from PIL import features

        with tempfile.TemporaryDirectory(prefix="itmcp-selftest-") as tmp:
            root = Path(tmp).resolve() / "images"
            root.mkdir()
            fixtures = _make_fixtures(root)
            before = {k: _sha(p) for k, p in fixtures.items()}
            try:
                asyncio.run(_in_process(rep, root, webp=features.check("webp")))
            except Exception as exc:  # noqa: BLE001
                rep.fail("in-process client", f"{type(exc).__name__}: {exc}"[:200])
            if stdio:
                try:
                    asyncio.run(_stdio(rep, root))
                except Exception as exc:  # noqa: BLE001
                    rep.fail(
                        "stdio server", f"could not start or talk to it ({type(exc).__name__})"
                    )
            if all(_sha(p) == before[k] for k, p in fixtures.items()):
                rep.ok("originals unchanged", "source files byte-identical after all tools")
            else:
                rep.fail("originals unchanged", "a source file was modified")
            out_dir = root / "imagetoolbox-out"
            written = len(list(out_dir.iterdir())) if out_dir.is_dir() else 0
            if written:
                rep.ok("outputs written", f"{written} new files in the output folder")
            else:
                rep.fail("outputs written", "no output files were created")
    total = len(rep.lines)
    if rep.failed:
        print(f"SELF-TEST FAILED: {rep.failed} of {total} checks failed.", file=rep.stream)
        return 1
    tail = f" ({rep.warned} warning(s))" if rep.warned else ""
    print(f"SELF-TEST PASSED: {total} checks{tail}.", file=rep.stream)
    return 0
