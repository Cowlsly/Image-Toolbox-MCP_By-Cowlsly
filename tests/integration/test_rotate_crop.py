"""MCP-level tests for ``image_rotate_flip`` and ``image_crop``."""

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


class RotateCropToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.root_dir = self.base / "images"
        (self.root_dir / "trip").mkdir(parents=True)
        im = Image.new("RGB", (400, 300), (0, 128, 0))
        im.paste((255, 0, 0), (0, 0, 200, 300))  # left half red
        im.save(self.root_dir / "trip" / "view.png")
        Image.new("RGB", (4, 4)).save(self.base / "outside.png")
        self.out_dir = self.root_dir / "imagetoolbox-out"

    def tearDown(self):
        self._tmp.cleanup()

    def client(self):
        return Client(build_server(InputRoot(self.root_dir)), raise_exceptions=False)

    async def test_schemas_and_annotations(self):
        async with self.client() as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
        rf, cr = tools["image_rotate_flip"], tools["image_crop"]
        self.assertEqual(rf.input_schema["required"], ["path"])
        self.assertEqual(rf.input_schema["properties"]["rotate"]["enum"], [0, 90, 180, 270])
        flip = rf.input_schema["properties"]["flip"]["anyOf"][0]
        self.assertEqual(flip["enum"], ["horizontal", "vertical"])
        self.assertEqual(cr.input_schema["required"], ["path"])
        for name in ("left", "top", "width", "height", "aspect", "format", "output_name"):
            self.assertIn(name, cr.input_schema["properties"])
        for tool in (rf, cr):
            a = tool.annotations
            self.assertEqual(
                (a.read_only_hint, a.destructive_hint, a.idempotent_hint, a.open_world_hint),
                (False, False, False, False),
            )
        self.assertIn("rotate", rf.output_schema["properties"])
        self.assertIn("crop_left", cr.output_schema["properties"])

    async def test_rotate_flip_then_inspect(self):
        async with self.client() as c:
            r = await c.call_tool(
                "image_rotate_flip", {"path": "trip/view.png", "rotate": 90, "flip": "vertical"}
            )
            self.assertFalse(r.is_error, _text(r))
            d = r.structured_content
            self.assertEqual(d["output"], "imagetoolbox-out/view-rot90-flipV.png")
            self.assertEqual(
                (d["width"], d["height"], d["rotate"], d["flip"]), (300, 400, 90, "vertical")
            )
            ins = await c.call_tool("image_inspect", {"path": d["output"]})
            self.assertEqual(ins.structured_content["height"], 400)
        with Image.open(self.out_dir / "view-rot90-flipV.png") as im:
            # red left half -> top after clockwise turn -> bottom after vertical flip
            self.assertEqual(im.getpixel((150, 399)), (255, 0, 0))
            self.assertEqual(im.getpixel((150, 0)), (0, 128, 0))

    async def test_crop_box_and_aspect(self):
        async with self.client() as c:
            r = await c.call_tool(
                "image_crop",
                {"path": "trip/view.png", "left": 190, "top": 10, "width": 20, "height": 30},
            )
            self.assertFalse(r.is_error, _text(r))
            d = r.structured_content
            self.assertEqual(d["output"], "imagetoolbox-out/view-crop-20x30.png")
            self.assertEqual((d["crop_left"], d["crop_top"], d["source_width"]), (190, 10, 400))
            r2 = await c.call_tool(
                "image_crop",
                {
                    "path": "trip/view.png",
                    "aspect": "16:9",
                    "format": "webp",
                    "output_name": "wide",
                },
            )
            self.assertFalse(r2.is_error, _text(r2))
            self.assertEqual(r2.structured_content["output"], "imagetoolbox-out/wide.webp")
            self.assertEqual(
                (r2.structured_content["width"], r2.structured_content["height"]), (400, 225)
            )
        with Image.open(self.out_dir / "view-crop-20x30.png") as im:
            self.assertEqual(im.getpixel((5, 5)), (255, 0, 0))
            self.assertEqual(im.getpixel((15, 5)), (0, 128, 0))

    async def test_structured_errors_and_nothing_written(self):
        os.symlink(self.base / "outside.png", self.root_dir / "link.png")
        cases = [
            ("image_rotate_flip", {"path": "../outside.png", "rotate": 90}, "[outside_root]"),
            ("image_rotate_flip", {"path": "link.png", "rotate": 90}, "[symlink_rejected]"),
            ("image_rotate_flip", {"path": "trip/view.png"}, "[invalid_argument]"),
            ("image_crop", {"path": "trip/view.png"}, "[invalid_argument]"),
            (
                "image_crop",
                {"path": "trip/view.png", "left": 390, "width": 20, "height": 20},
                "[crop_out_of_bounds]",
            ),
            (
                "image_crop",
                {"path": "trip/view.png", "aspect": "1:1", "width": 5, "height": 5},
                "[invalid_argument]",
            ),
            ("image_crop", {"path": "trip/view.png", "aspect": "0:1"}, "[invalid_argument]"),
            (
                "image_crop",
                {"path": "trip/view.png", "aspect": "1:1", "output_name": "a/b"},
                "[invalid_name]",
            ),
        ]
        async with self.client() as c:
            for tool, args, code in cases:
                with self.subTest(tool=tool, args=args):
                    r = await c.call_tool(tool, args)
                    self.assertTrue(r.is_error)
                    self.assertIn(code, _text(r))
                    self.assertNotIn(str(self.base), _text(r))
            for tool, bad in (
                ("image_rotate_flip", {"path": "trip/view.png", "rotate": 45}),
                ("image_rotate_flip", {"path": "trip/view.png", "flip": "diagonal"}),
                ("image_crop", {"path": "trip/view.png", "aspect": "16/9"}),
                ("image_crop", {"path": "trip/view.png", "width": 0, "height": 5}),
                ("image_crop", {"path": "trip/view.png", "left": -1, "width": 5, "height": 5}),
            ):
                with self.subTest(schema=bad):
                    self.assertTrue((await c.call_tool(tool, bad)).is_error)
        self.assertFalse(self.out_dir.exists() and any(self.out_dir.iterdir()))


if __name__ == "__main__":
    unittest.main()
