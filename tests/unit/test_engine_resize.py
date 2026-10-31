"""Golden tests for ``engine.resize_image`` / ``plan_resize`` (M3)."""

import tempfile
import unittest
from pathlib import Path

from PIL import ExifTags, Image, ImageCms

from imagetoolbox_mcp.engine import EngineError, Limits, plan_resize, resize_image
from imagetoolbox_mcp.output import OutputDir


class PlanResizeTests(unittest.TestCase):
    def test_contain_width_only_keeps_aspect(self):
        self.assertEqual(plan_resize((400, 300), 200, None)[:2], ((200, 150), (200, 150)))

    def test_contain_height_only(self):
        self.assertEqual(plan_resize((400, 300), None, 100)[1], (133, 100))

    def test_contain_box_uses_tighter_side(self):
        self.assertEqual(plan_resize((400, 300), 100, 100)[1], (100, 75))
        self.assertEqual(plan_resize((300, 400), 100, 100)[1], (75, 100))

    def test_contain_never_overshoots_box(self):
        for sw in range(1, 60):
            for sh in (1, 7, 33, 59):
                (w, h), _, _ = plan_resize((sw, sh), 17, 13, allow_upscale=True)
                self.assertLessEqual(w, 17, (sw, sh))
                self.assertLessEqual(h, 13, (sw, sh))
                self.assertTrue(w == 17 or h == 13, (sw, sh, w, h))

    def test_contain_tiny_side_is_at_least_one(self):
        self.assertEqual(plan_resize((10000, 10), 100, None)[1], (100, 1))

    def test_contain_no_upscale_keeps_size_with_warning(self):
        _, final, warns = plan_resize((50, 40), 500, None)
        self.assertEqual(final, (50, 40))
        self.assertTrue(warns[0].startswith("upscale_skipped"))

    def test_contain_upscale_when_allowed(self):
        self.assertEqual(plan_resize((50, 40), 100, None, allow_upscale=True)[1], (100, 80))

    def test_cover_scales_then_crops(self):
        scaled, final, _ = plan_resize((400, 300), 100, 100, "cover")
        self.assertEqual((scaled, final), ((133, 100), (100, 100)))

    def test_exact_warns_on_aspect_change(self):
        _, final, warns = plan_resize((400, 300), 100, 100, "exact")
        self.assertEqual(final, (100, 100))
        self.assertTrue(warns[0].startswith("aspect_changed"))
        self.assertEqual(plan_resize((400, 300), 200, 150, "exact")[2], [])

    def test_cover_and_exact_refuse_upscale(self):
        for fit in ("cover", "exact"):
            with self.assertRaises(EngineError) as cm:
                plan_resize((50, 40), 60, 30, fit)
            self.assertEqual(cm.exception.code, "upscale_refused")

    def test_invalid_arguments(self):
        bad = [
            dict(width=None, height=None),
            dict(width=0, height=None),
            dict(width=16385, height=None),
            dict(width=10, height=None, fit="cover"),
            dict(width=10, height=None, fit="exact"),
            dict(width=10, height=10, fit="stretch"),
        ]
        for kw in bad:
            with self.assertRaises(EngineError, msg=kw) as cm:
                plan_resize((100, 100), kw["width"], kw["height"], kw.get("fit", "contain"))
            self.assertEqual(cm.exception.code, "invalid_argument")


class ResizeImageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)  # LIFO: close opened images before deleting files.
        self.base = Path(self._tmp.name).resolve()
        self.src = self.base / "src"
        self.src.mkdir()
        self.out = OutputDir(self.base / "out")

    def resize(self, name, stem=None, **kw):
        r = resize_image(self.src / name, self.out, stem, **kw)
        im = Image.open(r["output_file"])
        self.addCleanup(im.close)
        return r, im

    def test_default_name_format_and_size(self):
        Image.new("RGB", (400, 300), (10, 200, 30)).save(self.src / "photo.jpg", quality=95)
        r, im = self.resize("photo.jpg", width=200)
        self.assertEqual(r["output_file"].name, "photo-200x150.jpg")
        self.assertEqual((im.format, im.size), ("JPEG", (200, 150)))
        self.assertEqual((r["source_width"], r["source_height"]), (400, 300))
        self.assertEqual(r["warnings"], [])
        px = im.getpixel((100, 75))
        self.assertTrue(all(abs(a - b) <= 6 for a, b in zip(px, (10, 200, 30), strict=True)), px)

    def test_second_run_never_overwrites(self):
        Image.new("RGB", (40, 30)).save(self.src / "a.png")
        r1, _ = self.resize("a.png", width=20)
        r2, _ = self.resize("a.png", width=20)
        self.assertEqual(
            (r1["output_file"].name, r2["output_file"].name), ("a-20x15.png", "a-20x15-1.png")
        )

    def test_cover_crops_centre(self):
        # Left third red, middle green, right third blue; cover to a square keeps the middle.
        im = Image.new("RGB", (300, 100), (255, 0, 0))
        im.paste((0, 255, 0), (100, 0, 200, 100))
        im.paste((0, 0, 255), (200, 0, 300, 100))
        im.save(self.src / "bands.png")
        r, out = self.resize("bands.png", width=50, height=50, fit="cover")
        self.assertEqual(out.size, (50, 50))
        self.assertEqual(out.getpixel((25, 25)), (0, 255, 0))
        for xy in ((0, 0), (49, 49), (0, 49), (49, 0)):  # edges: only filter ringing
            r, g, b = out.getpixel(xy)
            self.assertTrue(g > 240 and r < 16 and b < 16, (xy, r, g, b))

    def test_exif_orientation_applied_before_sizing(self):
        ex = Image.Exif()
        ex[ExifTags.Base.Orientation] = 6  # rotate 90 CW: stored 400x200 shows as 200x400
        im = Image.new("RGB", (400, 200), (200, 0, 0))
        im.paste((0, 0, 200), (0, 0, 200, 200))  # stored left half blue -> displayed top
        im.save(self.src / "rot.jpg", exif=ex, quality=95)
        r, out = self.resize("rot.jpg", width=100)
        self.assertEqual(out.size, (100, 200))
        self.assertEqual((r["source_width"], r["source_height"]), (200, 400))
        self.assertGreater(out.getpixel((50, 20))[2], 150)  # top is blue
        self.assertGreater(out.getpixel((50, 180))[0], 150)  # bottom is red
        self.assertNotIn(ExifTags.Base.Orientation, out.getexif())

    def test_gps_and_exif_stripped_icc_kept(self):
        ex = Image.Exif()
        ex[ExifTags.Base.Make] = "TestCam"
        ex[ExifTags.IFD.GPSInfo] = {ExifTags.GPS.GPSLatitudeRef: "N"}
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        Image.new("RGB", (80, 60)).save(self.src / "g.jpg", exif=ex, icc_profile=icc)
        r, out = self.resize("g.jpg", width=40)
        self.assertTrue(r["had_gps_metadata"])
        self.assertTrue(r["icc_profile_kept"])
        self.assertEqual(len(out.getexif()), 0)
        self.assertEqual(out.info.get("icc_profile"), icc)
        self.assertNotIn(b"TestCam", r["output_file"].read_bytes())

    def test_alpha_preserved_without_dark_fringes(self):
        # Opaque white square on a fully transparent *black* background: premultiplied
        # resampling must not drag black into the edge pixels' colour.
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        im.paste((255, 255, 255, 255), (16, 16, 48, 48))
        im.save(self.src / "a.png")
        _, out = self.resize("a.png", width=21)
        self.assertEqual(out.mode, "RGBA")
        for x in range(out.width):
            for y in range(out.height):
                r, g, b, a = out.getpixel((x, y))
                if a > 32:
                    self.assertGreater(min(r, g, b), 200, (x, y, r, g, b, a))

    def test_palette_png_lanczos_and_nearest(self):
        Image.new("RGB", (40, 40), (255, 0, 0)).convert("P").save(self.src / "p.png")
        r, out = self.resize("p.png", width=10)
        self.assertEqual(out.size, (10, 10))
        self.assertEqual(out.convert("RGB").getpixel((5, 5)), (255, 0, 0))
        r, out = self.resize("p.png", width=20, resample="nearest")
        self.assertEqual(out.mode, "P")

    def test_nearest_keeps_hard_edges(self):
        im = Image.new("L", (2, 1))
        im.putpixel((1, 0), 255)
        im.save(self.src / "px.png")
        _, out = self.resize("px.png", width=8, resample="nearest", allow_upscale=True)
        self.assertEqual(out.size, (8, 4))
        self.assertEqual(list(out.crop((0, 0, 8, 1)).getdata()), [0] * 4 + [255] * 4)

    def test_16bit_png_stays_16bit(self):
        Image.new("I;16", (20, 20), 40000).save(self.src / "d.png")
        _, out = self.resize("d.png", width=10)
        self.assertIn(out.mode, ("I;16", "I"))
        self.assertEqual(out.getpixel((5, 5)), 40000)

    def test_unsupported_source_format_falls_back_to_png(self):
        Image.new("RGB", (30, 20), (1, 2, 3)).save(self.src / "b.bmp")
        r, out = self.resize("b.bmp", width=15)
        self.assertEqual((out.format, r["output_file"].suffix), ("PNG", ".png"))
        self.assertTrue(any(w.startswith("format_changed") for w in r["warnings"]))

    def test_explicit_format_and_name(self):
        Image.new("RGBA", (30, 20), (0, 0, 255, 100)).save(self.src / "c.png")
        r, out = self.resize("c.png", "thumb", width=15, target="webp", quality=80)
        self.assertEqual(
            (r["output_file"].name, out.format, out.size), ("thumb.webp", "WEBP", (15, 10))
        )

    def test_animated_first_frame_warning(self):
        frames = [Image.new("RGB", (20, 20), c) for c in ((255, 0, 0), (0, 255, 0))]
        frames[0].save(self.src / "anim.gif", save_all=True, append_images=frames[1:])
        r, out = self.resize("anim.gif", width=10)
        self.assertTrue(any(w.startswith("frames_dropped") for w in r["warnings"]))
        self.assertEqual(out.format, "PNG")

    def test_source_unchanged(self):
        Image.new("RGB", (50, 50), (9, 9, 9)).save(self.src / "s.png")
        before = (self.src / "s.png").read_bytes()
        self.resize("s.png", width=10)
        self.assertEqual((self.src / "s.png").read_bytes(), before)

    def test_errors_write_nothing(self):
        Image.new("RGB", (50, 40)).save(self.src / "e.png")
        (self.src / "junk.png").write_bytes(b"not an image")
        cases = [
            (dict(name="e.png", width=60, height=60, fit="cover"), "upscale_refused"),
            (dict(name="e.png"), "invalid_argument"),
            (dict(name="e.png", width=10, resample="cubic"), "invalid_argument"),
            (dict(name="e.png", width=10, quality=0), "invalid_argument"),
            (dict(name="e.png", width=10, target="gif"), "unsupported_target"),
            (dict(name="e.png", width=10, stem="../x"), "invalid_name"),
            (dict(name="junk.png", width=10), "unsupported_format"),
            (dict(name="missing.png", width=10), "not_found"),
        ]
        for kw, code in cases:
            name = kw.pop("name")
            stem = kw.pop("stem", None)
            with self.assertRaises(EngineError, msg=(name, kw)) as cm:
                resize_image(self.src / name, self.out, stem, **kw)
            self.assertEqual(cm.exception.code, code, (name, kw))
        self.assertFalse((self.base / "out").exists() and any((self.base / "out").iterdir()))

    def test_output_pixel_limit(self):
        Image.new("RGB", (100, 100)).save(self.src / "big.png")
        with self.assertRaises(EngineError) as cm:
            resize_image(
                self.src / "big.png",
                self.out,
                None,
                width=200,
                height=200,
                fit="exact",
                allow_upscale=True,
                limits=Limits(max_pixels=20_000),
            )
        self.assertEqual(cm.exception.code, "too_many_pixels")


if __name__ == "__main__":
    unittest.main()
