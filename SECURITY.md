# Security policy

## Supported versions

Pre-release (0.x). Only the latest commit on `root` receives fixes.

## Reporting a vulnerability

Please **do not** open a public issue. Use GitHub's private reporting: the repository's **Security** tab → **Report a vulnerability**. Include steps to reproduce and, if possible, a minimal generated test image (never a personal photo).

Expect an acknowledgement within 7 days. This is a one-person project, so fixes may take longer; you will be credited unless you ask otherwise.

## Scope and design commitments

- MCP tools only read from explicitly allowlisted input roots and write to an allowlisted output root.
- Symlinks, non-regular files, oversized files and decompression bombs are rejected (file-size and pixel limits).
- Originals are never overwritten by default.
- GPS and other private metadata are never returned; image bytes and full paths are not logged by default.
- No tool exposes shell, process, network or arbitrary filesystem access.
- Only JPEG, PNG, WebP, GIF, TIFF and BMP decoders are used; other formats are refused before parsing.

The full threat model, with the test that backs each control and the known residual risks, is in [`docs/threat-model.md`](docs/threat-model.md).

## Data retention and temporary files

- The server keeps no database, cache or history. The only things it creates are the output images and (for `image_batch`) a JSON manifest, both in the output folder, where you can delete them at any time.
- Each output is first written to a hidden temp file (`.itmcp-*.tmp`) in the output folder and then renamed; if anything fails, the temp file is deleted (tested in `tests/unit/test_output.py` and the fuzz tests). A temp file can only be left behind if the process is killed mid-write; it is safe to delete.
- Logs go to stderr only (the MCP client decides whether to keep them) and contain error codes, formats and sizes — never image content, GPS data or full paths.

Image decoding uses [Pillow](https://python-pillow.org/); keep it updated, because most image-parser vulnerabilities are fixed there.
