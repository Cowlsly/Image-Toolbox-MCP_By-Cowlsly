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


@dataclass
class _Loaded:
    """An upright, fully loaded first frame plus facts about the source."""

    image: Image.Image
    source_format: str | None
    input_bytes: int
    had_gps: bool
    icc: bytes | None
    warnings: list[str]


def _load_upright(src: str | os.PathLike[str], limits: Limits) -> _Loaded:
    """Open, check limits, take frame 0 and apply EXIF orientation to the pixels."""
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
                    f"frames_dropped: input has {frames} frames; only the first was used."
                )
            had_gps = ExifTags.IFD.GPSInfo in im.getexif()
            icc = im.info.get("icc_profile")
            im.seek(0)
            im.load()
            upright = ImageOps.exif_transpose(im)
            if upright is im:
                upright = im.copy()
    except UnidentifiedImageError:
        raise EngineError("unsupported_format", "The file is not a recognised image.") from None
    except Image.DecompressionBombError:
        raise EngineError("too_many_pixels", "Image exceeds the pixel safety limit.") from None
    except OSError:
        raise EngineError(
            "decode_failed", "The image could not be decoded (corrupt or truncated?)."
        ) from None
    return _Loaded(upright, src_format, in_bytes, had_gps, icc, warnings)


def _encode_new(
    loaded: _Loaded,
    image: Image.Image,
    target: str,
    out,
    stem: str,
    *,
    quality: int,
    lossless: bool,
    background: tuple[int, int, int],
) -> dict:
    """Prepare ``image`` for ``target``, strip metadata and write it as a new file."""
    fmt, ext, _ = CONVERT_FORMATS[target]
    warnings = list(loaded.warnings)
    pixels, more = _prepare_pixels(image, target, background)
    warnings.extend(more)
    # Drop every ancillary chunk (EXIF, XMP, text, comments); some encoders read
    # them from ``info`` implicitly. Only palette transparency survives.
    pixels.info = {k: v for k, v in pixels.info.items() if k == "transparency"}

    params: dict = {}
    if loaded.icc:
        params["icc_profile"] = loaded.icc
    if target == "jpeg":
        params.update(quality=int(quality), optimize=True)
        if lossless:
            warnings.append("lossless_ignored: JPEG is always lossy.")
    elif target == "webp":
        params.update(quality=int(quality), lossless=bool(lossless), method=4)
    else:
        params.update(optimize=True)

    def _write(fh):
        try:
            pixels.save(fh, format=fmt, **params)
        except (OSError, ValueError) as exc:
            raise EngineError(
                "encode_failed", f"Could not encode {fmt}: {type(exc).__name__}."
            ) from None

    dest = out.write_new(stem, ext, _write)
    return {
        "output_file": dest,
        "source_format": loaded.source_format,
        "format": fmt,
        "width": pixels.size[0],
        "height": pixels.size[1],
        "mode": pixels.mode,
        "input_bytes": loaded.input_bytes,
        "output_bytes": dest.stat().st_size,
        "metadata_stripped": True,
        "had_gps_metadata": loaded.had_gps,
        "icc_profile_kept": bool(loaded.icc),
        "warnings": warnings,
    }


def _check_encode_args(target: str, quality: int) -> None:
    if target not in CONVERT_FORMATS:
        raise EngineError(
            "unsupported_target", f"Target format must be one of {sorted(CONVERT_FORMATS)}."
        )
    if not 1 <= int(quality) <= 100:
        raise EngineError("invalid_argument", "Quality must be between 1 and 100.")


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
    _check_encode_args(target, quality)
    loaded = _load_upright(src, limits)
    if (
        loaded.source_format == "JPEG"
        and target in ("png", "webp")
        and (lossless or target == "png")
    ):
        loaded.warnings.append(
            "no_quality_gain: converting from JPEG cannot restore detail already lost."
        )
    return _encode_new(
        loaded,
        loaded.image,
        target,
        out,
        stem,
        quality=quality,
        lossless=lossless,
        background=background,
    )


# --- resize (milestone M3) ----------------------------------------------------------------

MAX_SIDE = 16384  # largest output width/height accepted
FIT_MODES = ("contain", "cover", "exact")
RESAMPLE_FILTERS = {
    "lanczos": Image.Resampling.LANCZOS,
    "bicubic": Image.Resampling.BICUBIC,
    "bilinear": Image.Resampling.BILINEAR,
    "nearest": Image.Resampling.NEAREST,
}
# Pillow format name -> our target key, for "keep the source format".
_FORMAT_TO_TARGET = {fmt: key for key, (fmt, _, _) in CONVERT_FORMATS.items()}


def default_target_for(source_format: str | None) -> str:
    """Target used when the caller does not pick one: the source format, else PNG."""
    return _FORMAT_TO_TARGET.get(source_format or "", "png")


def plan_resize(
    src_size: tuple[int, int],
    width: int | None,
    height: int | None,
    fit: str = "contain",
    allow_upscale: bool = False,
) -> tuple[tuple[int, int], tuple[int, int], list[str]]:
    """Pure geometry. Return (scaled size, final size, warnings).

    ``contain``: fit inside the box, keep aspect (one side may be omitted).
    ``cover``: fill the box, keep aspect, centre-crop the overflow (both sides needed).
    ``exact``: stretch to exactly width x height (both sides needed).
    Without ``allow_upscale``, ``contain`` never enlarges (keeps the source size, with a
    warning) and ``cover``/``exact`` refuse a box larger than the source.
    """
    if fit not in FIT_MODES:
        raise EngineError("invalid_argument", f"fit must be one of {list(FIT_MODES)}.")
    for name, v in (("width", width), ("height", height)):
        if v is not None and not 1 <= int(v) <= MAX_SIDE:
            raise EngineError("invalid_argument", f"{name} must be between 1 and {MAX_SIDE}.")
    if width is None and height is None:
        raise EngineError("invalid_argument", "Give a width, a height, or both.")
    if fit != "contain" and (width is None or height is None):
        raise EngineError("invalid_argument", f"fit='{fit}' needs both width and height.")
    sw, sh = src_size
    warnings: list[str] = []

    if fit == "contain":
        scales = []
        if width is not None:
            scales.append(width / sw)
        if height is not None:
            scales.append(height / sh)
        scale = min(scales)
        if scale > 1 and not allow_upscale:
            warnings.append(
                "upscale_skipped: the image is already smaller than the requested size; "
                "kept its original size (set allow_upscale to enlarge)."
            )
            scale = 1.0
        size = (max(1, round(sw * scale)), max(1, round(sh * scale)))
        return size, size, warnings

    if not allow_upscale and (width > sw or height > sh):
        raise EngineError(
            "upscale_refused",
            f"The source is {sw}x{sh}; {width}x{height} would enlarge it. "
            "Set allow_upscale to true to allow this.",
        )
    if fit == "exact":
        if abs((width / sw) / (height / sh) - 1) > 0.01:
            warnings.append("aspect_changed: the image was stretched to the exact size.")
        return (width, height), (width, height), warnings
    scale = max(width / sw, height / sh)
    scaled = (max(width, round(sw * scale)), max(height, round(sh * scale)))
    return scaled, (width, height), warnings


def _resample_ready(im: Image.Image, resample: int) -> Image.Image:
    """Convert modes Pillow cannot filter (palette, 1-bit, 16-bit) to ones it can."""
    if resample == Image.Resampling.NEAREST and im.mode in ("1", "P", "L", "RGB", "RGBA"):
        return im
    if im.mode in ("L", "LA", "RGB", "RGBA", "CMYK", "I", "F"):
        return im
    if _has_alpha(im):
        return im.convert("RGBA")
    if im.mode == "1":
        return im.convert("L")
    if im.mode.startswith("I;16"):
        return im.convert("I")
    return im.convert("RGB")


def resize_image(
    src: str | os.PathLike[str],
    out,
    stem: str | None,
    *,
    width: int | None = None,
    height: int | None = None,
    fit: str = "contain",
    resample: str = "lanczos",
    allow_upscale: bool = False,
    target: str | None = None,
    quality: int = DEFAULT_QUALITY,
    lossless: bool = False,
    background: tuple[int, int, int] = (255, 255, 255),
    limits: Limits = DEFAULT_LIMITS,
) -> dict:
    """Resize ``src`` and write a *new* file in ``out``. Sizes refer to the upright image.

    ``stem`` None means ``<source name>-<W>x<H>``. ``target`` None keeps the source format
    when it is JPEG/PNG/WebP, otherwise PNG.
    """
    if resample not in RESAMPLE_FILTERS:
        raise EngineError("invalid_argument", f"resample must be one of {list(RESAMPLE_FILTERS)}.")
    if target is not None:
        _check_encode_args(target, quality)
    elif not 1 <= int(quality) <= 100:
        raise EngineError("invalid_argument", "Quality must be between 1 and 100.")
    from .output import default_stem, validate_stem  # local import: output imports engine

    # Validate arguments before touching the file (cheap, and nothing is opened).
    plan_resize((1, 1), width, height, fit, allow_upscale=True)
    if stem is not None:
        stem = validate_stem(stem)
    loaded = _load_upright(src, limits)
    im = loaded.image
    scaled, final, warnings = plan_resize(im.size, width, height, fit, allow_upscale)
    if final[0] * final[1] > limits.max_pixels or scaled[0] * scaled[1] > limits.max_pixels:
        raise EngineError(
            "too_many_pixels",
            f"The result would be {final[0]}x{final[1]}; the pixel limit is {limits.max_pixels}.",
        )
    loaded.warnings.extend(warnings)
    if target is None:
        target = default_target_for(loaded.source_format)
        if CONVERT_FORMATS[target][0] != loaded.source_format:
            loaded.warnings.append(
                f"format_changed: {loaded.source_format} output is not supported; saved as PNG."
            )
    flt = RESAMPLE_FILTERS[resample]
    work = im if scaled == im.size else _resample_ready(im, flt).resize(scaled, flt)
    if im.mode.startswith("I;16") and work.mode == "I":
        work = work.convert(im.mode)  # back to 16-bit (clamped) so PNG stays 16-bit
    if final != scaled:
        left = (scaled[0] - final[0]) // 2
        top = (scaled[1] - final[1]) // 2
        work = work.crop((left, top, left + final[0], top + final[1]))
    if stem is None:
        base = default_stem(Path(src))[: 100 - 12]
        stem = f"{base}-{final[0]}x{final[1]}"
    result = _encode_new(
        loaded,
        work,
        target,
        out,
        stem,
        quality=quality,
        lossless=lossless,
        background=background,
    )
    result["source_width"], result["source_height"] = im.size
    return result
