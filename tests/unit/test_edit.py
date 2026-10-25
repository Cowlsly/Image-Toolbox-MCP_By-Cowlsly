"""Unit tests for ``edit`` (M10): adjust, watermark, recipe and controlled tags."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import ExifTags, Image

from imagetoolbox_mcp.edit import (
    MAX_RECIPE_STEPS,
    adjust_image,
    apply_adjust,
    apply_watermark,
    check_recipe,
    recipe_image,
    tag_image,
    watermark_image,
)
from imagetoolbox_mcp.engine import EngineError
from imagetoolbox_mcp.output import OutputDir


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.out = OutputDir(self.base / "out")
        self.jpg = self.base / "photo.jpg"
        im = Image.new("RGB", (200, 100), (100, 120, 140))
        exif = im.getexif()
        exif[0x0112] = 6  # display rotated 90 CW -> upright 100x200
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        gps[1] = "N"
        exif[ExifTags.IFD.GPSInfo] = gps
        exif[0x0110] = "SecretCam"  # camera model, must not survive
        im.save(self.jpg, "JPEG", quality=95, exif=exif)
        self.png = self.base / "logo.png"
        Image.new("RGBA", (120, 80), (255, 0, 0, 100)).save(self.png)
        self.before = {p: _sha(p) for p in (self.jpg, self.png)}

    def tearDown(self):
        for p, h in self.before.items():
            self.assertEqual(_sha(p), h, f"{p.name} was modified")
        self._tmp.cleanup()


class AdjustTests(_Base):
    def test_brightness_changes_pixels_and_keeps_orientation(self):
        r = adjust_image(self.jpg, self.out, None, brightness=1.5)
        self.assertEqual((r["width"], r["height"]), (100, 200))
        self.assertEqual(r["output_file"].name, "photo-adjusted.jpg")
        with Image.open(r["output_file"]) as im:
            px = im.convert("RGB").getpixel((50, 100))
            self.assertGreater(px[0], 130)
            exif = im.getexif()
            self.assertNotIn(ExifTags.IFD.GPSInfo, exif)
            self.assertNotIn(0x0110, exif)

    def test_grayscale_and_alpha_kept(self):
        r = adjust_image(self.png, self.out, None, grayscale=True)
        with Image.open(r["output_file"]) as im:
            self.assertEqual(im.mode, "RGBA")
            red, green, blue, alpha = im.getpixel((5, 5))
            self.assertEqual(red, green)
            self.assertEqual(green, blue)
            self.assertEqual(alpha, 100)

    def test_nothing_to_do_and_range(self):
        with self.assertRaises(EngineError) as cm:
            adjust_image(self.jpg, self.out, None)
        self.assertEqual(cm.exception.code, "invalid_argument")
        with self.assertRaises(EngineError):
            adjust_image(self.jpg, self.out, None, contrast=1.0)
        with self.assertRaises(EngineError):
            adjust_image(self.jpg, self.out, None, contrast=5)
        with self.assertRaises(EngineError):
            adjust_image(self.jpg, self.out, None, saturation=float("nan"))
        self.assertFalse((self.base / "out").exists() and any((self.base / "out").iterdir()))

    def test_apply_adjust_identity_is_pixel_exact(self):
        im = Image.new("RGB", (3, 3), (10, 20, 30))
        self.assertEqual(apply_adjust(im).tobytes(), im.tobytes())


class WatermarkTests(_Base):
    def test_text_is_drawn_in_the_requested_corner(self):
        r = watermark_image(
            self.jpg,
            self.out,
            None,
            text="(c) Cowlsly",
            position="top-left",
            opacity=1.0,
            size_percent=20,
            color="#ffffff",
        )
        self.assertEqual(r["output_file"].name, "photo-wm.jpg")
        with Image.open(r["output_file"]) as im:
            im = im.convert("RGB")
            w, h = im.size
            corner = im.crop((0, 0, w // 2, h // 4))
            other = im.crop((w // 2, h * 3 // 4, w, h))
            self.assertGreater(corner.getextrema()[0][1], 220)
            self.assertLess(other.getextrema()[0][1], 140)

    def test_alpha_survives_and_original_area_unchanged(self):
        im = Image.open(self.png).convert("RGBA")
        out = apply_watermark(im, text="x", position="bottom-right", size_percent=10)
        self.assertEqual(out.mode, "RGBA")
        self.assertEqual(out.getpixel((0, 0)), im.getpixel((0, 0)))

    def test_bad_arguments(self):
        for kw in (
            {"text": ""},
            {"text": "a\nb"},
            {"text": "x" * 121},
            {"text": "x", "position": "middle"},
            {"text": "x", "opacity": 0},
            {"text": "x", "color": "notacolour"},
            {"text": "x", "size_percent": 80},
        ):
            with self.subTest(kw=kw), self.assertRaises(EngineError) as cm:
                watermark_image(self.jpg, self.out, None, **kw)
            self.assertEqual(cm.exception.code, "invalid_argument")


class RecipeTests(_Base):
    def test_steps_apply_in_order_with_one_encode(self):
        steps = [
            {"op": "resize", "width": 50},
            {"op": "rotate_flip", "rotate": 90},
            {"op": "crop", "aspect": "1:1"},
            {"op": "adjust", "contrast": 1.1},
            {"op": "watermark", "text": " hi "},
        ]
        r = recipe_image(self.jpg, self.out, None, steps=steps)
        # upright 100x200 -> 50x100 -> rotated 100x50 -> square 50x50
        self.assertEqual((r["width"], r["height"]), (50, 50))
        self.assertEqual((r["source_width"], r["source_height"]), (100, 200))
        self.assertEqual(r["steps"][-1]["text"], "hi")
        self.assertEqual(r["output_file"].name, "photo-recipe.jpg")
        # The normalised steps re-run to an identical result.
        r2 = recipe_image(self.jpg, self.out, None, steps=r["steps"])
        self.assertEqual(_sha(r["output_file"]), _sha(r2["output_file"]))

    def test_validation_before_opening(self):
        bad = [
            [],
            [{"op": "explode"}],
            [{"op": "crop", "foo": 1}],
            [{"op": "resize"}],
            [{"op": "rotate_flip"}],
            [{"op": "watermark"}],
            [{"op": "adjust", "brightness": 9}],
            [{"op": "adjust", "contrast": 1.2}] * (MAX_RECIPE_STEPS + 1),
            "resize",
        ]
        for steps in bad:
            with self.subTest(steps=steps), self.assertRaises(EngineError) as cm:
                check_recipe(steps)
            self.assertEqual(cm.exception.code, "invalid_argument")

    def test_out_of_bounds_crop_names_the_step(self):
        with self.assertRaises(EngineError) as cm:
            recipe_image(
                self.jpg,
                self.out,
                None,
                steps=[{"op": "resize", "width": 10}, {"op": "crop", "width": 50, "height": 50}],
            )
        self.assertEqual(cm.exception.code, "crop_out_of_bounds")
        self.assertIn("Step 2", cm.exception.message)


class TagTests(_Base):
    def test_jpeg_gets_only_the_given_tags(self):
        r = tag_image(self.jpg, self.out, None, artist="Cowlsly", copyright="2026 Cowlsly")
        self.assertEqual(r["tags_written"], ["artist", "copyright"])
        with Image.open(r["output_file"]) as im:
            exif = im.getexif()
            self.assertEqual(exif[0x013B], "Cowlsly")
            self.assertEqual(exif[0x8298], "2026 Cowlsly")
            self.assertNotIn(ExifTags.IFD.GPSInfo, exif)
            self.assertNotIn(0x0110, exif)
            self.assertNotIn(0x0112, exif)  # orientation already applied to pixels
            self.assertEqual(im.size, (100, 200))

    def test_png_text_chunks(self):
        r = tag_image(self.png, self.out, None, description="Red square")
        with Image.open(r["output_file"]) as im:
            self.assertEqual(im.info.get("Description"), "Red square")

    def test_refusals(self):
        with self.assertRaises(EngineError):
            tag_image(self.jpg, self.out, None)
        with self.assertRaises(EngineError):
            tag_image(self.jpg, self.out, None, artist="   ")
        with self.assertRaises(EngineError):
            tag_image(self.jpg, self.out, None, artist="x" * 300)


if __name__ == "__main__":
    unittest.main()
