# ADR-0005: Advanced features (M10)

Status: accepted, 2026-10-25 (run 12).

## Decisions

1. **Built:** `image_adjust` (brightness, contrast, saturation, sharpness, grayscale, autocontrast), `image_watermark` (one line of text, 9 positions, opacity, size, colour), `image_recipe` (up to 10 steps of resize/crop/rotate_flip/adjust/watermark in memory, one encode, normalised steps returned so the recipe can be re-run exactly), `image_tag` (controlled metadata: writes only description/artist/copyright; all source metadata still dropped). `adjust` and `watermark` are also `image_batch` operations. All use Pillow only, so no new dependency or licence.
2. **Process isolation** (`--isolate SECONDS`): optional child process per call with a hard timeout; closes residual risk R2 when enabled. Off by default because it costs ~0.3–1 s per call on a phone.
3. **Batch resume and retries:** `resume_from` skips files an earlier manifest finished (same operation and options, unchanged source checksum, output still present); `retries` (0–3) retries `output_unavailable`, `out_of_memory` and unexpected errors.
4. **Watermark images (logo files):** not built. Text covers the stated need; image overlays need a second input path and alpha rules — add only if asked.
5. **OCR:** not built. Needs the Tesseract binary (Apache-2.0) outside Python; not in Termux by default; recognised text is a new data-leak surface for the threat model. Revisit on request.
6. **PDF workflows:** not built. Pillow can write a PDF from images, but reading PDFs needs a PDF parser (attack surface, licences of the common ones: pypdf BSD, pdfium BSD/Apache, MuPDF AGPL — the last is excluded). Revisit on request.
7. **Formats:**
   - **AVIF**: Pillow ≥ 11.2 wheels include it (BSD libavif/dav1d/aom) and it works in the build workspace (Pillow 12.3). Termux's `python-pillow` build is not confirmed to include it. Decision: keep it off the input allowlist until a phone self-test shows `features.check("avif")`; then add as input and output with fuzz tests.
   - **HEIC/HEIF**: needs `pillow-heif` (libheif LGPL-3.0 plus HEVC patent licensing). Not added.
   - **GIF**: already accepted as input (first frame). Animated output not built: frames multiply memory use on phones.
8. **GUI / companion app:** not built. The Android Image Toolbox app is the GUI; this project is the assistant-facing backend (see ADR-0006).

## Consequences

Tool count 7 → 11. Every new tool has unit tests (`tests/unit/test_edit.py`) and MCP tests (`tests/integration/test_edit_tools.py`); the self-test runs them all.
