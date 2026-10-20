"""Local image engine (ADR-0001, option 1): Pillow-backed, no network, read-only by default.

This module is deliberately independent of the MCP SDK so it can be unit-tested on its
own and reused if the transport layer changes.
"""

from __future__ import annotations

import contextlib
import errno
import io
import os
import stat
import struct
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

# Conservative defaults; callers may lower them, never raise them silently.
MAX_FILE_BYTES = 64 * 1024 * 1024  # 64 MiB
MAX_PIXELS = 64_000_000  # ~8000 x 8000; guards against decompression bombs
# Wall-clock budget for image_compress's max_bytes search (M6, threat model T6). A 64 MP
# PNG palette search took well over a minute in the cloud test; a phone is slower.
MAX_SEARCH_SECONDS = 30.0

# EXIF tags we are willing to report by default. GPS and maker notes are never included.
SAFE_EXIF_TAGS = frozenset(
    {"Make", "Model", "Orientation", "DateTime", "Software", "XResolution", "YResolution"}
)


# Decoders we let Pillow use (M6, threat model T4). Everything else -- EPS (which would
# start Ghostscript), PSD, ICNS, FITS, ... -- is refused as ``unsupported_format`` before
# its plugin parses a byte. Multi-picture JPEGs from phone cameras still open: Pillow's
# JPEG opener hands them to its MPO class (``im.format == "MPO"``).
ALLOWED_INPUT_FORMATS = ("JPEG", "PNG", "WEBP", "GIF", "TIFF", "BMP")

# Exceptions Pillow's parsers raise on malformed input (found by fuzzing, run 10). They are
# mapped to ``decode_failed`` so a bad file never surfaces as an unexplained crash.
_DECODE_ERRORS = (
    OSError,
    ValueError,
    SyntaxError,
    IndexError,
    KeyError,
    TypeError,
    EOFError,
    struct.error,
    ZeroDivisionError,
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
    max_search_seconds: float = MAX_SEARCH_SECONDS


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


_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)  # final component must not be a symlink
    | getattr(os, "O_NONBLOCK", 0)  # a FIFO swapped in must not hang the open
    | getattr(os, "O_BINARY", 0)
)


@contextlib.contextmanager
def _open(p: Path, limits: Limits = DEFAULT_LIMITS):
    """Open ``p`` race-safely and yield a Pillow image restricted to the allowed decoders.

    ``_check_regular_file`` looked at the path with ``lstat``; between that check and the
    open the file could be swapped for a symlink or FIFO (threat T2). So the file is opened
    with ``O_NOFOLLOW`` and the *open descriptor* is checked again with ``fstat``; Pillow
    then reads from that descriptor, never from the path.
    """
    try:
        fd = os.open(p, _OPEN_FLAGS)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise EngineError("symlink_rejected", "Symbolic links are not accepted.") from None
        if exc.errno == errno.ENOENT:
            raise EngineError("not_found", "The image file does not exist.") from None
        raise EngineError("permission_denied", "The image file cannot be read.") from None
    with os.fdopen(fd, "rb") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise EngineError("not_a_file", "The input is not a regular file.")
        if st.st_size > limits.max_file_bytes:
            raise EngineError("file_too_large", "The file grew past the size limit.")
        if hasattr(os, "set_blocking"):
            os.set_blocking(fh.fileno(), True)
        with Image.open(fh, formats=ALLOWED_INPUT_FORMATS) as im:
            yield im


def _decode_error(exc: BaseException) -> EngineError:
    """Translate an exception raised while parsing/decoding into a stable EngineError."""
    if isinstance(exc, UnidentifiedImageError):
        return EngineError(
            "unsupported_format",
            "The file is not a recognised image (supported: JPEG, PNG, WebP, GIF, TIFF, BMP).",
        )
    if isinstance(exc, Image.DecompressionBombError):
        return EngineError("too_many_pixels", "Image exceeds the pixel safety limit.")
    if isinstance(exc, MemoryError):
        return EngineError("out_of_memory", "Not enough memory to decode this image.")
    return EngineError("decode_failed", "The image could not be decoded (corrupt or truncated?).")


def inspect_image(path: str | os.PathLike[str], limits: Limits = DEFAULT_LIMITS) -> dict:
    """Return format, dimensions, mode, alpha, size and a small set of safe EXIF fields.

    Never modifies the file. Never returns GPS or other location metadata.
    """
    p = Path(path)
    size = _check_regular_file(p, limits)
    try:
        with _open(p, limits) as im:
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
    except EngineError:
        raise
    except (*_DECODE_ERRORS, Image.DecompressionBombError, MemoryError) as exc:
        raise _decode_error(exc) from None


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
        with _open(p, limits) as im:
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
    except EngineError:
        raise
    except (*_DECODE_ERRORS, Image.DecompressionBombError, MemoryError) as exc:
        raise _decode_error(exc) from None
    return _Loaded(upright, src_format, in_bytes, had_gps, icc, warnings)


def _encoder_setup(
    loaded: _Loaded,
    image: Image.Image,
    target: str,
    *,
    quality: int,
    lossless: bool,
    background: tuple[int, int, int],
):
    """Return (pixels ready for ``target`` with metadata stripped, encoder params, warnings)."""
    fmt, _, _ = CONVERT_FORMATS[target]
    warnings = list(loaded.warnings)
    pixels, more = _prepare_pixels(image, target, background)
    warnings.extend(more)
    # Drop every ancillary chunk (EXIF, XMP, text, comments); some encoders read
    # them from ``info`` implicitly. Only palette transparency survives.
    # (``image`` is always our private decoded copy, so editing its ``info`` is safe.)
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
    return pixels, params, warnings


def _save(pixels: Image.Image, fh, target: str, params: dict) -> None:
    fmt = CONVERT_FORMATS[target][0]
    try:
        pixels.save(fh, format=fmt, **params)
    except (OSError, ValueError) as exc:
        raise EngineError(
            "encode_failed", f"Could not encode {fmt}: {type(exc).__name__}."
        ) from None


def _result(loaded: _Loaded, pixels: Image.Image, target: str, dest: Path, warnings) -> dict:
    return {
        "output_file": dest,
        "source_format": loaded.source_format,
        "format": CONVERT_FORMATS[target][0],
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
    pixels, params, warnings = _encoder_setup(
        loaded, image, target, quality=quality, lossless=lossless, background=background
    )
    dest = out.write_new(
        stem, CONVERT_FORMATS[target][1], lambda fh: _save(pixels, fh, target, params)
    )
    return _result(loaded, pixels, target, dest, warnings)


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


def _pick_target(loaded: _Loaded, target: str | None) -> str:
    """``target`` if given, else the source format (PNG + ``format_changed`` warning)."""
    if target is not None:
        return target
    target = default_target_for(loaded.source_format)
    if CONVERT_FORMATS[target][0] != loaded.source_format:
        loaded.warnings.append(
            f"format_changed: {loaded.source_format} output is not supported; saved as PNG."
        )
    return target


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
    target = _pick_target(loaded, target)
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


# --- compress (milestone M3) --------------------------------------------------------------

DEFAULT_COMPRESS_QUALITY = 80
MIN_TARGET_BYTES = 1024
_QUANTIZE_MODES = ("RGB", "RGBA")
PALETTE_LADDER = (2, 4, 8, 16, 32, 64, 128, 256)


def _quantize(pixels: Image.Image, colors: int) -> Image.Image:
    """Reduce to a ``colors``-entry palette (PNG). Alpha is kept via FASTOCTREE."""
    src = (
        pixels
        if pixels.mode in _QUANTIZE_MODES
        else pixels.convert("RGBA" if _has_alpha(pixels) else "RGB")
    )
    method = Image.Quantize.FASTOCTREE if src.mode == "RGBA" else Image.Quantize.MEDIANCUT
    return src.quantize(colors=colors, method=method, dither=Image.Dither.FLOYDSTEINBERG)


def _encoded(pixels: Image.Image, target: str, params: dict) -> bytes:
    buf = io.BytesIO()
    _save(pixels, buf, target, params)
    return buf.getvalue()


def compress_image(
    src: str | os.PathLike[str],
    out,
    stem: str | None,
    *,
    target: str | None = None,
    quality: int | None = None,
    max_bytes: int | None = None,
    min_quality: int = 10,
    colors: int | None = None,
    background: tuple[int, int, int] = (255, 255, 255),
    limits: Limits = DEFAULT_LIMITS,
) -> dict:
    """Re-encode ``src`` smaller and write a *new* file in ``out``.

    JPEG/WebP: fixed ``quality`` (default 80), or ``max_bytes`` = the highest quality in
    ``[min_quality, 95]`` whose output fits (binary search). PNG: lossless optimisation,
    optional ``colors`` (2-256) palette reduction; with ``max_bytes`` the largest palette in
    ``PALETTE_LADDER`` (2, 4, ... 256 colours) that fits is used.
    If the target cannot be met, the smallest attempt is kept with a ``target_not_met``
    warning. ``stem`` None means ``<source name>-compressed``.
    """
    from .output import default_stem, validate_stem  # local import: output imports engine

    if quality is not None and max_bytes is not None:
        raise EngineError("invalid_argument", "Give either quality or max_bytes, not both.")
    if quality is not None and not 1 <= int(quality) <= 100:
        raise EngineError("invalid_argument", "Quality must be between 1 and 100.")
    if max_bytes is not None and not MIN_TARGET_BYTES <= int(max_bytes) <= limits.max_file_bytes:
        raise EngineError(
            "invalid_argument",
            f"max_bytes must be between {MIN_TARGET_BYTES} and {limits.max_file_bytes}.",
        )
    if not 1 <= int(min_quality) <= 95:
        raise EngineError("invalid_argument", "min_quality must be between 1 and 95.")
    if colors is not None and not 2 <= int(colors) <= 256:
        raise EngineError("invalid_argument", "colors must be between 2 and 256.")
    if target is not None:
        _check_encode_args(target, DEFAULT_COMPRESS_QUALITY)
    if stem is not None:
        stem = validate_stem(stem)
    loaded = _load_upright(src, limits)
    target = _pick_target(loaded, target)
    if colors is not None and target != "png":
        loaded.warnings.append("colors_ignored: palette reduction only applies to PNG.")
    if quality is not None and target == "png":
        loaded.warnings.append("quality_ignored: PNG is lossless; use colors or max_bytes.")

    q0 = DEFAULT_COMPRESS_QUALITY if quality is None else int(quality)
    pixels, params, warnings = _encoder_setup(
        loaded, loaded.image, target, quality=q0, lossless=False, background=background
    )
    quality_used: int | None = None
    colors_used: int | None = None
    deadline = time.monotonic() + limits.max_search_seconds
    budget_hit = False

    if target == "png":
        if colors is not None:
            pixels = _quantize(pixels, int(colors))
            colors_used = int(colors)
        data = _encoded(pixels, target, params)
        if max_bytes is not None and len(data) > max_bytes and colors is None:
            # Most colours that fit: walk the ladder down from 256 and stop at the first fit.
            # (Not a binary search: PNG size is not monotonic in palette size, e.g. 16
            # colours packs to 4-bit and can be larger than 32.) Probes skip ``optimize``,
            # the slow part; optimisation only shrinks the final file further.
            fast = {k: v for k, v in params.items() if k != "optimize"}
            best = None  # (colors, image) that fits, with the most colours
            smallest = None  # (size, colors, image) fallback if nothing fits
            for n in reversed(PALETTE_LADDER):
                if smallest is not None and time.monotonic() > deadline:
                    budget_hit = True
                    break
                cand = _quantize(pixels, n)
                size = len(_encoded(cand, target, fast))
                if smallest is None or size < smallest[0]:
                    smallest = (size, n, cand)
                if size <= max_bytes:
                    best = (n, cand)
                    break
            colors_used, pixels = best if best is not None else smallest[1:]
            # Over budget: skip the slow optimised re-encode; the probe result is valid PNG.
            data = _encoded(pixels, target, fast if budget_hit else params)
            warnings.append(
                f"palette_reduced: reduced to {colors_used} colours to approach max_bytes."
            )
    else:
        if max_bytes is None:
            quality_used = q0
            data = _encoded(pixels, target, params)
        else:
            best = None
            smallest = None
            lo, hi = int(min_quality), 95
            while lo <= hi:
                if smallest is not None and time.monotonic() > deadline:
                    budget_hit = True
                    break
                mid = (lo + hi) // 2
                cdata = _encoded(pixels, target, {**params, "quality": mid})
                if smallest is None or len(cdata) < len(smallest[1]):
                    smallest = (mid, cdata)
                if len(cdata) <= max_bytes:
                    best = (mid, cdata)
                    lo = mid + 1
                else:
                    hi = mid - 1
            quality_used, data = best if best is not None else smallest

    if budget_hit:
        warnings.append(
            f"time_budget_reached: the max_bytes search stopped after "
            f"{limits.max_search_seconds:g} s with the best result so far. Resize the image "
            "first for a faster, better fit."
        )
    target_met = None if max_bytes is None else len(data) <= max_bytes
    if target_met is False:
        warnings.append(
            f"target_not_met: the smallest result is {len(data)} bytes, above max_bytes "
            f"({max_bytes}). Try image_resize first, a lower min_quality, or WebP."
        )
    if len(data) >= loaded.input_bytes:
        warnings.append(
            "larger_than_source: the result is not smaller than the original "
            f"({len(data)} vs {loaded.input_bytes} bytes); the original may already be "
            "well compressed."
        )
    if stem is None:
        stem = f"{default_stem(Path(src))[: 100 - 11]}-compressed"
    dest = out.write_new(stem, CONVERT_FORMATS[target][1], lambda fh: fh.write(data))
    result = _result(loaded, pixels, target, dest, warnings)
    result.update(
        quality_used=quality_used,
        colors_used=colors_used,
        max_bytes=max_bytes,
        target_met=target_met,
        saved_bytes=loaded.input_bytes - result["output_bytes"],
    )
    return result


# --- rotate / flip and crop (milestone M3) ------------------------------------------------

ROTATIONS = (0, 90, 180, 270)  # degrees clockwise, as the user sees the upright image
FLIPS = ("horizontal", "vertical")
# Clockwise degrees -> Pillow transpose (Pillow's ROTATE_90 is counter-clockwise).
_ROTATE_OPS = {
    90: Image.Transpose.ROTATE_270,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}
_FLIP_OPS = {
    "horizontal": Image.Transpose.FLIP_LEFT_RIGHT,
    "vertical": Image.Transpose.FLIP_TOP_BOTTOM,
}
MAX_ASPECT_TERM = 10000


def _lossy_note(target: str, lossless: bool) -> str | None:
    if target == "jpeg" or (target == "webp" and not lossless):
        return (
            "lossy_reencode: the result was re-encoded with lossy compression; "
            "use format 'png' (or lossless WebP) for a pixel-exact copy."
        )
    return None


def _check_quality(target: str | None, quality: int) -> None:
    if target is not None:
        _check_encode_args(target, quality)
    elif not 1 <= int(quality) <= 100:
        raise EngineError("invalid_argument", "Quality must be between 1 and 100.")


def rotate_flip_image(
    src: str | os.PathLike[str],
    out,
    stem: str | None,
    *,
    rotate: int = 0,
    flip: str | None = None,
    target: str | None = None,
    quality: int = DEFAULT_QUALITY,
    lossless: bool = False,
    background: tuple[int, int, int] = (255, 255, 255),
    limits: Limits = DEFAULT_LIMITS,
) -> dict:
    """Rotate by 90/180/270 degrees clockwise and/or flip, writing a *new* file in ``out``.

    Directions refer to the upright image (EXIF orientation already applied). Rotation is
    applied first, then the flip. The pixel moves are exact; only a lossy output format
    (JPEG, lossy WebP) re-encodes with loss. ``stem`` None means e.g. ``<source>-rot90-flipH``.
    """
    from .output import default_stem, validate_stem  # local import: output imports engine

    if rotate not in ROTATIONS:
        raise EngineError("invalid_argument", f"rotate must be one of {list(ROTATIONS)}.")
    if flip is not None and flip not in FLIPS:
        raise EngineError("invalid_argument", f"flip must be one of {list(FLIPS)} or omitted.")
    if rotate == 0 and flip is None:
        raise EngineError("invalid_argument", "Nothing to do: give rotate (90/180/270) or flip.")
    _check_quality(target, quality)
    if stem is not None:
        stem = validate_stem(stem)
    loaded = _load_upright(src, limits)
    im = loaded.image
    target = _pick_target(loaded, target)
    work = im
    if rotate:
        work = work.transpose(_ROTATE_OPS[rotate])
    if flip is not None:
        work = work.transpose(_FLIP_OPS[flip])
    note = _lossy_note(target, lossless)
    if note:
        loaded.warnings.append(note)
    if stem is None:
        parts = []
        if rotate:
            parts.append(f"rot{rotate}")
        if flip is not None:
            parts.append("flipH" if flip == "horizontal" else "flipV")
        suffix = "-" + "-".join(parts)
        stem = default_stem(Path(src))[: 100 - len(suffix)] + suffix
    result = _encode_new(
        loaded, work, target, out, stem, quality=quality, lossless=lossless, background=background
    )
    result.update(rotate=rotate, flip=flip, source_width=im.size[0], source_height=im.size[1])
    return result


def parse_aspect(aspect: str) -> tuple[int, int]:
    """Parse ``"W:H"`` (e.g. ``"16:9"``, ``"1:1"``) into two positive integers."""
    parts = str(aspect).strip().split(":")
    try:
        if len(parts) != 2:
            raise ValueError
        aw, ah = int(parts[0]), int(parts[1])
    except ValueError:
        raise EngineError(
            "invalid_argument", "aspect must look like 'W:H', e.g. '1:1', '4:3' or '16:9'."
        ) from None
    if not (1 <= aw <= MAX_ASPECT_TERM and 1 <= ah <= MAX_ASPECT_TERM):
        raise EngineError(
            "invalid_argument", f"aspect terms must be between 1 and {MAX_ASPECT_TERM}."
        )
    return aw, ah


def plan_crop(
    size: tuple[int, int],
    *,
    left: int | None = None,
    top: int | None = None,
    width: int | None = None,
    height: int | None = None,
    aspect: str | None = None,
) -> tuple[tuple[int, int, int, int], list[str]]:
    """Pure geometry. Return ((left, top, right, bottom), warnings) in upright pixels.

    Either an explicit box (``width`` and ``height``, plus ``left``/``top`` defaulting to
    0) that must lie fully inside the image, or ``aspect`` alone for the largest centred
    box with that ratio. Out-of-bounds boxes are refused, never silently clamped.
    """
    sw, sh = size
    warnings: list[str] = []
    if aspect is not None:
        if any(v is not None for v in (left, top, width, height)):
            raise EngineError(
                "invalid_argument", "Give either aspect or a box (left/top/width/height), not both."
            )
        aw, ah = parse_aspect(aspect)
        if sw * ah >= sh * aw:  # source is wider than the ratio: keep full height
            w, h = min(sw, max(1, round(sh * aw / ah))), sh
        else:
            w, h = sw, min(sh, max(1, round(sw * ah / aw)))
        x, y = (sw - w) // 2, (sh - h) // 2
    else:
        if width is None or height is None:
            raise EngineError(
                "invalid_argument", "Give width and height (and optionally left/top), or aspect."
            )
        x, y, w, h = int(left or 0), int(top or 0), int(width), int(height)
        if x < 0 or y < 0 or w < 1 or h < 1:
            raise EngineError(
                "invalid_argument", "left/top must be >= 0 and width/height must be >= 1."
            )
        if x + w > sw or y + h > sh:
            raise EngineError(
                "crop_out_of_bounds",
                f"The box (left {x}, top {y}, {w}x{h}) does not fit inside the upright image, "
                f"which is {sw}x{sh}. Use image_inspect to check the size.",
            )
    if (w, h) == (sw, sh):
        warnings.append("crop_full_image: the box covers the whole image; nothing was removed.")
    return (x, y, x + w, y + h), warnings


def crop_image(
    src: str | os.PathLike[str],
    out,
    stem: str | None,
    *,
    left: int | None = None,
    top: int | None = None,
    width: int | None = None,
    height: int | None = None,
    aspect: str | None = None,
    target: str | None = None,
    quality: int = DEFAULT_QUALITY,
    lossless: bool = False,
    background: tuple[int, int, int] = (255, 255, 255),
    limits: Limits = DEFAULT_LIMITS,
) -> dict:
    """Crop a box (or a centred ``aspect`` box) of the upright image into a *new* file.

    ``stem`` None means ``<source name>-crop-<W>x<H>``.
    """
    from .output import default_stem, validate_stem  # local import: output imports engine

    box_args = dict(left=left, top=top, width=width, height=height, aspect=aspect)
    # Validate the arguments before opening anything (a huge canvas accepts any valid box).
    plan_crop((1 << 30, 1 << 30), **box_args)
    _check_quality(target, quality)
    if stem is not None:
        stem = validate_stem(stem)
    loaded = _load_upright(src, limits)
    im = loaded.image
    box, warnings = plan_crop(im.size, **box_args)
    loaded.warnings.extend(warnings)
    target = _pick_target(loaded, target)
    note = _lossy_note(target, lossless)
    if note:
        loaded.warnings.append(note)
    work = im.crop(box)
    w, h = box[2] - box[0], box[3] - box[1]
    if stem is None:
        suffix = f"-crop-{w}x{h}"
        stem = default_stem(Path(src))[: 100 - len(suffix)] + suffix
    result = _encode_new(
        loaded, work, target, out, stem, quality=quality, lossless=lossless, background=background
    )
    result.update(
        crop_left=box[0], crop_top=box[1], source_width=im.size[0], source_height=im.size[1]
    )
    return result
