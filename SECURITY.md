# Security policy

## Supported versions

Pre-release (0.0.x). Only the latest commit on `root` receives fixes.

## Reporting a vulnerability

Please **do not** open a public issue. Use GitHub's private reporting: the repository's **Security** tab → **Report a vulnerability**. Include steps to reproduce and, if possible, a minimal generated test image (never a personal photo).

Expect an acknowledgement within 7 days. This is a one-person project, so fixes may take longer; you will be credited unless you ask otherwise.

## Scope and design commitments

- MCP tools only read from explicitly allowlisted input roots and write to an allowlisted output root.
- Symlinks, non-regular files, oversized files and decompression bombs are rejected (file-size and pixel limits).
- Originals are never overwritten by default.
- GPS and other private metadata are never returned; image bytes and full paths are not logged by default.
- No tool exposes shell, process, network or arbitrary filesystem access.

Image decoding uses [Pillow](https://python-pillow.org/); keep it updated, because most image-parser vulnerabilities are fixed there.
