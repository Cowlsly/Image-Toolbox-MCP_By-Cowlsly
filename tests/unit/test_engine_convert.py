"""Golden tests for ``engine.convert_image`` (M3): pixels, modes, metadata, warnings."""

import io
import tempfile
import unittest
from pathlib import Path

from PIL import ExifTags, Image, ImageChops, ImageCms

from imagetoolbox_mcp.engine import EngineError, convert_image
from imagetoolbox_mcp.output import OutputDir


def _exif(orientation=None, gps=False):
    ex = Image.Exif()
    ex[ExifTags.Base.Make] = "TestCam"
    if orientation:
        ex[ExifTags.Base.Orientation] = orientation
    if gps:
        ex[ExifTags.IFD.GPSInfo] = {ExifTags.GPS.GPSLatitudeRef: "N"}
    return ex


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.src = self.base / "src"
        self.src.mkdir()
        self.out = OutputDir(self.base / "out")

    def tearDown(self):
        self._tmp.cleanup()

    def convert(self, name, target, stem="o", **kw):
        r = convert_image(self.src / name, target, self.out, stem, **kw)
        im = Image.open(r["output_file"])
        self.addCleanup(im.close)
        return r, im

    def test_rgba_png_to_jpeg_flattens_on_white(self):
        Image.new("RGBA", (10, 6), (255, 0, 0, 128)).save(self.src / "a.png")
        r, im = self.convert("a.png", "jpeg", quality=95)
        self.assertEqual((im.format, im.mode, im.size), ("JPEG", "RGB", (10, 6)))
        self.assertEqual(r["output_file"].name, "o.jpg")
        self.assertTrue(any(w.startswith("alpha_flattened") for w in r["warnings"]))
        rr, g, b = im.getpixel((5, 3))
        self.assertGreater(rr, 245)
        self.assertTrue(115 <= g <= 140 and 115 <= b <= 140, (rr, g, b))

    def test_exif_orientation_applied_and_metadata_stripped(self):
        img = Image.new("RGB", (20, 10), (0, 0, 255))
        img.putpixel((0, 0), (255, 255, 255))
        img.save(
            self.src / "p.jpg", exif=_exif(orientation=6, gps=True), xmp=b"<x:xmpmeta secret/>"
        )
        r, im = self.convert("p.jpg", "png")
        self.assertEqual(im.size, (10, 20))  # rotated upright
        self.assertTrue(r["had_gps_metadata"])
        self.assertTrue(r["metadata_stripped"])
        self.assertEqual(len(im.getexif()), 0)
        self.assertNotIn("exif", im.info)
        self.assertNotIn("xmp", im.info)
        self.assertNotIn(b"secret", r["output_file"].read_bytes())
        self.assertTrue(any(w.startswith("no_quality_gain") for w in r["warnings"]))

    def test_jpeg_to_jpeg_drops_xmp_and_exif(self):
        Image.new("RGB", (8, 8)).save(self.src / "j.jpg", exif=_exif(gps=True), xmp=b"<secretxmp/>")
        r, im = self.convert("j.jpg", "jpeg")
        data = r["output_file"].read_bytes()
        self.assertNotIn(b"secretxmp", data)
        self.assertNotIn(b"TestCam", data)
        self.assertEqual(len(im.getexif()), 0)

    def test_icc_profile_kept(self):
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        Image.new("RGB", (4, 4)).save(self.src / "c.png", icc_profile=icc)
        for target in ("jpeg", "png", "webp"):
            with self.subTest(target=target):
                r, im = self.convert("c.png", target, stem=target)
                self.assertTrue(r["icc_profile_kept"])
                self.assertEqual(im.info.get("icc_profile"), icc)

    def test_webp_lossless_is_pixel_exact(self):
        img = Image.effect_noise((32, 32), 64).convert("RGB")
        img.save(self.src / "n.png")
        r, im = self.convert("n.png", "webp", lossless=True)
        self.assertEqual(im.format, "WEBP")
        self.assertIsNone(ImageChops.difference(im.convert("RGB"), img).getbbox())

    def test_png_round_trip_is_pixel_exact_with_alpha(self):
        img = Image.new("RGBA", (5, 5), (1, 2, 3, 4))
        img.save(self.src / "t.webp", lossless=True)
        r, im = self.convert("t.webp", "png")
        self.assertEqual(im.mode, "RGBA")
        self.assertEqual(im.getpixel((2, 2)), (1, 2, 3, 4))

    def test_palette_transparency_to_webp_keeps_alpha(self):
        p = Image.new("P", (4, 4), 0)
        p.putpalette([255, 0, 0, 0, 255, 0] + [0] * 762)
        p.putpixel((1, 1), 1)
        p.save(self.src / "p.png", transparency=0)
        r, im = self.convert("p.png", "webp", lossless=True)
        self.assertEqual(im.convert("RGBA").getpixel((0, 0))[3], 0)
        self.assertEqual(im.convert("RGBA").getpixel((1, 1)), (0, 255, 0, 255))

    def test_quality_changes_size(self):
        Image.effect_noise((128, 128), 80).convert("RGB").save(self.src / "q.png")
        lo, _ = self.convert("q.png", "jpeg", stem="lo", quality=10)
        hi, _ = self.convert("q.png", "jpeg", stem="hi", quality=95)
        self.assertLess(lo["output_bytes"], hi["output_bytes"])
        self.assertEqual(lo["output_bytes"], (self.base / "out" / "lo.jpg").stat().st_size)

    def test_modes(self):
        Image.new("L", (4, 4), 100).save(self.src / "g.png")
        Image.new("CMYK", (4, 4), (0, 255, 0, 0)).save(self.src / "k.jpg")
        Image.new("I;16", (4, 4), 4000).save(self.src / "i.png")
        Image.new("1", (4, 4), 1).save(self.src / "b.png")
        cases = [
            ("g.png", "jpeg", "L"),
            ("k.jpg", "png", "RGB"),
            ("k.jpg", "webp", "RGB"),
            ("i.png", "jpeg", None),
            ("b.png", "webp", "RGB"),
        ]
        for i, (name, target, mode) in enumerate(cases):
            with self.subTest(name=name, target=target):
                r, im = self.convert(name, target, stem=f"m{i}")
                if mode:
                    self.assertEqual(r["mode"], mode)
                im.load()

    def test_animated_gif_first_frame_with_warning(self):
        frames = [Image.new("RGB", (6, 6), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
        frames[0].save(self.src / "a.gif", save_all=True, append_images=frames[1:])
        r, im = self.convert("a.gif", "png")
        self.assertTrue(any(w.startswith("frames_dropped") for w in r["warnings"]))
        self.assertEqual(getattr(im, "n_frames", 1), 1)

    def test_source_never_modified(self):
        Image.new("RGB", (8, 8), (9, 9, 9)).save(self.src / "s.jpg", exif=_exif(orientation=3))
        f = self.src / "s.jpg"
        before = (f.read_bytes(), f.stat().st_mtime_ns)
        self.convert("s.jpg", "jpeg")
        self.convert("s.jpg", "png")
        self.assertEqual((f.read_bytes(), f.stat().st_mtime_ns), before)

    def test_errors(self):
        Image.new("RGB", (4, 4)).save(self.src / "ok.png")
        buf = io.BytesIO()
        Image.new("RGB", (64, 64)).save(buf, "PNG")
        (self.src / "trunc.png").write_bytes(buf.getvalue()[:60])
        (self.src / "txt.png").write_text("hello")
        cases = [
            (("ok.png", "gif"), {}, "unsupported_target"),
            (("ok.png", "jpeg"), {"quality": 0}, "invalid_argument"),
            (("ok.png", "jpeg"), {"quality": 101}, "invalid_argument"),
            (("trunc.png", "jpeg"), {}, "decode_failed"),
            (("txt.png", "jpeg"), {}, "unsupported_format"),
            (("missing.png", "jpeg"), {}, "not_found"),
        ]
        for (name, target), kw, code in cases:
            with self.subTest(name=name, code=code):
                with self.assertRaises(EngineError) as cm:
                    self.convert(name, target, **kw)
                self.assertEqual(cm.exception.code, code)
        out = self.base / "out"
        self.assertEqual(list(out.iterdir()) if out.exists() else [], [])


if __name__ == "__main__":
    unittest.main()
