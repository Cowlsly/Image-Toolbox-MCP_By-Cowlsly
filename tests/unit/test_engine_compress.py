"""Golden tests for ``engine.compress_image`` (M3): quality, max_bytes search, PNG palette."""

import random
import tempfile
import unittest
from pathlib import Path

from PIL import ExifTags, Image

from imagetoolbox_mcp.engine import (
    PALETTE_LADDER,
    EngineError,
    _encoded,
    _quantize,
    compress_image,
)
from imagetoolbox_mcp.output import OutputDir


def _noisy(size=(160, 120), mode="RGB", seed=1):
    """Photo-like content: smooth gradient plus noise, so quality changes the size."""
    rnd = random.Random(seed)
    w, h = size
    im = Image.new("RGB", size)
    im.putdata(
        [
            (
                (x * 255 // w + rnd.randint(-40, 40)) % 256,
                (y * 255 // h + rnd.randint(-40, 40)) % 256,
                rnd.randint(0, 255),
            )
            for y in range(h)
            for x in range(w)
        ]
    )
    if mode == "RGBA":
        im = im.convert("RGBA")
        im.putalpha(Image.linear_gradient("L").resize(size))
    return im


class CompressTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.src = self.base / "src"
        self.src.mkdir()
        self.out = OutputDir(self.base / "out")

    def tearDown(self):
        self._tmp.cleanup()

    def compress(self, name, stem=None, **kw):
        r = compress_image(self.src / name, self.out, stem, **kw)
        im = Image.open(r["output_file"])
        self.addCleanup(im.close)
        return r, im

    def test_default_quality_shrinks_high_quality_jpeg(self):
        _noisy().save(self.src / "p.jpg", quality=98)
        r, im = self.compress("p.jpg")
        self.assertEqual(r["output_file"].name, "p-compressed.jpg")
        self.assertEqual((im.format, im.size), ("JPEG", (160, 120)))
        self.assertEqual(r["quality_used"], 80)
        self.assertIsNone(r["target_met"])
        self.assertLess(r["output_bytes"], r["input_bytes"])
        self.assertEqual(r["saved_bytes"], r["input_bytes"] - r["output_bytes"])
        self.assertEqual(r["output_bytes"], r["output_file"].stat().st_size)
        self.assertEqual(r["warnings"], [])

    def test_lower_quality_gives_smaller_file(self):
        _noisy().save(self.src / "p.jpg", quality=98)
        hi, _ = self.compress("p.jpg", "hi", quality=90)
        lo, _ = self.compress("p.jpg", "lo", quality=30)
        self.assertLess(lo["output_bytes"], hi["output_bytes"])

    def test_max_bytes_picks_highest_fitting_quality(self):
        _noisy().save(self.src / "p.jpg", quality=98)
        q50, _ = self.compress("p.jpg", "q50", quality=50)
        q51, _ = self.compress("p.jpg", "q51", quality=51)
        limit = q50["output_bytes"] + (q51["output_bytes"] - q50["output_bytes"]) // 2
        if q51["output_bytes"] <= q50["output_bytes"]:
            self.skipTest("encoder sizes not monotonic at q50/q51 on this platform")
        r, _ = self.compress("p.jpg", "fit", max_bytes=limit)
        self.assertTrue(r["target_met"])
        self.assertLessEqual(r["output_bytes"], limit)
        self.assertEqual(r["quality_used"], 50)
        self.assertEqual(r["max_bytes"], limit)

    def test_webp_max_bytes(self):
        _noisy((200, 200)).save(self.src / "w.png")
        lo, _ = self.compress("w.png", "lo", target="webp", quality=10)
        hi, _ = self.compress("w.png", "hi", target="webp", quality=95)
        limit = (lo["output_bytes"] + hi["output_bytes"]) // 2
        r, im = self.compress("w.png", "fit", target="webp", max_bytes=limit)
        self.assertEqual(im.format, "WEBP")
        self.assertTrue(r["target_met"])
        self.assertLessEqual(r["output_bytes"], limit)
        self.assertTrue(10 < r["quality_used"] < 95)
        above, _ = self.compress("w.png", "above", target="webp", quality=r["quality_used"] + 1)
        self.assertGreater(above["output_bytes"], limit)  # it really is the highest that fits

    def test_unreachable_target_keeps_smallest_with_warning(self):
        _noisy((400, 400)).save(self.src / "big.jpg", quality=95)
        r, _ = self.compress("big.jpg", max_bytes=1024, min_quality=40)
        self.assertFalse(r["target_met"])
        self.assertEqual(r["quality_used"], 40)
        self.assertGreater(r["output_bytes"], 1024)
        self.assertTrue(any(w.startswith("target_not_met") for w in r["warnings"]))

    def test_larger_than_source_warns(self):
        _noisy().save(self.src / "small.jpg", quality=20)
        r, _ = self.compress("small.jpg", quality=95)
        self.assertGreaterEqual(r["output_bytes"], r["input_bytes"])
        self.assertTrue(any(w.startswith("larger_than_source") for w in r["warnings"]))

    def test_png_stays_lossless_by_default(self):
        src = _noisy(mode="RGBA")
        src.save(self.src / "a.png", compress_level=0)
        r, im = self.compress("a.png")
        self.assertEqual((im.format, im.mode), ("PNG", "RGBA"))
        self.assertIsNone(r["quality_used"])
        self.assertIsNone(r["colors_used"])
        self.assertEqual(im.tobytes(), src.tobytes())  # pixel-exact
        self.assertLess(r["output_bytes"], r["input_bytes"])

    def test_png_colors_quantizes_and_keeps_alpha(self):
        src = Image.new("RGBA", (60, 40), (0, 0, 255, 0))
        src.paste((255, 0, 0, 255), (0, 0, 30, 40))
        src.paste((0, 200, 0, 128), (30, 0, 45, 40))
        src.save(self.src / "a.png")
        r, im = self.compress("a.png", colors=16)
        self.assertEqual((im.mode, r["colors_used"]), ("P", 16))
        self.assertLessEqual(len(im.getcolors(256)), 16)
        rgba = im.convert("RGBA")
        self.assertEqual(rgba.getpixel((5, 5)), (255, 0, 0, 255))
        self.assertEqual(rgba.getpixel((55, 5))[3], 0)  # transparency survives
        self.assertTrue(110 <= rgba.getpixel((35, 5))[3] <= 145)

    def test_png_max_bytes_reduces_palette_only_as_needed(self):
        _noisy((200, 200)).save(self.src / "n.png")
        full, _ = self.compress("n.png", "full")
        limit = full["output_bytes"] // 2
        r, im = self.compress("n.png", "fit", max_bytes=limit)
        self.assertTrue(r["target_met"], r)
        self.assertLessEqual(r["output_bytes"], limit)
        self.assertEqual(im.mode, "P")
        self.assertTrue(2 <= r["colors_used"] <= 256)
        self.assertTrue(any(w.startswith("palette_reduced") for w in r["warnings"]))

    def test_png_max_bytes_uses_largest_fitting_ladder_step(self):
        _noisy((120, 120)).save(self.src / "n.png")
        src = Image.open(self.src / "n.png").convert("RGB")
        self.addCleanup(src.close)
        sizes = {n: len(_encoded(_quantize(src, n), "png", {})) for n in PALETTE_LADDER}
        limit = sizes[32] + 1
        r, _ = self.compress("n.png", max_bytes=max(limit, 1024))
        expected = max(n for n in PALETTE_LADDER if sizes[n] <= max(limit, 1024))
        self.assertEqual(r["colors_used"], expected)

    def test_png_max_bytes_already_fits_is_untouched(self):
        Image.new("RGB", (50, 50), (10, 20, 30)).save(self.src / "flat.png")
        r, im = self.compress("flat.png", max_bytes=10_000)
        self.assertTrue(r["target_met"])
        self.assertIsNone(r["colors_used"])
        self.assertEqual(im.mode, "RGB")

    def test_ignored_option_warnings(self):
        _noisy().save(self.src / "p.png")
        _noisy().save(self.src / "p.jpg")
        r, _ = self.compress("p.png", "a", quality=50)
        self.assertTrue(any(w.startswith("quality_ignored") for w in r["warnings"]))
        r, _ = self.compress("p.jpg", "b", colors=8)
        self.assertTrue(any(w.startswith("colors_ignored") for w in r["warnings"]))

    def test_unsupported_source_format_saved_as_png(self):
        _noisy().save(self.src / "b.bmp")
        r, im = self.compress("b.bmp")
        self.assertEqual((im.format, r["output_file"].name), ("PNG", "b-compressed.png"))
        self.assertTrue(any(w.startswith("format_changed") for w in r["warnings"]))

    def test_metadata_stripped_orientation_applied_source_untouched(self):
        ex = Image.Exif()
        ex[ExifTags.Base.Orientation] = 6
        ex[ExifTags.IFD.GPSInfo] = {ExifTags.GPS.GPSLatitudeRef: "N"}
        _noisy((40, 20)).save(self.src / "g.jpg", exif=ex, quality=95)
        before = (self.src / "g.jpg").read_bytes()
        r, im = self.compress("g.jpg")
        self.assertEqual(im.size, (20, 40))
        self.assertTrue(r["had_gps_metadata"])
        self.assertEqual(len(im.getexif()), 0)
        self.assertEqual((self.src / "g.jpg").read_bytes(), before)

    def test_never_overwrites(self):
        _noisy().save(self.src / "p.jpg")
        a, _ = self.compress("p.jpg")
        b, _ = self.compress("p.jpg")
        self.assertEqual(
            (a["output_file"].name, b["output_file"].name),
            ("p-compressed.jpg", "p-compressed-1.jpg"),
        )

    def test_invalid_arguments_write_nothing(self):
        _noisy().save(self.src / "p.jpg")
        bad = [
            dict(quality=50, max_bytes=5000),
            dict(quality=0),
            dict(max_bytes=10),
            dict(min_quality=99),
            dict(colors=1),
            dict(colors=300),
            dict(target="gif"),
        ]
        for kw in bad:
            with self.subTest(kw=kw), self.assertRaises(EngineError) as cm:
                compress_image(self.src / "p.jpg", self.out, None, **kw)
            self.assertIn(cm.exception.code, ("invalid_argument", "unsupported_target"))
        with self.assertRaises(EngineError) as cm:
            compress_image(self.src / "p.jpg", self.out, "../x")
        self.assertEqual(cm.exception.code, "invalid_name")
        self.assertFalse(self.out.path.exists() and any(self.out.path.iterdir()))


if __name__ == "__main__":
    unittest.main()
