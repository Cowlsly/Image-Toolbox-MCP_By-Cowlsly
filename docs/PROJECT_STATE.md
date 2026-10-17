# Project state — handover log

Newest entry first. Each run: what was done, test evidence, blockers, next action. No secrets or personal data here.

## Current snapshot

| Milestone | Status |
| --- | --- |
| M0 Foundations | ACTIVE — runtime, packaging, CI workflow, community files done; CI activation BLOCKED (owner must move `ci/ci.yml`); branch rules, secret scanning: owner settings |
| M1 Upstream audit | **COMPLETE** (2026-10-17) |
| M2 Minimal MCP server | PENDING — next |
| M3–M10 | PENDING |

**Stack:** Python ≥ 3.10, Pillow, official MCP Python SDK (stdio), `unittest`, `ruff`. See `docs/adr/0001-processing-backend.md`.

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