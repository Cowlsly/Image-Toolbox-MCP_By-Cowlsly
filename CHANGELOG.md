# Changelog

All notable changes are listed here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
