"""MCP-level tests for ``image_resize``: schema, hints, results, structured errors."""

import os
import tempfile
import unittest
from pathlib import Path

from mcp import Client
from PIL import Image

from imagetoolbox_mcp.sandbox import InputRoot
from imagetoolbox_mcp.server import build_server


def _text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


class ResizeToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.root_dir = self.base / "images"
        (self.root_dir / "trip").mkdir(parents=True)
        Image.new("RGB", (400, 300), (0, 128, 0)).save(self.root_dir / "trip" / "view.jpg")
        Image.new("RGB", (4, 4)).save(self.base / "outside.png")
        self.out_dir = self.root_dir / "imagetoolbox-out"

    def tearDown(self):
        self._tmp.cleanup()

    def client(self):
        return Client(build_server(InputRoot(self.root_dir)), raise_exceptions=False)

    async def test_schema_and_annotations(self):
        async with self.client() as c:
            tool = next(t for t in (await c.list_tools()).tools if t.name == "image_resize")
        props = tool.input_schema["properties"]
        self.assertEqual(tool.input_schema["required"], ["path"])
        self.assertEqual(props["fit"]["enum"], ["contain", "cover", "exact"])
        self.assertEqual(props["fit"]["default"], "contain")
        self.assertEqual(props["resample"]["default"], "lanczos")
        self.assertFalse(props["allow_upscale"]["default"])
        self.assertNotIn("output_dir", props)
        a = tool.annotations
        self.assertEqual(
            (a.read_only_hint, a.destructive_hint, a.idempotent_hint, a.open_world_hint),
            (False, False, False, False),
        )
        self.assertIn("source_width", tool.output_schema["properties"])

    async def test_resize_then_inspect(self):
        async with self.client() as c:
            r = await c.call_tool("image_resize", {"path": "trip/view.jpg", "width": 100})
            self.assertFalse(r.is_error, _text(r))
            d = r.structured_content
            self.assertEqual(d["output"], "imagetoolbox-out/view-100x75.jpg")
            self.assertEqual((d["format"], d["width"], d["height"]), ("JPEG", 100, 75))
            self.assertEqual((d["source_width"], d["source_height"]), (400, 300))
            ins = await c.call_tool("image_inspect", {"path": d["output"]})
            self.assertEqual(ins.structured_content["width"], 100)

    async def test_cover_with_format_and_name(self):
        async with self.client() as c:
            r = await c.call_tool(
                "image_resize",
                {
                    "path": "trip/view.jpg",
                    "width": 64,
                    "height": 64,
                    "fit": "cover",
                    "format": "webp",
                    "output_name": "avatar",
                },
            )
        self.assertFalse(r.is_error, _text(r))
        self.assertEqual(r.structured_content["output"], "imagetoolbox-out/avatar.webp")
        with Image.open(self.out_dir / "avatar.webp") as im:
            self.assertEqual((im.format, im.size), ("WEBP", (64, 64)))

    async def test_upscale_skipped_warning(self):
        async with self.client() as c:
            r = await c.call_tool("image_resize", {"path": "trip/view.jpg", "width": 800})
        self.assertFalse(r.is_error, _text(r))
        self.assertEqual(r.structured_content["width"], 400)
        self.assertTrue(r.structured_content["warnings"][0].startswith("upscale_skipped"))

    async def test_structured_errors_and_nothing_written(self):
        os.symlink(self.base / "outside.png", self.root_dir / "link.png")
        cases = [
            ({"path": "../outside.png", "width": 2}, "[outside_root]"),
            ({"path": "link.png", "width": 2}, "[symlink_rejected]"),
            ({"path": "trip/view.jpg"}, "[invalid_argument]"),
            ({"path": "trip/view.jpg", "width": 50, "fit": "cover"}, "[invalid_argument]"),
            (
                {"path": "trip/view.jpg", "width": 500, "height": 500, "fit": "exact"},
                "[upscale_refused]",
            ),
            ({"path": "trip/view.jpg", "width": 9, "output_name": "../x"}, "[invalid_name]"),
        ]
        async with self.client() as c:
            for args, code in cases:
                with self.subTest(args=args):
                    r = await c.call_tool("image_resize", args)
                    self.assertTrue(r.is_error)
                    self.assertIn(code, _text(r))
                    self.assertNotIn(str(self.base), _text(r))
            for bad in (
                {"path": "trip/view.jpg", "width": 0},
                {"path": "trip/view.jpg", "width": 20000},
                {"path": "trip/view.jpg", "width": 10, "fit": "stretch"},
                {"path": "trip/view.jpg", "width": 10, "resample": "magic"},
                {"width": 10},
            ):
                with self.subTest(schema=bad):
                    self.assertTrue((await c.call_tool("image_resize", bad)).is_error)
        self.assertFalse(self.out_dir.exists() and any(self.out_dir.iterdir()))


if __name__ == "__main__":
    unittest.main()
