# Changelog

All notable changes are listed here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.9.0] - 2026-10-25

### Added
- M10 tools: `image_adjust`, `image_watermark`, `image_recipe` (reproducible multi-step, one encode) and `image_tag` (controlled description/artist/copyright metadata). `adjust` and `watermark` are also `image_batch` operations. ADR-0005.
- `image_batch`: `resume_from` (skip files an earlier manifest finished, same options, unchanged source) and `retries` (0–3 for temporary failures); new item status `resumed` and result field `resumed`.
- `--isolate SECONDS` / `IMAGETOOLBOX_MCP_ISOLATE`: every engine call in a spawned child process with a hard timeout (`[timed_out]`); a decoder crash becomes `[decode_failed]`.
- `--max-megapixels MP`, `--log-format json` (one JSON object per line on stderr) and `--sbom` (CycloneDX 1.5 JSON from installed metadata, no network).
- Docs: `docs/development.md`, `docs/dependencies.md` (licence + native-build review), `docs/examples.md` (incl. local vs remote), `docs/config-samples.md`, `docs/errors.md`, ADR-0005 (advanced features, OCR/PDF/HEIC/AVIF decisions), ADR-0006 (Android bridge: ship the independent backend).
- CI workflow moved to `.github/workflows/ci.yml` (was staged at `ci/ci.yml`).
- 37 new tests (232 total).

### Changed
- Input files are opened with a confined `openat` walk from the input root (threat model R1 closed on POSIX).
- Tool count 7 → 11; self-test exercises all 11.

## [0.8.0] - 2026-10-20

### Added
- `imagetoolbox-mcp --self-test` (M9): checks Python/Pillow/MCP SDK versions and codecs (JPEG, zlib required; WebP optional → warning), runs all 7 tools through an in-process MCP client on generated images in a temporary folder, launches the real stdio server as a child process, checks originals are byte-identical, and prints one PASS/WARN/FAIL line per check (no absolute paths). Exit 0 = usable. Needs no `--root`.
- `docs/install-termux.md`: phone install guide (F-Droid Termux, prebuilt `python-pillow`/`python-cryptography`, Rust build fallback for `pydantic-core`/`rpds-py`, self-test, troubleshooting table). VERIFY on a real phone.
- `docs/release-checklist.md` and draft release notes `docs/releases/v0.8.0.md`.
- 6 new tests (195 total) in `tests/unit/test_selftest.py`.

### Changed
- `docs/clients.md`: Termux step also installs `python-cryptography`, runs `--self-test` and links the install guide; Gemini tool count corrected to 7.

## [0.7.0] - 2026-10-20

### Added
- `docs/threat-model.md` (M6): trust boundaries, assets, threats T1–T12 each mapped to its control and test, residual risks R1–R5, rules for future changes.
- 20 new tests (189 total): deterministic mutation fuzzing of JPEG/PNG/WebP/GIF/TIFF/BMP (truncation, byte flips, length-field corruption, deleted slices) through inspect/convert/resize; header-only decompression bombs; decoder allowlist incl. an EPS that must not start Ghostscript; multi-picture (MPO) phone JPEGs; parser-exception mapping; swap-after-check races (symlink, FIFO, grown file); tool catch-all for sync, write and async tools (result and log free of paths); compress time budget.

### Changed
- **Input formats are now an allowlist:** JPEG (incl. MPO), PNG, WebP, GIF, TIFF, BMP. Other formats Pillow could open (ICO, PCX, PPM, TGA, PSD, EPS, ...) are refused with `[unsupported_format]`.
- Malformed files always give `[decode_failed]` (or `[out_of_memory]`/`[too_many_pixels]`); before, fuzzing found 9 crash classes (e.g. GIF `IndexError`, PNG `SyntaxError`, `OSError` from `image_inspect`) that surfaced as an unexplained "Error executing tool".
- Input files are opened with `O_NOFOLLOW`/`O_NONBLOCK` and re-checked with `fstat` on the open descriptor; Pillow reads the descriptor, not the path.
- Any unexpected exception in a tool returns a fixed `[internal_error]` message and is logged as its type only (no traceback text that could contain paths).
- `image_compress` `max_bytes` search stops after 30 s (`Limits.max_search_seconds`) and keeps the best result with warning `time_budget_reached` (a 64 MP PNG search went from > 120 s to 37 s in the cloud test).

## [0.6.0] - 2026-10-17

### Added
- `image_batch` tool (M4): one operation (`convert`/`resize`/`compress`/`rotate_flip`/`crop`) over every image directly inside a folder, with optional case-insensitive name `pattern`; options validated once up front (unknown keys refused); sequential processing; per-file `ok`/`failed`/`not_run` results; partial failures never abort (argument errors stop the batch); `dry_run`; `max_files` (default 50, hard cap 200) and a 1 GiB total-input budget that refuse instead of truncating; JSON manifest with SHA-256 checksums in the output folder; MCP progress after each file; cancellation keeps finished files and writes a `cancelled` manifest. ADR-0004.
- `InputRoot.resolve_dir` (same sandbox rules for folders; new code `not_a_folder`).
- 24 new tests (169 total): option validation, file selection (symlink/hidden/oversized/no recursion/limits), each operation's default naming, mixed-format folder (EXIF-rotated JPEG with GPS, RGBA PNG, WebP, animated GIF, corrupt JPEG, text file, symlink) with manifest checksum checks, dry run, never-overwrite on repeat, refusals that write nothing, cancellation; stdio test lists 7 tools and runs a batch.
- `docs/clients.md`: which MCP clients can reach the server from an Android phone (Claude Code / Gemini CLI in Termux over stdio; Claude app needs a remote OAuth server; ChatGPT MCP is web-only), with sources and Termux setup steps (unverified on a phone).
- ADR-0003: stdio stays the only transport for now; remote HTTP deferred until OAuth and the threat model.
- `tests/integration/test_protocol.py`: protocol-version negotiation over real stdio (2 tests, 145 total).

## [0.5.0] - 2026-10-17

### Added
- `image_rotate_flip` tool: `rotate` 0/90/180/270 degrees clockwise and/or `flip` `horizontal`/`vertical` (rotation first), exact pixel moves on the upright image; all modes kept (palette + transparency, 16-bit, alpha). Result adds `rotate`, `flip`, `source_width/height`. Default name `<source>-rot90-flipH`.
- `image_crop` tool: explicit box (`width`/`height` + `left`/`top` default 0) or `aspect` `"W:H"` for the largest centred box; out-of-bounds boxes refused with `[crop_out_of_bounds]` naming the real upright size; `crop_full_image` warning when nothing is removed. Result adds `crop_left`, `crop_top`, `source_width/height`. Default name `<source>-crop-<W>x<H>`.
- `lossy_reencode` warning for rotate/flip and crop when the output is JPEG or lossy WebP.
- 30 new tests (143 total): golden pixel-mapping tests against reference transposes, rotate-then-flip order, EXIF-oriented sources, mode preservation, crop geometry incl. an aspect sweep, error cases with nothing written, MCP-level tests; stdio test lists and calls 6 tools.

### Changed
- `_pick_target` helper shared by resize, compress, rotate/flip and crop (behaviour unchanged).

## [0.4.0] - 2026-10-17

### Added
- `image_compress` tool: JPEG/WebP by `quality` (default 80) or `max_bytes` (binary search for the highest quality in `[min_quality, 95]` that fits; `min_quality` default 10); PNG lossless optimisation, optional `colors` palette reduction (alpha kept), and `max_bytes` walking a 256→2 colour ladder (not a binary search: PNG size is not monotonic in palette size). Result adds `quality_used`, `colors_used`, `max_bytes`, `target_met`, `saved_bytes`. Warnings: `target_not_met`, `larger_than_source`, `palette_reduced`, `quality_ignored`, `colors_ignored`, `format_changed`.
- 20 new tests (113 total): golden compress tests (quality ordering, highest-fitting quality, WebP target, unreachable target, PNG pixel-exact lossless, palette alpha, ladder choice, metadata/orientation, never-overwrite, argument errors) and MCP-level compress tests; stdio test lists and calls 4 tools.

### Changed
- Engine encode step split into `_encoder_setup` / `_save` / `_result` so compress can encode to memory and search; convert/resize behaviour unchanged (all earlier tests pass unmodified).

## [0.3.0] - 2026-10-17

### Added
- `image_resize` tool: `width`/`height` (1–16384, either or both, measured on the upright image), `fit` = `contain` | `cover` | `exact`, `resample` = `lanczos` | `bicubic` | `bilinear` | `nearest`, `allow_upscale` (default off: `contain` keeps the source size with an `upscale_skipped` warning, `cover`/`exact` return `[upscale_refused]`), optional `format`/`quality`/`output_name`; default name `<source>-<W>x<H>`. Palette and 1-bit images are expanded before filtering; 16-bit greyscale stays 16-bit; alpha is resampled premultiplied (no dark fringes).
- 31 new tests (93 total): resize geometry, golden pixel tests (centre crop, orientation, alpha edges, nearest edges, 16-bit), metadata stripping, MCP-level resize tests.

### Changed
- Engine: the shared "open → check limits → first frame → apply orientation → strip metadata → write new file" pipeline is now `_load_upright` + `_encode_new`, used by both convert and resize. The `frames_dropped` warning now says "used" instead of "converted".

## [0.2.0] - 2026-10-17

### Added
- `image_convert` tool: JPEG/PNG/WebP with quality and WebP-lossless options; EXIF orientation applied; EXIF/XMP/GPS removed; ICC profile kept; JPEG alpha flattened onto white; animated input → first frame; warnings returned for every lossy-looking side effect.
- Output policy (ADR-0002, `output.OutputDir`): one output folder (`--out` / `IMAGETOOLBOX_MCP_OUT`, default `<root>/imagetoolbox-out`), flat validated names, never overwrite (`O_EXCL` claim + numbered suffixes), atomic write via temp file + `os.replace`, symlink-swap refusal, cleanup on failure.
- 30 new tests (62 total): golden pixel/mode/metadata tests, output-policy tests incl. concurrency and planted symlinks, MCP-level convert tests.

## [0.1.0] - 2026-10-17

### Added
- Working MCP server over stdio (`imagetoolbox-mcp --root DIR`, or `IMAGETOOLBOX_MCP_ROOT`).
- `image_inspect` tool: read-only, typed input and output schemas, read-only/non-destructive tool annotations, errors returned as `is_error` results with a stable `[code]` prefix.
- `sandbox.InputRoot`: single allowlisted input folder; rejects `..`, symlinks at any level, absolute paths outside the folder, NUL bytes and over-long paths; error messages never reveal the host folder layout.
- Integration tests with the official MCP client, in-process and over a real stdio subprocess.

### Changed
- `imagetoolbox-mcp` now requires an input folder and starts the server (previously `--version` only).

## [0.0.1] - 2026-10-17

### Added
- `pyproject.toml` packaging (setuptools ≥ 77, Python ≥ 3.10, deps `pillow`, `mcp>=2,<3`) and `imagetoolbox-mcp` console script (`--version` only for now).
- GitHub Actions CI workflow (staged at `ci/ci.yml` until moved to `.github/workflows/`): ruff lint/format and unit tests on Python 3.10–3.13 (Ubuntu) plus 3.13 on Windows and macOS; actions pinned by commit SHA.
- Dependabot for pip and GitHub Actions.
- CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, issue and PR templates.
- Upstream licence/feasibility audit, ADR-0001 (Python + Pillow + MCP SDK), read-only `inspect_image()` engine spike.
