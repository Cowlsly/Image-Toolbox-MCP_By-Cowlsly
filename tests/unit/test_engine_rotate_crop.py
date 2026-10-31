"""Golden tests for ``engine.rotate_flip_image``, ``plan_crop`` and ``crop_image`` (M3)."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import ExifTags, Image, ImageCms

from imagetoolbox_mcp.engine import (
    EngineError,
    crop_image,
    parse_aspect,
    plan_crop,
    rotate_flip_image,
)
from imagetoolbox_mcp.output import OutputDir


def _grid(w=3, h=2, mode="RGB"):
    """Every pixel a different colour, so pixel moves can be checked exactly."""
    im = Image.new("RGB", (w, h))
    for y in range(h):
        for x in range(w):
            im.putpixel((x, y), (x * 40, y * 40, 100 + x + 10 * y))
    return im.convert(mode) if mode != "RGB" else im


def _pixels(im):
    return [[im.getpixel((x, y)) for x in range(im.size[0])] for y in range(im.size[1])]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)  # LIFO: close opened images before deleting files.
        self.base = Path(self._tmp.name).resolve()
        self.src = self.base / "src"
        self.src.mkdir()
        self.out = OutputDir(self.base / "out")

    def opened(self, result):
        im = Image.open(result["output_file"])
        self.addCleanup(im.close)
        return im

    def assert_nothing_written(self):
        out_dir = self.base / "out"
        self.assertTrue(not out_dir.exists() or not any(out_dir.iterdir()))


class RotateFlipTests(_Base):
    def rot(self, name, stem=None, **kw):
        r = rotate_flip_image(self.src / name, self.out, stem, **kw)
        return r, self.opened(r)

    def test_rotate_90_is_clockwise_and_pixel_exact(self):
        g = _grid()
        g.save(self.src / "g.png")
        r, im = self.rot("g.png", rotate=90)
        self.assertEqual(im.size, (2, 3))
        w, h = g.size
        for y in range(w):  # new height = old width
            for x in range(h):
                self.assertEqual(im.getpixel((x, y)), g.getpixel((y, h - 1 - x)), (x, y))
        # top-left of the source ends up top-right after a clockwise turn
        self.assertEqual(im.getpixel((1, 0)), g.getpixel((0, 0)))
        self.assertEqual(r["output_file"].name, "g-rot90.png")
        self.assertEqual((r["rotate"], r["flip"]), (90, None))
        self.assertEqual((r["source_width"], r["source_height"]), (3, 2))
        self.assertEqual(r["warnings"], [])

    def test_all_operations_match_reference_transposes(self):
        g = _grid(4, 3)
        g.save(self.src / "g.png")
        T = Image.Transpose
        cases = {
            (180, None): [T.ROTATE_180],
            (270, None): [T.ROTATE_90],  # 270 clockwise == 90 counter-clockwise
            (0, "horizontal"): [T.FLIP_LEFT_RIGHT],
            (0, "vertical"): [T.FLIP_TOP_BOTTOM],
            (90, "horizontal"): [T.ROTATE_270, T.FLIP_LEFT_RIGHT],  # rotate first, then flip
            (270, "vertical"): [T.ROTATE_90, T.FLIP_TOP_BOTTOM],
        }
        for (rotate, flip), ops in cases.items():
            ref = g
            for op in ops:
                ref = ref.transpose(op)
            _, im = self.rot("g.png", rotate=rotate, flip=flip)
            self.assertEqual(_pixels(im.convert("RGB")), _pixels(ref), (rotate, flip))

    def test_rotate_then_flip_differs_from_flip_then_rotate(self):
        g = _grid(4, 3)
        g.save(self.src / "g.png")
        _, im = self.rot("g.png", rotate=90, flip="horizontal")
        other = g.transpose(Image.Transpose.FLIP_LEFT_RIGHT).transpose(Image.Transpose.ROTATE_270)
        self.assertNotEqual(_pixels(im), _pixels(other))

    def test_default_names(self):
        _grid().save(self.src / "a.png")
        names = [
            rotate_flip_image(self.src / "a.png", self.out, None, **kw)["output_file"].name
            for kw in (
                dict(rotate=180),
                dict(flip="horizontal"),
                dict(flip="vertical"),
                dict(rotate=270, flip="vertical"),
                dict(rotate=180),
            )
        ]
        self.assertEqual(
            names,
            ["a-rot180.png", "a-flipH.png", "a-flipV.png", "a-rot270-flipV.png", "a-rot180-1.png"],
        )

    def test_directions_refer_to_upright_image(self):
        ex = Image.Exif()
        ex[ExifTags.Base.Orientation] = 6  # stored 40x20, displayed 20x40
        im = Image.new("RGB", (40, 20), (200, 0, 0))
        im.paste((0, 0, 200), (0, 0, 20, 20))  # stored left = displayed top = blue
        im.save(self.src / "o.jpg", exif=ex, quality=95)
        r, out = self.rot("o.jpg", rotate=90, target="png")
        # displayed: blue top, red bottom (20x40); turn clockwise -> blue on the right
        self.assertEqual(out.size, (40, 20))
        self.assertEqual((r["source_width"], r["source_height"]), (20, 40))
        self.assertGreater(out.getpixel((35, 10))[2], 150)
        self.assertGreater(out.getpixel((5, 10))[0], 150)
        self.assertNotIn(ExifTags.Base.Orientation, out.getexif())

    def test_jpeg_warns_lossy_png_and_lossless_webp_do_not(self):
        _grid(8, 6).save(self.src / "p.jpg", quality=95)
        r, _ = self.rot("p.jpg", rotate=90)
        self.assertTrue(r["warnings"][0].startswith("lossy_reencode"))
        r, _ = self.rot("p.jpg", rotate=90, target="png")
        self.assertEqual(r["warnings"], [])
        r, _ = self.rot("p.jpg", rotate=90, target="webp")
        self.assertTrue(r["warnings"][0].startswith("lossy_reencode"))
        r, _ = self.rot("p.jpg", rotate=90, target="webp", lossless=True)
        self.assertEqual(r["warnings"], [])

    def test_webp_lossless_is_pixel_exact(self):
        g = _grid(5, 4, "RGBA")
        g.putalpha(Image.linear_gradient("L").resize((5, 4)))  # real, varying alpha
        g.save(self.src / "w.png")
        _, im = self.rot("w.png", flip="vertical", target="webp", lossless=True)
        self.assertEqual(_pixels(im), _pixels(g.transpose(Image.Transpose.FLIP_TOP_BOTTOM)))

    def test_modes_preserved(self):
        pal = _grid(4, 3).convert("P")
        pal.info["transparency"] = 0
        pal.save(self.src / "pal.png", transparency=0)
        _, im = self.rot("pal.png", rotate=180)
        self.assertEqual(im.mode, "P")
        self.assertIn("transparency", im.info)
        ref = Image.open(self.src / "pal.png").transpose(Image.Transpose.ROTATE_180)
        self.assertEqual(_pixels(im.convert("RGBA")), _pixels(ref.convert("RGBA")))

        deep = Image.new("I;16", (3, 2))
        deep.putpixel((0, 0), 65000)
        deep.save(self.src / "deep.png")
        _, im = self.rot("deep.png", rotate=90)
        self.assertEqual(im.mode, "I;16")
        self.assertEqual(im.getpixel((1, 0)), 65000)

        Image.new("LA", (3, 2), (90, 30)).save(self.src / "la.png")
        _, im = self.rot("la.png", flip="horizontal")
        self.assertTrue(im.mode in ("LA", "RGBA"))
        self.assertEqual(im.getpixel((0, 0))[-1], 30)

    def test_gps_stripped_icc_kept_source_unchanged(self):
        ex = Image.Exif()
        ex[ExifTags.Base.Make] = "TestCam"
        ex[ExifTags.IFD.GPSInfo] = {ExifTags.GPS.GPSLatitudeRef: "N"}
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        Image.new("RGB", (8, 6)).save(self.src / "g.jpg", exif=ex, icc_profile=icc)
        before = _sha(self.src / "g.jpg")
        r, im = self.rot("g.jpg", rotate=270)
        self.assertTrue(r["had_gps_metadata"])
        self.assertTrue(r["icc_profile_kept"])
        self.assertEqual(im.info.get("icc_profile"), icc)
        self.assertEqual(dict(im.getexif()), {})
        self.assertNotIn(b"TestCam", r["output_file"].read_bytes())
        self.assertEqual(_sha(self.src / "g.jpg"), before)

    def test_invalid_arguments_write_nothing(self):
        _grid().save(self.src / "a.png")
        bad = [
            dict(),  # nothing to do
            dict(rotate=45),
            dict(rotate=-90),
            dict(rotate=360),
            dict(flip="diagonal"),
            dict(rotate=90, target="gif"),
            dict(rotate=90, quality=0),
        ]
        for kw in bad:
            with self.assertRaises(EngineError, msg=kw) as cm:
                rotate_flip_image(self.src / "a.png", self.out, None, **kw)
            self.assertIn(cm.exception.code, ("invalid_argument", "unsupported_target"), kw)
        with self.assertRaises(EngineError) as cm:
            rotate_flip_image(self.src / "a.png", self.out, "../x", rotate=90)
        self.assertEqual(cm.exception.code, "invalid_name")
        with self.assertRaises(EngineError) as cm:
            rotate_flip_image(self.src / "missing.png", self.out, None, rotate=90)
        self.assertEqual(cm.exception.code, "not_found")
        self.assert_nothing_written()

    def test_unsupported_source_format_saved_as_png(self):
        _grid().save(self.src / "a.bmp")
        r, im = self.rot("a.bmp", rotate=90)
        self.assertEqual(im.format, "PNG")
        self.assertTrue(r["warnings"][0].startswith("format_changed"))


class PlanCropTests(unittest.TestCase):
    def test_explicit_box(self):
        self.assertEqual(
            plan_crop((100, 80), left=10, top=5, width=30, height=20)[0], (10, 5, 40, 25)
        )

    def test_left_top_default_to_zero(self):
        self.assertEqual(plan_crop((100, 80), width=30, height=20)[0], (0, 0, 30, 20))

    def test_box_touching_edges_ok_and_full_image_warns(self):
        self.assertEqual(
            plan_crop((100, 80), left=70, top=60, width=30, height=20)[0], (70, 60, 100, 80)
        )
        box, warns = plan_crop((100, 80), width=100, height=80)
        self.assertEqual(box, (0, 0, 100, 80))
        self.assertTrue(warns[0].startswith("crop_full_image"))

    def test_out_of_bounds_refused_with_size_in_message(self):
        for kw in (
            dict(left=71, top=0, width=30, height=20),
            dict(left=0, top=61, width=30, height=20),
            dict(width=101, height=1),
            dict(width=1, height=81),
        ):
            with self.assertRaises(EngineError, msg=kw) as cm:
                plan_crop((100, 80), **kw)
            self.assertEqual(cm.exception.code, "crop_out_of_bounds")
            self.assertIn("100x80", cm.exception.message)

    def test_aspect_wide_and_tall_sources(self):
        self.assertEqual(plan_crop((400, 300), aspect="1:1")[0], (50, 0, 350, 300))
        self.assertEqual(plan_crop((300, 400), aspect="1:1")[0], (0, 50, 300, 350))
        self.assertEqual(plan_crop((400, 300), aspect="16:9")[0], (0, 37, 400, 262))
        self.assertEqual(plan_crop((1920, 1080), aspect="16:9")[1][0][:15], "crop_full_image")

    def test_aspect_sweep_stays_inside_and_close_to_ratio(self):
        for sw in (1, 2, 7, 33, 100, 641):
            for sh in (1, 3, 50, 479):
                for aw, ah in ((1, 1), (4, 3), (3, 4), (16, 9), (9, 16), (21, 1), (1, 21)):
                    (x0, y0, x1, y1), _ = plan_crop((sw, sh), aspect=f"{aw}:{ah}")
                    w, h = x1 - x0, y1 - y0
                    self.assertTrue(0 <= x0 and 0 <= y0 and x1 <= sw and y1 <= sh)
                    self.assertTrue(w >= 1 and h >= 1)
                    # one side is full, the other the rounded ideal length (at least 1 px)
                    self.assertTrue(w == sw or h == sh, (sw, sh, aw, ah, w, h))
                    if h == sh and w < sw:
                        self.assertLessEqual(abs(w - max(1, sh * aw / ah)), 0.5 + 1e-9)
                    if w == sw and h < sh:
                        self.assertLessEqual(abs(h - max(1, sw * ah / aw)), 0.5 + 1e-9)

    def test_invalid_arguments(self):
        bad = [
            dict(),
            dict(width=10),
            dict(height=10),
            dict(width=0, height=10),
            dict(width=10, height=10, left=-1),
            dict(aspect="1:1", width=10, height=10),
            dict(aspect="1:1", left=0),
        ]
        for kw in bad:
            with self.assertRaises(EngineError, msg=kw) as cm:
                plan_crop((100, 80), **kw)
            self.assertEqual(cm.exception.code, "invalid_argument", kw)

    def test_parse_aspect(self):
        self.assertEqual(parse_aspect("16:9"), (16, 9))
        self.assertEqual(parse_aspect(" 1:1 "), (1, 1))
        for bad in ("", "1", "1:1:1", "a:b", "0:1", "1:0", "-1:2", "1.5:1", "1/1", "10001:1"):
            with self.assertRaises(EngineError, msg=bad):
                parse_aspect(bad)


class CropImageTests(_Base):
    def crop(self, name, stem=None, **kw):
        r = crop_image(self.src / name, self.out, stem, **kw)
        return r, self.opened(r)

    def test_png_crop_is_pixel_exact(self):
        g = _grid(10, 8)
        g.save(self.src / "g.png")
        r, im = self.crop("g.png", left=2, top=3, width=5, height=4)
        self.assertEqual(im.size, (5, 4))
        self.assertEqual(_pixels(im), _pixels(g.crop((2, 3, 7, 7))))
        self.assertEqual(r["output_file"].name, "g-crop-5x4.png")
        self.assertEqual((r["crop_left"], r["crop_top"]), (2, 3))
        self.assertEqual((r["source_width"], r["source_height"]), (10, 8))
        self.assertEqual(r["warnings"], [])

    def test_single_pixel_and_aspect_crop(self):
        g = _grid(10, 8)
        g.save(self.src / "g.png")
        _, im = self.crop("g.png", left=9, top=7, width=1, height=1)
        self.assertEqual(im.getpixel((0, 0)), g.getpixel((9, 7)))
        r, im = self.crop("g.png", aspect="1:1")
        self.assertEqual(im.size, (8, 8))
        self.assertEqual((r["crop_left"], r["crop_top"]), (1, 0))
        self.assertEqual(_pixels(im), _pixels(g.crop((1, 0, 9, 8))))

    def test_coordinates_refer_to_upright_image(self):
        ex = Image.Exif()
        ex[ExifTags.Base.Orientation] = 6  # stored 40x20, displayed 20x40
        im = Image.new("RGB", (40, 20), (200, 0, 0))
        im.paste((0, 0, 200), (0, 0, 20, 20))  # displayed top half blue
        im.save(self.src / "o.jpg", exif=ex, quality=95)
        r, out = self.crop("o.jpg", left=0, top=0, width=20, height=15)
        self.assertEqual(out.size, (20, 15))
        self.assertGreater(out.getpixel((10, 7))[2], 150)
        with self.assertRaises(EngineError) as cm:
            crop_image(self.src / "o.jpg", self.out, None, width=40, height=20)
        self.assertEqual(cm.exception.code, "crop_out_of_bounds")
        self.assertIn("20x40", cm.exception.message)

    def test_palette_transparency_kept(self):
        pal = _grid(6, 4).convert("P")
        pal.save(self.src / "pal.png", transparency=0)
        _, im = self.crop("pal.png", width=3, height=2)
        self.assertEqual(im.mode, "P")
        self.assertIn("transparency", im.info)

    def test_jpeg_warns_lossy_and_gps_stripped(self):
        ex = Image.Exif()
        ex[ExifTags.IFD.GPSInfo] = {ExifTags.GPS.GPSLatitudeRef: "N"}
        Image.new("RGB", (40, 30), (0, 100, 0)).save(self.src / "g.jpg", exif=ex)
        before = _sha(self.src / "g.jpg")
        r, im = self.crop("g.jpg", aspect="4:3")
        self.assertTrue(r["had_gps_metadata"])
        self.assertEqual(dict(im.getexif()), {})
        self.assertEqual(
            [w.split(":")[0] for w in r["warnings"]], ["crop_full_image", "lossy_reencode"]
        )
        self.assertEqual(_sha(self.src / "g.jpg"), before)

    def test_format_and_name(self):
        _grid(10, 8).save(self.src / "g.png")
        r, im = self.crop("g.png", "thumb", width=4, height=4, target="jpeg", quality=70)
        self.assertEqual((r["output_file"].name, im.format), ("thumb.jpg", "JPEG"))

    def test_errors_write_nothing(self):
        _grid(10, 8).save(self.src / "g.png")
        Image.new("RGB", (10, 8)).save(self.base / "outside.png")
        (self.src / "link.png").symlink_to(self.base / "outside.png")
        cases = [
            (dict(width=11, height=8), "crop_out_of_bounds"),
            (dict(aspect="x"), "invalid_argument"),
            (dict(), "invalid_argument"),
            (dict(width=4, height=4, quality=101), "invalid_argument"),
        ]
        for kw, code in cases:
            with self.assertRaises(EngineError, msg=kw) as cm:
                crop_image(self.src / "g.png", self.out, None, **kw)
            self.assertEqual(cm.exception.code, code, kw)
        with self.assertRaises(EngineError) as cm:
            crop_image(self.src / "link.png", self.out, None, width=2, height=2)
        self.assertEqual(cm.exception.code, "symlink_rejected")
        self.assert_nothing_written()


if __name__ == "__main__":
    unittest.main()
