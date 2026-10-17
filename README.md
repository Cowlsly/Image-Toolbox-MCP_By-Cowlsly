# Image-Toolbox-MCP_By-Cowlsly

An open-source Model Context Protocol (MCP) integration for Image Toolbox, enabling AI assistants to access image conversion, editing, compression, metadata, and batch-processing workflows. Developed by Cowlsly as an independent integration with attribution to the original project.

> **Status: early development.** A minimal MCP server works with one read-only tool, `image_inspect`. See [roadmap.md](roadmap.md) and [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md).

## Attribution

[Image Toolbox](https://github.com/T8RIN/ImageToolbox) is an Android image editor by **T8RIN (Malik Mukhametzyanov)**, licensed under Apache-2.0. This project is independent and is not affiliated with or endorsed by the Image Toolbox authors. It currently contains **no** Image Toolbox source code; image processing is done by its own Python engine built on [Pillow](https://python-pillow.org/). See [docs/audit/upstream-audit.md](docs/audit/upstream-audit.md).

## How it works

Python 3.10+ server, Pillow image engine, official MCP Python SDK over stdio. Rationale: [ADR-0001](docs/adr/0001-processing-backend.md).

You choose **one input folder**; the server can only read images inside it. Paths with `..`, symbolic links, and absolute paths outside the folder are refused. Originals are never modified. There are no shell, network or general file tools.

| Tool | What it does |
| --- | --- |
| `image_inspect` | Format, width/height, colour mode, alpha, frames, file size, orientation, a safe EXIF subset. GPS is never returned — only whether it is present. |

Run it (an MCP client normally launches this for you):

```sh
imagetoolbox-mcp --root ~/Pictures        # or: IMAGETOOLBOX_MCP_ROOT=~/Pictures imagetoolbox-mcp
```

Example client config (`mcpServers` style, used by many desktop clients):

```json
{ "mcpServers": { "imagetoolbox": { "command": "imagetoolbox-mcp", "args": ["--root", "/path/to/images"] } } }
```

## Install and test (developers)

```sh
python -m pip install -e .                    # Python 3.10+; pulls in pillow and mcp
python -m unittest discover -s tests -t .
imagetoolbox-mcp --version
```

Lint: `ruff check src tests && ruff format --check src tests`.

Termux (Android): `pkg install python python-pillow`, then `pip install mcp` — still being verified, see [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md). More in [CONTRIBUTING.md](CONTRIBUTING.md); security reports: [SECURITY.md](SECURITY.md).

## Licence

MIT. See [LICENSE](LICENSE).
