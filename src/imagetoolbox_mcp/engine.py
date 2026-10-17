"""Local image engine (ADR-0001, option 1): Pillow-backed, no network, read-only by default.

This module is deliberately independent of the MCP SDK so it can be unit-tested on its
own and reused if the transport layer changes.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

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


# --- conversion (milestone M3) ------------------------------------------------------------

# Target format -> (Pillow format name, file extension, modes the encoder accepts as-is).
CONVERT_FORMATS = {
    "jpeg": ("JPEG", "jpg", ("RGB", "L", "CMYK")),
    "png": ("PNG", "png", ("1", "L", "LA", "P", "RGB", "RGBA", "I;16")),
    "webp": ("WEBP", "webp", ("RGB", "RGBA")),
}
DEFAULT_QUALITY = 90


def _has_alpha(im: Image.Image) -> bool:
    return im.mode in ("RGBA", "LA", "PA", "La", "RGBa") or "transparency" in im.info


def _prepare_pixels(im: Image.Image, target: str, background: tuple[int, int, int]):
    """Return (image ready for the encoder, warnings)."""
    warnings: list[str] = []
    _, _, ok_modes = CONVERT_FORMATS[target]
    alpha = _has_alpha(im)
    if target == "jpeg" and alpha:
        rgba = im.convert("RGBA")
        flat = Image.new("RGB", rgba.size, background)
        flat.paste(rgba, mask=rgba.getchannel("A"))
        warnings.append(
            "alpha_flattened: JPEG has no transparency; it was filled with the background colour."
        )
        return flat, warnings
    if im.mode in ok_modes and not (im.mode == "P" and target != "png"):
        return im, warnings
    if alpha:
        return im.convert("RGBA"), warnings
    if im.mode in ("1", "L", "I", "I;16", "F") and target == "jpeg":
        return im.convert("L") if im.mode in ("1", "L") else im.convert("RGB"), warnings
    return im.convert("RGB"), warnings


def convert_image(
    src: str | os.PathLike[str],
    target: str,
    out,
    stem: str,
    *,
    quality: int = DEFAULT_QUALITY,
    lossless: bool = False,
    background: tuple[int, int, int] = (255, 255, 255),
    limits: Limits = DEFAULT_LIMITS,
) -> dict:
    """Convert ``src`` to ``target`` (jpeg/png/webp) as a *new* file in ``out`` (OutputDir).

    EXIF orientation is applied to the pixels; EXIF/XMP/GPS are not copied; the ICC profile
    is kept. Animated inputs: only the first frame is converted (a warning says so).
    """
    if target not in CONVERT_FORMATS:
        raise EngineError(
            "unsupported_target", f"Target format must be one of {sorted(CONVERT_FORMATS)}."
        )
    if not 1 <= int(quality) <= 100:
        raise EngineError("invalid_argument", "Quality must be between 1 and 100.")
    fmt, ext, _ = CONVERT_FORMATS[target]
    p = Path(src)
    in_bytes = _check_regular_file(p, limits)
    warnings: list[str] = []
    try:
        with Image.open(p) as im:
            w, h = im.size
            if w * h > limits.max_pixels:
                raise EngineError(
                    "too_many_pixels", f"Image is {w}x{h}; the pixel limit is {limits.max_pixels}."
                )
            src_format = im.format
            frames = getattr(im, "n_frames", 1)
            if frames > 1:
                warnings.append(
                    f"frames_dropped: input has {frames} frames; only the first was converted."
                )
            had_gps = ExifTags.IFD.GPSInfo in im.getexif()
            icc = im.info.get("icc_profile")
            im.seek(0)
            im.load()
            upright = ImageOps.exif_transpose(im)
            pixels, more = _prepare_pixels(upright, target, background)
            warnings.extend(more)
            # Drop every ancillary chunk (EXIF, XMP, text, comments); some encoders read
            # them from ``info`` implicitly. Only palette transparency survives.
            pixels.info = {k: v for k, v in pixels.info.items() if k == "transparency"}
    except UnidentifiedImageError:
        raise EngineError("unsupported_format", "The file is not a recognised image.") from None
    except Image.DecompressionBombError:
        raise EngineError("too_many_pixels", "Image exceeds the pixel safety limit.") from None
    except OSError:
        raise EngineError(
            "decode_failed", "The image could not be decoded (corrupt or truncated?)."
        ) from None

    params: dict = {}
    if icc:
        params["icc_profile"] = icc
    if target == "jpeg":
        params.update(quality=int(quality), optimize=True)
        if lossless:
            warnings.append("lossless_ignored: JPEG is always lossy.")
    elif target == "webp":
        params.update(quality=int(quality), lossless=bool(lossless), method=4)
    else:
        params.update(optimize=True)
    if src_format == "JPEG" and target in ("png", "webp") and (lossless or target == "png"):
        warnings.append("no_quality_gain: converting from JPEG cannot restore detail already lost.")

    def _write(fh):
        try:
            pixels.save(fh, format=fmt, **params)
        except (OSError, ValueError) as exc:
            raise EngineError(
                "encode_failed", f"Could not encode {fmt}: {type(exc).__name__}."
            ) from None

    dest = out.write_new(stem, ext, _write)
    out_bytes = dest.stat().st_size
    return {
        "output_file": dest,
        "source_format": src_format,
        "format": fmt,
        "width": pixels.size[0],
        "height": pixels.size[1],
        "mode": pixels.mode,
        "input_bytes": in_bytes,
        "output_bytes": out_bytes,
        "metadata_stripped": True,
        "had_gps_metadata": had_gps,
        "icc_profile_kept": bool(icc),
        "warnings": warnings,
    }
