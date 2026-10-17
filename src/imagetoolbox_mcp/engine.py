"""Local image engine (ADR-0001, option 1): Pillow-backed, no network, read-only by default.

This module is deliberately independent of the MCP SDK so it can be unit-tested on its
own and reused if the transport layer changes.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from PIL import ExifTags, Image, UnidentifiedImageError

# Conservative defaults; callers may lower them, never raise them silently.
MAX_FILE_BYTES = 64 * 1024 * 1024  # 64 MiB
MAX_PIXELS = 64_000_000  # ~8000 x 8000; guards against decompression bombs

# EXIF tags we are willing to report by default. GPS and maker notes are never included.
SAFE_EXIF_TAGS = frozenset(
    {"Make", "Model", "Orientation", "DateTime", "Software", "XResolution", "YResolution"}
)


class EngineError(Exception):
    """Error with a stable machine-readable code and a plain-English message."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = MAX_FILE_BYTES
    max_pixels: int = MAX_PIXELS


DEFAULT_LIMITS = Limits()


def _check_regular_file(path: Path, limits: Limits) -> int:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        raise EngineError("not_found", "The image file does not exist.") from None
    except PermissionError:
        raise EngineError("permission_denied", "The image file cannot be read.") from None
    if stat.S_ISLNK(st.st_mode):
        raise EngineError("symlink_rejected", "Symbolic links are not accepted as inputs.")
    if not stat.S_ISREG(st.st_mode):
        raise EngineError("not_a_file", "The input is not a regular file.")
    if st.st_size > limits.max_file_bytes:
        raise EngineError(
            "file_too_large",
            f"The file is {st.st_size} bytes; the limit is {limits.max_file_bytes} bytes.",
        )
    return st.st_size


def inspect_image(path: str | os.PathLike[str], limits: Limits = DEFAULT_LIMITS) -> dict:
    """Return format, dimensions, mode, alpha, size and a small set of safe EXIF fields.

    Never modifies the file. Never returns GPS or other location metadata.
    """
    p = Path(path)
    size = _check_regular_file(p, limits)
    try:
        with Image.open(p) as im:
            width, height = im.size
            if width * height > limits.max_pixels:
                raise EngineError(
                    "too_many_pixels",
                    f"Image is {width}x{height}; the pixel limit is {limits.max_pixels}.",
                )
            exif = im.getexif()
            safe_exif = {}
            for tag_id, value in exif.items():
                name = ExifTags.TAGS.get(tag_id)
                if name in SAFE_EXIF_TAGS:
                    safe_exif[name] = value if isinstance(value, (int, str)) else str(value)
            has_gps = ExifTags.IFD.GPSInfo in exif
            return {
                "format": im.format,
                "width": width,
                "height": height,
                "mode": im.mode,
                "has_alpha": im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info,
                "frames": getattr(im, "n_frames", 1),
                "file_bytes": size,
                "orientation": safe_exif.get("Orientation", 1),
                "exif": safe_exif,
                "has_gps_metadata": has_gps,
            }
    except UnidentifiedImageError:
        raise EngineError("unsupported_format", "The file is not a recognised image.") from None
    except Image.DecompressionBombError:
        raise EngineError("too_many_pixels", "Image exceeds the pixel safety limit.") from None
