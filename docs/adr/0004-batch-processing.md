# ADR-0004: Batch processing (`image_batch`)

- **Status:** Accepted (2026-10-17, run 9).
- **Deciders:** Claude (scheduled session) under authority delegated by Cowlsly.
- **Applies to:** M4. Builds on ADR-0002 (output policy).

## Context

A phone user mostly wants "do this to all the photos in that folder". Calling a single-file tool 50 times costs a model 50 round trips and a lot of context, and gives no overall record. A batch tool, however, multiplies every risk of a single call: more files read, more files written, more CPU and memory on a phone, and more chance that one bad file hides what happened to the others.

## Decision

One tool, `image_batch`, applies **one** existing operation (`convert`, `resize`, `compress`, `rotate_flip`, `crop`) to the files **directly inside one folder** of the input root.

1. **Selection.** The folder goes through the same sandbox as single paths (`InputRoot.resolve_dir`: no `..`, no symlinks at any level, must stay in the root). No recursion. Hidden files (`.…`) are ignored; symlinks, non-regular files and files over the size limit are *skipped and reported*, never followed. Without a `pattern`, common image extensions are matched; `pattern` is a case-insensitive glob on the file **name** only. The output folder itself cannot be the batch folder (no re-processing of earlier results). Order is sorted by name, so runs are reproducible.
2. **Hard limits, refuse instead of truncate.** `max_files` (default 50, hard cap 200); 1 GiB total input per call; at most 10 000 folder entries scanned. Going over a limit refuses the whole call with a clear code (`too_many_files`, `batch_too_large`, `folder_too_large`) — silently processing "the first 200" would be a silent data-loss-style surprise.
3. **Options validated once, before any file is touched.** Per-operation pydantic models with `extra="forbid"` (typos such as `widht` are refused, and the error lists allowed keys) and the same cross-field rules as the single tools. `output_name` is refused: every file gets its operation's default name. The MCP schema exposes `options` as a plain object rather than a `oneOf` union, because several clients (Gemini in particular) handle unions poorly; the description lists each operation's keys.
4. **Sequential, one file at a time** in a worker thread. Phones have little RAM and the single-file limits (64 MiB, 64 MP) already bound one file; parallelism would multiply peak memory for little gain. Concurrency = 1 is the "bounded concurrency" of the roadmap.
5. **Partial failure never aborts.** Each file ends as `ok`, `failed` (stable `error_code` + message) or `not_run`. Unexpected exceptions become `internal_error` for that file only. The one exception: `invalid_argument` from the engine means the arguments are wrong for every file, so the batch stops; if nothing was written yet the whole call is an error.
6. **Collision policy:** only ADR-0002's — never overwrite, numbered suffix. Running the same batch twice gives `-1` names, never replacement. No overwrite or "skip existing" option is offered (overwriting would need the M6 confirmation design).
7. **Manifest.** Unless `write_manifest=false`, a new `batch-<operation>-<UTC time>.json` is written to the output folder with tool version, start/finish time, full options, folder, pattern, skipped entries, and per file: source, status, output, SHA-256 of source and output, sizes, warnings or error. Only root-relative paths — never host paths. Checksums are in the manifest but not in the tool result, to keep the model's context small.
8. **Dry run.** `dry_run=true` lists the files that would be processed and writes nothing (no output folder, no manifest).
9. **Progress and cancellation.** After each file the server sends MCP progress (`n/total`) when the client asked for it. If the client cancels, the in-flight file finishes (writes are atomic, so there is never a half file), no further files start, and a manifest with `status: "cancelled"` records exactly what was done.

## Consequences

- One call can now create up to 200 files. Still bounded, still only inside the output folder, still never overwrites; annotations stay non-destructive.
- Resuming an interrupted batch is possible by hand (the manifest lists what was done) but not automatic. A `resume_from` manifest option is a possible later addition; not built now (roadmap M4 says "when feasible").
- Cancellation is tested in-process (SDK direct dispatcher). Cancellation over a real stdio client depends on the client sending `notifications/cancelled`; **VERIFY** with Claude Code / Gemini CLI on the phone.
- Speed on the phone is unmeasured; cloud numbers: small images take milliseconds each, PNG palette compression of 900×900 noise ≈ 0.3 s each.
