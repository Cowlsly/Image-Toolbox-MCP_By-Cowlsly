# ADR-0006: Android bridge (M5) — ship the independent backend

Status: accepted, 2026-10-25 (run 12).

## Context

M5 asked whether the Image Toolbox Android app (fork `ImageToolbox-For_Cowlsly-MCP`) could expose an authorised entry point the MCP server calls. The upstream audit found no headless, parameterised entry point; adding one means changing a large Compose app, holding a content-URI permission model (SAF grants that expire), a foreground service for long jobs, and caller verification. The roadmap's exit rule says: "If infeasible, publish the independent local backend instead."

## Decision

1. The independent Python backend (this repo) is the product. It already runs on the phone inside Termux with storage access granted once by `termux-setup-storage`, needs no broad storage permission inside another app, and keeps all processing on-device.
2. The Android bridge is **not built now**. Re-open only if a user need appears that Termux cannot meet (e.g. using the Image Toolbox app's own filters).
3. If re-opened, the design constraints are fixed now:
   - Explicit, per-operation user consent in the app (no silent background calls).
   - Storage Access Framework only; no `MANAGE_EXTERNAL_STORAGE`.
   - A bound service protected by a signature-level permission so only the Cowlsly-signed companion can call it; reject all other callers.
   - Foreground service with a visible notification for any job over a few seconds (Android 14+ requires a declared foreground-service type).
   - Tests on a physical Samsung Galaxy A17 5G before any release.

## Limitations documented for users

- The Claude and ChatGPT phone apps cannot reach a server inside the phone (they call connectors from the cloud) — [clients.md](../clients.md).
- Inside Termux the server only sees folders shared through `termux-setup-storage`.
