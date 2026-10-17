"""Unit tests for the output policy (ADR-0002): safe names, never overwrite, atomic writes."""

import os
import tempfile
import threading
import unittest
from pathlib import Path

from imagetoolbox_mcp.engine import EngineError
from imagetoolbox_mcp.output import MAX_SUFFIX, OutputDir, default_stem, validate_stem


def _writer(data: bytes):
    return lambda fh: fh.write(data)


class StemTests(unittest.TestCase):
    def test_valid_stems(self):
        for s in ("cat", "Cat 2", "a.b_c-d", "x" * 100, "  padded  "):
            with self.subTest(s=s):
                self.assertEqual(validate_stem(s), s.strip())

    def test_invalid_stems(self):
        bad = ["", "   ", "x" * 101, "a/b", "a\\b", "..", ".", ".hidden", "a\x00b", "é", "a:b", 5]
        for s in bad:
            with self.subTest(s=s):
                with self.assertRaises(EngineError) as cm:
                    validate_stem(s)
                self.assertEqual(cm.exception.code, "invalid_name")

    def test_default_stem_sanitises(self):
        self.assertEqual(default_stem(Path("Ünïcode phöto.JPG")), "_n_code ph_to")
        self.assertEqual(default_stem(Path("...")), "image")
        self.assertEqual(default_stem(Path(".bashrc")), "bashrc")
        self.assertEqual(len(default_stem(Path("y" * 300 + ".png"))), 100)
        validate_stem(default_stem(Path("weird;name$(x).png")))  # always valid


class OutputDirTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.out = OutputDir(self.base / "out")

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_folder_lazily_and_writes(self):
        self.assertFalse((self.base / "out").exists())
        p = self.out.write_new("cat", "png", _writer(b"abc"))
        self.assertEqual(p, self.base / "out" / "cat.png")
        self.assertEqual(p.read_bytes(), b"abc")

    def test_never_overwrites_existing(self):
        (self.base / "out").mkdir()
        existing = self.base / "out" / "cat.png"
        existing.write_bytes(b"ORIGINAL")
        p1 = self.out.write_new("cat", "png", _writer(b"1"))
        p2 = self.out.write_new("cat", "png", _writer(b"2"))
        self.assertEqual([p1.name, p2.name], ["cat-1.png", "cat-2.png"])
        self.assertEqual(existing.read_bytes(), b"ORIGINAL")

    def test_planted_symlink_is_not_written_through(self):
        (self.base / "out").mkdir()
        victim = self.base / "victim.txt"
        victim.write_bytes(b"keep")
        os.symlink(victim, self.base / "out" / "cat.png")
        p = self.out.write_new("cat", "png", _writer(b"new"))
        self.assertEqual(p.name, "cat-1.png")
        self.assertEqual(victim.read_bytes(), b"keep")

    def test_output_folder_replaced_by_symlink_is_refused(self):
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        os.symlink(elsewhere, self.base / "out")
        with self.assertRaises(EngineError) as cm:
            self.out.write_new("cat", "png", _writer(b"x"))
        self.assertEqual(cm.exception.code, "output_unavailable")
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_failed_writer_leaves_nothing_behind(self):
        def boom(fh):
            fh.write(b"partial")
            raise EngineError("encode_failed", "nope")

        with self.assertRaises(EngineError):
            self.out.write_new("cat", "png", boom)
        self.assertEqual(list((self.base / "out").iterdir()), [])

    def test_name_exhausted(self):
        (self.base / "out").mkdir()
        (self.base / "out" / "c.png").touch()
        for n in range(1, MAX_SUFFIX + 1):
            (self.base / "out" / f"c-{n}.png").touch()
        with self.assertRaises(EngineError) as cm:
            self.out.write_new("c", "png", _writer(b"x"))
        self.assertEqual(cm.exception.code, "name_exhausted")

    def test_rejects_bad_extension_and_stem(self):
        for stem, ext in (("a/b", "png"), ("a", "PNG"), ("a", "sh/x"), ("a", "")):
            with self.subTest(stem=stem, ext=ext):
                with self.assertRaises(EngineError):
                    self.out.write_new(stem, ext, _writer(b"x"))

    def test_concurrent_writes_get_distinct_names(self):
        results, errors = [], []

        def go(i):
            try:
                results.append(self.out.write_new("same", "png", _writer(str(i).encode())))
            except Exception as e:  # pragma: no cover - failure path
                errors.append(e)

        threads = [threading.Thread(target=go, args=(i,)) for i in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len({p.name for p in results}), 16)
        contents = sorted(int(p.read_bytes()) for p in results)
        self.assertEqual(contents, list(range(16)))

    def test_constructor_validation(self):
        f = self.base / "file"
        f.write_bytes(b"")
        with self.assertRaises(ValueError):
            OutputDir(f)
        with self.assertRaises(ValueError):
            OutputDir(self.base / "no" / "such" / "parent")


if __name__ == "__main__":
    unittest.main()
