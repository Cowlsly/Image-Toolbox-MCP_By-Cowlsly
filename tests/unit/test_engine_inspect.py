"""Unit tests for the Pillow inspect spike. Fixtures are generated at test time."""

import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from imagetoolbox_mcp.engine import EngineError, Limits, inspect_image


class InspectImageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make(self, name, mode="RGB", size=(32, 16), fmt=None, **save_kw):
        path = self.dir / name
        Image.new(mode, size, 0).save(path, format=fmt, **save_kw)
        return path

    def test_jpeg_basic(self):
        p = self._make("a.jpg")
        r = inspect_image(p)
        self.assertEqual(r["format"], "JPEG")
        self.assertEqual((r["width"], r["height"]), (32, 16))
        self.assertFalse(r["has_alpha"])
        self.assertEqual(r["file_bytes"], p.stat().st_size)

    def test_png_alpha(self):
        r = inspect_image(self._make("a.png", mode="RGBA"))
        self.assertEqual(r["format"], "PNG")
        self.assertTrue(r["has_alpha"])

    def test_webp(self):
        r = inspect_image(self._make("a.webp", mode="RGBA"))
        self.assertEqual(r["format"], "WEBP")

    def test_orientation_reported_gps_withheld(self):
        exif = Image.Exif()
        exif[0x0112] = 6  # Orientation: rotate 90 CW
        exif[0x010F] = "TestMake"
        exif[0x8825] = {1: "N", 2: (1.0, 2.0, 3.0)}  # GPSInfo IFD
        p = self.dir / "e.jpg"
        Image.new("RGB", (10, 20)).save(p, exif=exif)
        r = inspect_image(p)
        self.assertEqual(r["orientation"], 6)
        self.assertEqual(r["exif"].get("Make"), "TestMake")
        self.assertTrue(r["has_gps_metadata"])
        self.assertNotIn("GPSInfo", r["exif"])

    def test_original_untouched(self):
        p = self._make("keep.png")
        before = (p.read_bytes(), p.stat().st_mtime_ns)
        inspect_image(p)
        self.assertEqual(before, (p.read_bytes(), p.stat().st_mtime_ns))

    def test_missing_file(self):
        with self.assertRaises(EngineError) as cm:
            inspect_image(self.dir / "nope.png")
        self.assertEqual(cm.exception.code, "not_found")

    def test_not_an_image(self):
        p = self.dir / "x.png"
        p.write_bytes(b"not an image at all")
        with self.assertRaises(EngineError) as cm:
            inspect_image(p)
        self.assertEqual(cm.exception.code, "unsupported_format")

    def test_directory_rejected(self):
        with self.assertRaises(EngineError) as cm:
            inspect_image(self.dir)
        self.assertEqual(cm.exception.code, "not_a_file")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unsupported")
    def test_symlink_rejected(self):
        target = self._make("t.png")
        link = self.dir / "l.png"
        os.symlink(target, link)
        with self.assertRaises(EngineError) as cm:
            inspect_image(link)
        self.assertEqual(cm.exception.code, "symlink_rejected")

    def test_file_size_limit(self):
        p = self._make("big.png")
        with self.assertRaises(EngineError) as cm:
            inspect_image(p, Limits(max_file_bytes=10))
        self.assertEqual(cm.exception.code, "file_too_large")

    def test_pixel_limit(self):
        p = self._make("wide.png", size=(100, 100))
        with self.assertRaises(EngineError) as cm:
            inspect_image(p, Limits(max_pixels=50))
        self.assertEqual(cm.exception.code, "too_many_pixels")


if __name__ == "__main__":
    unittest.main()
