# Dependencies, licences and supply chain

Status: reviewed 2026-10-25 (run 12). Regenerate the table with `imagetoolbox-mcp --sbom` (CycloneDX 1.5 JSON, built offline from installed package metadata) or the snippet at the end.

## Direct dependencies

| Package | Why | Licence |
| --- | --- | --- |
| Pillow ≥ 10 | All image decoding/encoding (JPEG, PNG, WebP, GIF, TIFF, BMP) | MIT-CMU (HPND) |
| mcp ≥ 2, < 3 | Official MCP Python SDK: stdio server, schemas, client used in tests | MIT |

No other runtime dependency. Tests use only the standard library (`unittest`); lint uses `ruff` (MIT, dev only).

## Full runtime tree (as installed in the build workspace)

| Package | Version (tested) | Licence | Pulled in by |
| --- | --- | --- | --- |
| pillow | 12.3.0 | MIT-CMU | imagetoolbox-mcp |
| mcp | 2.3.0 | MIT | imagetoolbox-mcp |
| anyio | 4.15.1 | MIT | httpx2, mcp, sse-starlette, starlette |
| httpx2 | 2.13.1 | BSD-3-Clause | mcp |
| jsonschema | 4.26.0 | MIT | mcp |
| mcp-types | 2.3.0 | MIT | mcp |
| opentelemetry-api | 1.45.0 | Apache-2.0 | mcp |
| pydantic | 2.13.5 | MIT | mcp, mcp-types |
| PyJWT | 2.15.0 | MIT | mcp |
| python-multipart | 0.0.32 | Apache-2.0 | mcp |
| sse-starlette | 3.4.11 | BSD-3-Clause | mcp |
| starlette | 1.7.0 | BSD-3-Clause | mcp, sse-starlette |
| typing_extensions | 4.16.0 | PSF-2.0 | anyio, mcp, mcp-types, opentelemetry-api, pydantic, pydantic_core, typing-inspection |
| typing-inspection | 0.4.4 | MIT | mcp, pydantic |
| uvicorn | 0.54.0 | BSD-3-Clause | mcp |
| idna | 3.20 | BSD-3-Clause | anyio, httpx2 |
| httpcore2 | 2.13.1 | BSD-3-Clause | httpx2 |
| truststore | 0.10.4 | MIT | httpcore2, httpx2 |
| attrs | 26.1.0 | MIT | jsonschema, referencing |
| jsonschema-specifications | 2025.9.1 | MIT | jsonschema |
| referencing | 0.37.0 | MIT | jsonschema, jsonschema-specifications |
| rpds-py | 2026.6.3 | MIT | jsonschema, referencing |
| annotated-types | 0.8.0 | MIT | pydantic |
| pydantic_core | 2.46.5 | MIT | pydantic |
| click | 8.5.0 | BSD-3-Clause | uvicorn |
| h11 | 0.16.0 | MIT | httpcore2, uvicorn |

All licences are permissive (MIT, BSD-3-Clause, Apache-2.0, PSF-2.0, MIT-CMU). None is copyleft, so shipping this MIT project with them needs only their notices; nothing is vendored into this repository.

## Heavy or native packages (matter on a phone)

| Package | Native code | Termux note |
| --- | --- | --- |
| Pillow | C (libjpeg, zlib, libwebp, libtiff…) | Use `pkg install python-pillow` (prebuilt). |
| pydantic-core | Rust | No Android wheel: compiles 10–30 min. `pkg install rust binutils build-essential` first. |
| rpds-py | Rust | Pulled in by `jsonschema`; same build need. |
| cryptography | Rust (only if `PyJWT[crypto]` is selected) | `pkg install python-cryptography` (prebuilt). |

**Lighter install (finding).** `uvicorn`, `starlette`, `sse-starlette`, `python-multipart`, `PyJWT`, `httpx2` and `opentelemetry-api` are only needed for the SDK's HTTP transports and client; this server uses stdio only. They are hard requirements of the `mcp` package, so they cannot be excluded through pip without forking the SDK. They are pure Python except the crypto extra, so the real cost on a phone is the two Rust builds (`pydantic-core`, `rpds-py`), which the SDK genuinely needs (schemas, JSON-Schema validation). Decision: keep the official SDK; the install guide covers the Rust step.

## Vulnerability review

- Dependabot (`.github/dependabot.yml`) watches pip and GitHub Actions weekly.
- CI installs from PyPI on every push; `ruff` runs with a pinned version.
- Pillow is the main attack surface (image parsers). Controls: decoder allowlist, size/pixel limits, malformed-file fuzz tests, and optional process isolation (`--isolate SECONDS`, threat model R2/R5).
- No known vulnerable version is pinned: the project sets lower bounds only and records tested versions.
- Owner step: enable GitHub secret scanning, push protection and private vulnerability reporting (repository Settings → Code security).

## Regenerate this table

```sh
imagetoolbox-mcp --sbom > sbom.json        # attach to each GitHub release
```
