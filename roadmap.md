# Image Toolbox MCP by Cowlsly — Development Roadmap

> Status: ACTIVE (M1–M4 done, M0 mostly done, M7 research done; phone check + M6 next) | Version: 0.6 | Updated: 2026-10-17
>
> Repository: https://github.com/Cowlsly/Image-Toolbox-MCP_By-Cowlsly
> Upstream Android project: https://github.com/T8RIN/ImageToolbox
>
> This roadmap describes intended work, not completed functionality. A checked box means verified evidence exists in a commit, test report or release.

## 1. Vision and scope

Build an open-source, privacy-conscious Model Context Protocol (MCP) integration that lets compatible AI clients request supported image operations through a documented, permission-controlled execution layer. Preserve the original Image Toolbox project and its authorship. Avoid claiming that an Android UI feature is automatically callable through an API.

**Primary goals**
- Offer dependable single-image and batch conversion, resize, compression, metadata inspection and selected transformations.
- Support a mobile-first Android workflow and, where practical, a desktop or local-host processing backend.
- Keep image contents local by default; never upload them to a third party without informed user consent.
- Publish accurate tool schemas, examples, validation, compatibility notes and reproducible tests.
- Minimize cost, dependencies, permissions and lock-in.

**Non-goals for the first release**
- No uncontrolled remote access to Android files or unrestricted shell execution.
- No reverse engineering of private services or bypassing Android sandboxing.
- No promises of full feature parity with the Image Toolbox UI.
- No automatic modification, deletion or publishing of user images.
- No hosted processing service or paid API dependency required for baseline functions.

## 2. Repository roles and upstream relationship

| Repository | Role |
| --- | --- |
| `Cowlsly/Image-Toolbox-MCP_By-Cowlsly` | Independent MCP interface, adapters, tests, docs and release tooling |
| `Cowlsly/ImageToolbox-For_Cowlsly-MCP` | Fork used to investigate feasible Android integration and contribute changes where appropriate |
| `T8RIN/ImageToolbox` | Original upstream source and attribution |

Before reusing code, inspect the upstream license, dependency licenses, attribution obligations and any copyleft requirements. The connector repository's MIT license does **not** override licenses of imported upstream code. Prefer a clean adapter/interface where practical. Keep fork changes focused, traceable and eligible for upstream contribution.

## 3. Architecture decision gate

Do not choose a bridge implementation until a short feasibility spike verifies what Image Toolbox exposes.

Candidate execution paths:
1. **Independent local image engine**: an MCP server invokes documented open-source libraries for conversions and transformations. Lowest coupling to the Android app; feature behavior may differ.
2. **Android companion integration**: a separately authorized companion service or explicit Android intents/IPC implemented in the fork. Requires Android lifecycle, foreground/background restrictions, URI permissions and security testing.
3. **Shared processing module**: reuse suitable upstream processing code only if modularity, build tooling and licenses permit it.

Record the chosen approach in `docs/adr/0001-processing-backend.md`, with evidence, tradeoffs and a fallback. MCP transport (stdio for local hosts; authenticated HTTP only if needed) is distinct from the Android execution bridge. A mobile ChatGPT client is **not** assumed to launch or connect to a local MCP server directly; verify supported client installation, transport and approval flows independently.

Proposed logical flow:

```text
Compatible AI client
    -> MCP transport / server
    -> tool registry + schema validation
    -> consent / path & permission policy
    -> job coordinator + resource limits
    -> image processing adapter
    -> selected backend (local library OR authorized Android bridge)
    -> validated output + metadata + audit record
```

## 4. Milestones and acceptance gates

### M0 — Repository foundations [P0]
- [ ] Audit existing README, license, gitignore, branch rules and GitHub App permissions.
- [x] Add CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md and clear upstream attribution. — 2026-10-17 run 2.
- [x] Establish issue templates, PR template, changelog and architecture decision records. — `.github/ISSUE_TEMPLATE/`, PR template, CHANGELOG.md, `docs/adr/` (2026-10-17).
- [x] Choose implementation language/runtime after confirming host compatibility. — Python 3.10+ / Pillow / official MCP SDK, see ADR-0001 (Termux install: VERIFY).
- [ ] Configure lint, formatting, unit tests, dependency review and secret scanning. — Dependabot committed 2026-10-17; ruff + unittest CI workflow written and staged at `ci/ci.yml` — **BLOCKED**: agent cannot write `.github/workflows/` (owner must move it), then VERIFY first green run; secret scanning/push protection is a repo setting (owner).
- [ ] Document local development and supported operating systems.
**Exit:** fresh clone installs and passes documented checks on a supported machine.

### M1 — Upstream capability and license audit [P0]
- [x] Map Image Toolbox features to source modules and actual callable boundaries. — `docs/audit/upstream-audit.md` §3–5.
- [x] Inspect upstream license and transitive dependencies; record obligations. — Apache-2.0 (T8RIN); obligations in audit §1. `lib/qrose` header: VERIFY (only if reused).
- [x] Determine Android app package, SDK targets, file access mechanisms and exportable interfaces. — audit §2–3 (static reading; not run on device).
- [x] Test whether fork changes are needed for a safe invocation surface. — Yes: no headless/parameterised entry point exists (audit §3). Deferred to M5.
- [x] Write a feature feasibility matrix: direct / adapter / fork change / unsupported. — audit §5.
**Exit:** signed-off architecture decision with a working minimal processing spike.
**Status (2026-10-17): COMPLETE** — ADR-0001 accepted; `engine.inspect_image` spike with 11 passing unit tests.

### M2 — Minimal MCP server [P0]
- [x] Implement MCP initialization, tool listing, invocation and structured errors. (`server.py`; errors are `is_error` results prefixed `[code]`; tests in `tests/integration/test_server.py`)
- [x] Validate inputs using explicit schemas and conservative size/path limits. (JSON schema with length limits; `sandbox.InputRoot` rejects `..`, symlinks, outside-root paths; engine file-size/pixel limits; `tests/unit/test_sandbox.py`)
- [x] Implement one end-to-end operation (prefer image metadata or JPEG-to-PNG conversion). (`image_inspect`)
- [ ] Provide deterministic output paths, safe filename handling and cancellation. **Moved to M3** (2026-10-17): no tool writes output yet; this lands with `image_convert`. (Done in M3 run 4, ADR-0002.)
- [~] Add structured logging without image bytes or sensitive paths by default. Partial: stderr logs carry only error codes and dimensions, never paths or bytes; not yet JSON-structured.
- [x] Add integration tests with a compatible MCP inspector/client. (official SDK `Client`, in-process and over a real stdio subprocess; raw JSON-RPC `initialize` with protocol 2025-06-18 also answered)
**Exit:** independent client discovers and invokes one tool successfully with test fixtures.

**Status (2026-10-17, run 3): COMPLETE** — exit criterion demonstrated by `StdioSubprocessTests.test_stdio_end_to_end` (32 tests passing). Tool names are `snake_case` (`image_inspect`, not `image.inspect`): several model APIs only accept `[A-Za-z0-9_-]` in tool names, so dots would break those clients. The section 5 table keeps the dotted names as concept labels.

### M3 — Core image operations [P1]
- [x] `image.inspect`: format, dimensions, orientation and optional safe metadata. (shipped in M2 as `image_inspect`)
- [x] Deterministic output paths, safe filename handling, never-overwrite policy (ADR-0002, `output.py`, `tests/unit/test_output.py`, run 4). Cancellation deferred to M4 batch jobs: single conversions are bounded by size/pixel limits.
- [x] `image.convert`: JPEG/PNG/WebP as supported by tested backend. (`image_convert`, golden tests in `tests/unit/test_engine_convert.py`, MCP tests in `tests/integration/test_convert.py`, run 4)
- [x] `image.resize`: dimensions, aspect ratio, interpolation and orientation. (`image_resize`, `tests/unit/test_engine_resize.py`, `tests/integration/test_resize.py`, run 5)
- [x] `image.compress`: quality controls and before/after byte counts. (`image_compress`: quality or `max_bytes` search, PNG palette reduction; `tests/unit/test_engine_compress.py`, `tests/integration/test_compress.py`, run 6)
- [x] `image.rotate_flip` and `image.crop` with explicit coordinates. (`image_rotate_flip`: 90/180/270 clockwise + horizontal/vertical flip; `image_crop`: explicit box or centred `aspect`, out-of-bounds refused; `tests/unit/test_engine_rotate_crop.py`, `tests/integration/test_rotate_crop.py`, run 7)
- [x] Handle EXIF orientation and color profiles consistently. All five write tools load through one `_load_upright` path (orientation applied to pixels; coordinates, sizes and directions refer to the upright image) and one encode path (ICC kept, EXIF/XMP/GPS dropped); each has an EXIF-orientation and a metadata test (runs 4–7).
- [x] Document format-specific limits: JPEG has no alpha; converting JPEG to PNG does not restore lost detail or transparency. (README tool table, tool description, and runtime `warnings` in results)
**Exit:** golden-image tests, visual comparisons and metadata assertions pass for each declared operation.

**Status (2026-10-17, run 7): COMPLETE** — six tools (`image_inspect`, `image_convert`, `image_resize`, `image_compress`, `image_rotate_flip`, `image_crop`), 143 tests passing locally and against the installed wheel. "Visual comparisons" are implemented as exact/tolerance pixel assertions against reference images (no human eyeballing step). GitHub CI has still not run (M0 blocker), so cross-platform results are VERIFY.

### M4 — Batch processing and workflows [P1]
- [x] Support multiple inputs, per-file results, dry-run previews and collision policies. (`image_batch`: one folder + optional name glob, per-file `ok`/`failed`/`not_run`, `dry_run`, collision policy = ADR-0002 never-overwrite with numbered names; ADR-0004; `tests/integration/test_batch.py`, run 9)
- [x] Bound concurrency, CPU/memory use, file counts and output sizes. (Sequential = concurrency 1; `max_files` default 50 / hard cap 200 and 1 GiB total input refuse rather than truncate; 10 000-entry scan cap; per-file 64 MiB / 64 MP / 16384 px limits unchanged; `tests/unit/test_batch.py`, run 9)
- [x] Preserve originals by default; write atomically and recover from partial failures. (Source SHA-256 unchanged after batches; atomic writes from ADR-0002; a failing file never aborts the batch, argument errors stop it early; run 9)
- [ ] Support progress, cancellation, retries and resumable job manifests when feasible. **Partial (run 9):** MCP progress after each file and cancellation (finished files kept, `cancelled` manifest) done and tested in-process; over real stdio clients VERIFY. Automatic retries and resume-from-manifest not built (low value for small phone batches; revisit if users ask).
- [x] Produce a manifest of source, output, parameters, checksums and failures. (`batch-<op>-<UTC>.json` in the output folder; root-relative paths only; checksum match verified in tests; run 9)
**Exit:** mixed-format batch fixtures complete with no silent data loss.

**Status (2026-10-17, run 9): exit criterion met** — a mixed folder (EXIF-rotated JPEG with GPS, RGBA PNG, WebP, animated GIF, corrupt JPEG, text file, symlink) converts with every file accounted for (4 ok, 1 failed with a code, symlink reported as skipped, text file not matched), originals' checksums unchanged, manifest checksums match the outputs. Only retries/resume remain (deferred, see above).

### M5 — Android bridge feasibility and implementation [P1, conditional]
- [ ] Prototype an explicit user-authorized integration in the fork.
- [ ] Verify scoped storage, Storage Access Framework, content URI grants and permission expiry.
- [ ] Avoid broad storage access unless genuinely required and justified.
- [ ] Verify background execution and foreground service requirements on supported Android versions.
- [ ] Design safe app-to-service communication; reject untrusted callers.
- [ ] Test on physical Android devices, including Samsung Galaxy A17 5G where available.
- [ ] Document limitations when the mobile MCP client cannot reach the service.
**Exit:** a real device successfully performs an authorized operation with repeatable tests. If infeasible, publish the independent local backend instead.

### M6 — Privacy, safety and threat modeling [P0 before public beta]
- [ ] Threat-model path traversal, symlinks, malicious images, decompression bombs and metadata leakage.
- [ ] Enforce allowlisted inputs/outputs or per-operation explicit grants.
- [ ] Never expose arbitrary filesystem, network, process or shell access as MCP tools.
- [ ] Require confirmation for destructive, overwrite or sharing operations.
- [ ] Clearly disclose metadata policy. **Amended 2026-10-17 (run 4):** was "strip GPS/private EXIF only on explicit request"; ADR-0002 instead strips EXIF/XMP/GPS from every *new* output by default (originals are untouched), because silently copying location data into files a user may share is the bigger privacy risk. An explicit `keep_metadata` opt-in can be added later if needed.
- [ ] Use timeouts, resource quotas, parser isolation where possible and dependency patching.
- [ ] Do not log image content, access tokens or private image metadata.
- [ ] Document vulnerability reporting, retention and temporary-file cleanup.
**Exit:** security checklist reviewed, negative tests pass, critical vulnerabilities resolved.

### M7 — Client interoperability [P1]
- [x] Validate MCP protocol version and official SDK support. — `tests/integration/test_protocol.py`: 2024-11-05 … 2025-11-25 echoed over real stdio, unknown version answered with a supported one (run 8, SDK 2.2.0).
- [ ] Test stdio with at least two compatible desktop clients where possible.
- [ ] Evaluate authenticated HTTP transport only with a real need and proper access controls. — Evaluated in [ADR-0003](docs/adr/0003-transports-and-phone-clients.md) (run 8): real need = Claude Android app; SDK Streamable HTTP works on loopback (spike); needs OAuth + tunnel + M6 threat model first. Not built.
- [ ] Document ChatGPT and Claude connection steps only after checking current product support. — Product support checked with sources in [docs/clients.md](docs/clients.md) (run 8): Claude app = remote OAuth/authless only; ChatGPT MCP = web only. Termux CLI steps written, VERIFY on phone.
- [ ] Publish copy-pasteable configuration samples with placeholders, not secrets.
- [ ] Verify tool results, errors, progress and client-specific limitations.
**Exit:** documented evidence of successful tool calls per advertised client.

### M8 — Documentation and accessibility [P1]
- [ ] Quick start, architecture, threat model, tool catalog and troubleshooting.
- [ ] Android/mobile-first instructions with screenshots that match tested versions.
- [ ] Examples for bulk JPEG-to-PNG, resize, compression and metadata cleanup.
- [ ] Accessibility review for any companion UI; plain-language error messages.
- [ ] Explain local versus remote processing and offline capabilities.
**Exit:** newcomer can install, test and safely process a sample image.

### M9 — Release engineering [P1]
- [ ] Semantic versioning, signed tags where supported, changelog and SBOM.
- [ ] CI matrix for supported runtimes/OSes; Android build checks if applicable.
- [ ] Automated unit/integration/security checks and reproducible release artifacts.
- [ ] License/attribution audit and dependency vulnerability review.
- [ ] Publish alpha -> beta -> stable only after each gate passes.
**Exit:** clean installation from published release and documented rollback.

### M10 — Advanced features [P2, after stable core]
- [ ] Watermarking, format optimization and controlled metadata editing.
- [ ] Filters, color adjustments, OCR or PDF/image workflows only after feasibility and license review.
- [ ] Optional job presets and reproducible transformation recipes.
- [ ] Optional GUI and advanced Android features with explicit user permissions.
- [ ] Evaluate additional formats (HEIC/AVIF/GIF) individually for decoder support, licensing and test coverage.
**Exit:** each feature has isolated tests, documentation and opt-in permissions as needed.

## 5. Initial tool contract (proposed, not implemented)

All operations must expose JSON-schema-validated arguments, explicit errors and a consistent response envelope.

| Tool | Inputs | Outputs |
| --- | --- | --- |
| `image.inspect` | authorized source reference | format, dimensions, size, safe metadata |
| `image.convert` | source, target format, output policy | output reference, format, size |
| `image.resize` | source, width/height, aspect policy | output reference, dimensions |
| `image.compress` | source, quality, output policy | output reference, before/after size |
| `image.crop` | source, rectangle | output reference, dimensions |
| `image.batch` | authorized source set, operation recipe | per-file status, manifest |

Do not accept unrestricted arbitrary paths from untrusted remote clients. Define an authorization mechanism for source references. Every operation must specify whether original files can ever be replaced; default is no.

## 6. Quality strategy

**Unit:** schemas, validation, error mapping, output naming, format capability checks.

**Integration:** fixture processing, EXIF orientation, alpha preservation, color profiles, malformed files, cancellations and temporary-file cleanup.

**Property/security:** path traversal, oversized dimensions, corrupt files, zip/image bombs, race conditions, unauthorized callers and metadata leaks.

**Performance:** peak memory, wall time and output size on representative image sets; publish measurements with hardware and versions, not unsupported claims.

**Manual:** mobile UX, accessibility, image comparison and client interoperability.

A release must not be described as functional solely because code compiles. Evidence should include passing CI, a real MCP invocation and representative output verification.

## 7. Suggested project structure (future)

```text
/
  README.md
  roadmap.md
  LICENSE
  CONTRIBUTING.md
  SECURITY.md
  CHANGELOG.md
  docs/
    architecture.md
    adr/
    tool-contracts/
    android/
    clients/
  src/imagetoolbox_mcp/
    engine.py        # Pillow, no MCP imports
    sandbox.py       # allowlisted input root / path policy
    output.py        # output folder, never-overwrite atomic writes (ADR-0002)
    batch.py         # batch selection, option validation, manifest (ADR-0004)
    server.py        # MCP SDK wiring (stdio)
    tools/           # per-tool schemas, envelope (planned, once there are several tools)
  tests/
    unit/
    integration/
    fixtures/
  examples/
  .github/
    workflows/
    ISSUE_TEMPLATE/
```

This is a target layout, not a claim that these files exist.

## 8. Backlog prioritization and dependencies

| Priority | Work item | Dependency | Evidence |
| --- | --- | --- | --- |
| P0 | Verify licensing and architecture | upstream audit | ADR + license inventory |
| P0 | Working single-tool MCP prototype | chosen backend | client transcript + test |
| P0 | Permission and resource boundaries | tool contract | negative tests |
| P1 | Conversion, resize and compression | prototype | golden fixtures |
| P1 | Batch pipeline | stable core tools | failure/recovery tests |
| P1 | Android integration | feasibility spike | device test |
| P1 | Client documentation | verified interoperability | installation logs |
| P2 | Advanced filters/OCR/PDF | security + license review | isolated tests |

## 9. Project workflow and continuity

Use small, reversible commits and PRs. Avoid force pushes, history rewrites and unreviewed merges. Each issue/PR should include:
- Objective and user value
- Verified facts versus assumptions
- Dependencies and risk
- Implementation plan
- Test commands and actual results
- Status: PENDING / ACTIVE / BLOCKED / VERIFY / COMPLETE
- Next action and handover notes

A future `docs/PROJECT_STATE.md` may summarize verified checkpoints and open blockers for Everloom Memory Nexus workflows. Do not store credentials, tokens, private image contents or personal data in repository memory files.

## 10. Definition of done

A milestone is COMPLETE only when code/docs are committed, acceptance criteria are demonstrated, relevant tests pass, security and license implications are addressed, and any limitations are documented. If tests cannot run, mark VERIFY or BLOCKED instead of COMPLETE.

## 11. Immediate next actions

1. ~~Inspect the original Image Toolbox license, architecture and existing Android entry points.~~ Done 2026-10-17 (audit).
2. ~~Record the feasibility matrix and choose a backend via ADR-0001.~~ Done 2026-10-17.
3. ~~M0 scaffold: `pyproject.toml`, GitHub Actions CI, CONTRIBUTING/SECURITY/CHANGELOG.~~ Done 2026-10-17 run 2, except CI activation: owner moves `ci/ci.yml` → `.github/workflows/ci.yml` (BLOCKED for the agent).
4. ~~M2: minimal stdio MCP server exposing `image.inspect` with an allowlisted input root, structured errors, and an MCP client integration test.~~ Done 2026-10-17 run 3 (`image_inspect`).
5. Owner check (VERIFY): install `python`, `python-pillow` and `mcp` in Termux on the phone and report whether `pip install mcp` succeeds (pydantic-core/cryptography).
6. ~~M3 `image_convert` with output folder and never-overwrite names.~~ Done 2026-10-17 run 4 (ADR-0002).
7. ~~M3 `image_resize`.~~ Done 2026-10-17 run 5. ~~`image_compress`~~ Done run 6. ~~`image_rotate_flip` + `image_crop`~~ Done run 7 — **M3 complete**.
8. ~~M7 client research~~ Done run 8: `docs/clients.md`, ADR-0003 (stdio stays; phone path = agent CLI in Termux; Claude-app remote path deferred until OAuth + M6). Original item: The owner is phone-only, so the server is useless until some MCP client can reach it. Research (with sources) which clients can launch a local stdio server inside Termux, or whether a phone needs Streamable HTTP on `127.0.0.1` / a tunnel for Claude or ChatGPT remote connectors; write `docs/clients.md` and an ADR if a transport change is needed. Then M4 batch.
9. **Owner check (VERIFY, highest value now):** on the phone, follow `docs/clients.md` Path A (install the server, then Claude Code or Gemini CLI in Termux, run one tool). This is M7's exit evidence and also answers item 5.
10. ~~M4 batch~~ Done run 9: `image_batch` (ADR-0004), 169 tests. Retries/resume deferred.
11. **Next agent run (run 10): M6 threat model** — write `docs/threat-model.md` (assets, attackers, entry points; path traversal, symlink races, decompression bombs, malformed files, metadata leakage, resource exhaustion, prompt-injected tool arguments), map each threat to the existing control and test, add fuzz-style tests with malformed/truncated files for every format, and close the gaps found (e.g. a per-call time budget). Prerequisite for any remote/HTTP mode.
12. Then M9 release prep (tagged 0.x release, Termux install notes verified by the owner) and only then Android-specific bridging (M5).

**Current checkpoint (2026-10-17, run 9):** M1–M4 complete: `image_inspect`, `image_convert`, `image_resize`, `image_compress`, `image_rotate_flip`, `image_crop`, `image_batch` over stdio, 169 tests passing. M7 research done (ADR-0003, `docs/clients.md`); real-client evidence waits on the owner's phone. M0 CI activation still waits on the owner. No Android bridge or releases yet. Handover: `docs/PROJECT_STATE.md`.

**Roadmap change (2026-10-17, run 9):** after M6, M9 release prep (a tagged 0.x release with phone-verified install notes) is placed before M5, because the owner needs something installable to test on the phone, and M5 (Android bridge) is only worth doing once the local server is proven there.

**Roadmap change (2026-10-17, run 8):** M4 kept before M6, but M6 is now a hard prerequisite for any HTTP/remote transport (ADR-0003), because the only remote client the owner could use (Claude app) needs a publicly reachable server.

**Roadmap change (2026-10-17):** M1 was done before M0's remaining items because the runtime choice (M0) depended on the audit. Section 7 layout adjusted to Python (`src/imagetoolbox_mcp/`).
