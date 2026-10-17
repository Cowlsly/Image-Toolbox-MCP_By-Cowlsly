# Upstream licence and feasibility audit (M1)

- **Audited:** 2026-10-17, by Claude (scheduled session for Cowlsly)
- **Source:** `Cowlsly/ImageToolbox-For_Cowlsly-MCP` @ `3f53dbc` (branch `master`, 2026-10-16), a fork of [T8RIN/ImageToolbox](https://github.com/T8RIN/ImageToolbox)
- **Method:** shallow clone and static reading of manifests, Gradle files and source headers. The Android app was **not** built or run on a device in this audit.

## 1. Licence

| Item | Finding | Evidence |
| --- | --- | --- |
| Upstream licence | Apache License 2.0 | `LICENSE` at repo root; README "License" section |
| Copyright holder | T8RIN (Malik Mukhametzyanov) | Header in every source file, e.g. `core/data/.../coil/Base64Fetcher.kt` |
| Bundled `lib/*` modules | Apache-2.0 headers on 17 of 18; `lib/qrose` has no header in the first file checked | `grep` of first `.kt` file per module |
| Flavours | `foss` and `market`; `market` pulls Google Play Services / ML Kit (proprietary) | `app/build.gradle.kts`, `build-logic/.../ConfigureKotlinAndroid.kt`, `gradle/libs.versions.toml` |
| Other notable deps | Tesseract4Android (OCR), ONNX Runtime (AI tools), ML Kit (market only) | `gradle/libs.versions.toml` |

**Obligations for this repo (MIT):**
- We currently include **no upstream code**, so Apache-2.0 redistribution terms (§4: keep licence, notices, mark changes) do not yet apply to our files.
- We still credit T8RIN and link upstream in README and package docstring (courtesy + clarity), and must not imply endorsement or use the "Image Toolbox" trademark/logo as if official (Apache-2.0 §6 grants no trademark rights).
- If any upstream file is ever copied or adapted: keep its header, add a `NOTICE`/third-party section listing it, mark modifications, and check that file's own dependencies. Apache-2.0 code may be included in an MIT project under those conditions.
- Fork (`ImageToolbox-For_Cowlsly-MCP`) changes stay Apache-2.0.
- **VERIFY later:** `lib/qrose` licence (only relevant if reused; we don't plan to).

## 2. Android facts

| Item | Value | Evidence |
| --- | --- | --- |
| Package (applicationId) | `ru.tech.imageresizershrinker` (`.debug` suffix for debug) | `app/build.gradle.kts:35` |
| minSdk / targetSdk / compileSdk | 24 / 37 / 37 | `gradle/libs.versions.toml` |
| Modules | 68 `feature/*`, 10 `core/*`, 18 `lib/*` | directory listing |
| UI | Jetpack Compose + Decompose (`RootComponent`) | `feature/root/.../RootComponent.kt` |
| Storage permissions | Requests broad storage incl. `MANAGE_EXTERNAL_STORAGE` | `app/src/main/AndroidManifest.xml` |

## 3. Exported entry points (what another app can call)

| Entry point | Type | What it does | Returns a result to caller? |
| --- | --- | --- | --- |
| `AppActivity` MAIN/LAUNCHER | Activity | Opens app | No |
| `AppActivity` VIEW / REVIEW (image/*, pdf, zip, .jxl/.qoi/.itp) | Activity | Opens file in preview/editor UI | No |
| `AppActivity` SEND / SEND_MULTIPLE (`*/*`) | Activity (share target) | Receives shared files, user picks a tool | No |
| `AppActivity` EDIT / INSERT / INSERT_OR_EDIT | Activity | Opens editor UI | No (optional "return to external app after save" setting only switches app) |
| `AppActivity` action `shortcut` + int extra `screen_id` | Activity deep link | Navigates to a specific tool screen | No |
| `MediaPickerActivity` PICK / GET_CONTENT (image/*) | Activity | Image picker | Yes, but only a picked image URI — no processing |
| Quick-settings tiles (9, `exported=true`) | TileService | System tiles that open screens | n/a (system-bound) |
| `FileProvider` | ContentProvider | `exported=false` | n/a |
| `KeepAliveForegroundService`, `ScreenshotService` | Service | Internal | Not exported |

Evidence: `app/src/main/AndroidManifest.xml`, `feature/media-picker/.../AndroidManifest.xml`, `feature/quick-tiles/.../AndroidManifest.xml`, `core/ui/.../helper/ContextUtils.kt:304-335`, `RootComponent.handleDeeplinks`.

**Conclusion:** Image Toolbox has **no headless API**. Every exported route opens an interactive Compose screen; none takes processing parameters (size, quality, format) or returns a processed file. An AI client therefore cannot drive it today without a fork change (a new, permission-guarded, parameterised entry point) — that is roadmap M5, not a quick win.

## 4. Can upstream processing code be reused off-device? (option 3)

No, not practically. Processing lives in Android modules (35 files in `core/data`/`core/domain` import `android.graphics.Bitmap`; the rest is Compose/Hilt wired). Running it in Termux or on a desktop JVM would need the Android framework. Reuse only makes sense *inside* the fork for M5.

## 5. Feature feasibility matrix

Legend: **Local** = implement in our own engine (Pillow) · **Fork** = needs new entry point in the fork (M5) · **Defer** = later, needs separate licence/feasibility review · **No** = out of scope.

| Image Toolbox feature (module) | Local engine | Via Android app | Plan |
| --- | --- | --- | --- |
| Inspect / metadata (`image-preview`, `edit-exif`) | Yes (Pillow EXIF) | UI only | **Local — M2 first tool** |
| Format conversion JPEG/PNG/WebP (`format-conversion`, `resize-convert`) | Yes | UI only | Local — M3 |
| Resize (`resize-convert`, `limits-resize`) | Yes | UI only | Local — M3 |
| Compress to quality / target size (`weight-resize`, `compression-lab`) | Yes (quality search) | UI only | Local — M3 |
| Crop / rotate / flip (`crop`) | Yes | UI only | Local — M3 |
| Delete EXIF / GPS (`delete-exif`) | Yes | UI only | Local — M3/M6 (explicit request only) |
| Batch (`batch-rename`, multi-select) | Yes | UI only | Local — M4 |
| Watermark (`watermarking`) | Yes (Pillow draw) | UI only | Defer — M10 |
| Filters (`filters`, `core/filters`) | Partial (Pillow filters ≠ upstream look) | UI only | Defer — M10 |
| AVIF / HEIC / JXL (`jxl-tools`) | AVIF yes in this env; HEIC/JXL need extra plugins | UI only | Defer — M10, per-format |
| PDF tools (`pdf-tools`) | Partial | UI only | Defer — M10 |
| OCR (`recognize-text`, Tesseract) | Needs tesseract binary | UI only | Defer — M10 |
| Background removal / AI (`erase-background`, `ai-tools`, ONNX/ML Kit) | Heavy models | UI only | Defer — M10 |
| Open result in Image Toolbox for manual editing | n/a | **Yes today** (VIEW/EDIT/SEND intent) | Optional helper later (e.g. Termux `termux-open`) |

## 6. Decision input

See [ADR-0001](../adr/0001-processing-backend.md): use an independent local engine first; keep the Android bridge as a conditional M5 track.
