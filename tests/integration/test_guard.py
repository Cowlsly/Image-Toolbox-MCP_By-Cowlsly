"""M6: unexpected exceptions inside a tool become a fixed ``[internal_error]`` result.

Neither the tool result nor the server log may contain the exception message, which can
carry host paths or private file names (threat model T9).
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import Client
from PIL import Image

from imagetoolbox_mcp import server as server_mod
from imagetoolbox_mcp.sandbox import InputRoot
from imagetoolbox_mcp.server import build_server


def _text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


class GuardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="alice-private-")
        self.root = Path(self._tmp.name).resolve()
        Image.new("RGB", (6, 4)).save(self.root / "holiday-with-bob.png")
        self.secret = f"crash in {self.root}/holiday-with-bob.png"

    def tearDown(self):
        self._tmp.cleanup()

    def client(self):
        return Client(build_server(InputRoot(self.root)), raise_exceptions=False)

    async def _call(self, tool, args):
        with self.assertLogs("imagetoolbox_mcp", level="WARNING") as logs:
            async with self.client() as c:
                r = await c.call_tool(tool, args)
        return r, "\n".join(logs.output)

    def _check(self, r, log_text, tool, exc_name):
        self.assertTrue(r.is_error)
        self.assertIn("[internal_error]", _text(r))
        self.assertNotIn("alice-private", _text(r))
        self.assertNotIn("bob", _text(r))
        self.assertIn(f"{tool} internal error: {exc_name}", log_text)
        self.assertNotIn("alice-private", log_text)
        self.assertNotIn("bob", log_text)

    async def test_sync_tool_unexpected_exception(self):
        with mock.patch.object(server_mod, "inspect_image", side_effect=IndexError(self.secret)):
            r, log_text = await self._call("image_inspect", {"path": "holiday-with-bob.png"})
        self._check(r, log_text, "image_inspect", "IndexError")

    async def test_write_tool_unexpected_exception_writes_nothing(self):
        with mock.patch.object(server_mod, "convert_image", side_effect=RuntimeError(self.secret)):
            r, log_text = await self._call(
                "image_convert", {"path": "holiday-with-bob.png", "format": "jpeg"}
            )
        self._check(r, log_text, "image_convert", "RuntimeError")
        self.assertFalse((self.root / "imagetoolbox-out").exists())

    async def test_async_batch_tool_unexpected_exception(self):
        with mock.patch.object(server_mod, "select_files", side_effect=KeyError(self.secret)):
            r, log_text = await self._call(
                "image_batch", {"operation": "convert", "options": {"format": "png"}}
            )
        self._check(r, log_text, "image_batch", "KeyError")

    async def test_guard_keeps_schemas_and_normal_errors(self):
        async with self.client() as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
            r = await c.call_tool("image_inspect", {"path": "missing.png"})
        self.assertEqual(tools["image_inspect"].input_schema["required"], ["path"])
        self.assertNotIn("ctx", tools["image_batch"].input_schema["properties"])
        self.assertTrue(r.is_error)
        self.assertIn("[not_found]", _text(r))


if __name__ == "__main__":
    unittest.main()
