# Release checklist

Releases are `0.x` alphas until the gates in [roadmap.md](../roadmap.md) §4 M9 pass. Version lives only in `src/imagetoolbox_mcp/__init__.py` (`__version__`); `pyproject.toml` reads it.

Who does what: the agent prepares everything up to "Owner" steps. Since 2026-10-25 the agent can `git push` (including tags); publishing the GitHub release (and deciding *when* a 0.x becomes 1.0) stays with the owner, because it needs the phone self-test first.

## 1. Before tagging (agent)

- [ ] `CHANGELOG.md`: move "Unreleased" items under `## [X.Y.Z] - YYYY-MM-DD`.
- [ ] `__version__` bumped (SemVer: new tool or option = minor; fix only = patch; any breaking tool-schema change = minor while 0.x, and listed under **Breaking**).
- [ ] Full suite: `PYTHONPATH=src python3 -W error::ResourceWarning -m unittest discover -s tests -t .` — all OK.
- [ ] `ruff check src tests && ruff format --check src tests` — clean.
- [ ] Build + install the wheel in a fresh venv and run `imagetoolbox-mcp --self-test` from outside the repo — `SELF-TEST PASSED`.
- [ ] Tool list unchanged or documented: README tool table, `selftest.EXPECTED_TOOLS`, `test_server.py`.
- [ ] Security: `docs/threat-model.md` updated for any new input, output or transport; no new tool touches files outside `--root` / `--out`; no secrets in the diff.
- [ ] Attribution: README and `__init__.py` still credit T8RIN / Image Toolbox (Apache-2.0); no upstream code copied (if any is, add NOTICE + Apache-2.0 header per `docs/audit/upstream-audit.md` §1).
- [ ] Dependencies: lower bounds in `pyproject.toml` still match what was tested (versions in `docs/PROJECT_STATE.md`); Dependabot alerts reviewed.
- [ ] Draft release notes written in `docs/releases/vX.Y.Z.md`.

## 2. Owner steps (phone, github.com)

1. Releases → **Draft a new release** → "Choose a tag" → type `vX.Y.Z` → "Create new tag on publish", target `root`.
2. Title `vX.Y.Z`; paste the body of `docs/releases/vX.Y.Z.md`.
3. Tick **Set as a pre-release** while the version is 0.x.
4. Publish.

## 3. After the release

- [ ] On the phone: `pip install --upgrade --force-reinstall --no-deps "git+https://github.com/Cowlsly/Image-Toolbox-MCP_By-Cowlsly@vX.Y.Z"` then `imagetoolbox-mcp --self-test`; paste the output into `docs/PROJECT_STATE.md` (agent can do the pasting if the owner sends it).
- [ ] Record the release in `docs/PROJECT_STATE.md` and tick roadmap items only with evidence.

## Not done yet (tracked in roadmap M9)

- Signed tags, SBOM, reproducible artifacts, PyPI publishing — need CI first (`ci/ci.yml` must be moved to `.github/workflows/` by the owner).
- CI matrix (Linux/macOS/Windows × Python 3.10–3.13) — defined in `ci/ci.yml`, never run.
