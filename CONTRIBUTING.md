# Contributing

Thanks for helping. This project is small and run from a phone, so keep changes small and easy to review.

## Ground rules

- **Safety first.** Never add MCP tools that expose arbitrary filesystem, shell, process or network access. Tools read only from allowlisted locations and never overwrite originals by default.
- **No secrets or personal data** in code, tests, fixtures, issues or logs. Test images are generated at test time.
- **Attribution.** This project is inspired by [Image Toolbox](https://github.com/T8RIN/ImageToolbox) by T8RIN (Apache-2.0). If you copy or adapt any upstream code, keep its licence header, add a NOTICE entry and say so in the PR. Today the repo contains no upstream code.
- **Engine stays MCP-free.** `src/imagetoolbox_mcp/engine.py` only uses Pillow; MCP wiring lives in separate modules.

## Development

Requires Python 3.10+.

```sh
python -m pip install -e .        # installs pillow + mcp
python -m unittest discover -s tests -t .
ruff check src tests && ruff format --check src tests
```

Without installing: `PYTHONPATH=src python -m unittest discover -s tests -t .`

On Android/Termux: `pkg install python python-pillow`, then `pip install mcp` (see `docs/PROJECT_STATE.md` for current status).

## Workflow

- Default branch is `root`. Small, tested changes may go straight to `root`; larger or risky ones go on a branch with a PR.
- Every behaviour change needs a test. CI (`.github/workflows/ci.yml`; staged at `ci/ci.yml` until activated) runs ruff and the unit tests on Python 3.10–3.13.
- Architecture decisions go in `docs/adr/`. Progress and handover notes go in `docs/PROJECT_STATE.md`.
- Tick a roadmap checkbox only with evidence (a passing test or a commit).
- Update `CHANGELOG.md` under "Unreleased".

## Code of conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
