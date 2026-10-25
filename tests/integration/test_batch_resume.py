"""``image_batch`` resume-from-manifest and retries."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import Client
from PIL import Image

from imagetoolbox_mcp import batch as batch_mod
from imagetoolbox_mcp.engine import EngineError
from imagetoolbox_mcp.sandbox import InputRoot
from imagetoolbox_mcp.server import build_server


def _text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


class ResumeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root_dir = Path(self._tmp.name).resolve() / "images"
        self.set = self.root_dir / "set"
        self.set.mkdir(parents=True)
        for i in range(4):
            Image.new("RGB", (10 + i, 10), (i * 50, 0, 0)).save(self.set / f"p{i}.png")
        self.out_dir = self.root_dir / "imagetoolbox-out"

    def tearDown(self):
        self._tmp.cleanup()

    def client(self):
        return Client(build_server(InputRoot(self.root_dir)), raise_exceptions=False)

    async def _first_run(self, c):
        args = {"operation": "convert", "options": {"format": "jpeg"}, "folder": "set"}
        r = await c.call_tool("image_batch", args)
        self.assertFalse(r.is_error, _text(r))
        return args, r.structured_content["manifest"].split("/")[-1]

    async def test_resume_skips_finished_unchanged_files(self):
        async with self.client() as c:
            args, manifest = await self._first_run(c)
            before = sorted(p.name for p in self.out_dir.glob("*.jpg"))
            # change one source and delete one output: both must be redone
            Image.new("RGB", (30, 30), (1, 2, 3)).save(self.set / "p1.png")
            (self.out_dir / "p2.jpg").unlink()
            r = await c.call_tool("image_batch", {**args, "resume_from": manifest})
            self.assertFalse(r.is_error, _text(r))
            d = r.structured_content
            status = {it["source"]: it["status"] for it in d["items"]}
            self.assertEqual(status["set/p0.png"], "resumed")
            self.assertEqual(status["set/p3.png"], "resumed")
            self.assertEqual(status["set/p1.png"], "ok")
            self.assertEqual(status["set/p2.png"], "ok")
            self.assertEqual((d["resumed"], d["succeeded"]), (2, 2))
        after = sorted(p.name for p in self.out_dir.glob("*.jpg"))
        self.assertEqual(len(after), len(before) + 1)  # p1-1.jpg new, p2.jpg recreated
        new_manifest = json.loads((self.out_dir / d["manifest"].split("/")[-1]).read_text())
        self.assertEqual(
            sorted(i["status"] for i in new_manifest["items"]), ["ok", "ok", "resumed", "resumed"]
        )

    async def test_resume_refuses_other_operation_options_and_paths(self):
        async with self.client() as c:
            args, manifest = await self._first_run(c)
            for bad, code in (
                ({**args, "options": {"format": "png"}, "resume_from": manifest}, "invalid"),
                (
                    {
                        **args,
                        "operation": "resize",
                        "options": {"width": 5},
                        "resume_from": manifest,
                    },
                    "invalid",
                ),  # fmt: skip
                ({**args, "resume_from": "../" + manifest}, "invalid_argument"),
                ({**args, "resume_from": "missing.json"}, "not_found"),
                ({**args, "resume_from": "p0.jpg"}, "invalid_argument"),
            ):
                with self.subTest(bad=bad):
                    r = await c.call_tool("image_batch", bad)
                    self.assertTrue(r.is_error)
                    self.assertIn(f"[{code}", _text(r))

    async def test_retries_recover_a_temporary_failure(self):
        real = batch_mod.run_one
        calls = {"n": 0}

        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise EngineError("output_unavailable", "busy")
            return real(*a, **k)

        args = {"operation": "convert", "options": {"format": "jpeg"}, "folder": "set"}
        with mock.patch("imagetoolbox_mcp.server.run_one", side_effect=flaky):
            async with self.client() as c:
                r = await c.call_tool("image_batch", {**args, "retries": 1})
        self.assertFalse(r.is_error, _text(r))
        self.assertEqual(r.structured_content["succeeded"], 4)
        self.assertEqual(r.structured_content["failed"], 0)

    async def test_without_retries_the_failure_is_reported(self):
        def always(*a, **k):
            raise EngineError("output_unavailable", "busy")

        args = {"operation": "convert", "options": {"format": "jpeg"}, "folder": "set"}
        with mock.patch("imagetoolbox_mcp.server.run_one", side_effect=always):
            async with self.client() as c:
                r = await c.call_tool("image_batch", {**args, "retries": 2})
        self.assertEqual(r.structured_content["failed"], 4)
        self.assertEqual(r.structured_content["items"][0]["error_code"], "output_unavailable")


if __name__ == "__main__":
    unittest.main()
