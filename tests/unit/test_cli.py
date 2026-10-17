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


if __name__ == "__main__":
    unittest.main()
