# Project state — handover log

Newest entry first. Each run: what was done, test evidence, blockers, next action. No secrets or personal data here.

## Current snapshot

| Milestone | Status |
| --- | --- |
| M0 Foundations | ACTIVE — runtime, packaging, CI workflow, community files done; CI activation BLOCKED (owner must move `ci/ci.yml`); branch rules, secret scanning: owner settings |
| M1 Upstream audit | **COMPLETE** (2026-10-17) |
| M2 Minimal MCP server | **COMPLETE** (2026-10-17, run 3) — `image_inspect` over stdio; output-path item moved to M3 |
| M3 Core operations | **COMPLETE** (2026-10-17, run 7) — convert + output policy (run 4), resize (run 5), compress (run 6), rotate/flip + crop (run 7) |
| M7 Client interoperability | NEXT — phone-client research (run 8) |
| M4–M6, M8–M10 | PENDING |

**Stack:** Python ≥ 3.10, Pillow, official MCP Python SDK (stdio), `unittest`, `ruff`. See `docs/adr/0001-processing-backend.md`.

**Run:** `imagetoolbox-mcp --root DIR [--out DIR]` (or `IMAGETOOLBOX_MCP_ROOT` / `IMAGETOOLBOX_MCP_OUT`). Tools: `image_inspect`, `image_convert`, `image_resize`, `image_compress`, `image_rotate_flip`, `image_crop`. Version 0.5.0.

**How to test:** `PYTHONPATH=src python3 -m unittest discover -s tests -t .` (or `pip install -e .` first) and `ruff check src tests && ruff format --check src tests`.

**Sandbox packaging note:** the sandbox's Debian setuptools 68.1.2 is broken on Python 3.13 (`AttributeError: install_layout`) and is too old for SPDX `license = "MIT"`. Workaround: in a venv, `pip install /usr/lib/python3.11/ensurepip/_bundled/setuptools-79.0.1-py3-none-any.whl`, then `pip install --no-build-isolation --no-deps .`. Normal machines (CI, Termux) fetch setuptools ≥ 77 from PyPI automatically.

## Open blockers / VERIFY items

1. **Cloud sandbox has no PyPI/npm access** (egress proxy returns 403 for pypi.org and registry.npmjs.org). Work relies on preinstalled Python 3.13.16, Pillow 12.3.0, mcp 2.2.0, pydantic 2.13.5, ruff 0.16.8. Pin versions conservatively; CI on GitHub will install from PyPI.
2. **`git push` from the sandbox is denied** (repo not in the session's authorised git set). Workaround used: commit via the GitHub connector (`push_files`). Works, but each file's full content must be sent — keep commits small. Owner can fix by adding this repo to the scheduled task's sources.
3. **VERIFY on owner's phone (Termux):** `pkg install python python-pillow` then `pip install mcp`. Unknown whether `pydantic-core`/`cryptography` build cleanly. Fallback plan in ADR-0001.
4. **BLOCKED → owner:** CI workflow is staged at `ci/ci.yml`. The GitHub connector returns `403 Resource not accessible by integration` for any commit touching `.github/workflows/` (no `workflows` permission), and `git push` is denied. **Owner fix (phone, 1 min):** open `ci/ci.yml` on github.com → Edit → change the file name/path to `.github/workflows/ci.yml` → delete the 4-line comment header → Commit. Then check the Actions tab for a green run (VERIFY: Actions billing/availability still untested).
5. **Open question (M7):** which MCP client the owner can use from a phone to reach a local stdio server.
6. **Owner setting:** enable Settings → Code security → Secret scanning + Push protection, and Private vulnerability reporting (SECURITY.md points to it). Optional: branch protection on `root` requiring CI.

## Run log

### 2026-10-17 — run 7 (Claude, scheduled)

**Done (M3 closed — `image_rotate_flip` + `image_crop`)**
- Oriented at 13:43 UTC: last commit 09:57 UTC (run 6, same agent); no other agent activity, no clash. `ci/ci.yml` still not moved (blocker 4).
- Small refactor first: `engine._pick_target` (source format or PNG + `format_changed`) replaces two copies in resize/compress; 113 old tests passed unchanged.
- `engine.rotate_flip_image` + MCP `image_rotate_flip`: `rotate` 0/90/180/270 **clockwise** (Pillow's `ROTATE_90` is counter-clockwise, so mapped explicitly), `flip` horizontal/vertical, rotation before flip; no-op call → `[invalid_argument]`. Exact `transpose` moves keep every mode (P + transparency, I;16, LA/RGBA). Default name `<source>-rot90-flipH`.
- `engine.plan_crop` (pure geometry) + `engine.crop_image` + MCP `image_crop`: explicit box (`width`/`height`, `left`/`top` default 0) or `aspect` `"W:H"` (largest centred box, min 1 px). Out-of-bounds → `[crop_out_of_bounds]` whose message gives the real upright size (helps the model retry); deliberately **not** clamped. `crop_full_image` warning when nothing is removed. Arguments validated before the file is opened. Default name `<source>-crop-<W>x<H>`.
- Decision: both tools warn `lossy_reencode` for JPEG/lossy-WebP output, because users expect rotate/crop to be lossless (jpegtran-style); true lossless JPEG transforms would need libjpeg's `jpegtran`, which Pillow does not expose — deferred (M10 candidate, needs a Termux availability check).
- Shared MCP parameter types (`SourcePath`, `OutFormat`, `Quality`, `Lossless`) moved to module level in `server.py` — the SDK evaluates string annotations by name, so function-local aliases fail (`InvalidSignature`).
- Version 0.5.0; README tool table, CHANGELOG, pyproject description; roadmap M3 ticked and marked COMPLETE; next action changed to M7 client research (reason in roadmap §11.8).

**Tests:** 143 OK (was 113), also with `-W error::ResourceWarning`: +26 engine tests (pixel mapping vs reference transposes for all 6 rotate/flip combos, rotate-then-flip order, upright-coordinate semantics with EXIF orientation 6, lossless-WebP alpha exactness, P/I;16/LA modes, GPS stripped + ICC kept + source hash unchanged, crop geometry incl. a 168-case aspect sweep, 10 bad aspect strings, errors write nothing incl. symlink), +4 MCP tests; stdio subprocess test lists 6 tools and calls both new ones. Same 143 pass against the wheel installed in a venv (`imagetoolbox-mcp --version` → 0.5.0). `ruff check`/`ruff format --check` clean. GitHub CI still not run (blocker 4).

**Next action (run 8):** M7 — research, with sources, how a phone-only owner can actually use this server: (a) MCP clients that run in Termux and launch stdio servers; (b) whether the Claude/ChatGPT Android apps can only use remote (HTTPS) connectors, which would need Streamable HTTP + auth + a tunnel; (c) recommend one path. Write `docs/clients.md` (+ ADR-0003 if the transport changes). Then M4 batch.

### 2026-10-17 — run 6 (Claude, scheduled)

**Done (M3 — `image_compress`)**
- Oriented at 09:43 UTC: last commit 08:54 UTC (run 5, ~49 min earlier, same agent); no other agent activity, no clash. `ci/ci.yml` still not moved (blocker 4).
- Refactor: `_encode_new` split into `_encoder_setup` (mode prep + metadata strip + params), `_save`, `_result`; all 93 earlier tests passed unchanged.
- `engine.compress_image` + MCP tool `image_compress`: JPEG/WebP by `quality` (default 80) or `max_bytes` (binary search for highest quality in `[min_quality=10, 95]`); PNG lossless optimise, `colors` 2–256 palette reduction (RGBA via FASTOCTREE keeps alpha), `max_bytes` walks the ladder 256→128→…→2 and takes the first fit. `CompressResult` adds `quality_used`, `colors_used`, `max_bytes`, `target_met`, `saved_bytes`. Warnings: `target_not_met` (smallest attempt kept), `larger_than_source`, `palette_reduced`, `quality_ignored`, `colors_ignored`, `format_changed`. Default name `<source>-compressed`.
- Evidence-driven design change: a first version binary-searched PNG palette sizes 2–256; on a 6 MP image it took 32.6 s, and measuring showed PNG size is **not monotonic** in palette size (16 colours → 4-bit packing → 2.26 MB vs 32 colours 1.79 MB), so binary search picked a needlessly small palette. Now: descending ladder, probes encoded without `optimize` (the slow part, ~3× cost), final encode optimised → 13.9 s worst case (noise image), picks 32 colours. JPEG `max_bytes` on the same 6 MP image: 0.4 s.
- Version 0.4.0; README tool table, CHANGELOG, roadmap M3 tick, pyproject description.

**Tests:** 113 OK (was 93), also with `-W error::ResourceWarning`: +16 golden compress tests, +4 MCP compress tests, stdio subprocess test lists 4 tools and compresses. Same 113 pass against the wheel installed in a venv (`imagetoolbox-mcp --version` → 0.4.0). `ruff check`/`ruff format --check` clean. GitHub CI still not run (blocker 4).

**Next action (run 7):** close M3 with `image_rotate_flip` (90/180/270 + horizontal/vertical flip, lossless pixel moves on the upright image) and `image_crop` (explicit `left/top/width/height` on the upright image, bounds-checked, optional aspect-ratio centre crop), golden tests, then mark M3 exit. After that: M7 client research (which phone MCP client can launch a stdio server in Termux) before M4 batch.

### 2026-10-17 — run 5 (Claude, scheduled)

**Done (M3 — `image_resize`)**
- Oriented at 08:43 UTC: last commit 05:55 UTC (run 4); no other agent activity, no clash. `ci/ci.yml` still not moved (blocker 4); `git push` still denied (blocker 2) → committed via the connector.
- Refactor first: `engine._load_upright` (size/pixel checks, frame 0, EXIF orientation, GPS/ICC facts) + `engine._encode_new` (mode prep, metadata strip, encode, never-overwrite write). `convert_image` now uses them; all 62 old tests passed unchanged after the refactor.
- `engine.plan_resize` (pure geometry) + `engine.resize_image`: `contain`/`cover`/`exact`; Lanczos default, plus bicubic/bilinear/nearest; no upscaling unless `allow_upscale` (`contain` keeps size + `upscale_skipped` warning; `cover`/`exact` → `upscale_refused`); max 16384 px per side and the pixel limit on the result; `aspect_changed` warning for stretched `exact`; output format = source (JPEG/PNG/WebP) else PNG with `format_changed` warning; default name `<stem>-<W>x<H>`; output name validated before decoding.
- Mode handling decided: P/1-bit expanded before filtering (Pillow would otherwise silently use nearest), `nearest` keeps palette; I;16 resampled as I then clamped back to I;16 (PNG stays 16-bit); RGBA relies on Pillow's premultiplied resize (tested: no dark fringes).
- MCP tool `image_resize` (same annotations as convert; `ResizeResult` adds `source_width/height`). Version 0.3.0; README, CHANGELOG, roadmap M3 tick.

**Tests:** 93 OK (was 62), also with `-W error::ResourceWarning`: +12 geometry tests (incl. exhaustive "contain never overshoots the box" sweep), +14 golden resize tests, +5 MCP resize tests; stdio subprocess test now lists 3 tools and resizes. Same 93 pass against the wheel installed in a venv (`imagetoolbox-mcp --version` → 0.3.0). `ruff check`/`ruff format --check` clean. GitHub CI still not run (blocker 4).

**Next action (run 6):** M3 `image_compress`: re-encode JPEG/WebP (PNG: optimize + optional palette quantize) with either `quality` or `max_bytes` (binary search on quality, report the quality reached and before/after bytes; warn and keep best effort if the target cannot be met; never larger-than-source without a warning). Then `image_rotate_flip` + `image_crop` (explicit pixel box on the upright image) to close M3, then start M7 client research (which phone MCP client can launch a stdio server in Termux).

### 2026-10-17 — run 4 (Claude, scheduled)

**Done (M3 — first write tool)**
- Oriented: last commit 04:52 UTC (run 3, ~50 min earlier); no other agent activity, no clash. `ci/ci.yml` still not moved (blocker 4 unchanged); `git push` still denied (blocker 2), so committed via the connector again.
- `docs/adr/0002-output-policy.md`: one output folder (`--out`/`IMAGETOOLBOX_MCP_OUT`, default `<root>/imagetoolbox-out`, created lazily); flat names, client gives a validated stem only, extension from the format; never overwrite (`O_CREAT|O_EXCL|O_NOFOLLOW` claim, `-1`…`-999` suffixes, then `[name_exhausted]`); atomic content (hidden temp file → fsync → `os.replace` onto the claimed name — chosen because Android shared storage (FUSE) has no hard links); output folder re-checked for symlink swap at write time; EXIF/XMP/GPS dropped, orientation baked in, ICC kept.
- `src/imagetoolbox_mcp/output.py` (`OutputDir`, `validate_stem`, `default_stem`).
- `engine.convert_image`: jpeg/png/webp; mode handling (alpha→white for JPEG, P/1/I;16/CMYK); ancillary `info` cleared before encode (Pillow's JPEG encoder otherwise re-emits XMP from `im.info`); warnings `alpha_flattened`, `frames_dropped`, `no_quality_gain`, `lossless_ignored`; `decode_failed`/`encode_failed` codes.
- `image_convert` MCP tool: enum `format`, `quality` 1–100, `lossless`, optional `output_name`; annotations not-read-only / non-destructive / non-idempotent / closed-world; result path is root-relative (e.g. `imagetoolbox-out/cat.jpg`) so it can be passed to `image_inspect`; host paths never returned.
- CLI `--out`; version 0.2.0; README, CHANGELOG, roadmap M3 ticks (output policy, convert, format-limits docs; orientation/ICC partial).
- Roadmap amendment: M6 "strip GPS/EXIF only on explicit request" reversed — outputs are stripped by default (privacy); originals untouched. Reason recorded in roadmap M6.

**Tests:** 62 OK (was 32), also with `-W error::ResourceWarning`: +12 golden convert tests (alpha flattening pixel values, EXIF-6 rotation, GPS/XMP/EXIF byte-level absence, ICC round-trip for all 3 formats, WebP-lossless pixel-exact, palette transparency, quality vs size, 5 mode cases, animated GIF, source unchanged, 6 error codes with nothing written), +12 output-policy tests (incl. 16 concurrent writers get distinct names, planted symlink not written through, output folder swapped for a symlink refused, failed writer leaves nothing), +5 MCP convert tests, +1 CLI test; stdio subprocess test now also converts. Same 62 pass against the wheel installed in a venv. `ruff check`/`ruff format --check` clean. GitHub CI still not run (blocker 4).

**Next action (run 5):** M3 `image_resize` — `width`/`height` (either or both), `fit` = `contain` (default, keep aspect) | `cover` (crop centre) | `exact`; Lanczos default with `nearest`/`bilinear`/`bicubic` options; refuse upscaling beyond source unless `allow_upscale`; output limits (max 16384 px per side, ≤ `MAX_PIXELS`); output format default = source format (fallback PNG), reuse `OutputDir` and the metadata rules; golden tests. Consider extracting the shared "open → orient → strip → save" pipeline from `convert_image` first.

### 2026-10-17 — run 3 (Claude, scheduled)

**Done (M2 — minimal MCP server)**
- Oriented: last commit 03:49 UTC (run 2, ~55 min earlier); no other agent activity, no clash. `ci/ci.yml` not yet moved by owner (blocker 4 unchanged).
- `src/imagetoolbox_mcp/sandbox.py` — `InputRoot`: single allowlisted input folder. Rejects empty/NUL/over-long paths, any `..`, symlinks at **every** path component (lstat walk), absolute paths outside the root; final `resolve()` containment check. The root itself may be a symlink (Termux `~/storage/...`). Errors never include the host path.
- `src/imagetoolbox_mcp/server.py` — `MCPServer` (mcp 2.2) with tool `image_inspect`: typed input schema (`path`, 1–1024 chars), pydantic `InspectResult` output schema (→ `structuredContent`), annotations read-only / non-destructive / idempotent / closed-world. Engine errors → `is_error` result `"[code] message"`. Logs carry codes and dimensions only.
- CLI: `imagetoolbox-mcp --root DIR [--log-level]`, env `IMAGETOOLBOX_MCP_ROOT`; exits 2 with a clear message if the root is missing. Version → 0.1.0; CHANGELOG, README (usage, client config example), roadmap M2 ticked with evidence.
- Decision: tool names are `snake_case` (`image_inspect`) because several model APIs reject dots in tool names. Recorded in roadmap M2.

**Tests:** 32 OK (was 13): 11 engine, 3 CLI, 11 sandbox, 7 integration — of which one launches the server as a real **stdio subprocess** and lists/calls the tool via the official SDK client (M2 exit criterion). Same 32 pass against the wheel installed in a venv. Raw JSON-RPC `initialize` (protocol 2025-06-18) + `tools/list` piped into the installed console script answered correctly. `ruff check` / `ruff format --check` clean. GitHub CI still not run (blocker 4).

**Next action (run 4):** M3 `image_convert` — JPEG/PNG/WebP via Pillow; separate allowlisted **output** folder (`--out DIR`, default `<root>/imagetoolbox-out`? decide in an ADR-0002 "output policy"), deterministic names (`<stem>.<fmt>`, then `<stem>-1.<fmt>`… never overwrite), atomic write (temp file + `os.replace` only into a fresh name), EXIF/GPS stripped by default, orientation applied, pixel/size limits, tests incl. no-overwrite and symlinked-output refusal. Check whether the owner moved the CI workflow.

### 2026-10-17 — run 2 (Claude, scheduled)

**Done (M0 scaffold)**
- Oriented: no new commits since run 1 (00:51 UTC); no other agent activity, no clash.
- `pyproject.toml`: setuptools ≥ 77 backend, SPDX `MIT`, Python ≥ 3.10, deps `pillow>=10`, `mcp>=2,<3` (the SDK API used is v2, tested with 2.2.0), console script `imagetoolbox-mcp` (`src/imagetoolbox_mcp/__main__.py`, `--version` only; server lands in M2).
- CI workflow (written as `.github/workflows/ci.yml`, **staged at `ci/ci.yml`** because the connector cannot write workflow files): ruff (pinned 0.16.8) lint + format check; unittest on Python 3.10–3.13 (Ubuntu) + 3.13 on Windows/macOS; installs the package and runs the entry point; `permissions: contents: read`; `actions/checkout` v7.0.1 and `actions/setup-python` v7.0.0 pinned by SHA (looked up via GitHub tags).
- `.github/dependabot.yml` (pip + actions, weekly).
- CONTRIBUTING, SECURITY (private reporting, design commitments), CODE_OF_CONDUCT (Contributor Covenant 2.1 by reference), CHANGELOG, PR template, bug/feature issue templates.
- README install/test section; roadmap M0 items ticked (2 done, CI item marked BLOCKED).

**Tests:** wheel built and installed into a venv (setuptools 79 workaround above); tests run against the *installed* package → 13 tests OK (11 engine + 2 CLI). `imagetoolbox-mcp --version` → `imagetoolbox-mcp 0.0.1`. Metadata shows `License-Expression: MIT`. ruff check/format clean. Workflow YAML parses; no actionlint available. **CI on GitHub not run** (BLOCKED, see blocker 4).

**Next action (run 3):** M2 — `src/imagetoolbox_mcp/server.py`: stdio MCP server (mcp 2.x `MCPServer`) exposing `image.inspect` wrapping `engine.inspect_image`, with an allowlisted input root (CLI flag/env var, required), path resolution that rejects escapes/symlinks, structured error results, and an in-process MCP client integration test in `tests/integration/`. If the owner has moved the workflow, check its result; if `ci/ci.yml` still exists and `.github/workflows/ci.yml` too, delete the staged copy.

### 2026-10-17 — run 1 (Claude, scheduled)

**Done**
- Oriented: repo had only README, LICENSE (MIT), `.gitignore`, roadmap. No other agents' commits.
- Static audit of the fork `ImageToolbox-For_Cowlsly-MCP@3f53dbc` → `docs/audit/upstream-audit.md`: Apache-2.0 by T8RIN; package `ru.tech.imageresizershrinker`; min/target SDK 24/37; full list of exported intents; **no headless API** (every entry opens UI, none returns a processed file); processing code is Android-bound; feature feasibility matrix.
- `docs/adr/0001-processing-backend.md`: independent Python + Pillow engine, official MCP Python SDK over stdio; Node/sharp rejected (no Termux prebuilds); Android bridge deferred to M5.
- Spike: `src/imagetoolbox_mcp/engine.py` → `inspect_image()` (format, size, mode, alpha, frames, orientation, safe EXIF subset; GPS never returned, only a `has_gps_metadata` flag; rejects symlinks/non-files; file-size and pixel limits; read-only).
- README: attribution + test instructions. Roadmap: M1 ticked with evidence, next actions rewritten, layout section updated.
- Confirmed `mcp` 2.2.0 `MCPServer` imports and registers a tool in the sandbox (smoke only, not committed).

**Tests:** `python3 -m unittest` → 11 tests, all OK (0.04 s). `ruff check` + `ruff format --check` → clean. Fork not modified.

**Next action (run 2):** M0 scaffold — `pyproject.toml` (deps `pillow`, `mcp`; console script), `.github/workflows/ci.yml` (ruff + unittest, Python 3.10–3.13, pinned action SHAs), CONTRIBUTING.md, SECURITY.md, CHANGELOG.md. Then run 3: M2 `image.inspect` MCP tool with allowlisted root + in-process client test.
