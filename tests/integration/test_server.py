"""End-to-end tests: a real MCP client discovers and calls ``image_inspect``.

Two transports are covered:

* in-process (``Client(server)``) for fast, detailed checks;
* a real stdio subprocess (``python -m imagetoolbox_mcp --root ...``), which is what an
  MCP client app actually launches. This is the M2 exit criterion.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from PIL import Image

from imagetoolbox_mcp.sandbox import InputRoot
from imagetoolbox_mcp.server import build_server

SRC = str(Path(__file__).resolve().parents[2] / "src")


def _text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


class _Fixtures(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.root_dir = base / "images"
        (self.root_dir / "holiday").mkdir(parents=True)
        Image.new("RGBA", (40, 30), (255, 0, 0, 128)).save(self.root_dir / "holiday" / "a.png")
        Image.new("RGB", (8, 8)).save(self.root_dir / "b.jpg")
        (self.root_dir / "notes.txt").write_text("not an image")
        Image.new("RGB", (4, 4)).save(base / "outside.png")
        self.base = base

    def tearDown(self):
        self._tmp.cleanup()


class InProcessServerTests(_Fixtures):
    def client(self):
        return Client(build_server(InputRoot(self.root_dir)), raise_exceptions=False)

    async def test_lists_tool_with_schema_and_read_only_hints(self):
        async with self.client() as c:
            tools = (await c.list_tools()).tools
        self.assertEqual(
            sorted(t.name for t in tools),
            [
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
            ],
        )
        tool = next(t for t in tools if t.name == "image_inspect")
        self.assertEqual(tool.input_schema["required"], ["path"])
        self.assertEqual(tool.input_schema["properties"]["path"]["type"], "string")
        self.assertTrue(tool.annotations.read_only_hint)
        self.assertFalse(tool.annotations.destructive_hint)
        self.assertFalse(tool.annotations.open_world_hint)
        self.assertIn("width", tool.output_schema["properties"])

    async def test_inspect_png(self):
        async with self.client() as c:
            r = await c.call_tool("image_inspect", {"path": "holiday/a.png"})
        self.assertFalse(r.is_error, _text(r))
        data = r.structured_content
        self.assertEqual(data["path"], "holiday/a.png")
        self.assertEqual(data["format"], "PNG")
        self.assertEqual((data["width"], data["height"]), (40, 30))
        self.assertTrue(data["has_alpha"])
        self.assertFalse(data["has_gps_metadata"])

    async def test_original_file_unchanged(self):
        target = self.root_dir / "b.jpg"
        before = (target.read_bytes(), target.stat().st_mtime_ns)
        async with self.client() as c:
            r = await c.call_tool("image_inspect", {"path": "b.jpg"})
        self.assertFalse(r.is_error)
        self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), before)

    async def test_structured_errors(self):
        cases = {
            "../outside.png": "[outside_root]",
            str(self.base / "outside.png"): "[outside_root]",
            "missing.png": "[not_found]",
            "notes.txt": "[unsupported_format]",
            "holiday": "[not_a_file]",
        }
        os.symlink(self.base / "outside.png", self.root_dir / "sneaky.png")
        cases["sneaky.png"] = "[symlink_rejected]"
        async with self.client() as c:
            for path, code in cases.items():
                with self.subTest(path=path):
                    r = await c.call_tool("image_inspect", {"path": path})
                    self.assertTrue(r.is_error)
                    msg = _text(r)
                    self.assertIn(code, msg)
                    self.assertNotIn(str(self.base), msg)  # host layout never leaked

    async def test_schema_validation_rejects_bad_arguments(self):
        async with self.client() as c:
            for args in ({}, {"path": ""}, {"path": 5}):
                with self.subTest(args=args):
                    r = await c.call_tool("image_inspect", args)
                    self.assertTrue(r.is_error)

    async def test_unknown_tool_is_error(self):
        async with self.client() as c:
            r = await c.call_tool("shell", {"cmd": "id"})
        self.assertTrue(r.is_error)


class StdioSubprocessTests(_Fixtures):
    async def test_stdio_end_to_end(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "imagetoolbox_mcp", "--root", str(self.root_dir)],
            env=env,
        )
        async with Client(params, read_timeout_seconds=30) as c:
            names = [t.name for t in (await c.list_tools()).tools]
            self.assertEqual(
                sorted(names),
                [
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
                ],
            )
            r = await c.call_tool("image_inspect", {"path": "b.jpg"})
            self.assertFalse(r.is_error, _text(r))
            self.assertEqual(r.structured_content["format"], "JPEG")
            bad = await c.call_tool("image_inspect", {"path": "../outside.png"})
            self.assertTrue(bad.is_error)
            self.assertIn("[outside_root]", _text(bad))
            conv = await c.call_tool("image_convert", {"path": "holiday/a.png", "format": "webp"})
            self.assertFalse(conv.is_error, _text(conv))
            self.assertEqual(conv.structured_content["output"], "imagetoolbox-out/a.webp")
            rs = await c.call_tool("image_resize", {"path": "holiday/a.png", "width": 2})
            self.assertFalse(rs.is_error, _text(rs))
            self.assertEqual(rs.structured_content["width"], 2)
            cp = await c.call_tool("image_compress", {"path": "b.jpg", "quality": 50})
            self.assertFalse(cp.is_error, _text(cp))
            self.assertEqual(cp.structured_content["quality_used"], 50)
            rf = await c.call_tool("image_rotate_flip", {"path": "b.jpg", "rotate": 90})
            self.assertFalse(rf.is_error, _text(rf))
            self.assertEqual(rf.structured_content["output"], "imagetoolbox-out/b-rot90.jpg")
            cr = await c.call_tool("image_crop", {"path": "holiday/a.png", "aspect": "1:1"})
            self.assertFalse(cr.is_error, _text(cr))
            self.assertEqual(cr.structured_content["width"], cr.structured_content["height"])
            bt = await c.call_tool(
                "image_batch",
                {"operation": "convert", "options": {"format": "png"}, "folder": "holiday"},
            )
            self.assertFalse(bt.is_error, _text(bt))
            self.assertEqual(bt.structured_content["succeeded"], 1)
            self.assertTrue(bt.structured_content["manifest"].endswith(".json"))
        self.assertTrue((self.root_dir / "imagetoolbox-out" / "a.webp").is_file())


if __name__ == "__main__":
    unittest.main()
