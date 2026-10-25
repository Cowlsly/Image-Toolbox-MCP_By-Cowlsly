"""MCP-level tests for the M10 tools and the new batch operations."""

import tempfile
import unittest
from pathlib import Path

from mcp import Client
from PIL import Image

from imagetoolbox_mcp.sandbox import InputRoot
from imagetoolbox_mcp.server import build_server


def _text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


class EditToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root_dir = Path(self._tmp.name).resolve() / "images"
        (self.root_dir / "set").mkdir(parents=True)
        Image.new("RGB", (80, 60), (40, 80, 120)).save(self.root_dir / "set" / "a.jpg")
        Image.new("RGBA", (40, 40), (0, 255, 0, 200)).save(self.root_dir / "set" / "b.png")

    def tearDown(self):
        self._tmp.cleanup()

    def client(self):
        return Client(build_server(InputRoot(self.root_dir)), raise_exceptions=False)

    async def test_write_hints_on_new_tools(self):
        async with self.client() as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
        for name in ("image_adjust", "image_watermark", "image_recipe", "image_tag"):
            a = tools[name].annotations
            self.assertFalse(a.read_only_hint, name)
            self.assertFalse(a.destructive_hint, name)
            self.assertEqual(tools[name].input_schema["required"][0], "path")
        self.assertIn("text", tools["image_watermark"].input_schema["required"])
        self.assertIn("steps", tools["image_recipe"].input_schema["required"])

    async def test_each_tool_writes_a_new_file(self):
        async with self.client() as c:
            r = await c.call_tool("image_adjust", {"path": "set/a.jpg", "saturation": 0})
            self.assertFalse(r.is_error, _text(r))
            self.assertEqual(r.structured_content["output"], "imagetoolbox-out/a-adjusted.jpg")
            r = await c.call_tool(
                "image_watermark", {"path": "set/b.png", "text": "C", "position": "center"}
            )
            self.assertFalse(r.is_error, _text(r))
            self.assertEqual(r.structured_content["mode"], "RGBA")
            r = await c.call_tool(
                "image_recipe",
                {
                    "path": "set/a.jpg",
                    "steps": [{"op": "crop", "aspect": "1:1"}, {"op": "resize", "width": 30}],
                    "format": "png",
                },
            )
            self.assertFalse(r.is_error, _text(r))
            self.assertEqual((r.structured_content["width"], r.structured_content["height"]),
                             (30, 30))  # fmt: skip
            self.assertEqual(r.structured_content["output"], "imagetoolbox-out/a-recipe.png")
            r = await c.call_tool("image_tag", {"path": "set/a.jpg", "copyright": "2026"})
            self.assertFalse(r.is_error, _text(r))
            self.assertEqual(r.structured_content["tags_written"], ["copyright"])

    async def test_errors_are_structured(self):
        async with self.client() as c:
            r = await c.call_tool("image_adjust", {"path": "set/a.jpg"})
            self.assertTrue(r.is_error)
            self.assertIn("[invalid_argument]", _text(r))
            r = await c.call_tool("image_recipe", {"path": "set/a.jpg", "steps": [{"op": "x"}]})
            self.assertTrue(r.is_error)
            self.assertIn("[invalid_argument]", _text(r))
            r = await c.call_tool("image_tag", {"path": "../escape.jpg", "artist": "x"})
            self.assertTrue(r.is_error)
            self.assertIn("[outside_root]", _text(r))

    async def test_batch_adjust_and_watermark(self):
        async with self.client() as c:
            r = await c.call_tool(
                "image_batch",
                {"operation": "watermark", "options": {"text": "Cowlsly"}, "folder": "set"},
            )
            self.assertFalse(r.is_error, _text(r))
            self.assertEqual(r.structured_content["succeeded"], 2)
            r = await c.call_tool(
                "image_batch",
                {"operation": "adjust", "options": {"grayscale": True}, "folder": "set"},
            )
            self.assertEqual(r.structured_content["succeeded"], 2)
            r = await c.call_tool(
                "image_batch", {"operation": "adjust", "options": {}, "folder": "set"}
            )
            self.assertTrue(r.is_error)
            self.assertIn("[invalid_argument]", _text(r))


if __name__ == "__main__":
    unittest.main()
