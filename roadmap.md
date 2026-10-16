# Image Toolbox MCP by Cowlsly — Development Roadmap

> Status: PLANNING | Version: 0.1 | Updated: 2026-10-16
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
- [ ] Add CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md and clear upstream attribution.
- [ ] Establish issue templates, PR template, changelog and architecture decision records.
- [ ] Choose implementation language/runtime after confirming host compatibility.
- [ ] Configure lint, formatting, unit tests, dependency review and secret scanning.
- [ ] Document local development and supported operating systems.
**Exit:** fresh clone installs and passes documented checks on a supported machine.

### M1 — Upstream capability and license audit [P0]
- [ ] Map Image Toolbox features to source modules and actual callable boundaries.
- [ ] Inspect upstream license and transitive dependencies; record obligations.
- [ ] Determine Android app package, SDK targets, file access mechanisms and exportable interfaces.
- [ ] Test whether fork changes are needed for a safe invocation surface.
- [ ] Write a feature feasibility matrix: direct / adapter / fork change / unsupported.
**Exit:** signed-off architecture decision with a working minimal processing spike.

### M2 — Minimal MCP server [P0]
- [ ] Implement MCP initialization, tool listing, invocation and structured errors.
- [ ] Validate inputs using explicit schemas and conservative size/path limits.
- [ ] Implement one end-to-end operation (prefer image metadata or JPEG-to-PNG conversion).
- [ ] Provide deterministic output paths, safe filename handling and cancellation.
- [ ] Add structured logging without image bytes or sensitive paths by default.
- [ ] Add integration tests with a compatible MCP inspector/client.
**Exit:** independent client discovers and invokes one tool successfully with test fixtures.

### M3 — Core image operations [P1]
- [ ] `image.inspect`: format, dimensions, orientation and optional safe metadata.
- [ ] `image.convert`: JPEG/PNG/WebP as supported by tested backend.
- [ ] `image.resize`: dimensions, aspect ratio, interpolation and orientation.
- [ ] `image.compress`: quality controls and before/after byte counts.
- [ ] `image.rotate_flip` and `image.crop` with explicit coordinates.
- [ ] Handle EXIF orientation and color profiles consistently.
- [ ] Document format-specific limits: JPEG has no alpha; converting JPEG to PNG does not restore lost detail or transparency.
**Exit:** golden-image tests, visual comparisons and metadata assertions pass for each declared operation.

### M4 — Batch processing and workflows [P1]
- [ ] Support multiple inputs, per-file results, dry-run previews and collision policies.
- [ ] Bound concurrency, CPU/memory use, file counts and output sizes.
- [ ] Preserve originals by default; write atomically and recover from partial failures.
- [ ] Support progress, cancellation, retries and resumable job manifests when feasible.
- [ ] Produce a manifest of source, output, parameters, checksums and failures.
**Exit:** mixed-format batch fixtures complete with no silent data loss.

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
- [ ] Strip GPS/private EXIF only on explicit request; clearly disclose metadata policy.
- [ ] Use timeouts, resource quotas, parser isolation where possible and dependency patching.
- [ ] Do not log image content, access tokens or private image metadata.
- [ ] Document vulnerability reporting, retention and temporary-file cleanup.
**Exit:** security checklist reviewed, negative tests pass, critical vulnerabilities resolved.

### M7 — Client interoperability [P1]
- [ ] Validate MCP protocol version and official SDK support.
- [ ] Test stdio with at least two compatible desktop clients where possible.
- [ ] Evaluate authenticated HTTP transport only with a real need and proper access controls.
- [ ] Document ChatGPT and Claude connection steps only after checking current product support.
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
  src/
    server/
    tools/
    adapters/
    security/
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

1. Inspect the original Image Toolbox license, architecture and existing Android entry points.
2. Record the feasibility matrix and choose a backend via ADR-0001.
3. Select a supported MCP SDK/runtime and create the smallest possible inspect/convert proof of concept.
4. Add CI and test fixtures before expanding the tool catalog.
5. Only then implement Android-specific bridging and client setup guides.

**Current checkpoint (2026-10-16):** Repository initialized; roadmap planning prepared. No MCP server, Android bridge or working image tools are claimed to exist yet.
