"""Process isolation with a hard timeout (threat model R2)."""

import tempfile
import time
import unittest
from pathlib import Path

from mcp import Client
from PIL import Image

from imagetoolbox_mcp.engine import EngineError, inspect_image
from imagetoolbox_mcp.isolation import isolated, run_isolated
from imagetoolbox_mcp.sandbox import InputRoot
from imagetoolbox_mcp.server import build_server
from tests.unit import iso_helpers as h


class RunIsolatedTests(unittest.TestCase):
    def test_result_and_kwargs_come_back(self):
        self.assertEqual(run_isolated(h.add, 2, b=3, timeout=30), 5)

    def test_timeout_kills_the_child(self):
        t0 = time.monotonic()
        with self.assertRaises(EngineError) as cm:
            run_isolated(h.slow, 30, timeout=1.5)
        self.assertEqual(cm.exception.code, "timed_out")
        self.assertLess(time.monotonic() - t0, 15)

    def test_engine_error_survives_unchanged(self):
        with self.assertRaises(EngineError) as cm:
            run_isolated(h.refuse, timeout=30)
        self.assertEqual((cm.exception.code, cm.exception.message), ("not_found", "no such image"))

    def test_child_crash_is_decode_failed(self):
        with self.assertRaises(EngineError) as cm:
            run_isolated(h.crash, timeout=30)
        self.assertEqual(cm.exception.code, "decode_failed")

    def test_other_exception_reports_type_only(self):
        with self.assertRaises(RuntimeError) as cm:
            run_isolated(h.boom, timeout=30)
        self.assertIn("KeyError", str(cm.exception))
        self.assertNotIn("secret", str(cm.exception))

    def test_wrapper_is_identity_when_off_and_validates_range(self):
        self.assertIs(isolated(h.add, None), h.add)
        with self.assertRaises(ValueError):
            isolated(h.add, 0.1)
        self.assertEqual(isolated(h.add, 30)(1, 1), 2)

    def test_real_engine_call(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.png"
            Image.new("RGB", (7, 5)).save(p)
            info = run_isolated(inspect_image, p, timeout=60)
        self.assertEqual((info["width"], info["height"]), (7, 5))


class IsolatedServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_work_through_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            Image.new("RGB", (20, 10), (9, 9, 9)).save(root / "a.png")
            server = build_server(InputRoot(root), isolate_seconds=60)
            async with Client(server, raise_exceptions=False) as c:
                r = await c.call_tool("image_inspect", {"path": "a.png"})
                self.assertFalse(r.is_error)
                self.assertEqual(r.structured_content["width"], 20)
                r = await c.call_tool("image_convert", {"path": "a.png", "format": "jpeg"})
                self.assertFalse(r.is_error)
                self.assertEqual(r.structured_content["output"], "imagetoolbox-out/a.jpg")
                bad = await c.call_tool("image_inspect", {"path": "missing.png"})
                self.assertTrue(bad.is_error)
            self.assertTrue((root / "imagetoolbox-out" / "a.jpg").is_file())


if __name__ == "__main__":
    unittest.main()
