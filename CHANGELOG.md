# Changelog

All notable changes are listed here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `pyproject.toml` packaging (setuptools ≥ 77, Python ≥ 3.10, deps `pillow`, `mcp>=2,<3`) and `imagetoolbox-mcp` console script (`--version` only for now).
- GitHub Actions CI workflow (staged at `ci/ci.yml` until moved to `.github/workflows/`): ruff lint/format and unit tests on Python 3.10–3.13 (Ubuntu) plus 3.13 on Windows and macOS; actions pinned by commit SHA.
- Dependabot for pip and GitHub Actions.
- CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, issue and PR templates.
- Upstream licence/feasibility audit, ADR-0001 (Python + Pillow + MCP SDK), read-only `inspect_image()` engine spike.
