"""M6: the ``image_compress`` max_bytes search stops at the wall-clock budget (threat T6)."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from imagetoolbox_mcp.engine import DEFAULT_LIMITS, Limits, compress_image
from imagetoolbox_mcp.output import OutputDir

NO_TIME = Limits(max_search_seconds=0)


class CompressBudgetTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.png = base / "noise.png"
        self.jpg = base / "noise.jpg"
        noise = Image.effect_noise((160, 120), 80).convert("RGB")
        noise.save(self.png)
        noise.save(self.jpg, quality=95)
        self.out = OutputDir(base / "out")

    def tearDown(self):
        self._tmp.cleanup()

    def _budget_warning(self, res) -> bool:
        return any(w.startswith("time_budget_reached") for w in res["warnings"])

    def test_png_palette_search_stops_after_first_probe(self):
        res = compress_image(self.png, self.out, "p", max_bytes=1024, limits=NO_TIME)
        self.assertTrue(self._budget_warning(res))
        self.assertEqual(res["colors_used"], 256)  # only the first ladder step was tried
        self.assertFalse(res["target_met"])
        with Image.open(res["output_file"]) as im:
            self.assertEqual((im.format, im.size), ("PNG", (160, 120)))

    def test_jpeg_quality_search_stops_after_first_probe(self):
        res = compress_image(self.jpg, self.out, "j", max_bytes=1024, limits=NO_TIME)
        self.assertTrue(self._budget_warning(res))
        self.assertEqual(res["quality_used"], (10 + 95) // 2)
        self.assertTrue(res["output_file"].exists())

    def test_no_warning_within_budget(self):
        self.assertGreater(DEFAULT_LIMITS.max_search_seconds, 0)
        for src in (self.png, self.jpg):
            res = compress_image(src, self.out, None, max_bytes=8000)
            self.assertFalse(self._budget_warning(res), res["warnings"])

    def test_fixed_quality_ignores_budget(self):
        res = compress_image(self.jpg, self.out, "q", quality=50, limits=NO_TIME)
        self.assertFalse(self._budget_warning(res))
        self.assertEqual(res["quality_used"], 50)


if __name__ == "__main__":
    unittest.main()
