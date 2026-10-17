# ADR-0001: Processing backend and runtime

- **Status:** Accepted (2026-10-17). Termux install path is **VERIFY** (see Consequences).
- **Deciders:** Claude (scheduled session) under authority delegated by Cowlsly.

## Context

The roadmap (§3) lists three backend options. The upstream audit ([docs/audit/upstream-audit.md](../audit/upstream-audit.md)) found:

1. Image Toolbox exposes **no headless API**: all exported intents open interactive screens and return nothing.
2. Its processing code depends on the Android framework (`android.graphics.Bitmap`, Compose, Hilt), so it can't run in Termux or on a desktop.
3. Upstream is Apache-2.0 (T8RIN); we copy no code, so no redistribution obligations yet beyond honest attribution.

The owner works only from an Android phone using Termux. The server must be something they can run there, and something we can build and test in a cloud sandbox where package registries may be blocked.

## Decision

1. **Backend: option 1, an independent local image engine** built on **Pillow** (Python Imaging Library fork, MIT-CMU licence).
2. **Runtime: Python ≥ 3.10.** MCP transport via the **official MCP Python SDK** (`mcp`, tested against 2.2.0 using `mcp.server.mcpserver.MCPServer`) over **stdio**.
3. **Layering:** `engine` (pure functions, Pillow only, no MCP imports) → `tools` (schemas, policy, response envelope) → `server` (SDK wiring). The engine is unit-testable without the SDK.
4. **Tests:** standard-library `unittest` (no pytest dependency), fixtures generated at test time. Lint/format with `ruff` (dev-only, optional on the phone).
5. **Android bridge (option 2)** stays a conditional M5 track. Option 3 (reusing upstream code) is rejected off-device.

## Why not the alternatives

| Option | Verdict | Reason |
| --- | --- | --- |
| Node.js + `sharp` | Rejected | `sharp` ships native libvips binaries; no prebuilt for Android/Termux, building from source on a phone is fragile. |
| Node.js + pure-JS (Jimp) | Rejected | Slow, weak WebP/EXIF support. |
| Python + Pillow | **Chosen** | Termux ships `python` and a prebuilt `python-pillow` package (no compiling); Pillow covers JPEG/PNG/WebP/EXIF; official MCP SDK exists. |
| Kotlin inside the fork | Deferred (M5) | Needs Android build tooling, a new exported component, permission design and device testing. |

## Consequences

- Output will not be pixel-identical to Image Toolbox; we document that and never claim parity.
- **VERIFY (owner's phone):** the `mcp` SDK depends on `pydantic-core` (Rust) and `cryptography` via `pyjwt[crypto]`. In Termux these may need `pkg install python-cryptography rust` or long builds. If installation fails on the phone, fallback: a small, dependency-free stdio JSON-RPC shim implementing only `initialize`, `tools/list` and `tools/call`, kept behind the same `tools` layer. Decide after the first real Termux install report.
- **Client reachability:** a phone-only owner also needs an MCP *client* that can launch a local stdio server. Mobile ChatGPT/Claude apps generally can't do that; this is tracked under M7 and may require an authenticated HTTP transport later (not before a threat model).
- The cloud build sandbox has no PyPI/npm access (HTTP 403 from the egress proxy on 2026-10-17); it relies on preinstalled Python 3.13, Pillow 12.3.0, mcp 2.2.0 and ruff. CI on GitHub Actions should install from PyPI normally.

## Fallback

If Pillow proves inadequate for a format, add a per-format optional plugin (e.g. `pillow-heif`) behind a capability check, never as a hard dependency.
