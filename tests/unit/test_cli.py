"""Smoke tests for the command-line entry point."""

import contextlib
import io
import unittest

from imagetoolbox_mcp import __version__
from imagetoolbox_mcp.__main__ import main


class CliTests(unittest.TestCase):
    def test_version_flag(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn(__version__, out.getvalue())

    def test_no_args_reports_not_implemented(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main([]), 2)
        self.assertIn("not implemented", err.getvalue())


if __name__ == "__main__":
    unittest.main()
