"""Unit tests for the allowlisted input root (path traversal, symlinks, odd inputs)."""

import os
import tempfile
import unittest
from pathlib import Path

from imagetoolbox_mcp.engine import EngineError
from imagetoolbox_mcp.sandbox import InputRoot


class InputRootTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.root_dir = base / "root"
        (self.root_dir / "sub").mkdir(parents=True)
        (self.root_dir / "a.png").write_bytes(b"x")
        (self.root_dir / "sub" / "b.png").write_bytes(b"x")
        self.outside = base / "secret.png"
        self.outside.write_bytes(b"x")
        self.root = InputRoot(self.root_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def assertCode(self, code, user_path):
        with self.assertRaises(EngineError) as cm:
            self.root.resolve(user_path)
        self.assertEqual(cm.exception.code, code)
        self.assertNotIn(str(self.root_dir), cm.exception.message)

    def test_relative_paths(self):
        self.assertEqual(self.root.resolve("a.png"), self.root_dir / "a.png")
        self.assertEqual(self.root.resolve("sub/b.png"), self.root_dir / "sub" / "b.png")
        self.assertEqual(self.root.resolve("./sub/./b.png"), self.root_dir / "sub" / "b.png")

    def test_absolute_inside_root_allowed(self):
        p = self.root_dir / "sub" / "b.png"
        self.assertEqual(self.root.resolve(str(p)), p)

    def test_absolute_outside_root_rejected(self):
        self.assertCode("outside_root", str(self.outside))
        self.assertCode("outside_root", "/etc/passwd")

    def test_dotdot_rejected_even_if_it_stays_inside(self):
        self.assertCode("outside_root", "../secret.png")
        self.assertCode("outside_root", "sub/../a.png")
        self.assertCode("outside_root", str(self.root_dir / ".." / "secret.png"))

    def test_symlink_file_rejected(self):
        os.symlink(self.outside, self.root_dir / "link.png")
        self.assertCode("symlink_rejected", "link.png")

    def test_symlink_directory_component_rejected(self):
        os.symlink(self.outside.parent, self.root_dir / "escape")
        self.assertCode("symlink_rejected", "escape/secret.png")

    def test_symlink_to_inside_still_rejected(self):
        os.symlink(self.root_dir / "a.png", self.root_dir / "alias.png")
        self.assertCode("symlink_rejected", "alias.png")

    def test_bad_inputs(self):
        self.assertCode("invalid_path", "")
        self.assertCode("invalid_path", "   ")
        self.assertCode("invalid_path", "a\x00.png")
        self.assertCode("invalid_path", "a" * 2000)
        self.assertCode("not_a_file", ".")
        self.assertCode("not_found", "missing.png")
        self.assertCode("not_found", "a.png/inner.png")

    def test_root_reached_through_symlink_is_allowed(self):
        link = Path(self._tmp.name) / "root-link"
        os.symlink(self.root_dir, link)
        r = InputRoot(link)
        self.assertEqual(r.resolve("a.png"), self.root_dir / "a.png")

    def test_root_must_exist(self):
        with self.assertRaises(ValueError):
            InputRoot(self.root_dir / "nope")

    def test_display_is_root_relative(self):
        self.assertEqual(self.root.display(self.root_dir / "sub" / "b.png"), "sub/b.png")

    def test_resolve_dir(self):
        self.assertEqual(self.root.resolve_dir("."), self.root_dir)
        self.assertEqual(self.root.resolve_dir(""), self.root_dir)
        self.assertEqual(self.root.resolve_dir("sub"), self.root_dir / "sub")
        self.assertEqual(self.root.resolve_dir("sub/"), self.root_dir / "sub")
        self.assertEqual(self.root.resolve_dir(str(self.root_dir / "sub")), self.root_dir / "sub")

    def test_resolve_dir_refusals(self):
        os.symlink(self.root_dir / "sub", self.root_dir / "link")
        os.symlink(self.outside.parent, self.root_dir / "escape")
        cases = {
            "../": "outside_root",
            "sub/../sub": "outside_root",
            str(self.outside.parent): "outside_root",
            "link": "symlink_rejected",
            "escape": "symlink_rejected",
            "a.png": "not_a_folder",
            "nope": "not_found",
            "a.png/x": "not_found",
            "sub\x00": "invalid_path",
        }
        for user_path, code in cases.items():
            with self.subTest(user_path=user_path):
                with self.assertRaises(EngineError) as cm:
                    self.root.resolve_dir(user_path)
                self.assertEqual(cm.exception.code, code)


if __name__ == "__main__":
    unittest.main()
