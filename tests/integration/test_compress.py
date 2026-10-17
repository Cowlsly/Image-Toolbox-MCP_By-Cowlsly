"""MCP-level tests for ``image_compress``: schema, hints, results, structured errors."""

import os
import random
import tempfile
import unittest
from pathlib import Path

from mcp import Client
from PIL import Image

from imagetoolbox_mcp.sandbox import InputRoot
from imagetoolbox_mcp.server import build_server


def _text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


class CompressToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.root_dir = self.base / "images"
        (self.root_dir / "trip").mkdir(parents=True)
        rnd = random.Random(7)
        im = Image.new("RGB", (240, 180))
        im.putdata([(rnd.randrange(256), x % 256, 90) for x in range(240 * 180)])
        im.save(self.root_dir / "trip" / "view.jpg", quality=97)
        Image.new("RGB", (4, 4)).save(self.base / "outside.png")
        self.out_dir = self.root_dir / "imagetoolbox-out"

    def tearDown(self):
        self._tmp.cleanup()

    def client(self):
        return Client(build_server(InputRoot(self.root_dir)), raise_exceptions=False)

    async def test_schema_and_annotations(self):
        async with self.client() as c:
            tool = next(t for t in (await c.list_tools()).tools if t.name == "image_compress")
        props = tool.input_schema["properties"]
        self.assertEqual(tool.input_schema["required"], ["path"])
        self.assertEqual(props["min_quality"]["default"], 10)
        self.assertIn("max_bytes", props)
        self.assertNotIn("output_dir", props)
        a = tool.annotations
        self.assertEqual(
            (a.read_only_hint, a.destructive_hint, a.idempotent_hint, a.open_world_hint),
            (False, False, False, False),
        )
        for key in ("quality_used", "saved_bytes", "target_met"):
            self.assertIn(key, tool.output_schema["properties"])

    async def test_compress_then_inspect(self):
        async with self.client() as c:
            r = await c.call_tool("image_compress", {"path": "trip/view.jpg", "quality": 60})
            self.assertFalse(r.is_error, _text(r))
            d = r.structured_content
            self.assertEqual(d["output"], "imagetoolbox-out/view-compressed.jpg")
            self.assertEqual((d["format"], d["quality_used"]), ("JPEG", 60))
            self.assertGreater(d["saved_bytes"], 0)
            ins = await c.call_tool("image_inspect", {"path": d["output"]})
            self.assertEqual(ins.structured_content["file_bytes"], d["output_bytes"])

    async def test_max_bytes_to_webp(self):
        limit = 20_000
        async with self.client() as c:
            r = await c.call_tool(
                "image_compress",
                {
                    "path": "trip/view.jpg",
                    "max_bytes": limit,
                    "format": "webp",
                    "output_name": "small",
                },
            )
        self.assertFalse(r.is_error, _text(r))
        d = r.structured_content
        self.assertEqual(d["output"], "imagetoolbox-out/small.webp")
        self.assertEqual(d["target_met"], d["output_bytes"] <= limit)
        if not d["target_met"]:
            self.assertTrue(any(w.startswith("target_not_met") for w in d["warnings"]))

    async def test_structured_errors_and_nothing_written(self):
        os.symlink(self.base / "outside.png", self.root_dir / "link.png")
        cases = [
            ({"path": "../outside.png"}, "[outside_root]"),
            ({"path": "link.png"}, "[symlink_rejected]"),
            ({"path": "trip/view.jpg", "quality": 50, "max_bytes": 5000}, "[invalid_argument]"),
            ({"path": "trip/view.jpg", "output_name": "a/b"}, "[invalid_name]"),
        ]
        async with self.client() as c:
            for args, code in cases:
                with self.subTest(args=args):
                    r = await c.call_tool("image_compress", args)
                    self.assertTrue(r.is_error)
                    self.assertIn(code, _text(r))
                    self.assertNotIn(str(self.base), _text(r))
            for bad in (
                {"path": "trip/view.jpg", "quality": 0},
                {"path": "trip/view.jpg", "max_bytes": 5},
                {"path": "trip/view.jpg", "colors": 1},
                {"path": "trip/view.jpg", "format": "gif"},
                {"quality": 50},
            ):
                with self.subTest(schema=bad):
                    self.assertTrue((await c.call_tool("image_compress", bad)).is_error)
        self.assertFalse(self.out_dir.exists() and any(self.out_dir.iterdir()))


if __name__ == "__main__":
    unittest.main()
