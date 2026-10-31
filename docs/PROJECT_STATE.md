# Project state — handover log

Newest entry first. Each run: what was done, test evidence, blockers, next action. No secrets or personal data here.

## Current snapshot

**1 November verification:** PR #2's portability repair and PR #1's complete 0.9.0 feature set are merged into `root` at `bc0e644a370672736559343ac2541e6ca663500f`. The integrated file tree was checked against the tested feature head. All seven CI jobs passed on that head: Ubuntu Python 3.10–3.13, macOS/Windows Python 3.13, and lint. Local ResourceWarning-strict suite: 234 tests; fresh installed wheel: 24 self-test checks. This is a release candidate, not a phone-tested or published release.

| Milestone | Status |
| --- | --- |
| M0 Foundations | **COMPLETE** (2026-10-25, run 12) — CI live at `.github/workflows/ci.yml`; secret scanning / branch rules are owner settings |
| M1 Upstream audit | **COMPLETE** (2026-10-17) |
| M2 Minimal MCP server | **COMPLETE** (2026-10-17, run 3) — `image_inspect` over stdio; output-path item moved to M3 |
| M3 Core operations | **COMPLETE** (2026-10-17, run 7) — convert + output policy (run 4), resize (run 5), compress (run 6), rotate/flip + crop (run 7) |
| M4 Batch | **COMPLETE** (2026-10-17, run 9; resume + retries run 12) |
| M7 Client interoperability | ACTIVE — research, ADR-0003, protocol test, config samples done; real-client evidence = owner's phone (VERIFY) |
| M6 Threat model | **COMPLETE for local stdio mode** — R1 closed on POSIX, R2 available via `--isolate` (run 12); remote mode needs a new section |
| M9 Release prep | Agent side **COMPLETE** (run 12: SBOM, dependency review, CI); publishing the release = owner |
| M5 Android bridge | **CLOSED by decision** (ADR-0006): ship the independent backend |
| M8 Docs | **COMPLETE** except phone screenshots (need the phone) |
| M10 Advanced | **COMPLETE** (run 12, ADR-0005) |

**Stack:** Python ≥ 3.10, Pillow, official MCP Python SDK (stdio), `unittest`, `ruff`. See `docs/adr/0001-processing-backend.md`.

**Run:** `imagetoolbox-mcp --root DIR [--out DIR] [--isolate S] [--max-megapixels MP] [--log-format json]`. Tools: `image_inspect`, `image_convert`, `image_resize`, `image_compress`, `image_rotate_flip`, `image_crop`, `image_adjust`, `image_watermark`, `image_recipe`, `image_tag`, `image_batch`. Version 0.9.0. Install check: `imagetoolbox-mcp --self-test`. Inputs: JPEG/MPO, PNG, WebP, GIF, TIFF, BMP only.

**How to test:** `PYTHONPATH=src python3 -m unittest discover -s tests -t .` (or `pip install -e .` first) and `ruff check src tests && ruff format --check src tests`.

**Sandbox packaging note:** the sandbox's Debian setuptools 68.1.2 is broken on Python 3.13 (`AttributeError: install_layout`) and is too old for SPDX `license = "MIT"`. Workaround: in a venv, `pip install /usr/lib/python3.11/ensurepip/_bundled/setuptools-79.0.1-py3-none-any.whl`, then `pip install --no-build-isolation --no-deps .`. Normal machines (CI, Termux) fetch setuptools ≥ 77 from PyPI automatically.

## Open blockers / VERIFY items

1. **Historical environment restriction, superseded for the 1 November worker:** dependency installation succeeded in an isolated Python 3.12.14 environment with Pillow 13.0.0, MCP 2.3.0 and Pydantic 2.14.2. The old no-PyPI limitation remains a historical run-log fact, not a current blocker for this worker.
2. ~~`git push` denied~~ — resolved 2026-10-25: the repo is attached to the session and `git push` works.
3. **VERIFY on owner's phone (Termux):** follow `docs/install-termux.md` and run `imagetoolbox-mcp --self-test`. Native deps without Android wheels: `pydantic-core`, `rpds-py` (Rust; may compile 10–30 min), `cryptography` (use Termux `python-cryptography`). Fallback plan in ADR-0001.
4. **CI is live:** `.github/workflows/ci.yml` ran on PR #1. Retrieved evidence showed Linux/macOS and lint passing, but Windows failed (32 failures, 101 errors, 8 skips). The 1 November repair removes a pipe-only API call from regular-file reads and rejects Windows anchored-relative paths. Native CI must pass on the repair head before integration; local Linux results do not certify Windows.
5. **Answered (M7, run 8) → owner VERIFY:** phone path = an agent CLI inside Termux (Claude Code via community installer, or Gemini CLI) launching the stdio server — steps in `docs/clients.md`. Claude Android app needs a public OAuth server (deferred, ADR-0003); ChatGPT MCP connectors are web-only.
6. **Owner setting:** enable Settings → Code security → Secret scanning + Push protection, and Private vulnerability reporting (SECURITY.md points to it). Optional: branch protection on `root` requiring CI.

## Run log

### 2026-11-01 — portability repair and evidence reconciliation (Marla)

**Final checkpoint:** native matrix passed and both PRs were merged. The initial repair removed every Windows decode/path failure; the follow-up fixed 31 fixture-cleanup errors by closing images before deleting their temporary directories. Evidence and remaining blockers are recorded in the maintenance validation document below. No Windows job or assertion was disabled. Highest-value next action: owner runs the Termux self-test and two real agent-client checks, then decides release publication.

**Objective:** turn the existing 0.9.0 feature PR into a verifiable local image tool without losing its work or weakening the sandbox. Base: PR #1 head `322405bcefc5d6acfcf24ea3f56ef53e1e2ed80c`.

**Research first:** inspected the exact PR, all 76 source files, TODO/roadmap, threat model and Windows CI log. Python documents `os.set_blocking` as pipe-only on Windows and treats rooted-relative/drive-relative paths as anchored but not absolute. Sources and implementation decisions: [maintenance validation](audit/maintenance-validation-2026-11-01.md).

**Implemented:** remove the unnecessary regular-file blocking-mode change; reject anchored-relative Windows paths lexically; reject `..` before normalizing absolute inputs. Decoder allowlist, file-descriptor checks, FIFO refusal and POSIX confined `openat` remain intact. Added a simulated unsupported-blocking regression and Windows lexical-path regression, and expanded the absolute traversal test. All three checks failed on the original code and pass after repair.

**Verified locally:** baseline 232 tests passed on Linux; repaired full suite 234 tests passed, including real stdio MCP and isolation tests. All 24 self-test checks passed. Ruff lint and formatting passed. Native Windows/macOS repair-head CI, installed-wheel validation and phone testing remain separate gates; record their actual outcomes before declaring completion.

**Next:** publish the repair on its own branch into the existing feature branch; inspect native matrix checks, then integrate only exact passing heads. Phone/real-client verification and release publication remain owner steps. No tag, package or release published by this repair.

### 2026-10-25 — run 12 (Claude, owner request: "finish the roadmap")

**Done (v0.9.0)**
- M10: `edit.py` with `image_adjust`, `image_watermark`, `image_recipe`, `image_tag`; batch ops `adjust`/`watermark`. ADR-0005 (OCR/PDF/HEIC declined for now, AVIF waits for a Termux codec check, no GUI).
- M4 leftovers: `resume_from` + `retries` in `image_batch`.
- M6 R2: `isolation.py`, `--isolate SECONDS` (spawned child, hard timeout, crash → `decode_failed`). R1: confined `openat` walk from the root (`Limits.confine_to`, `engine._open_confined`). R3: `--max-megapixels`.
- M2 logging: `--log-format json`. M9: `sbom.py` / `--sbom`, `docs/dependencies.md`, release notes `docs/releases/v0.9.0.md`.
- M0: CI moved to `.github/workflows/ci.yml`; `docs/development.md`. M7: `docs/config-samples.md`. M8: `docs/examples.md`, `docs/errors.md`. M5: ADR-0006.

**Tests:** 232 OK (was 195). `ruff check` / `ruff format --check` clean. Wheel installed in a fresh venv: `imagetoolbox-mcp --self-test` → `SELF-TEST PASSED: 24 checks`; `--sbom` → 26 components.

**Next action:** owner phone check (TODO.md "Needs you"), then 1.0.0.


### 2026-10-20 — run 11 (Claude, scheduled)

**Done (M9 release prep, v0.8.0)**
- Oriented at 01:43 UTC: last commits 01:10 UTC (run 10, same agent); no other agent activity, no clash. Blockers 2 and 4 unchanged (`git push` denied, `ci/ci.yml` not moved) → committing via the connector. No phone results from the owner yet. Sandbox MCP SDK is now 2.3.0.
- `src/imagetoolbox_mcp/selftest.py` + `imagetoolbox-mcp --self-test` (no `--root` needed): versions, codecs (JPEG/zlib required, WebP optional → WARN), all 7 tools via an in-process MCP client on two generated images (EXIF-rotated JPEG, RGBA PNG) in a temp folder, sandbox refusal, real stdio child process, originals byte-identical, PASS/WARN/FAIL lines, exit 0/1, no absolute paths. ~2 s in the cloud.
- `docs/install-termux.md` (F-Droid Termux, `pkg install python git python-pillow python-cryptography`, Rust/binutils fallback for `pydantic-core`/`rpds-py`, self-test with expected output, troubleshooting table, update/uninstall). Status VERIFY. Found while writing: the MCP SDK pulls in `jsonschema` → `rpds-py` (Rust) and `pyjwt[crypto]` → `cryptography` (Rust) even for stdio-only use — candidates for a lighter install next run.
- `docs/release-checklist.md` (agent vs owner steps; the connector cannot create tags/releases) and draft `docs/releases/v0.8.0.md`. README, `docs/clients.md`, CHANGELOG 0.8.0, roadmap M8/M9 annotated (partly, not ticked) and §11 items 12–14.
- Decision: release as **0.8.0** (new feature → minor) rather than 0.7.x.
- Commits via the connector: `0309f44` (code+tests), `9c977ca` + `a783355` (docs), then roadmap/state; after each, `git fetch` + `cmp` showed the pushed files byte-identical to the tested tree.

**Tests:** 195 OK (was 189) with `-W error::ResourceWarning`; new `tests/unit/test_selftest.py` (full pass incl. stdio child, no paths printed, missing WebP = warning, missing JPEG = fail, a failing tool = exit 1 while other checks still run, CLI flag needs no root). Wheel installed in a fresh venv: `imagetoolbox-mcp --self-test` from outside the repo → `SELF-TEST PASSED: 20 checks`. `ruff check`/`format --check` clean. GitHub CI still not run (blocker 4). Phone: VERIFY.

**Next action (run 12):** M9 dependency licence + vulnerability review: `docs/dependencies.md`, stdlib-only CycloneDX SBOM generator + test, and check whether HTTP-only deps can be avoided for a lighter Termux install. If the owner has sent self-test output, record it first and fix the guide.

### 2026-10-20 — run 10 (Claude, scheduled)

**Done (M6 — threat model + hardening, v0.7.0)**
- Oriented at 00:43 UTC: last commit 2026-10-17 19:03 UTC (run 9, same agent); no other agent activity, no clash. `ci/ci.yml` still not moved (blocker 4); `git push` still denied (blocker 2) → committed via the connector. No phone results from the owner yet.
- Fuzzed the engine first (scratch harness, 7 formats × 300 mutants × inspect/convert, seeds 1–3): **9 crash classes escaped** as non-`EngineError` exceptions — GIF `IndexError`, PNG `SyntaxError`, ICO `ValueError`, and `OSError` from `image_inspect` (it had no `OSError` handler) for BMP/JPEG/PNG/WebP/ICO. No host path leaked in any `EngineError`. The SDK hides the text of unexpected exceptions from the client but logs the full traceback (message may contain a path).
- Fixes: `engine._open` (decoder allowlist JPEG/PNG/WebP/GIF/TIFF/BMP via `Image.open(formats=...)`; `O_NOFOLLOW|O_NONBLOCK` open + `fstat` re-check on the descriptor) and `engine._decode_error` (parser exceptions → `decode_failed`, `MemoryError` → `out_of_memory`, bombs → `too_many_pixels`), used by inspect and every write tool. `server._guard`/`_tool`: every tool registered through a catch-all → fixed `[internal_error]`, logged as type only. `Limits.max_search_seconds` = 30 s for compress `max_bytes` searches (warning `time_budget_reached`).
- Gotcha found: `"MPO"` is not a valid `formats=` entry (KeyError inside Pillow, which my new mapping then turned into `decode_failed` for *every* file — caught by the existing 169 tests). MPO files still open through the JPEG opener; test added.
- Measured on a 64 MP noise JPEG (cloud): inspect 0.0 s, convert→PNG 25 s, resize 1.8 s, JPEG `max_bytes` 4.8 s, PNG `max_bytes` > 120 s before the budget → 37 s after.
- Commit slip: the first connector commit (`1387cc9`) accidentally replaced `src/imagetoolbox_mcp/__init__.py` with a placeholder; fixed in the very next commit (`9d27fb4`). After pushing, `git fetch` + `git diff origin/root` showed `src/` and `tests/` identical to the tested tree.
- `docs/threat-model.md`: boundaries, assets, T1–T12 → control → test, residual risks R1 (directory-component race), R2 (no hard per-call timeout / parser isolation), R3 memory on phones, R4 no output quota, R5 C-level parser bugs; rules for future changes. SECURITY.md: allowlist, link, data retention + temp-file cleanup. README input-format line. Roadmap M6 ticked item by item (timeouts/isolation item left open as "partly"). Version 0.7.0, CHANGELOG.

**Tests:** 189 OK (was 169), three consecutive full runs with `-W error::ResourceWarning`; same 189 pass against the wheel installed in a venv (`imagetoolbox-mcp --version` → 0.7.0). New: `tests/unit/test_malformed_inputs.py` (fuzz 6 formats × 40 × 3 ops, allowlist, EPS-no-Ghostscript, MPO, bombs, exception mapping), `test_engine_open_race.py`, `test_engine_budget.py`, `tests/integration/test_guard.py`. Extra hand-run fuzz after the fix: seeds 1–5 × 300 mutants × 7 formats × 2 ops → zero escapes, zero leaks. `ruff check`/`format --check` clean. GitHub CI still not run (blocker 4).

**Next action (run 11):** M9 release prep — `docs/install-termux.md` (exact Termux commands, expected output, troubleshooting incl. pydantic-core build), a one-command install self-check for the phone (e.g. `imagetoolbox-mcp --self-test` that creates a temp image and runs inspect/convert in-process), release checklist, draft GitHub release notes for 0.7.x for the owner to publish. If the owner has reported Path A phone results, record them in M7 first.

### 2026-10-17 — run 9 (Claude, scheduled)

**Done (M4 — `image_batch`)**
- Oriented at 18:43 UTC: last commit 14:54 UTC (run 8, same agent); no other agent activity, no clash. `ci/ci.yml` still not moved (blocker 4). Owner has not reported phone results yet (M7 VERIFY).
- `InputRoot.resolve_dir` (sandbox walk shared with `resolve`; `"."`/`""` = root; new code `not_a_folder`). All 145 earlier tests passed unchanged after the refactor.
- `src/imagetoolbox_mcp/batch.py` (SDK-independent): per-operation pydantic option models (`extra="forbid"`, cross-field rules mirrored from the engine, `output_name` refused); `select_files` (one folder, no recursion, sorted, hidden ignored, symlinks/non-files/oversized skipped and reported, case-insensitive name glob or default image extensions, output folder refused, `max_files` ≤ 200 and 1 GiB total refuse instead of truncate, 10 000-entry scan cap); `run_one`; `write_batch_manifest`.
- MCP tool `image_batch` (async): files processed one at a time in a worker thread; per-file `ok`/`failed`/`not_run`; `invalid_argument` stops the batch (whole-call error if nothing written yet); unexpected exceptions → `internal_error` for that file only; `dry_run`; MCP progress after each file; on cancel the in-flight file finishes, no new ones start, and a `cancelled` manifest is written (shielded). Manifest `batch-<op>-<UTC>.json` with full options, SHA-256 of sources and outputs, failures; checksums kept out of the tool result to save model context.
- Decision: `options` is a free-form object in the schema (validated server-side) rather than a `oneOf` union, because Gemini-style clients handle unions poorly. Recorded in ADR-0004.
- Found while testing: a corrupt `.jpg` reports `unsupported_format` (Pillow cannot identify it), not `decode_failed` — consistent with the single tools, left as is.
- Version 0.6.0; README tool table, CHANGELOG, pyproject description; roadmap M4 ticked (4 of 5; progress/cancel done, retries/resume deferred), next action = M6.

**Tests:** 169 OK (was 145), three consecutive full runs with `-W error::ResourceWarning`: +2 sandbox folder tests, +14 batch unit tests, +8 MCP batch tests (mixed-format folder with manifest-checksum and originals-unchanged checks, dry run writes nothing, repeat run gets `-1` names, per-file failure continues, 7 refusal cases write nothing, empty match, cancellation after 2 of 6 files). Stdio subprocess test lists 7 tools and runs a batch; protocol test expects 7 tools. Same 169 pass against the wheel installed in a venv (`imagetoolbox-mcp --version` → 0.6.0). `ruff check`/`ruff format --check` clean. GitHub CI still not run (blocker 4). Cancellation over a real stdio client: VERIFY.

**Next action (run 10):** M6 threat model — `docs/threat-model.md` mapping each threat (path traversal, symlink swap races, decompression bombs, malformed/truncated files per format, metadata leakage, resource exhaustion incl. batch, prompt-injected arguments, log leakage) to its control and test; add malformed-file fuzz tests for JPEG/PNG/WebP/GIF/TIFF/BMP; close gaps found (consider a per-call wall-clock budget and `Image.MAX_IMAGE_PIXELS` alignment). If the owner has reported Path A phone results, record them in M7 first.

### 2026-10-17 — run 8 (Claude, scheduled)

**Done (M7 research — phone clients)**
- Oriented at 14:43 UTC: last commit 13:57 UTC (run 7, same agent, ~46 min); no other agent activity, no clash. `ci/ci.yml` still not moved (blocker 4).
- Researched current product support with sources (Anthropic and OpenAI help pages, claude-code-android README, Termux guides) → `docs/clients.md`. Findings: Claude Android app uses only remote connectors added on claude.ai first (Streamable HTTP/SSE, authless or OAuth, called from Anthropic's cloud); ChatGPT full MCP connectors are web-only (Pro read/fetch-only); Claude Code runs in Termux via a community installer and reports stdio MCP works; Gemini CLI runs in Termux via npm with a build workaround.
- `docs/adr/0003-transports-and-phone-clients.md`: stdio stays the only shipped transport; recommended phone path = agent CLI in Termux; Claude-app remote path deferred until OAuth 2.1 + M6 threat model; authless remote never shipped; ChatGPT not targeted until mobile support.
- Spike (not committed): the unchanged server ran over SDK Streamable HTTP on 127.0.0.1; an SDK client listed 6 tools and called `image_inspect`; a foreign `Host` header got HTTP 421 (DNS-rebinding protection on by default). A tunnel would need its hostname allowlisted.
- `tests/integration/test_protocol.py`: raw JSON-RPC over a real stdio subprocess; versions 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25 echoed; unknown version → 2025-11-25. The SDK's `LATEST_PROTOCOL_VERSION` is `2026-07-28`, but a stdio `initialize` with it is answered with 2025-11-25 (newer revision apparently not negotiated via classic initialize in SDK 2.2.0) — noted, not a problem.
- Found while writing the test: if a client closes stdin right after sending requests, the server shuts down and may drop a queued request (flaky first version of the test). Real clients keep stdin open; test now waits for each reply. Not treated as a bug.
- Roadmap: M7 item 1 ticked; items 3–4 annotated (evaluated/checked, not done); next actions 8–11 rewritten (owner phone check, then M4 batch, then M6 before any HTTP). README links `docs/clients.md`; CHANGELOG Unreleased.

**Tests:** 145 OK (was 143), three consecutive full runs with `-W error::ResourceWarning`. `ruff check`/`ruff format --check` clean. No phone test possible from the cloud (VERIFY). GitHub CI still not run (blocker 4).

**Next action (run 9):** M4 `image_batch`: apply one existing operation (convert/resize/compress/rotate_flip/crop) to every image matching a relative folder + optional glob inside the root; limits (max files, e.g. 200; total pixel budget), per-file result list, partial failures reported not aborted, never overwrite, no recursion outside root/symlinks; progress notifications if the SDK supports them cheaply. Golden + MCP tests. If the owner has reported Path A results, record them in M7 first.

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
