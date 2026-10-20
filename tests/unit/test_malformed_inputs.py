"""M6 negative tests: hostile and broken image files (threat model T3-T5, docs/threat-model.md).

* Deterministic mutation fuzzing of every accepted format: truncation, byte flips and
  length-field corruption. The engine may only ever raise ``EngineError`` with a known
  code; it must never crash with another exception, echo a host path, or leave a file
  behind in the output folder for a failed call.
* Decoder allowlist: formats outside JPEG/PNG/WebP/GIF/TIFF/BMP are refused before
  their parser runs; EPS in particular must never start Ghostscript.
* Decompression bombs declared in the header are refused without decoding.
"""

import io
import random
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from PIL import Image

from imagetoolbox_mcp import engine
from imagetoolbox_mcp.engine import (
    ALLOWED_INPUT_FORMATS,
    EngineError,
    convert_image,
    inspect_image,
    resize_image,
)
from imagetoolbox_mcp.output import OutputDir

FAILURE_CODES = {"unsupported_format", "decode_failed", "too_many_pixels", "out_of_memory"}
MUTANTS_PER_FORMAT = 40


def _seed_image() -> Image.Image:
    im = Image.new("RGBA", (29, 17))
    im.putdata(
        [((x * 9) % 256, (y * 15) % 256, (x * y) % 256, 180) for y in range(17) for x in range(29)]
    )
    return im


def _seeds() -> dict[str, bytes]:
    base = _seed_image()
    out = {}
    for name, im, kw in [
        ("jpeg", base.convert("RGB"), {"format": "JPEG"}),
        ("png", base, {"format": "PNG"}),
        ("webp", base, {"format": "WEBP"}),
        (
            "gif",
            base.convert("RGB").convert("P"),
            {"format": "GIF", "save_all": True, "append_images": [base.convert("L").convert("P")]},
        ),
        ("tiff", base, {"format": "TIFF", "compression": "tiff_lzw"}),
        ("bmp", base.convert("RGB"), {"format": "BMP"}),
    ]:
        buf = io.BytesIO()
        im.save(buf, **kw)
        out[name] = buf.getvalue()
    return out


def _mutate(data: bytes, rnd: random.Random) -> bytes:
    m = bytearray(data)
    kind = rnd.randrange(4)
    if kind == 0:  # truncate
        return bytes(m[: rnd.randrange(1, len(m))])
    if kind == 1:  # flip a few bytes
        for _ in range(rnd.randint(1, 8)):
            m[rnd.randrange(len(m))] = rnd.randrange(256)
    elif kind == 2:  # corrupt something that may be a length/size field
        j = rnd.randrange(len(m))
        m[j : j + 4] = rnd.choice(
            [b"\xff\xff\xff\xff", b"\x7f\xff\xff\xff", b"\0\0\0\0", b"\x80\0\0\0"]
        )
    else:  # delete a slice
        j = rnd.randrange(len(m))
        del m[j : j + rnd.randint(1, 64)]
    return bytes(m)


def _png_header_only(width: int, height: int) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\0" * 64))
        + chunk(b"IEND", b"")
    )


class _Dirs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="private-home-")
        self.base = Path(self._tmp.name).resolve()
        self.src = self.base / "src"
        self.src.mkdir()
        self.out_path = self.base / "out"
        self.out = OutputDir(self.out_path)

    def tearDown(self):
        self._tmp.cleanup()

    def out_files(self) -> list[str]:
        return sorted(p.name for p in self.out_path.iterdir()) if self.out_path.exists() else []


class FuzzTests(_Dirs):
    def test_mutated_files_only_raise_engine_errors(self):
        rnd = random.Random(20261020)
        ok_outputs = 0
        for fmt, data in _seeds().items():
            for i in range(MUTANTS_PER_FORMAT):
                p = self.src / f"secret-{fmt}-{i}.{fmt}"
                p.write_bytes(_mutate(data, rnd))
                calls = {
                    "inspect": lambda p=p: inspect_image(p),
                    "convert": lambda p=p, i=i: convert_image(p, "png", self.out, f"c{i}"),
                    "resize": lambda p=p, i=i: resize_image(p, self.out, f"r{i}", width=8),
                }
                for op, call in calls.items():
                    with self.subTest(fmt=fmt, i=i, op=op):
                        try:
                            result = call()
                        except EngineError as err:
                            self.assertIn(err.code, FAILURE_CODES)
                            self.assertNotIn(str(self.base), err.message)
                            self.assertNotIn("secret", err.message)
                        else:
                            if op != "inspect":
                                ok_outputs += 1
                                self.assertTrue(result["output_file"].exists())
                p.unlink()
        # Every file in the output folder belongs to a call that succeeded: failed calls
        # leave nothing behind, not even hidden temp files.
        self.assertEqual(len(self.out_files()), ok_outputs)

    def test_every_allowlisted_format_is_registered(self):
        Image.init()
        for fmt in ALLOWED_INPUT_FORMATS:
            self.assertIn(fmt, Image.OPEN)

    def test_every_seed_is_accepted(self):
        for fmt, data in _seeds().items():
            p = self.src / f"ok.{fmt}"
            p.write_bytes(data)
            with self.subTest(fmt=fmt):
                self.assertEqual(inspect_image(p)["width"], 29)


class DecoderAllowlistTests(_Dirs):
    def _write(self, name: str, fmt: str, **kw) -> Path:
        p = self.src / name
        Image.new("RGB", (6, 5), (10, 20, 30)).save(p, fmt, **kw)
        return p

    def test_other_formats_are_refused_before_decoding(self):
        for name, fmt in [("a.pcx", "PCX"), ("a.ppm", "PPM"), ("a.ico", "ICO"), ("a.tga", "TGA")]:
            p = self._write(name, fmt)
            for call in (
                lambda p=p: inspect_image(p),
                lambda p=p: convert_image(p, "png", self.out, "x"),
            ):
                with self.subTest(fmt=fmt), self.assertRaises(EngineError) as cm:
                    call()
                self.assertEqual(cm.exception.code, "unsupported_format")
        self.assertEqual(self.out_files(), [])

    def test_eps_never_starts_ghostscript(self):
        p = self.src / "evil.eps"
        p.write_bytes(
            b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\n"
            b"(%pipe%id) (w) file\nshowpage\n%%EOF\n"
        )
        boom = AssertionError("a subprocess was started")
        with (
            mock.patch.object(subprocess, "Popen", side_effect=boom),
            mock.patch.object(subprocess, "check_call", side_effect=boom),
            mock.patch.object(subprocess, "run", side_effect=boom),
        ):
            for call in (
                lambda p=p: inspect_image(p),
                lambda p=p: convert_image(p, "png", self.out, "x"),
            ):
                with self.assertRaises(EngineError) as cm:
                    call()
                self.assertEqual(cm.exception.code, "unsupported_format")
        self.assertEqual(self.out_files(), [])

    def test_multi_picture_jpeg_from_phone_cameras_still_opens(self):
        p = self.src / "stereo.jpg"
        Image.new("RGB", (12, 8), "red").save(
            p, "MPO", save_all=True, append_images=[Image.new("RGB", (12, 8), "blue")]
        )
        info = inspect_image(p)
        self.assertEqual((info["format"], info["frames"]), ("MPO", 2))
        res = convert_image(p, "png", self.out, "stereo")
        with Image.open(res["output_file"]) as im:
            r, g, b = im.convert("RGB").getpixel((0, 0))
        self.assertGreater(r, 240)  # first frame (red), JPEG-lossy source
        self.assertLess(max(g, b), 15)


class BombTests(_Dirs):
    def test_header_bombs_refused_without_decoding(self):
        # 9000x9000 = 81 MP: above our 64 MP limit but below Pillow's own warning level;
        # 20000x20000 = 400 MP: Pillow itself raises DecompressionBombError.
        for w, h in [(9000, 9000), (20000, 20000), (1, 70_000_000)]:
            p = self.src / f"bomb-{w}.png"
            p.write_bytes(_png_header_only(w, h))
            self.assertLess(p.stat().st_size, 200)
            for call in (
                lambda p=p: inspect_image(p),
                lambda p=p: convert_image(p, "png", self.out, "b"),
            ):
                with self.subTest(size=(w, h)), self.assertRaises(EngineError) as cm:
                    call()
                self.assertEqual(cm.exception.code, "too_many_pixels")
        self.assertEqual(self.out_files(), [])


class ErrorMappingTests(_Dirs):
    def test_parser_exceptions_map_to_stable_codes(self):
        p = self.src / "a.png"
        Image.new("RGB", (3, 3)).save(p)
        cases = [
            (OSError("Truncated File Read"), "decode_failed"),
            (ValueError("unknown raw mode"), "decode_failed"),
            (SyntaxError("broken PNG file"), "decode_failed"),
            (IndexError("index out of range"), "decode_failed"),
            (KeyError("x"), "decode_failed"),
            (TypeError("x"), "decode_failed"),
            (EOFError(), "decode_failed"),
            (struct.error("unpack requires a buffer"), "decode_failed"),
            (ZeroDivisionError(), "decode_failed"),
            (MemoryError(), "out_of_memory"),
            (Image.DecompressionBombError("big"), "too_many_pixels"),
        ]
        for exc, code in cases:
            for call in (
                lambda p=p: inspect_image(p),
                lambda p=p: convert_image(p, "png", self.out, "x"),
            ):
                with (
                    self.subTest(exc=type(exc).__name__),
                    mock.patch.object(engine, "_open", side_effect=exc),
                    self.assertRaises(EngineError) as cm,
                ):
                    call()
                self.assertEqual(cm.exception.code, code)
        self.assertEqual(self.out_files(), [])


if __name__ == "__main__":
    unittest.main()
