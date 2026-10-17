# ADR-0003: Transports and how a phone-only owner reaches the server

- **Status:** Accepted (2026-10-17, run 8).
- **Deciders:** Claude (scheduled session) under authority delegated by Cowlsly.
- **Applies to:** M7 (client interoperability), and constrains M6 (threat model) and M9 (release).
- **Research and sources:** [`docs/clients.md`](../clients.md).

## Context

The owner works only from an Android phone (Termux). The server today speaks MCP over **stdio**, which means the MCP *client* must start it as a child process on the same device. Research (October 2026, sources in `docs/clients.md`) found:

1. **Claude Android app** — can use *custom connectors* (remote MCP servers) added on claude.ai first (the mobile app cannot add them). Transports: Streamable HTTP (SSE being retired). Auth: **authless or OAuth** only. Connections come **from Anthropic's cloud**, so a server on the phone is only reachable through a public HTTPS tunnel. No stdio.
2. **ChatGPT** — full MCP connectors (developer mode / "Plugins") are **web-only, not in the mobile apps**; Pro gets read/fetch-only MCP; Business/Enterprise need an admin. Remote public HTTPS only. Not a realistic target for this project right now.
3. **Agent CLIs inside Termux** — Claude Code runs in Termux through a community installer (glibc shim on the official arm64 binary, or proot Ubuntu), and that project reports **local stdio MCP servers work**. Gemini CLI also runs in Termux via npm (with a native-module workaround). Both can launch `imagetoolbox-mcp` over stdio with nothing exposed to the network.
4. **SDK spike (this run):** the official MCP Python SDK (2.2.0) already serves our unchanged server over Streamable HTTP on `127.0.0.1`; an SDK client listed all 6 tools and called `image_inspect`; a request with a foreign `Host` header was refused with **421** (DNS-rebinding protection is on by default for loopback). Through a tunnel the Host header is the tunnel's name, so it must be allowlisted explicitly.

The tools write files and read every image under the chosen root. An **authless public URL would let anyone who learns it read the owner's photos** (as metadata, and later as pixels) and fill storage. That is unacceptable for a personal photo folder.

## Decision

1. **stdio stays the primary, default and only shipped transport for now.** It needs no auth, opens no port, and works today with any MCP client that can launch a local process.
2. **Recommended phone path (Path A):** run an MCP-capable agent CLI *inside Termux* (Claude Code via the community installer, or Gemini CLI) and register `imagetoolbox-mcp` as a stdio server. Documented in `docs/clients.md`. VERIFY on the owner's phone.
3. **Claude-app path (Path B) is deferred, not rejected.** It requires all of: an `--transport http` mode bound to `127.0.0.1`, a tunnel (e.g. `cloudflared`, VERIFY in Termux), Host/Origin allowlisting for the tunnel name, and **OAuth 2.1** (the only auth Claude connectors accept besides none). It will be built only after the M6 threat model, and must also offer a read-only tool set. Authless remote mode will **not** be shipped.
4. **Loopback HTTP without remote exposure** (`--transport http --host 127.0.0.1`) may be added earlier if a local client needs it (e.g. a Termux client that speaks only HTTP). It must refuse non-loopback binds unless auth is configured, and keep DNS-rebinding protection on.
5. **ChatGPT** is documented as "not supported on mobile" and revisited when OpenAI ships MCP connectors in the mobile apps.
6. **Protocol versions:** the server negotiates 2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25 (echoed), and answers unknown versions with a supported one — locked by `tests/integration/test_protocol.py`.

## Consequences

- No new dependency and no network attack surface this milestone.
- The owner's first real use depends on a Termux agent CLI working on a Galaxy A17 5G (Exynos 1330, arm64). If neither works, Path B moves up and M6 becomes urgent.
- Images are passed by **path inside the root**, not uploaded from the chat. A photo attached in a chat app is not visible to the server; the owner must save it into the root folder first. Results are files in `imagetoolbox-out/`, not inline pictures. (Returning a small preview as MCP image content is an M10 candidate.)

## Alternatives considered

- **Authless HTTP + secret URL path** — rejected: URL secrets leak via logs, history and screenshots; Claude's connector UI offers no custom header for a static token.
- **Ship HTTP now for both apps** — rejected: ChatGPT mobile cannot use it at all, and Claude mobile needs OAuth, which is a large security-critical component that should follow the threat model.
- **Android app bridge (M5)** — unrelated to transport; still deferred.
