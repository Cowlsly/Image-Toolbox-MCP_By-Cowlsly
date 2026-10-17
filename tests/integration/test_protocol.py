"""MCP protocol-version negotiation, checked with raw JSON-RPC over a real stdio subprocess.

Clients in the wild pin different spec revisions (desktop apps, Termux CLIs, older SDKs).
The server must answer ``initialize`` with the client's version when it supports it, and
with a version it does support otherwise, and must then serve ``tools/list`` either way.
This is the M7 item "validate MCP protocol version and official SDK support".
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SRC = str(Path(__file__).resolve().parents[2] / "src")

# Released spec revisions a client may send and expect echoed back.
RELEASED = ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]


def _exchange(root: Path, version: str) -> tuple[dict, dict]:
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    msgs = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "protocol-probe", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    # Keep stdin open until both replies arrive: closing it early makes the server shut
    # down and may drop a request that is still queued (seen as a flaky KeyError).
    proc = subprocess.Popen(
        [sys.executable, "-m", "imagetoolbox_mcp", "--root", str(root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env=env,
    )
    replies = {}
    try:
        for m in msgs:
            proc.stdin.write(json.dumps(m) + "\n")
            proc.stdin.flush()
            if "id" in m:
                while m["id"] not in replies:
                    line = proc.stdout.readline()
                    if not line:
                        raise AssertionError(f"server closed stdout before reply {m['id']}")
                    msg = json.loads(line)  # stdout must carry JSON-RPC only
                    replies[msg.get("id")] = msg
    finally:
        proc.stdin.close()
        proc.wait(timeout=60)
        proc.stdout.close()
    return replies[1], replies[2]


class ProtocolNegotiationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name).resolve()
        Image.new("RGB", (4, 4)).save(cls.root / "a.png")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_released_versions_are_echoed(self):
        for version in RELEASED:
            with self.subTest(version=version):
                init, tools = _exchange(self.root, version)
                self.assertEqual(init["result"]["protocolVersion"], version)
                self.assertEqual(init["result"]["serverInfo"]["name"], "imagetoolbox-mcp")
                self.assertEqual(len(tools["result"]["tools"]), 7)

    def test_unknown_version_gets_a_supported_one(self):
        init, tools = _exchange(self.root, "1999-01-01")
        self.assertIn(init["result"]["protocolVersion"], RELEASED)
        self.assertEqual(len(tools["result"]["tools"]), 7)


if __name__ == "__main__":
    unittest.main()
