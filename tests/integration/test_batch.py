"""MCP-level tests for ``image_batch`` on a mixed-format folder (M4 exit criterion:
"mixed-format batch fixtures complete with no silent data loss")."""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import anyio
from mcp import Client
from PIL import Image

from imagetoolbox_mcp.sandbox import InputRoot
from imagetoolbox_mcp.server import build_server


def _text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class BatchToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.root_dir = self.base / "images"
        self.trip = self.root_dir / "trip"
        self.trip.mkdir(parents=True)
        # JPEG with EXIF orientation 6 (display rotated 90 cw) and GPS data.
        exif = Image.Exif()
        exif[0x0112] = 6
        exif[0x8825] = {1: "N", 2: (51.0, 30.0, 0.0)}
        Image.new("RGB", (60, 40), (200, 10, 10)).save(self.trip / "a.jpg", exif=exif)
        Image.new("RGBA", (30, 30), (0, 255, 0, 100)).save(self.trip / "b.png")
        Image.new("RGB", (50, 20), (0, 0, 255)).save(self.trip / "c.webp", lossless=True)
        frames = [Image.new("RGB", (16, 16), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
        frames[0].save(self.trip / "d.gif", save_all=True, append_images=frames[1:])
        (self.trip / "e.jpg").write_bytes(b"\xff\xd8 this is not really a jpeg")
        (self.trip / "readme.txt").write_text("not an image")
        Image.new("RGB", (4, 4)).save(self.base / "outside.png")
        os.symlink(self.base / "outside.png", self.trip / "sneaky.png")
        self.out_dir = self.root_dir / "imagetoolbox-out"
        self.hashes = {p.name: _sha(p) for p in self.trip.iterdir() if not p.is_symlink()}

    def tearDown(self):
        self._tmp.cleanup()

    def client(self):
        return Client(build_server(InputRoot(self.root_dir)), raise_exceptions=False)

    def assertOriginalsUntouched(self):
        now = {p.name: _sha(p) for p in self.trip.iterdir() if not p.is_symlink()}
        self.assertEqual(now, self.hashes)

    async def test_schema_and_annotations(self):
        async with self.client() as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
        bt = tools["image_batch"]
        self.assertEqual(bt.input_schema["required"], ["operation"])
        props = bt.input_schema["properties"]
        self.assertEqual(
            props["operation"]["enum"], ["convert", "resize", "compress", "rotate_flip", "crop"]
        )
        self.assertNotIn("ctx", props)
        self.assertEqual(props["max_files"]["maximum"], 200)
        a = bt.annotations
        self.assertEqual(
            (a.read_only_hint, a.destructive_hint, a.idempotent_hint, a.open_world_hint),
            (False, False, False, False),
        )
        self.assertIn("items", bt.output_schema["properties"])

    async def test_mixed_folder_convert_reports_every_file(self):
        progress = []

        async def on_progress(p, total, message):
            progress.append((p, total))

        async with self.client() as c:
            r = await c.call_tool(
                "image_batch",
                {"operation": "convert", "options": {"format": "webp"}, "folder": "trip"},
                progress_callback=on_progress,
            )
        self.assertFalse(r.is_error, _text(r))
        res = r.structured_content
        by_src = {it["source"]: it for it in res["items"]}
        self.assertEqual(
            sorted(by_src), ["trip/a.jpg", "trip/b.png", "trip/c.webp", "trip/d.gif", "trip/e.jpg"]
        )
        self.assertEqual((res["matched"], res["succeeded"], res["failed"]), (5, 4, 1))
        self.assertEqual(res["not_run"], 0)
        self.assertIsNone(res["stopped_reason"])
        self.assertEqual(by_src["trip/e.jpg"]["status"], "failed")
        self.assertEqual(by_src["trip/e.jpg"]["error_code"], "unsupported_format")
        self.assertEqual(res["skipped"], [{"name": "sneaky.png", "reason": "symlink_rejected"}])
        self.assertTrue(by_src["trip/d.gif"]["warnings"][0].startswith("frames_dropped"))
        # EXIF orientation applied: 60x40 stored, 40x60 displayed.
        self.assertEqual((by_src["trip/a.jpg"]["width"], by_src["trip/a.jpg"]["height"]), (40, 60))
        self.assertEqual(progress, [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)])

        # Every ok item's output exists, is WebP, and carries no EXIF/GPS.
        for it in res["items"]:
            if it["status"] != "ok":
                continue
            out = self.root_dir / it["output"]
            with Image.open(out) as im:
                self.assertEqual(im.format, "WEBP")
                self.assertEqual(dict(im.getexif()), {})
        # Output names are flat: trip/c.webp -> imagetoolbox-out/c.webp.
        self.assertEqual(by_src["trip/c.webp"]["output"], "imagetoolbox-out/c.webp")

        # Manifest: records all five files with checksums that match the files on disk.
        manifest = json.loads((self.root_dir / res["manifest"]).read_text())
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["operation"], "convert")
        self.assertEqual(manifest["options"]["format"], "webp")
        self.assertEqual(len(manifest["items"]), 5)
        for rec in manifest["items"]:
            if rec["status"] == "ok":
                self.assertEqual(rec["source_sha256"], self.hashes[Path(rec["source"]).name])
                self.assertEqual(rec["output_sha256"], _sha(self.root_dir / rec["output"]))
        self.assertNotIn(str(self.base), json.dumps(manifest))  # no host paths
        self.assertOriginalsUntouched()

    async def test_dry_run_writes_nothing(self):
        async with self.client() as c:
            r = await c.call_tool(
                "image_batch",
                {
                    "operation": "resize",
                    "options": {"width": 10},
                    "folder": "trip",
                    "pattern": "*.JPG",
                    "dry_run": True,
                },
            )
        self.assertFalse(r.is_error, _text(r))
        res = r.structured_content
        self.assertTrue(res["dry_run"])
        self.assertEqual([it["source"] for it in res["items"]], ["trip/a.jpg", "trip/e.jpg"])
        self.assertEqual({it["status"] for it in res["items"]}, {"planned"})
        self.assertIsNone(res["manifest"])
        self.assertFalse(self.out_dir.exists())

    async def test_second_run_never_overwrites(self):
        args = {
            "operation": "rotate_flip",
            "options": {"rotate": 180},
            "folder": "trip",
            "pattern": "b.png",
        }
        async with self.client() as c:
            first = (await c.call_tool("image_batch", args)).structured_content
            second = (await c.call_tool("image_batch", args)).structured_content
        self.assertEqual(first["items"][0]["output"], "imagetoolbox-out/b-rot180.png")
        self.assertEqual(second["items"][0]["output"], "imagetoolbox-out/b-rot180-1.png")
        self.assertNotEqual(first["manifest"], second["manifest"])
        self.assertTrue((self.root_dir / first["items"][0]["output"]).is_file())

    async def test_per_file_engine_errors_do_not_stop_the_batch(self):
        # 40x40 crop fits b.png (30x30)? No -> per-file failure; fits a.jpg (40x60 upright).
        async with self.client() as c:
            r = await c.call_tool(
                "image_batch",
                {
                    "operation": "crop",
                    "options": {"width": 40, "height": 40},
                    "folder": "trip",
                    "pattern": "[ab].*",
                },
            )
        res = r.structured_content
        status = {it["source"]: (it["status"], it["error_code"]) for it in res["items"]}
        self.assertEqual(
            status,
            {"trip/a.jpg": ("ok", None), "trip/b.png": ("failed", "crop_out_of_bounds")},
        )

    async def test_refusals_write_nothing(self):
        cases = [
            ({"operation": "resize", "options": {}, "folder": "trip"}, "[invalid_argument]"),
            ({"operation": "convert", "options": {"format": "bmp"}}, "[invalid_argument]"),
            ({"operation": "convert", "options": {"format": "png"}, "folder": ".."}, "[outside_"),
            (
                {"operation": "convert", "options": {"format": "png"}, "folder": "trip/a.jpg"},
                "[not_a_folder]",
            ),
            (
                {
                    "operation": "convert",
                    "options": {"format": "png"},
                    "folder": "trip",
                    "max_files": 2,
                },
                "[too_many_files]",
            ),
            (
                {
                    "operation": "convert",
                    "options": {"format": "png"},
                    "folder": "imagetoolbox-out",
                },
                "[not_found]",
            ),
        ]
        async with self.client() as c:
            for args, code in cases:
                with self.subTest(args=args):
                    r = await c.call_tool("image_batch", args)
                    self.assertTrue(r.is_error)
                    self.assertIn(code, _text(r))
            self.out_dir.mkdir()
            r = await c.call_tool(
                "image_batch",
                {
                    "operation": "convert",
                    "options": {"format": "png"},
                    "folder": "imagetoolbox-out",
                },
            )
            self.assertIn("output folder", _text(r))
        self.assertEqual(list(self.out_dir.iterdir()), [])
        self.assertOriginalsUntouched()

    async def test_empty_match_is_not_an_error(self):
        async with self.client() as c:
            r = await c.call_tool(
                "image_batch",
                {"operation": "compress", "folder": "trip", "pattern": "nothing*"},
            )
        self.assertFalse(r.is_error, _text(r))
        self.assertEqual(r.structured_content["matched"], 0)
        self.assertIsNone(r.structured_content["manifest"])
        self.assertFalse(self.out_dir.exists())

    async def test_cancellation_keeps_finished_files_and_records_them(self):
        big = self.root_dir / "big"
        big.mkdir()

        def make():
            for i in range(6):
                Image.effect_noise((900, 900), 60).convert("RGB").save(big / f"n{i}.png")

        await anyio.to_thread.run_sync(make)  # keep the event loop responsive
        async with self.client() as c:
            async with anyio.create_task_group() as tg:

                async def on_progress(p, total, message):
                    if p >= 2:
                        tg.cancel_scope.cancel()

                async def call():
                    await c.call_tool(
                        "image_batch",
                        {"operation": "compress", "options": {"colors": 16}, "folder": "big"},
                        progress_callback=on_progress,
                    )

                tg.start_soon(call)
            await anyio.sleep(1.5)  # a non-cancelled server would finish more files by now
            r = await c.call_tool("image_inspect", {"path": "big/n0.png"})
            self.assertFalse(r.is_error)
        outputs = sorted(p.name for p in self.out_dir.glob("*.png"))
        manifests = list(self.out_dir.glob("*.json"))
        self.assertLess(len(outputs), 6)
        self.assertGreaterEqual(len(outputs), 2)
        self.assertEqual(len(manifests), 1)
        manifest = json.loads(manifests[0].read_text())
        self.assertEqual(manifest["status"], "cancelled")
        self.assertEqual(sorted(Path(r["output"]).name for r in manifest["items"]), outputs)
        self.assertEqual(list(self.out_dir.glob(".itmcp-*")), [])  # no stray temp files


if __name__ == "__main__":
    unittest.main()
