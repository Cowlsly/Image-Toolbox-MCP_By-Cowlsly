# Error codes in plain language

Every failed tool call starts with a code in square brackets, then a sentence. The code never changes, so assistants and scripts can rely on it. No error ever contains a full path on your device.

| Code | What it means | What to do |
| --- | --- | --- |
| `outside_root` | The file is not inside the folder you allowed. | Move the file into that folder or use a path relative to it. |
| `symlink_rejected` | The path is a shortcut (symbolic link). | Use the real file. |
| `not_found` | No file with that name. | Check spelling; `image_batch` with `dry_run` lists files. |
| `not_a_file` / `not_a_folder` | You gave a folder where a file was needed, or the other way round. | Fix the path. |
| `invalid_path` | The path is empty, too long or contains forbidden characters. | Use a simple relative path. |
| `permission_denied` | The system will not let the server read it. | On Android run `termux-setup-storage`; check file permissions. |
| `unsupported_format` | Not one of JPEG, PNG, WebP, GIF, TIFF, BMP (or not an image). | Convert it elsewhere first. |
| `unsupported_target` | Output format must be jpeg, png or webp. | Pick one of those. |
| `file_too_large` | Over 64 MiB. | Use a smaller file. |
| `too_many_pixels` | Over 64 megapixels (or the result would be). | Resize smaller. |
| `decode_failed` | The file is damaged or not really that format. | Re-export the image. |
| `out_of_memory` | Not enough free memory. | Close other apps, or resize first. |
| `timed_out` | The operation took longer than the `--isolate` limit and was stopped. | Use a smaller image or raise the limit. |
| `invalid_argument` | A setting is missing or out of range (the message says which). | Change that setting. |
| `invalid_name` | `output_name` has a folder, an extension or odd characters. | Letters, digits, space, `.`, `_`, `-` only. |
| `crop_out_of_bounds` | The crop box goes past the image edge. | Use `image_inspect` for the real size. |
| `upscale_refused` | That size would enlarge the image. | Set `allow_upscale: true` if you really want it. |
| `output_unavailable` | The output folder cannot be created or written. | Check free space and permissions; batches can `retries`. |
| `name_exhausted` | 1000 files with that name already exist. | Clean up the output folder. |
| `encode_failed` | The output could not be written in that format. | Try another format. |
| `internal_error` | A bug. Nothing was overwritten. | Report it with the steps (no photos needed). |

Warnings (not errors) appear in a result's `warnings` list, e.g. `lossy_reencode`, `upscale_skipped`, `frames_dropped`, `target_not_met`, `time_budget_reached`.
