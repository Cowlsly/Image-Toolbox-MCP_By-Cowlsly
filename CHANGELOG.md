# Changelog

All notable changes are listed here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
