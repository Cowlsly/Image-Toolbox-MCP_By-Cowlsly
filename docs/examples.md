# Examples

These are things you can ask your assistant once the server is connected (see [clients.md](clients.md)). The tool calls it should make are shown so you can check what happened. Everything runs **on your device**: images never leave the phone or computer, the server makes no network requests, and results appear in the output folder (`imagetoolbox-out/` inside your input folder).

## Turn every JPEG in a folder into PNG

> "Convert all the JPEGs in holiday to PNG."

```json
{"tool": "image_batch", "arguments": {"operation": "convert", "folder": "holiday",
 "pattern": "*.jpg", "options": {"format": "png"}, "dry_run": true}}
```

Run it once with `dry_run: true` to see the file list, then again without it. A manifest `batch-convert-<time>.json` lists every source, output and checksum. If the run is interrupted, repeat it with `"resume_from": "batch-convert-<time>.json"` and finished files are skipped.

PNG cannot restore detail a JPEG already lost; it only stops further loss.

## Make photos small enough to send

> "Make the photos in screenshots at most 1600 px wide and under 300 KB."

```json
{"tool": "image_recipe", "arguments": {"path": "screenshots/a.png", "format": "jpeg",
 "steps": [{"op": "resize", "width": 1600}]}}
{"tool": "image_batch", "arguments": {"operation": "compress", "folder": "imagetoolbox-out",
 "pattern": "*-recipe.jpg", "options": {"max_bytes": 300000}}}
```

Or in one pass per folder: `image_batch` with `operation: "resize"`, then `operation: "compress"`.

## Remove location data before sharing

> "Strip the GPS from beach.jpg."

```json
{"tool": "image_convert", "arguments": {"path": "beach.jpg", "format": "jpeg", "quality": 95}}
```

Every output of every tool drops EXIF, XMP and GPS. `image_inspect` shows `has_gps_metadata: true/false` for the original so you can check. To add only your own credit back, use `image_tag`:

```json
{"tool": "image_tag", "arguments": {"path": "beach.jpg", "artist": "Cowlsly", "copyright": "2026 Cowlsly"}}
```

## Watermark a set of product photos

```json
{"tool": "image_batch", "arguments": {"operation": "watermark", "folder": "shop",
 "options": {"text": "© Cowlsly", "position": "bottom-right", "opacity": 0.6, "size_percent": 4}}}
```

## Brighten and square up one photo

```json
{"tool": "image_recipe", "arguments": {"path": "me.jpg", "steps": [
  {"op": "adjust", "brightness": 1.15, "contrast": 1.05},
  {"op": "crop", "aspect": "1:1"},
  {"op": "resize", "width": 1080}]}}
```

The result repeats the steps exactly; save them and pass them again to get the same output for another photo.

## Local vs remote

| | This server today | A remote/hosted server (not built) |
| --- | --- | --- |
| Where images are processed | On your device | On someone's server |
| Network needed | No (works offline) | Yes |
| Who can call it | Only the client that started it (stdio) | Anyone with the URL + login |
| Works with the Claude/ChatGPT phone apps | No (they need a public HTTPS server) | Would, with OAuth |

Why remote is not built yet: [ADR-0003](adr/0003-transports-and-phone-clients.md).
