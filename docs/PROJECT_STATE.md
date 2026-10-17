# Project state — handover log

Newest entry first. Each run: what was done, test evidence, blockers, next action. No secrets or personal data here.

## Current snapshot

| Milestone | Status |
| --- | --- |
| M0 Foundations | ACTIVE — runtime, packaging, CI workflow, community files done; CI activation BLOCKED (owner must move `ci/ci.yml`); branch rules, secret scanning: owner settings |
| M1 Upstream audit | **COMPLETE** (2026-10-17) |
| M2 Minimal MCP server | **COMPLETE** (2026-10-17, run 3) — `image_inspect` over stdio; output-path item moved to M3 |
| M3 Core operations | NEXT — `image_convert` first |
| M4–M10 | PENDING |

**Stack:** Python ≥ 3.10, Pillow, official MCP Python SDK (stdio), `unittest`, `ruff`. See `docs/adr/0001-processing-backend.md`.

**Run:** `imagetoolbox-mcp --root DIR` (or `IMAGETOOLBOX_MCP_ROOT=DIR`). Tool: `image_inspect`.

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
