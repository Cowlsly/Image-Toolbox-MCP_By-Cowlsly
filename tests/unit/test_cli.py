"""Smoke tests for the command-line entry point."""

import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from imagetoolbox_mcp import __version__
from imagetoolbox_mcp.__main__ import ROOT_ENV, main


class CliTests(unittest.TestCase):
    def test_version_flag(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn(__version__, out.getvalue())

    def test_root_is_required(self):
        err = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != ROOT_ENV}
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stderr(err):
            self.assertEqual(main([]), 2)
        self.assertIn("input folder is required", err.getvalue())

    def test_missing_root_directory_is_rejected(self):
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stderr(err):
            self.assertEqual(main(["--root", os.path.join(d, "nope")]), 2)
        self.assertIn("not an existing directory", err.getvalue())

    def test_bad_output_folder_is_rejected(self):
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stderr(err):
            afile = os.path.join(d, "file")
            open(afile, "w").close()
            self.assertEqual(main(["--root", d, "--out", afile]), 2)
            self.assertEqual(main(["--root", d, "--out", os.path.join(d, "a", "b")]), 2)
        self.assertIn("not a directory", err.getvalue())
        self.assertIn("Parent of the output folder", err.getvalue())


if __name__ == "__main__":
    unittest.main()


class CliExtrasTests(unittest.TestCase):
    def test_sbom_is_cyclonedx_with_runtime_deps(self):
        import json

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--sbom"]), 0)
        bom = json.loads(out.getvalue())
        self.assertEqual((bom["bomFormat"], bom["specVersion"]), ("CycloneDX", "1.5"))
        self.assertEqual(bom["metadata"]["component"]["name"], "imagetoolbox-mcp")
        names = {c["name"].lower() for c in bom["components"]}
        self.assertTrue({"pillow", "mcp"} <= names, names)
        for c in bom["components"]:
            self.assertTrue(c["purl"].startswith("pkg:pypi/"))
        refs = {d["ref"] for d in bom["dependencies"]}
        self.assertIn(bom["metadata"]["component"]["bom-ref"], refs)

    def test_json_log_formatter(self):
        import json
        import logging

        from imagetoolbox_mcp.__main__ import JsonLogFormatter

        rec = logging.LogRecord("imagetoolbox_mcp", logging.INFO, "x", 1, "ok %s", ("a",), None)
        entry = json.loads(JsonLogFormatter().format(rec))
        self.assertEqual(entry["level"], "INFO")
        self.assertEqual(entry["msg"], "ok a")
        self.assertTrue(entry["ts"].endswith("Z"))

    def test_isolate_out_of_range(self):
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stderr(err):
            self.assertEqual(main(["--root", d, "--isolate", "0.2"]), 2)
        self.assertIn("--isolate", err.getvalue())


class CliLimitsTests(unittest.TestCase):
    def test_max_megapixels_range_and_passthrough(self):
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stderr(err):
            self.assertEqual(main(["--root", d, "--max-megapixels", "100"]), 2)
        with (
            tempfile.TemporaryDirectory() as d,
            mock.patch("imagetoolbox_mcp.server.run_stdio") as run,
        ):
            self.assertEqual(main(["--root", d, "--max-megapixels", "12", "--isolate", "30"]), 0)
        limits = run.call_args.args[1]
        self.assertEqual(limits.max_pixels, 12_000_000)
        self.assertEqual(run.call_args.kwargs["isolate_seconds"], 30)
