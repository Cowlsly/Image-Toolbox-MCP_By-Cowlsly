"""M10 advanced operations: colour adjustments, text watermark, multi-step recipes and
controlled metadata tags.

Every function follows the same rules as :mod:`engine`: the original is never touched, the
upright first frame is used, the result is a *new* file in the output folder, and EXIF / XMP
/ GPS are stripped. :func:`tag_image` is the single deliberate exception: it writes back
only the three text fields the caller gives (description, artist, copyright) and never GPS,
camera serials or any other source metadata.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFont, ImageOps
from PIL.PngImagePlugin import PngInfo

from .engine import (
    _FLIP_OPS,
    _ROTATE_OPS,
    CONVERT_FORMATS,
    DEFAULT_LIMITS,
    DEFAULT_QUALITY,
    FLIPS,
    RESAMPLE_FILTERS,
    ROTATIONS,
    EngineError,
    Limits,
    _check_quality,
    _encode_new,
    _encoder_setup,
    _has_alpha,
    _load_upright,
    _lossy_note,
    _pick_target,
    _resample_ready,
    _result,
    _save,
    plan_crop,
    plan_resize,
)

# --- adjust -------------------------------------------------------------------------------

MIN_FACTOR = 0.0
MAX_FACTOR = 4.0
ADJUST_FACTORS = ("brightness", "contrast", "saturation", "sharpness")


def _check_factor(name: str, value: float | None) -> None:
    if value is None:
        return
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise EngineError("invalid_argument", f"{name} must be a number.") from None
    if not MIN_FACTOR <= v <= MAX_FACTOR or v != v:  # also rejects NaN
        raise EngineError(
            "invalid_argument",
            f"{name} must be between {MIN_FACTOR} and {MAX_FACTOR} (1.0 = unchanged).",
        )


def check_adjust_args(
    brightness=None,
    contrast=None,
    saturation=None,
    sharpness=None,
    grayscale=False,
    autocontrast=False,
) -> None:
    for name, value in zip(
        ADJUST_FACTORS, (brightness, contrast, saturation, sharpness), strict=True
    ):
        _check_factor(name, value)
    factors = [v for v in (brightness, contrast, saturation, sharpness) if v is not None]
    if not grayscale and not autocontrast and all(float(v) == 1.0 for v in factors):
        raise EngineError(
            "invalid_argument",
            "Nothing to do: give brightness, contrast, saturation or sharpness (1.0 = unchanged), "
            "grayscale or autocontrast.",
        )


def apply_adjust(
    im: Image.Image,
    *,
    brightness: float | None = None,
    contrast: float | None = None,
    saturation: float | None = None,
    sharpness: float | None = None,
    grayscale: bool = False,
    autocontrast: bool = False,
) -> Image.Image:
    """Pure pixel step. Alpha is kept unchanged; colour work is done on the RGB part."""
    alpha = None
    work = im
    if _has_alpha(work):
        work = work.convert("RGBA")
        alpha = work.getchannel("A")
        work = work.convert("RGB")
    elif work.mode not in ("RGB", "L"):
        work = work.convert("RGB")
    if autocontrast:
        work = ImageOps.autocontrast(work)
    if grayscale:
        work = ImageOps.grayscale(work)
    if brightness is not None and float(brightness) != 1.0:
        work = ImageEnhance.Brightness(work).enhance(float(brightness))
    if contrast is not None and float(contrast) != 1.0:
        work = ImageEnhance.Contrast(work).enhance(float(contrast))
    if saturation is not None and float(saturation) != 1.0 and work.mode != "L":
        work = ImageEnhance.Color(work).enhance(float(saturation))
    if sharpness is not None and float(sharpness) != 1.0:
        work = ImageEnhance.Sharpness(work).enhance(float(sharpness))
    if alpha is not None:
        work = work.convert("RGBA")
        work.putalpha(alpha)
    return work


def _stem_with(src, suffix: str, stem: str | None) -> str:
    from .output import default_stem, validate_stem  # local import: output imports engine

    if stem is not None:
        return validate_stem(stem)
    return default_stem(Path(src))[: 100 - len(suffix)] + suffix


def adjust_image(
    src: str | os.PathLike[str],
    out,
    stem: str | None,
    *,
    brightness: float | None = None,
    contrast: float | None = None,
    saturation: float | None = None,
    sharpness: float | None = None,
    grayscale: bool = False,
    autocontrast: bool = False,
    target: str | None = None,
    quality: int = DEFAULT_QUALITY,
    lossless: bool = False,
    background: tuple[int, int, int] = (255, 255, 255),
    limits: Limits = DEFAULT_LIMITS,
) -> dict:
    """Colour/tone adjustments into a *new* file. ``stem`` None means ``<source>-adjusted``."""
    kw = dict(
        brightness=brightness,
        contrast=contrast,
        saturation=saturation,
        sharpness=sharpness,
        grayscale=grayscale,
        autocontrast=autocontrast,
    )
    check_adjust_args(**kw)
    _check_quality(target, quality)
    stem = _stem_with(src, "-adjusted", stem)
    loaded = _load_upright(src, limits)
    target = _pick_target(loaded, target)
    note = _lossy_note(target, lossless)
    if note:
        loaded.warnings.append(note)
    work = apply_adjust(loaded.image, **kw)
    result = _encode_new(
        loaded, work, target, out, stem, quality=quality, lossless=lossless, background=background
    )
    result.update({k: v for k, v in kw.items()})
    return result


# --- watermark ----------------------------------------------------------------------------

POSITIONS = (
    "top-left", "top", "top-right",
    "left", "center", "right",
    "bottom-left", "bottom", "bottom-right",
)  # fmt: skip
MAX_WATERMARK_CHARS = 120
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def check_watermark_args(
    text,
    position="bottom-right",
    opacity=0.5,
    size_percent=5.0,
    color="#ffffff",
    margin_percent=2.0,
) -> str:
    if not isinstance(text, str) or not text.strip():
        raise EngineError("invalid_argument", "text must be a non-empty string.")
    if len(text) > MAX_WATERMARK_CHARS or _CONTROL.search(text):
        raise EngineError(
            "invalid_argument",
            f"text must be one line of at most {MAX_WATERMARK_CHARS} printable characters.",
        )
    if position not in POSITIONS:
        raise EngineError("invalid_argument", f"position must be one of {list(POSITIONS)}.")
    if not 0.0 < float(opacity) <= 1.0:
        raise EngineError("invalid_argument", "opacity must be above 0 and at most 1.")
    if not 1.0 <= float(size_percent) <= 50.0:
        raise EngineError("invalid_argument", "size_percent must be between 1 and 50.")
    if not 0.0 <= float(margin_percent) <= 25.0:
        raise EngineError("invalid_argument", "margin_percent must be between 0 and 25.")
    try:
        ImageColor.getrgb(color)
    except (ValueError, AttributeError):
        raise EngineError(
            "invalid_argument", "color must be a colour like '#ffffff', '#000' or 'white'."
        ) from None
    return text.strip()


def _font(px: int):
    try:
        return ImageFont.load_default(size=px)
    except TypeError:  # Pillow < 10.1: bitmap default font, fixed size
        return ImageFont.load_default()


def apply_watermark(
    im: Image.Image,
    *,
    text: str,
    position: str = "bottom-right",
    opacity: float = 0.5,
    size_percent: float = 5.0,
    color: str = "#ffffff",
    margin_percent: float = 2.0,
) -> Image.Image:
    """Pure pixel step: draw one line of text. Text height = ``size_percent`` of the shorter
    side. A thin contrasting outline keeps it readable on any background."""
    text = check_watermark_args(text, position, opacity, size_percent, color, margin_percent)
    had_alpha = _has_alpha(im)
    base = im.convert("RGBA")
    w, h = base.size
    px = max(8, round(min(w, h) * float(size_percent) / 100))
    font = _font(px)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=max(1, px // 16))
    tw, th = right - left, bottom - top
    m = round(min(w, h) * float(margin_percent) / 100)
    col = position.split("-")[-1] if "-" in position else position
    row = position.split("-")[0] if "-" in position else position
    if col in ("left",):
        x = m
    elif col in ("right",):
        x = w - tw - m
    else:
        x = (w - tw) // 2
    if row == "top":
        y = m
    elif row == "bottom":
        y = h - th - m
    else:
        y = (h - th) // 2
    a = round(255 * float(opacity))
    r, g, b = ImageColor.getrgb(color)[:3]
    outline = (0, 0, 0) if (r * 299 + g * 587 + b * 114) / 1000 > 128 else (255, 255, 255)
    draw.text(
        (x - left, y - top),
        text,
        font=font,
        fill=(r, g, b, a),
        stroke_width=max(1, px // 16),
        stroke_fill=(*outline, a // 2),
    )
    merged = Image.alpha_composite(base, layer)
    return merged if had_alpha else merged.convert("RGB")


def watermark_image(
    src: str | os.PathLike[str],
    out,
    stem: str | None,
    *,
    text: str,
    position: str = "bottom-right",
    opacity: float = 0.5,
    size_percent: float = 5.0,
    color: str = "#ffffff",
    margin_percent: float = 2.0,
    target: str | None = None,
    quality: int = DEFAULT_QUALITY,
    lossless: bool = False,
    background: tuple[int, int, int] = (255, 255, 255),
    limits: Limits = DEFAULT_LIMITS,
) -> dict:
    """Stamp one line of text into a *new* file. ``stem`` None means ``<source>-wm``."""
    wm = dict(
        text=text,
        position=position,
        opacity=opacity,
        size_percent=size_percent,
        color=color,
        margin_percent=margin_percent,
    )
    wm["text"] = check_watermark_args(**wm)
    _check_quality(target, quality)
    stem = _stem_with(src, "-wm", stem)
    loaded = _load_upright(src, limits)
    target = _pick_target(loaded, target)
    note = _lossy_note(target, lossless)
    if note:
        loaded.warnings.append(note)
    work = apply_watermark(loaded.image, **wm)
    result = _encode_new(
        loaded, work, target, out, stem, quality=quality, lossless=lossless, background=background
    )
    result.update(position=position, watermark_chars=len(wm["text"]))
    return result


# --- recipe -------------------------------------------------------------------------------

MAX_RECIPE_STEPS = 10
RECIPE_STEPS = ("resize", "crop", "rotate_flip", "adjust", "watermark")

_STEP_KEYS = {
    "resize": {"width", "height", "fit", "resample", "allow_upscale"},
    "crop": {"left", "top", "width", "height", "aspect"},
    "rotate_flip": {"rotate", "flip"},
    "adjust": {"brightness", "contrast", "saturation", "sharpness", "grayscale", "autocontrast"},
    "watermark": {"text", "position", "opacity", "size_percent", "color", "margin_percent"},
}


def check_recipe(steps: Any) -> list[dict]:
    """Validate a recipe without opening any file. Returns normalised step dicts."""
    if not isinstance(steps, list) or not steps:
        raise EngineError("invalid_argument", "steps must be a non-empty list.")
    if len(steps) > MAX_RECIPE_STEPS:
        raise EngineError("invalid_argument", f"A recipe has at most {MAX_RECIPE_STEPS} steps.")
    clean = []
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict) or "op" not in step:
            raise EngineError("invalid_argument", f"Step {i} must be an object with an 'op'.")
        op = step["op"]
        if op not in RECIPE_STEPS:
            raise EngineError(
                "invalid_argument", f"Step {i}: op must be one of {list(RECIPE_STEPS)}."
            )
        params = {k: v for k, v in step.items() if k != "op"}
        extra = set(params) - _STEP_KEYS[op]
        if extra:
            raise EngineError(
                "invalid_argument",
                f"Step {i} ({op}): unknown keys {sorted(extra)}. "
                f"Allowed: {sorted(_STEP_KEYS[op])}.",
            )
        try:
            if op == "resize":
                plan_resize(
                    (1, 1),
                    params.get("width"),
                    params.get("height"),
                    params.get("fit", "contain"),
                    allow_upscale=True,
                )
                if params.get("resample", "lanczos") not in RESAMPLE_FILTERS:
                    raise EngineError(
                        "invalid_argument", f"resample must be one of {list(RESAMPLE_FILTERS)}."
                    )
            elif op == "crop":
                plan_crop((1 << 30, 1 << 30), **params)
            elif op == "rotate_flip":
                if params.get("rotate", 0) not in ROTATIONS:
                    raise EngineError(
                        "invalid_argument", f"rotate must be one of {list(ROTATIONS)}."
                    )
                if params.get("flip") is not None and params["flip"] not in FLIPS:
                    raise EngineError("invalid_argument", f"flip must be one of {list(FLIPS)}.")
                if params.get("rotate", 0) == 0 and params.get("flip") is None:
                    raise EngineError("invalid_argument", "rotate_flip needs rotate or flip.")
            elif op == "adjust":
                check_adjust_args(**params)
            elif op == "watermark":
                if "text" not in params:
                    raise EngineError("invalid_argument", "watermark needs text.")
                params["text"] = check_watermark_args(**params)
        except EngineError as err:
            raise EngineError(err.code, f"Step {i} ({op}): {err.message}") from None
        except TypeError:
            raise EngineError("invalid_argument", f"Step {i} ({op}): bad parameter.") from None
        clean.append({"op": op, **params})
    return clean


def _apply_step(im: Image.Image, step: dict, limits: Limits, warnings: list[str]) -> Image.Image:
    op = step["op"]
    p = {k: v for k, v in step.items() if k != "op"}
    if op == "resize":
        scaled, final, more = plan_resize(
            im.size,
            p.get("width"),
            p.get("height"),
            p.get("fit", "contain"),
            bool(p.get("allow_upscale", False)),
        )
        if final[0] * final[1] > limits.max_pixels or scaled[0] * scaled[1] > limits.max_pixels:
            raise EngineError(
                "too_many_pixels",
                f"A step would make {final[0]}x{final[1]}; the limit is {limits.max_pixels} px.",
            )
        warnings.extend(more)
        flt = RESAMPLE_FILTERS[p.get("resample", "lanczos")]
        work = im if scaled == im.size else _resample_ready(im, flt).resize(scaled, flt)
        if final != scaled:
            left = (scaled[0] - final[0]) // 2
            top = (scaled[1] - final[1]) // 2
            work = work.crop((left, top, left + final[0], top + final[1]))
        return work
    if op == "crop":
        box, more = plan_crop(im.size, **p)
        warnings.extend(more)
        return im.crop(box)
    if op == "rotate_flip":
        work = im
        if p.get("rotate", 0):
            work = work.transpose(_ROTATE_OPS[p["rotate"]])
        if p.get("flip") is not None:
            work = work.transpose(_FLIP_OPS[p["flip"]])
        return work
    if op == "adjust":
        return apply_adjust(im, **p)
    if op == "watermark":
        return apply_watermark(im, **p)
    raise EngineError("invalid_argument", f"Unknown step {op!r}.")  # pragma: no cover


def recipe_image(
    src: str | os.PathLike[str],
    out,
    stem: str | None,
    *,
    steps: list[dict],
    target: str | None = None,
    quality: int = DEFAULT_QUALITY,
    lossless: bool = False,
    background: tuple[int, int, int] = (255, 255, 255),
    limits: Limits = DEFAULT_LIMITS,
) -> dict:
    """Apply ``steps`` in order in memory and encode once (one quality loss at most).

    ``stem`` None means ``<source>-recipe``. The result lists the normalised steps so the
    same recipe can be re-run exactly (reproducible transformation).
    """
    clean = check_recipe(steps)
    _check_quality(target, quality)
    stem = _stem_with(src, "-recipe", stem)
    loaded = _load_upright(src, limits)
    target = _pick_target(loaded, target)
    note = _lossy_note(target, lossless)
    if note:
        loaded.warnings.append(note)
    work = loaded.image
    for step in clean:
        try:
            work = _apply_step(work, step, limits, loaded.warnings)
        except EngineError as err:
            raise EngineError(err.code, f"Step {clean.index(step) + 1}: {err.message}") from None
    result = _encode_new(
        loaded, work, target, out, stem, quality=quality, lossless=lossless, background=background
    )
    result.update(steps=clean, source_width=loaded.image.size[0],
                  source_height=loaded.image.size[1])  # fmt: skip
    return result


# --- controlled metadata tags --------------------------------------------------------------

MAX_TAG_CHARS = 256
TAG_FIELDS = {"description": 0x010E, "artist": 0x013B, "copyright": 0x8298}
_PNG_KEYS = {"description": "Description", "artist": "Author", "copyright": "Copyright"}


def check_tags(tags: dict | None) -> dict[str, str]:
    if not isinstance(tags, dict) or not tags:
        raise EngineError("invalid_argument", f"Give at least one of {sorted(TAG_FIELDS)} as text.")
    extra = set(tags) - set(TAG_FIELDS)
    if extra:
        raise EngineError(
            "invalid_argument",
            f"Only {sorted(TAG_FIELDS)} can be written; refused {sorted(extra)}.",
        )
    clean = {}
    for k, v in tags.items():
        if not isinstance(v, str) or len(v) > MAX_TAG_CHARS or _CONTROL.search(v.replace("\n", "")):
            raise EngineError(
                "invalid_argument", f"{k} must be text of at most {MAX_TAG_CHARS} characters."
            )
        if v.strip():
            clean[k] = v.strip()
    if not clean:
        raise EngineError("invalid_argument", "Every tag was empty: nothing to write.")
    return clean


def tag_image(
    src: str | os.PathLike[str],
    out,
    stem: str | None,
    *,
    description: str | None = None,
    artist: str | None = None,
    copyright: str | None = None,  # noqa: A002 - EXIF field name
    target: str | None = None,
    quality: int = DEFAULT_QUALITY,
    lossless: bool = False,
    background: tuple[int, int, int] = (255, 255, 255),
    limits: Limits = DEFAULT_LIMITS,
) -> dict:
    """Write a new file whose only metadata is the given text fields (plus the ICC profile).

    JPEG and WebP get EXIF tags; PNG gets text chunks. All source EXIF/XMP/GPS is still
    dropped first. Pixels are re-encoded once (lossless for PNG and ``lossless`` WebP).
    """
    tags = check_tags(
        {
            k: v
            for k, v in (("description", description), ("artist", artist), ("copyright", copyright))
            if v is not None
        }  # fmt: skip
    )
    _check_quality(target, quality)
    stem = _stem_with(src, "-tagged", stem)
    loaded = _load_upright(src, limits)
    target = _pick_target(loaded, target)
    note = _lossy_note(target, lossless)
    if note:
        loaded.warnings.append(note)
    pixels, params, warnings = _encoder_setup(
        loaded, loaded.image, target, quality=quality, lossless=lossless, background=background
    )
    if target == "png":
        info = PngInfo()
        for k, v in tags.items():
            info.add_itxt(_PNG_KEYS[k], v)
        params["pnginfo"] = info
    else:
        exif = Image.Exif()
        for k, v in tags.items():
            exif[TAG_FIELDS[k]] = v
        params["exif"] = exif.tobytes()
    dest = out.write_new(
        stem, CONVERT_FORMATS[target][1], lambda fh: _save(pixels, fh, target, params)
    )
    result = _result(loaded, pixels, target, dest, warnings)
    result["metadata_stripped"] = True  # source metadata; only the given tags were written
    result["tags_written"] = sorted(tags)
    return result
