"""Unit tests for :mod:`imagetoolbox_mcp.batch` (option validation, file selection, run_one)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from imagetoolbox_mcp import batch
from imagetoolbox_mcp.batch import (
    MAX_BATCH_FILES,
    parse_options,
    run_one,
    select_files,
    sha256_file,
    write_batch_manifest,
)
from imagetoolbox_mcp.engine import EngineError, Limits
from imagetoolbox_mcp.output import OutputDir


class ParseOptionsTests(unittest.TestCase):
    def assertBad(self, operation, options, fragment):
        with self.assertRaises(EngineError) as cm:
            parse_options(operation, options)
        self.assertEqual(cm.exception.code, "invalid_argument")
        self.assertIn(fragment, cm.exception.message)

    def test_valid_options(self):
        self.assertEqual(parse_options("convert", {"format": "webp"}).format, "webp")
        self.assertEqual(parse_options("resize", {"width": 10}).fit, "contain")
        self.assertIsNone(parse_options("compress", None).quality)
        self.assertEqual(parse_options("rotate_flip", {"rotate": 90}).rotate, 90)
        self.assertEqual(parse_options("crop", {"aspect": "1:1"}).aspect, "1:1")
        self.assertEqual(parse_options("crop", {"width": 5, "height": 5}).width, 5)

    def test_invalid_options(self):
        self.assertBad("blur", {}, "operation must be one of")
        self.assertBad("convert", {}, "format")
        self.assertBad("convert", {"format": "gif"}, "format")
        self.assertBad("convert", {"format": "png", "qualty": 5}, "Allowed keys: format")
        self.assertBad("convert", {"format": "png", "output_name": "x"}, "output_name")
        self.assertBad("convert", "png", "options must be an object")
        self.assertBad("resize", {}, "give width, height or both")
        self.assertBad("resize", {"width": 5, "fit": "cover"}, "needs both width and height")
        self.assertBad("resize", {"width": 0}, "width")
        self.assertBad("resize", {"width": "big"}, "width")
        self.assertBad("compress", {"quality": 50, "max_bytes": 5000}, "not both")
        self.assertBad("compress", {"max_bytes": 10}, "max_bytes")
        self.assertBad("rotate_flip", {}, "nothing to do")
        self.assertBad("rotate_flip", {"rotate": 45}, "rotate")
        self.assertBad("crop", {}, "give width and height")
        self.assertBad("crop", {"aspect": "1:1", "left": 3}, "not both")
        self.assertBad("crop", {"aspect": "wide"}, "aspect")

    def test_every_operation_has_a_model(self):
        self.assertEqual(set(batch.OPTION_MODELS), set(batch.OPERATIONS))


class SelectFilesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.folder = self.base / "pics"
        (self.folder / "nested").mkdir(parents=True)
        for name in ("b.JPG", "a.png", "c.webp", "d.tiff"):
            Image.new("RGB", (4, 4)).save(self.folder / name, format=_fmt(name))
        (self.folder / "notes.txt").write_text("x")
        (self.folder / ".hidden.png").write_bytes(b"x")
        Image.new("RGB", (4, 4)).save(self.folder / "nested" / "deep.png")
        Image.new("RGB", (4, 4)).save(self.base / "outside.png")
        os.symlink(self.base / "outside.png", self.folder / "link.png")

    def tearDown(self):
        self._tmp.cleanup()

    def names(self, sel):
        return [p.name for p in sel.files]

    def test_default_selection_sorted_no_recursion_no_hidden(self):
        sel = select_files(self.folder, None)
        self.assertEqual(self.names(sel), ["a.png", "b.JPG", "c.webp", "d.tiff"])
        self.assertEqual(sel.skipped, [{"name": "link.png", "reason": "symlink_rejected"}])
        self.assertEqual(sel.total_bytes, sum(p.stat().st_size for p in sel.files))

    def test_pattern_is_case_insensitive_name_glob(self):
        self.assertEqual(self.names(select_files(self.folder, "*.jpg")), ["b.JPG"])
        self.assertEqual(self.names(select_files(self.folder, "[ab]*")), ["a.png", "b.JPG"])
        self.assertEqual(self.names(select_files(self.folder, "*.txt")), ["notes.txt"])
        self.assertEqual(self.names(select_files(self.folder, "zzz*")), [])

    def test_bad_patterns(self):
        for pattern in ("", "  ", "nested/*.png", "..\\x.png", "x" * 101):
            with self.subTest(pattern=pattern):
                with self.assertRaises(EngineError) as cm:
                    select_files(self.folder, pattern)
                self.assertEqual(cm.exception.code, "invalid_argument")

    def test_too_many_files_refuses_instead_of_truncating(self):
        with self.assertRaises(EngineError) as cm:
            select_files(self.folder, None, max_files=3)
        self.assertEqual(cm.exception.code, "too_many_files")
        self.assertIn("4 files match", cm.exception.message)
        for bad in (0, MAX_BATCH_FILES + 1):
            with self.assertRaises(EngineError):
                select_files(self.folder, None, max_files=bad)

    def test_total_bytes_budget(self):
        with self.assertRaises(EngineError) as cm:
            select_files(self.folder, None, max_total_bytes=10)
        self.assertEqual(cm.exception.code, "batch_too_large")

    def test_oversized_file_skipped(self):
        sel = select_files(self.folder, "*.png", limits=Limits(max_file_bytes=10))
        self.assertEqual(self.names(sel), [])
        self.assertIn({"name": "a.png", "reason": "file_too_large"}, sel.skipped)

    def test_output_folder_refused(self):
        with self.assertRaises(EngineError) as cm:
            select_files(self.folder, None, output_dir=self.folder)
        self.assertIn("output folder", cm.exception.message)

    def test_huge_folder_refused(self):
        with mock.patch.object(batch, "MAX_SCAN_ENTRIES", 3):
            with self.assertRaises(EngineError) as cm:
                select_files(self.folder, None)
        self.assertEqual(cm.exception.code, "folder_too_large")


def _fmt(name):
    return {"jpg": "JPEG", "png": "PNG", "webp": "WEBP", "tiff": "TIFF"}[
        name.rsplit(".")[-1].lower()
    ]


class RunOneTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.src = self.base / "photo.png"
        im = Image.new("RGB", (40, 20), (0, 0, 255))
        im.paste((255, 0, 0), (0, 0, 20, 20))
        im.save(self.src)
        self.out = OutputDir(self.base / "out")

    def tearDown(self):
        self._tmp.cleanup()

    def test_each_operation_uses_its_default_name(self):
        cases = [
            ("convert", {"format": "webp", "lossless": True}, "photo.webp", (40, 20)),
            ("resize", {"width": 10}, "photo-10x5.png", (10, 5)),
            ("compress", {"colors": 4}, "photo-compressed.png", (40, 20)),
            ("rotate_flip", {"rotate": 90}, "photo-rot90.png", (20, 40)),
            ("crop", {"aspect": "1:1"}, "photo-crop-20x20.png", (20, 20)),
        ]
        before = sha256_file(self.src)
        for operation, options, name, size in cases:
            with self.subTest(operation=operation):
                info = run_one(operation, parse_options(operation, options), self.src, self.out)
                self.assertEqual(info["output_file"].name, name)
                with Image.open(info["output_file"]) as im:
                    self.assertEqual(im.size, size)
        self.assertEqual(sha256_file(self.src), before)

    def test_engine_errors_propagate(self):
        with self.assertRaises(EngineError) as cm:
            run_one("crop", parse_options("crop", {"width": 99, "height": 5}), self.src, self.out)
        self.assertEqual(cm.exception.code, "crop_out_of_bounds")

    def test_manifest_is_new_json_file(self):
        p1 = write_batch_manifest(self.out, "rotate_flip", {"items": []})
        p2 = write_batch_manifest(self.out, "rotate_flip", {"items": []})
        self.assertNotEqual(p1, p2)
        self.assertTrue(p1.name.startswith("batch-rotate-flip-"))
        data = json.loads(p1.read_text())
        self.assertEqual(data["tool"], "imagetoolbox-mcp")
        self.assertEqual(data["items"], [])


if __name__ == "__main__":
    unittest.main()
