# Using Image Toolbox MCP from a client (phone first)

Status: research done 2026-10-17 (run 8). Nothing below has been run on the owner's phone yet — every phone step is marked **VERIFY**. Decision record: [ADR-0003](adr/0003-transports-and-phone-clients.md).

## Short answer

| Client | Can it use this server today? | How |
| --- | --- | --- |
| **Claude Code in Termux** | Yes (expected) — VERIFY | stdio, launched by Claude Code. Recommended. |
| **Gemini CLI in Termux** | Yes (expected) — VERIFY | stdio, via `~/.gemini/settings.json`. |
| Any desktop MCP client (Claude Desktop, VS Code, Cursor…) | Yes | stdio, `mcpServers` config in the README. |
| **Claude Android app** | Not yet | Needs a remote HTTPS server with OAuth + tunnel. Deferred (ADR-0003). |
| **ChatGPT Android app** | No | OpenAI says custom MCP connectors are web-only. |

Why the apps can't use it directly: the Claude and ChatGPT apps never start programs on your phone. Their MCP connectors are called **from the vendor's cloud** over public HTTPS, so a server inside Termux would have to be exposed to the internet. With a photo folder behind it, that needs real login (OAuth), which this project will only build after the threat model (M6).

## Path A — agent CLI inside Termux (recommended)

Everything stays on the phone: the CLI starts `imagetoolbox-mcp` as a child process and talks to it over stdin/stdout. No port is opened.

### 1. Install the server (VERIFY)

```sh
pkg update && pkg install python python-pillow git
termux-setup-storage                 # allow Termux to see your photos; creates ~/storage/...
pip install "git+https://github.com/Cowlsly/Image-Toolbox-MCP_By-Cowlsly@root"
imagetoolbox-mcp --version
```

If `pip` fails while building `pydantic-core` (a Rust package), run `pkg install rust` and retry, and please report it — this is open item 5 in the roadmap.

Choose **one** folder the server may read, for example `~/storage/pictures` (Android "Pictures"). Results go to `imagetoolbox-out/` inside it. Avoid pointing it at all of `~/storage/shared`.

### 2a. Claude Code (VERIFY)

There is no official Android build. The community project [claude-code-android](https://github.com/ferrumclaudepilgrim/claude-code-android) installs the official arm64 binary with a glibc shim (its "Path A", the default) or inside proot Ubuntu ("Path B", ~2 GB). It reports that local **stdio MCP servers work**. It needs a 64-bit phone (the A17 5G is arm64); the project says Android 8 and 10 are stuck on an old pinned version, newer Android runs current releases. Note its Path A sends Claude Code's own DNS lookups to Google DNS. Sign in with your Claude plan when it first starts.

Register the server once (available in every folder):

```sh
claude mcp add --scope user imagetoolbox -- imagetoolbox-mcp --root ~/storage/pictures
claude mcp list            # should show imagetoolbox ... connected
```

Then ask, e.g. *"Use imagetoolbox to make a 1080-px-wide JPEG copy of beach.png under 500 KB."* Claude Code will ask before running write tools.

If you used proot Ubuntu, install the server *inside* Ubuntu too and use a path the proot can see (Termux storage is usually bound at `/sdcard`).

### 2b. Gemini CLI (VERIFY)

Install with `pkg install nodejs` then `npm install -g @google/gemini-cli`. Community guides report a native-module build error on Termux that can be bypassed; follow the current workaround if `npm` fails. Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "imagetoolbox": {
      "command": "imagetoolbox-mcp",
      "args": ["--root", "/data/data/com.termux/files/home/storage/pictures"]
    }
  }
}
```

(Use the full path in JSON — `~` is not expanded there.) Run `gemini`, then `/mcp` to check that 6 tools are listed.

### Limitations on Path A

- The server works on **files in the root folder**, referred to by relative path (`holiday/a.jpg`). A photo you attach in a chat is not visible to it — save it into the folder first.
- Results are new files in `imagetoolbox-out/`; originals are never changed.
- Large PNG compression is slow on a phone (see README).

## Path B — Claude app via a remote connector (deferred)

What it would take (all required, see ADR-0003): an `--transport http` mode on `127.0.0.1`; a public HTTPS tunnel from Termux (e.g. `cloudflared`, VERIFY that the Termux package works); Host/Origin allowlisting for the tunnel name (the SDK refuses unknown Host headers with HTTP 421 — confirmed in a spike); and OAuth 2.1 so only you can call it. Claude custom connectors are added at claude.ai → Settings → Connectors (a phone browser works; the app itself cannot add them) and then appear in the Android app. Requires a paid Claude plan.

The SDK side is ready: in run 8 the unchanged server was served over Streamable HTTP on loopback and an SDK client listed and called the tools. The missing pieces are auth and the threat model, not the transport.

## ChatGPT

OpenAI's help centre (checked 2026-10-17) says full MCP connectors are available **only on the web**, Pro accounts get read/fetch-only MCP, and Business/Enterprise need an admin to create connectors. Remote public HTTPS only. Not targeted until mobile support exists.

## Protocol compatibility (tested)

`tests/integration/test_protocol.py` starts the real server over stdio and sends raw JSON-RPC `initialize`: protocol versions **2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25 are echoed back** and all 6 tools are listed; an unknown version is answered with a supported one (2025-11-25 with SDK 2.2.0). Older and newer clients therefore both connect.

## Sources (checked 2026-10-17)

- Anthropic: [Building custom connectors via remote MCP servers](https://support.claude.com/en/articles/11503834) — plans, mobile support ("servers must be added on the web first"), Streamable HTTP/SSE, authless or OAuth, connections from Anthropic IPs.
- OpenAI: [ChatGPT developer mode](https://developers.openai.com/api/docs/guides/developer-mode) and [Developer mode and full MCP connectors (help centre)](https://help.openai.com/sq-al/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt-beta) — web only, remote HTTPS, OAuth/none, write actions need confirmation.
- [claude-code-android README](https://cdn.jsdelivr.net/gh/ferrumclaudepilgrim/claude-code-android@main/README.md) — Termux install paths, stdio MCP works, device list (verified 2026-07-27).
- [Installing Gemini CLI on Termux (native build error workaround)](https://medium.com/@ROCKYSHARAF/how-to-install-gemini-cli-on-termux-bypassing-the-native-build-error-ccfa59b80be8).
- [Termux + Cloudflare Tunnel guide](https://kitemetric.com/blogs/host-a-live-website-from-your-android-phone-termux-cloudflare-tunnel) — for the deferred Path B.
