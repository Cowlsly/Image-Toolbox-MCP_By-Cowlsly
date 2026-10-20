"""M6: the input file is re-checked on the open descriptor (threat T2, swap after check).

``_check_regular_file`` runs ``lstat`` first; these tests pretend that check passed and the
file was then swapped for a symlink or a FIFO before the open.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from imagetoolbox_mcp import engine
from imagetoolbox_mcp.engine import EngineError, Limits, convert_image, inspect_image
from imagetoolbox_mcp.output import OutputDir


@unittest.skipIf(os.name == "nt", "POSIX symlink/FIFO semantics")
class SwapAfterCheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.secret = self.base / "secret.png"
        Image.new("RGB", (5, 5), "green").save(self.secret)
        self.out = OutputDir(self.base / "out")
        # Pretend the lstat check ran before the swap and saw a small regular file.
        self._patch = mock.patch.object(engine, "_check_regular_file", return_value=100)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _both(self, p):
        for call in (lambda: inspect_image(p), lambda: convert_image(p, "png", self.out, "x")):
            with self.assertRaises(EngineError) as cm:
                call()
            yield cm.exception.code

    def test_symlink_swapped_in_is_not_followed(self):
        link = self.base / "photo.png"
        link.symlink_to(self.secret)
        self.assertEqual(set(self._both(link)), {"symlink_rejected"})
        self.assertFalse(self.out.path.exists())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs mkfifo")
    def test_fifo_swapped_in_does_not_hang(self):
        fifo = self.base / "photo.png"
        os.mkfifo(fifo)
        self.assertEqual(set(self._both(fifo)), {"not_a_file"})

    def test_file_grown_past_limit_after_check(self):
        small = Limits(max_file_bytes=10)
        with self.assertRaises(EngineError) as cm:
            inspect_image(self.secret, small)
        self.assertEqual(cm.exception.code, "file_too_large")

    def test_regular_file_still_works(self):
        self.assertEqual(inspect_image(self.secret)["width"], 5)


if __name__ == "__main__":
    unittest.main()
