# Threat model — imagetoolbox-mcp

Status: **v1, 2026-10-20 (run 10, M6)**. Covers version 0.7.0, stdio transport only. Must be revised before any HTTP/remote transport ships (ADR-0003) and before an Android bridge (M5).

## 1. System and trust boundaries

```
 user ──► AI model ──► MCP client (Claude Code / Gemini CLI in Termux, desktop app)
                            │  stdio (JSON-RPC), child process on the same device
                            ▼
                   imagetoolbox-mcp server ──► engine (Pillow decoders/encoders)
                     │ reads only                  │ writes only
                     ▼                             ▼
           input root (--root)            output folder (--out, default <root>/imagetoolbox-out)
```

- **Trusted:** the person who starts the server and chooses `--root`/`--out`; the Python runtime; Pillow and its C libraries (kept patched, see T10).
- **Untrusted:** every tool argument (it is written by a model that may have read hostile text — prompt injection), and every byte of every file inside the input root (photos from the internet, messaging apps, other Android apps with storage access).
- **Out of scope for v1:** a malicious MCP client binary or a compromised device (they already have the user's files); network attackers (no network listener exists — stdio only).

## 2. Assets

1. Files outside the input root (the rest of the phone's storage, Termux home, SSH keys, tokens).
2. Original images inside the root (must never be modified or overwritten).
3. Private metadata in images (GPS location, camera serials, timestamps) and private file/folder names.
4. Device availability (CPU, memory, battery, storage) — a phone is the main target device.

## 3. Threats, controls and evidence

| # | Threat | Control (where) | Evidence (tests) | Status |
| --- | --- | --- | --- | --- |
| T1 | **Path traversal / escape** via `..`, absolute paths, NUL bytes, over-long paths, symlinks at any level (incl. a symlink pointing back inside) | `InputRoot`: lexical checks, `lstat` walk of every component, final `resolve()` containment (`sandbox.py`); folders via `resolve_dir`; batch skips symlinks and never recurses | `tests/unit/test_sandbox.py` (13 tests), `test_batch.py::test_default_selection_sorted_no_recursion_no_hidden`, MCP `test_server.py` outside-root/symlink cases | Mitigated |
| T2 | **Swap-after-check race** (TOCTOU): file replaced by a symlink or FIFO between the check and the open | Input opened with `O_NOFOLLOW \| O_NONBLOCK`, then `fstat` on the **open descriptor** (regular file, size limit); Pillow reads the descriptor, not the path (`engine._open`, run 10). Outputs: `O_CREAT\|O_EXCL\|O_NOFOLLOW` claim + output-folder symlink re-check (ADR-0002) | `tests/unit/test_engine_open_race.py` (symlink, FIFO does not hang, file grown past limit); `test_output.py` planted-symlink / folder-swapped tests | Mitigated (run 12: directory components too, via the confined `openat` walk; Windows keeps residual R1) |
| T3 | **Malformed / truncated files** crash the server or leak internals | Decoder exceptions (`OSError`, `ValueError`, `SyntaxError`, `IndexError`, `KeyError`, `TypeError`, `EOFError`, `struct.error`, `ZeroDivisionError`) → `[decode_failed]`, `MemoryError` → `[out_of_memory]` (`engine._decode_error`); any other exception in a tool → fixed `[internal_error]` text (`server._guard`) | Mutation fuzzing, 6 formats × 40 mutants × 3 operations per test run (`test_malformed_inputs.py::FuzzTests`) plus 4 200 extra mutants run by hand in run 10 (seeds 1–5): **before** the fix 9 crash classes escaped (e.g. GIF `IndexError`, PNG `SyntaxError`, `OSError` from `inspect`); after: none | Mitigated |
| T4 | **Parser attack surface**: Pillow can open ~40 formats; some are rarely audited and EPS **starts Ghostscript** (a separate interpreter with its own CVE history) | Decoder allowlist: `Image.open(..., formats=("JPEG","PNG","WEBP","GIF","TIFF","BMP"))` (`engine.ALLOWED_INPUT_FORMATS`); multi-picture phone JPEGs still open as MPO | `DecoderAllowlistTests`: PCX/PPM/ICO/TGA refused as `unsupported_format`; an EPS with a `%pipe%` payload is refused with `subprocess` patched to fail if called; MPO opens | Mitigated |
| T5 | **Decompression bombs** (tiny file, huge declared size) | 64 MiB file limit, 64 MP pixel limit checked from the header **before** decoding; Pillow's own `DecompressionBombError` mapped to `too_many_pixels`; 16 384 px max output side | `BombTests` (81 MP, 400 MP, 1×70 M PNG headers < 200 bytes, nothing written), `test_engine_inspect.py`, `test_engine_resize.py` limit tests | Mitigated |
| T6 | **Resource exhaustion** (CPU/time, memory, disk) by one call or a batch | Limits above; batch: ≤ 200 files, 1 GiB total input, 10 000-entry scan cap, sequential processing, cancellable; `image_compress` `max_bytes` search stops at a **30 s wall-clock budget** (`Limits.max_search_seconds`) with warning `time_budget_reached` (run 10) | `test_engine_budget.py`; batch limit tests. Measured (cloud, 64 MP noise JPEG): convert→PNG 25 s, resize 1.8 s, JPEG `max_bytes` 4.8 s; PNG `max_bytes` > 120 s before the budget, 37 s after | Mitigated when `--isolate` is on (hard timeout); otherwise partly — **R2** |
| T7 | **Overwriting or deleting originals / existing files** | No tool modifies inputs; outputs only in the output folder, never-overwrite claim with `-1…-999` suffixes, atomic temp + `os.replace`; no delete/move tool exists | `test_output.py` (never overwrites, 16 concurrent writers, failed writer leaves nothing); fuzz test asserts failed calls leave no file (incl. hidden temp files); golden tests check source hashes unchanged | Mitigated |
| T8 | **Metadata leakage** (GPS, serials) into outputs or model context | Outputs drop EXIF/XMP/GPS (orientation baked in, ICC kept) — ADR-0002; `image_inspect` returns only a safe EXIF subset and a `has_gps_metadata` flag, never coordinates; batch manifest has checksums, not metadata. `image_tag` (run 12) is the only tool that writes metadata: just the description/artist/copyright text the caller gives, after the same strip | `test_engine_convert.py` byte-level GPS/XMP absence; `test_engine_inspect.py`; `test_edit.py::TagTests` (GPS, camera model and orientation absent) | Mitigated |
| T9 | **Log / error leakage** of host paths, private file names or image content | Errors use stable codes and root-relative paths only; logs (stderr) carry codes, sizes, formats; unexpected exceptions are logged as the exception **type** only (the SDK would otherwise log a traceback whose message can contain a path) | `test_guard.py` (sync, write and async tools; result and log contain neither the root nor the file name); fuzz test asserts no host path in any error message | Mitigated |
| T10 | **Vulnerable dependency** (Pillow/libjpeg/libpng/libwebp/libtiff, MCP SDK, pydantic) | Lower bounds in `pyproject.toml`; Dependabot (pip + actions) configured; allowlist (T4) shrinks the reachable C code | `.github/dependabot.yml` | Partly mitigated — CI not active yet (owner action, PROJECT_STATE blocker 4) |
| T11 | **Prompt-injected tool arguments** (a web page tells the model to "convert ../../.ssh/id_rsa") | Same as T1/T7: arguments are untrusted; every path goes through `InputRoot`; enum/range-validated schemas (`extra="forbid"` for batch options); write tools are non-destructive by construction; tool annotations declare `destructive_hint=false`, `open_world_hint=false` | Sandbox + schema tests; batch invalid-option tests | Mitigated (the worst a hostile prompt can do is create extra files in the output folder — bounded by T6 limits) |
| T12 | **Arbitrary capability exposure** (shell, network, filesystem tools) | No such tools exist; no network code; server has 11 image tools only (run 12 added adjust, watermark, recipe, tag — all through `InputRoot` + `OutputDir.write_new`) | `test_server.py::test_lists_tool_with_schema_and_read_only_hints` asserts the exact tool list | Mitigated |

## 4. Residual risks (accepted for now, tracked)

- **R1 — directory-component race. CLOSED on POSIX (run 12).** The server sets `Limits.confine_to` to the resolved input root and `engine._open_confined` opens every file by walking down from the root with `dir_fd` and `O_NOFOLLOW` per component (`openat`), so a folder swapped for a symlink after the sandbox check gives `[symlink_rejected]` (`test_engine_open_race.py::ConfinedOpenTests`). Windows has no `dir_fd`; there the old check-then-open remains (residual, Windows only).
- **R2 — hard per-call timeout: AVAILABLE, opt-in (run 12).** `--isolate SECONDS` (or `IMAGETOOLBOX_MCP_ISOLATE`) runs every engine call in a `spawn`ed child that is killed after the limit (`[timed_out]`); a decoder crash in the child becomes `[decode_failed]` instead of killing the server (`tests/unit/test_isolation.py`). Off by default because it adds ~0.3–1 s per call on a phone. Must be **on** before any remote mode.
- **R3 — memory.** A 64 MP RGBA image needs ~256 MB, plus copies during transforms; on a low-RAM phone Android may kill Termux. `--max-megapixels MP` (run 12) lowers the pixel limit for low-RAM phones.
- **R4 — output disk use.** Each call creates a new file; a looping model could fill storage up to 200 files × 64 MiB per batch call. No quota exists. Acceptable for a single-user local tool; add an output-folder quota before remote mode.
- **R5 — Pillow C-library bugs** that do not raise Python exceptions (memory corruption) cannot be caught by T3's mapping. Mitigation is patching (T10) and process isolation (`--isolate`, R2), which contains a crash to the child process.

## 5. Rules for future changes

1. A new tool that reads a file must use `InputRoot.resolve` + `engine._open` (or `_load_upright`); a new tool that writes must use `OutputDir.write_new`.
2. A new input format is added only by extending `ALLOWED_INPUT_FORMATS` **and** the fuzz seeds in `test_malformed_inputs.py`.
3. Every tool is registered with `_tool(server, ...)` so the `_guard` catch-all applies.
4. No HTTP/remote transport until this document has a "remote" section covering auth (OAuth 2.1), R1, R2 and R4 (ADR-0003).

## 6. Review checklist (M6 exit)

- [x] Threats enumerated with controls and tests (this file).
- [x] Negative tests pass (189 tests, run 10).
- [x] No known critical vulnerability open (R1–R5 are medium/low for a single-user local server).
- [ ] Independent review — VERIFY: any second reviewer (owner, another agent) reads this file and opens issues for gaps.
