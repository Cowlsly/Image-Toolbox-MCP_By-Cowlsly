# Local development

## Supported platforms

| Platform | Python | Status |
| --- | --- | --- |
| Linux (x86-64, arm64) | 3.10–3.13 | Tested in CI (`ubuntu-latest`, all four versions) and in the build workspace (3.13). |
| macOS | 3.13 | CI (`macos-latest`). |
| Windows | 3.13 | CI (`windows-latest`). `--isolate` uses `spawn`, which Windows supports. |
| Android (Termux, arm64) | Termux's current Python | Supported target; install steps in [install-termux.md](install-termux.md). Phone run still VERIFY. |

Pillow ≥ 10 and the MCP Python SDK 2.x are the only runtime dependencies ([dependencies.md](dependencies.md)).

## Set up

```sh
git clone https://github.com/Cowlsly/Image-Toolbox-MCP_By-Cowlsly
cd Image-Toolbox-MCP_By-Cowlsly
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
python -m pip install -e .
python -m pip install "ruff==0.16.8"
```

## Everyday commands

```sh
python -m unittest discover -s tests -t .        # whole suite (~20 s)
python -m unittest tests.unit.test_edit          # one module
ruff check src tests && ruff format --check src tests
imagetoolbox-mcp --self-test                     # end-to-end check of an install
imagetoolbox-mcp --root ./sample --log-level DEBUG --log-format json
imagetoolbox-mcp --sbom > sbom.json
```

Without installing: prefix commands with `PYTHONPATH=src`.

## Layout

- `src/imagetoolbox_mcp/engine.py` — core image operations (no MCP imports).
- `src/imagetoolbox_mcp/edit.py` — adjust, watermark, recipe, tag (M10).
- `src/imagetoolbox_mcp/batch.py` — batch option models, file selection, manifests, resume.
- `src/imagetoolbox_mcp/isolation.py` — optional child-process execution with a hard timeout.
- `src/imagetoolbox_mcp/server.py` — MCP tool definitions; every tool goes through `_guard`.
- `src/imagetoolbox_mcp/sandbox.py`, `output.py` — input root and never-overwrite output folder.
- `tests/unit`, `tests/integration` — `unittest` only, no network.

## Rules for changes

Read [threat-model.md](threat-model.md) §5 first. In short: no tool may read outside `--root` or write outside `--out`; never overwrite; strip metadata unless the tool exists to write chosen metadata (`image_tag`); errors are `[code] message` with no host paths; add tests with every change.
