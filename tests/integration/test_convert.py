"""MCP-level tests for ``image_convert``: schema, hints, output policy, structured errors."""

import os
import tempfile
import unittest
from pathlib import Path

from mcp import Client
from PIL import Image

from imagetoolbox_mcp.output import OutputDir
from imagetoolbox_mcp.sandbox import InputRoot
from imagetoolbox_mcp.server import build_server


def _text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


class ConvertToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.root_dir = self.base / "images"
        (self.root_dir / "trip").mkdir(parents=True)
        Image.new("RGBA", (12, 9), (0, 128, 0, 200)).save(self.root_dir / "trip" / "leaf.png")
        Image.new("RGB", (4, 4)).save(self.base / "outside.png")
        self.out_dir = self.root_dir / "imagetoolbox-out"

    def tearDown(self):
        self._tmp.cleanup()

    def client(self, out=None):
        server = build_server(InputRoot(self.root_dir), out=out)
        return Client(server, raise_exceptions=False)

    async def test_schema_and_annotations(self):
        async with self.client() as c:
            tool = next(t for t in (await c.list_tools()).tools if t.name == "image_convert")
        props = tool.input_schema["properties"]
        self.assertEqual(sorted(tool.input_schema["required"]), ["format", "path"])
        self.assertEqual(props["format"]["enum"], ["jpeg", "png", "webp"])
        self.assertEqual((props["quality"]["minimum"], props["quality"]["maximum"]), (1, 100))
        self.assertNotIn("output_dir", props)  # clients cannot choose where files go
        a = tool.annotations
        self.assertFalse(a.read_only_hint)
        self.assertFalse(a.destructive_hint)
        self.assertFalse(a.idempotent_hint)
        self.assertFalse(a.open_world_hint)
        self.assertIn("output_bytes", tool.output_schema["properties"])

    async def test_convert_then_inspect_and_no_overwrite(self):
        async with self.client() as c:
            r1 = await c.call_tool("image_convert", {"path": "trip/leaf.png", "format": "jpeg"})
            r2 = await c.call_tool("image_convert", {"path": "trip/leaf.png", "format": "jpeg"})
            self.assertFalse(r1.is_error, _text(r1))
            d1, d2 = r1.structured_content, r2.structured_content
            self.assertEqual(d1["source"], "trip/leaf.png")
            self.assertEqual(d1["output"], "imagetoolbox-out/leaf.jpg")
            self.assertEqual(d2["output"], "imagetoolbox-out/leaf-1.jpg")
            self.assertEqual((d1["format"], d1["width"], d1["height"]), ("JPEG", 12, 9))
            self.assertTrue(d1["warnings"])
            # Output can be fed straight back into another tool.
            ins = await c.call_tool("image_inspect", {"path": d1["output"]})
            self.assertFalse(ins.is_error, _text(ins))
            self.assertEqual(ins.structured_content["format"], "JPEG")
        self.assertEqual(sorted(p.name for p in self.out_dir.iterdir()), ["leaf-1.jpg", "leaf.jpg"])

    async def test_custom_output_name_and_external_out_folder(self):
        ext = OutputDir(self.base / "exports")
        async with self.client(out=ext) as c:
            r = await c.call_tool(
                "image_convert",
                {
                    "path": "trip/leaf.png",
                    "format": "webp",
                    "output_name": "Leaf small",
                    "quality": 50,
                },
            )
        self.assertFalse(r.is_error, _text(r))
        self.assertEqual(r.structured_content["output"], "Leaf small.webp")  # name only
        self.assertTrue((self.base / "exports" / "Leaf small.webp").is_file())
        self.assertNotIn(str(self.base), _text(r))

    async def test_structured_errors_and_nothing_written(self):
        os.symlink(self.base / "outside.png", self.root_dir / "link.png")
        cases = [
            ({"path": "../outside.png", "format": "png"}, "[outside_root]"),
            ({"path": "link.png", "format": "png"}, "[symlink_rejected]"),
            ({"path": "trip/leaf.png", "format": "png", "output_name": "../x"}, "[invalid_name]"),
            (
                {"path": "trip/leaf.png", "format": "png", "output_name": ".bashrc"},
                "[invalid_name]",
            ),
            (
                {"path": "trip/leaf.png", "format": "png", "output_name": "a.png/b"},
                "[invalid_name]",
            ),
        ]
        async with self.client() as c:
            for args, code in cases:
                with self.subTest(args=args):
                    r = await c.call_tool("image_convert", args)
                    self.assertTrue(r.is_error)
                    self.assertIn(code, _text(r))
                    self.assertNotIn(str(self.base), _text(r))
            for bad in (
                {"path": "trip/leaf.png", "format": "gif"},
                {"path": "trip/leaf.png", "format": "png", "quality": 0},
                {"path": "trip/leaf.png"},
            ):
                with self.subTest(schema=bad):
                    self.assertTrue((await c.call_tool("image_convert", bad)).is_error)
        self.assertFalse(self.out_dir.exists() and any(self.out_dir.iterdir()))

    async def test_original_untouched(self):
        f = self.root_dir / "trip" / "leaf.png"
        before = (f.read_bytes(), f.stat().st_mtime_ns)
        async with self.client() as c:
            for fmt in ("jpeg", "png", "webp"):
                r = await c.call_tool("image_convert", {"path": "trip/leaf.png", "format": fmt})
                self.assertFalse(r.is_error, _text(r))
        self.assertEqual((f.read_bytes(), f.stat().st_mtime_ns), before)
        self.assertIn("leaf.png", os.listdir(self.out_dir))  # PNG -> PNG makes a new file


if __name__ == "__main__":
    unittest.main()
