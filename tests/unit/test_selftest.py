"""Tests for ``imagetoolbox-mcp --self-test`` (the phone install check)."""

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from imagetoolbox_mcp.__main__ import main
from imagetoolbox_mcp.selftest import run_self_test

SRC = str(Path(__file__).resolve().parents[2] / "src")


def _run(**kwargs) -> tuple[int, str]:
    buf = io.StringIO()
    code = run_self_test(buf, **kwargs)
    return code, buf.getvalue()


class SelfTestTests(unittest.TestCase):
    def test_full_self_test_passes_including_stdio_child(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
        with mock.patch.dict(os.environ, env):
            code, out = _run()
        self.assertEqual(code, 0, out)
        self.assertIn("SELF-TEST PASSED", out)
        self.assertNotIn("FAIL", out)
        for name in (
            "tools listed",
            "tool image_inspect",
            "tool image_batch",
            "sandbox",
            "stdio server",
            "originals unchanged",
        ):
            self.assertIn(f"PASS  {name}", out)
        self.assertIn("JPEG 64x48", out)

    def test_no_absolute_paths_printed(self):
        code, out = _run(stdio=False)
        self.assertEqual(code, 0, out)
        self.assertNotIn("itmcp-selftest-", out)
        self.assertNotIn(os.sep + "tmp", out)

    def test_missing_webp_is_a_warning_not_a_failure(self):
        from PIL import features

        real = features.check
        with mock.patch.object(features, "check", lambda f: False if f == "webp" else real(f)):
            code, out = _run(stdio=False)
        self.assertEqual(code, 0, out)
        self.assertIn("WARN  codec webp", out)
        self.assertNotIn("(webp)", out)  # webp conversion skipped
        self.assertIn("1 warning(s)", out)

    def test_missing_jpeg_codec_fails(self):
        from PIL import features

        real = features.check
        with mock.patch.object(features, "check", lambda f: False if f == "jpg" else real(f)):
            code, out = _run(stdio=False)
        self.assertEqual(code, 1)
        self.assertIn("FAIL  codec jpg", out)
        self.assertIn("SELF-TEST FAILED", out)

    def test_tool_failure_is_reported_and_exit_code_is_1(self):
        from imagetoolbox_mcp import server
        from imagetoolbox_mcp.engine import EngineError

        def boom(*a, **k):
            raise EngineError("decode_failed", "simulated")

        with mock.patch.object(server, "crop_image", boom):
            code, out = _run(stdio=False)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL  tool image_crop", out)
        self.assertIn("PASS  tool image_resize", out)  # other checks still ran

    def test_cli_flag_needs_no_root(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"IMAGETOOLBOX_MCP_ROOT": ""}):
            with (
                contextlib.redirect_stdout(buf),
                mock.patch("imagetoolbox_mcp.selftest.run_self_test", return_value=0) as fake,
            ):
                self.assertEqual(main(["--self-test"]), 0)
        fake.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
