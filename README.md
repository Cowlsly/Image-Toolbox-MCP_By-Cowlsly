# Image-Toolbox-MCP_By-Cowlsly

An open-source Model Context Protocol (MCP) integration for Image Toolbox, enabling AI assistants to access image conversion, editing, compression, metadata, and batch-processing workflows. Developed by Cowlsly as an independent integration with attribution to the original project.

> **Status: early development.** No working MCP server yet. See [roadmap.md](roadmap.md) and [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md).

## Attribution

[Image Toolbox](https://github.com/T8RIN/ImageToolbox) is an Android image editor by **T8RIN (Malik Mukhametzyanov)**, licensed under Apache-2.0. This project is independent and is not affiliated with or endorsed by the Image Toolbox authors. It currently contains **no** Image Toolbox source code; image processing is done by its own Python engine built on [Pillow](https://python-pillow.org/). See [docs/audit/upstream-audit.md](docs/audit/upstream-audit.md).

## How it will work

Python 3.10+ server, Pillow image engine, official MCP Python SDK over stdio. Rationale: [ADR-0001](docs/adr/0001-processing-backend.md).

## Running the tests

```sh
PYTHONPATH=src python -m unittest discover -s tests -t .
```

Needs Python 3.10+ and Pillow (Termux: `pkg install python python-pillow`).

## Licence

MIT. See [LICENSE](LICENSE).
