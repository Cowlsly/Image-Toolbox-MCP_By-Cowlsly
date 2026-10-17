# ADR-0002: Output folder, naming and write policy

- **Status:** Accepted (2026-10-17, run 4).
- **Deciders:** Claude (scheduled session) under authority delegated by Cowlsly.
- **Applies to:** every tool that writes a file (`image_convert` first; later resize, compress, crop, batch).

## Context

M3 adds the first tool that creates files. The roadmap's rules: originals are never overwritten by default, no arbitrary filesystem access, deterministic output paths. The owner runs everything in Termux, where the natural place for images is Android shared storage (`~/storage/shared/...`). That storage is a FUSE mount: **hard links are not supported** and permissions/ownership are synthetic, so tricks that rely on `link()` or `chmod` cannot be the only safety mechanism.

## Decision

1. **One output folder, fixed at startup.** `--out DIR` or `IMAGETOOLBOX_MCP_OUT`. Default: `<input root>/imagetoolbox-out`, created on first write (single level only; its parent must exist). Keeping the default *inside* the input root means results can be fed straight into `image_inspect` or the next operation, and on the phone everything stays in one folder the user already chose.
2. **Flat namespace.** Clients may pass an optional `output_name` **stem** only. It must be 1–100 characters from letters, digits, space, `.`, `_`, `-`; no path separators, no leading `.` (no hidden files), not `.`/`..`. The extension always comes from the target format, so a client cannot write `evil.sh` or `x.png.exe`-style names that differ from the real content type. Default stem = source file stem (sanitised the same way; falls back to `image`).
3. **Never overwrite.** Candidate names are `<stem>.<ext>`, then `<stem>-1.<ext>` … `<stem>-999.<ext>`; after that the call fails with `[name_exhausted]`. A name is *claimed* with `open(O_CREAT | O_EXCL | O_NOFOLLOW)`, which is atomic on every filesystem we target, so two concurrent calls can never pick the same file and an existing file (or a planted symlink) is never written through.
4. **Atomic content.** The image is encoded into a hidden temp file in the same folder (`.itmcp-*.tmp`), flushed and `fsync`ed, then `os.replace`d onto the placeholder we just claimed. A reader therefore sees either an empty placeholder or the complete file, never a half-written image. On any failure both temp file and placeholder are removed.
5. **Symlink and type checks.** The output folder is resolved once at startup; at write time it is re-checked with `lstat` and must still be a real directory (not replaced by a symlink). If the output folder is the input root itself, that is allowed but discouraged in docs.
6. **Metadata.** Outputs carry **no EXIF/XMP/GPS** by default. EXIF orientation is *applied to the pixels* before saving, so the image looks the same without the tag. The ICC colour profile is kept (it is colour data, not personal data, and dropping it shifts colours).
7. **Results are reported relative to the input root** when the output folder is inside it (e.g. `imagetoolbox-out/cat.png`), so the path can be passed back to other tools; otherwise only the file name is reported. Absolute host paths are never returned or logged.

## Consequences

- Repeated calls with the same arguments create `cat.png`, `cat-1.png`, … — the tool is *not* idempotent and is annotated so (`idempotentHint: false`, `destructiveHint: false`).
- If the process is killed between claiming a name and the final rename, an empty `<name>` or a `.itmcp-*.tmp` may be left behind. Never data loss; a cleanup command can come with M4 (batch manifests).
- `cancellation`: a single conversion is short and bounded by the pixel/file-size limits; real cancellation is deferred to M4 batch jobs.
- Alternatives rejected: writing next to the original (mixes outputs into the user's folders and needs write access to all of them); `link()`-based no-clobber (fails on Android shared storage); client-chosen subfolders (more surface, little value yet).
