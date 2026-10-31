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


class RegularFilePortabilityTests(unittest.TestCase):
    def test_read_does_not_require_pipe_blocking_api(self):
        """Windows exposes set_blocking, but only accepts pipe descriptors."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "photo.png"
            Image.new("RGB", (5, 3), "green").save(source)
            before = source.read_bytes()
            with mock.patch.object(
                engine.os, "set_blocking", side_effect=OSError("regular files unsupported")
            ) as blocking:
                result = inspect_image(source)
            self.assertEqual((result["width"], result["height"]), (5, 3))
            blocking.assert_not_called()
            self.assertEqual(source.read_bytes(), before)


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


@unittest.skipUnless(engine.CONFINED_OPEN_SUPPORTED, "needs openat (POSIX dir_fd)")
class ConfinedOpenTests(unittest.TestCase):
    """R1: a folder inside the root swapped for a symlink after the sandbox check."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.root = self.base / "root"
        (self.root / "album").mkdir(parents=True)
        Image.new("RGB", (3, 3)).save(self.root / "album" / "ok.png")
        self.outside = self.base / "outside"
        self.outside.mkdir()
        Image.new("RGB", (9, 9)).save(self.outside / "ok.png")
        self.limits = Limits(confine_to=str(self.root))

    def tearDown(self):
        self._tmp.cleanup()

    def test_normal_file_opens(self):
        self.assertEqual(inspect_image(self.root / "album" / "ok.png", self.limits)["width"], 3)

    def test_swapped_folder_is_not_followed(self):
        os.rename(self.root / "album", self.base / "album-moved")
        os.symlink(self.outside, self.root / "album")
        with mock.patch.object(engine, "_check_regular_file", return_value=100):
            with self.assertRaises(EngineError) as cm:
                inspect_image(self.root / "album" / "ok.png", self.limits)
        self.assertEqual(cm.exception.code, "symlink_rejected")

    def test_path_outside_root_refused(self):
        with self.assertRaises(EngineError) as cm:
            inspect_image(self.outside / "ok.png", self.limits)
        self.assertEqual(cm.exception.code, "outside_root")

    def test_server_passes_confined_limits(self):
        import anyio
        from mcp import Client

        from imagetoolbox_mcp.sandbox import InputRoot
        from imagetoolbox_mcp.server import build_server

        seen = {}

        def spy(path, limits):
            seen["confine_to"] = limits.confine_to
            return inspect_image(path, limits)

        async def go():
            with mock.patch("imagetoolbox_mcp.server.inspect_image", side_effect=spy):
                server = build_server(InputRoot(self.root))
            async with Client(server, raise_exceptions=False) as c:
                r = await c.call_tool("image_inspect", {"path": "album/ok.png"})
                self.assertFalse(r.is_error)

        anyio.run(go)
        self.assertEqual(seen["confine_to"], str(self.root))
