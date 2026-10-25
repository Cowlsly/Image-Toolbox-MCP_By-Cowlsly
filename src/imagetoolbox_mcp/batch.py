"""Batch processing (M4): apply one existing operation to every matching image in a folder.

Kept independent of the MCP SDK (like :mod:`engine`) so it can be unit-tested on its own.
The server drives the per-file loop itself so it can report progress and honour
cancellation between files; this module supplies the pieces:

* :func:`parse_options` — validate an operation's options once, before any file is touched;
* :func:`select_files` — list one folder (no recursion, no symlinks, no hidden files);
* :func:`run_one` — process one file (raises like the single-file tools);
* :func:`write_batch_manifest` — a JSON record of the run in the output folder.

Safety rules (ADR-0004): sequential processing (one file at a time — phones have little
RAM), hard caps on file count and total input bytes, never overwrite, originals untouched,
a partial failure never aborts the batch, and an argument error stops it immediately
(it would repeat for every file).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from . import __version__
from .engine import (
    DEFAULT_LIMITS,
    DEFAULT_QUALITY,
    MAX_ASPECT_TERM,
    MAX_SIDE,
    MIN_TARGET_BYTES,
    EngineError,
    Limits,
    compress_image,
    convert_image,
    crop_image,
    resize_image,
    rotate_flip_image,
)
from .output import OutputDir, default_stem

MAX_BATCH_FILES = 200  # hard cap per call
DEFAULT_BATCH_FILES = 50
MAX_BATCH_INPUT_BYTES = 1024 * 1024 * 1024  # 1 GiB of source files per call
MAX_SCAN_ENTRIES = 10_000  # folder entries looked at before giving up
MAX_PATTERN_CHARS = 100
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"})
OPERATIONS = ("convert", "resize", "compress", "rotate_flip", "crop", "adjust", "watermark")

Fmt = Literal["jpeg", "png", "webp"]


class _Opts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConvertOptions(_Opts):
    format: Fmt
    quality: int = Field(DEFAULT_QUALITY, ge=1, le=100)
    lossless: bool = False


class ResizeOptions(_Opts):
    width: int | None = Field(None, ge=1, le=MAX_SIDE)
    height: int | None = Field(None, ge=1, le=MAX_SIDE)
    fit: Literal["contain", "cover", "exact"] = "contain"
    resample: Literal["lanczos", "bicubic", "bilinear", "nearest"] = "lanczos"
    allow_upscale: bool = False
    format: Fmt | None = None
    quality: int = Field(DEFAULT_QUALITY, ge=1, le=100)

    @model_validator(mode="after")
    def _check(self):
        if self.width is None and self.height is None:
            raise ValueError("give width, height or both")
        if self.fit != "contain" and (self.width is None or self.height is None):
            raise ValueError(f"fit='{self.fit}' needs both width and height")
        return self


class CompressOptions(_Opts):
    quality: int | None = Field(None, ge=1, le=100)
    max_bytes: int | None = Field(None, ge=MIN_TARGET_BYTES, le=DEFAULT_LIMITS.max_file_bytes)
    min_quality: int = Field(10, ge=1, le=95)
    colors: int | None = Field(None, ge=2, le=256)
    format: Fmt | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.quality is not None and self.max_bytes is not None:
            raise ValueError("give either quality or max_bytes, not both")
        return self


class RotateFlipOptions(_Opts):
    rotate: Literal[0, 90, 180, 270] = 0
    flip: Literal["horizontal", "vertical"] | None = None
    format: Fmt | None = None
    quality: int = Field(DEFAULT_QUALITY, ge=1, le=100)
    lossless: bool = False

    @model_validator(mode="after")
    def _check(self):
        if self.rotate == 0 and self.flip is None:
            raise ValueError("nothing to do: give rotate (90/180/270) or flip")
        return self


class CropOptions(_Opts):
    left: int | None = Field(None, ge=0, le=MAX_SIDE * 4)
    top: int | None = Field(None, ge=0, le=MAX_SIDE * 4)
    width: int | None = Field(None, ge=1, le=MAX_SIDE * 4)
    height: int | None = Field(None, ge=1, le=MAX_SIDE * 4)
    aspect: str | None = Field(
        None, min_length=3, max_length=2 * len(str(MAX_ASPECT_TERM)) + 1, pattern=r"^\d+:\d+$"
    )
    format: Fmt | None = None
    quality: int = Field(DEFAULT_QUALITY, ge=1, le=100)
    lossless: bool = False

    @model_validator(mode="after")
    def _check(self):
        box = (self.left, self.top, self.width, self.height)
        if self.aspect is not None and any(v is not None for v in box):
            raise ValueError("give either aspect or a box (left/top/width/height), not both")
        if self.aspect is None and (self.width is None or self.height is None):
            raise ValueError("give width and height (and optionally left/top), or aspect")
        return self


class AdjustOptions(_Opts):
    brightness: float | None = Field(None, ge=0, le=4)
    contrast: float | None = Field(None, ge=0, le=4)
    saturation: float | None = Field(None, ge=0, le=4)
    sharpness: float | None = Field(None, ge=0, le=4)
    grayscale: bool = False
    autocontrast: bool = False
    format: Fmt | None = None
    quality: int = Field(DEFAULT_QUALITY, ge=1, le=100)
    lossless: bool = False

    @model_validator(mode="after")
    def _check(self):
        factors = [self.brightness, self.contrast, self.saturation, self.sharpness]
        if (
            not self.grayscale
            and not self.autocontrast
            and all(f is None or f == 1.0 for f in factors)
        ):
            raise ValueError("nothing to do: give a factor, grayscale or autocontrast")
        return self


class WatermarkOptions(_Opts):
    text: str = Field(min_length=1, max_length=120)
    position: Literal[
        "top-left",
        "top",
        "top-right",
        "left",
        "center",
        "right",
        "bottom-left",
        "bottom",
        "bottom-right",
    ] = "bottom-right"
    opacity: float = Field(0.5, gt=0, le=1)
    size_percent: float = Field(5.0, ge=1, le=50)
    color: str = Field("#ffffff", max_length=32)
    margin_percent: float = Field(2.0, ge=0, le=25)
    format: Fmt | None = None
    quality: int = Field(DEFAULT_QUALITY, ge=1, le=100)
    lossless: bool = False


OPTION_MODELS: dict[str, type[_Opts]] = {
    "convert": ConvertOptions,
    "resize": ResizeOptions,
    "compress": CompressOptions,
    "rotate_flip": RotateFlipOptions,
    "crop": CropOptions,
    "adjust": AdjustOptions,
    "watermark": WatermarkOptions,
}


def parse_options(operation: str, options: dict[str, Any] | None) -> _Opts:
    """Validate ``options`` for ``operation``; raise ``[invalid_argument]`` with a short reason."""
    model = OPTION_MODELS.get(operation)
    if model is None:
        raise EngineError("invalid_argument", f"operation must be one of {list(OPERATIONS)}.")
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise EngineError("invalid_argument", "options must be an object.")
    if "output_name" in options:
        raise EngineError(
            "invalid_argument",
            "output_name is not allowed in a batch: each file gets its own default name.",
        )
    try:
        return model.model_validate(options)
    except ValidationError as err:
        reasons = []
        for e in err.errors()[:5]:
            loc = ".".join(str(x) for x in e["loc"])
            msg = e["msg"].removeprefix("Value error, ")
            reasons.append(f"{loc}: {msg}" if loc else msg)
        allowed = ", ".join(model.model_fields)
        raise EngineError(
            "invalid_argument",
            f"Bad options for '{operation}': {'; '.join(reasons)}. Allowed keys: {allowed}.",
        ) from None


@dataclass
class Selection:
    folder: Path
    files: list[Path] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)  # {"name", "reason"}
    total_bytes: int = 0


def _check_pattern(pattern: str | None) -> str | None:
    if pattern is None:
        return None
    p = pattern.strip()
    if not p or len(p) > MAX_PATTERN_CHARS or "\x00" in p:
        raise EngineError("invalid_argument", f"pattern must be 1-{MAX_PATTERN_CHARS} characters.")
    if "/" in p or "\\" in p:
        raise EngineError(
            "invalid_argument",
            "pattern matches file names only (no folders); put the folder in 'folder'.",
        )
    return p


def select_files(
    folder: Path,
    pattern: str | None,
    *,
    max_files: int = DEFAULT_BATCH_FILES,
    output_dir: Path | None = None,
    limits: Limits = DEFAULT_LIMITS,
    max_total_bytes: int = MAX_BATCH_INPUT_BYTES,
) -> Selection:
    """List the regular image files directly inside ``folder`` (already sandbox-resolved).

    ``pattern`` is a case-insensitive shell glob on the file name (``*.jpg``, ``IMG_2026*``);
    without one, common image extensions are matched. Symlinks, hidden files, sub-folders and
    oversized files are skipped (and reported). More matches than ``max_files`` or more than
    ``max_total_bytes`` in total refuses the whole batch rather than silently truncating it.
    """
    pattern = _check_pattern(pattern)
    if not 1 <= max_files <= MAX_BATCH_FILES:
        raise EngineError("invalid_argument", f"max_files must be between 1 and {MAX_BATCH_FILES}.")
    if output_dir is not None and folder == output_dir:
        raise EngineError(
            "invalid_argument",
            "The folder is the output folder; batch-processing earlier results is refused.",
        )
    sel = Selection(folder=folder)
    try:
        entries = []
        with os.scandir(folder) as it:
            for n, entry in enumerate(it):
                if n >= MAX_SCAN_ENTRIES:
                    raise EngineError(
                        "folder_too_large",
                        f"The folder has more than {MAX_SCAN_ENTRIES} entries; use a smaller one.",
                    )
                entries.append(entry)
    except PermissionError:
        raise EngineError("permission_denied", "The folder cannot be read.") from None
    except FileNotFoundError:
        raise EngineError("not_found", "The folder does not exist.") from None

    pat = pattern.lower() if pattern else None
    for entry in sorted(entries, key=lambda e: e.name):
        name = entry.name
        if name.startswith("."):
            continue  # hidden files and our own temp files: silently ignored
        lname = name.lower()
        if pat is not None:
            if not fnmatch.fnmatchcase(lname, pat):
                continue
        elif os.path.splitext(lname)[1] not in IMAGE_EXTENSIONS:
            continue
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError:
            sel.skipped.append({"name": name, "reason": "unreadable"})
            continue
        if stat.S_ISLNK(st.st_mode):
            sel.skipped.append({"name": name, "reason": "symlink_rejected"})
        elif stat.S_ISDIR(st.st_mode):
            continue  # no recursion; folders are never inputs
        elif not stat.S_ISREG(st.st_mode):
            sel.skipped.append({"name": name, "reason": "not_a_file"})
        elif st.st_size > limits.max_file_bytes:
            sel.skipped.append({"name": name, "reason": "file_too_large"})
        else:
            sel.files.append(Path(entry.path))
            sel.total_bytes += st.st_size

    if len(sel.files) > max_files:
        raise EngineError(
            "too_many_files",
            f"{len(sel.files)} files match but max_files is {max_files} (hard limit "
            f"{MAX_BATCH_FILES}); narrow the pattern or raise max_files.",
        )
    if sel.total_bytes > max_total_bytes:
        raise EngineError(
            "batch_too_large",
            f"The matching files total {sel.total_bytes} bytes; the batch limit is "
            f"{max_total_bytes} bytes. Use a narrower pattern.",
        )
    return sel


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_one(
    operation: str,
    opts: _Opts,
    src: Path,
    out: OutputDir,
    limits: Limits = DEFAULT_LIMITS,
) -> dict:
    """Run one operation on one file. Returns the engine result dict (with ``output_file``).

    Raises :class:`EngineError` exactly like the single-file tools; the caller turns it into
    a per-file failure.
    """
    o = opts.model_dump()
    if operation == "convert":
        fmt = o.pop("format")
        return convert_image(src, fmt, out, default_stem(src), limits=limits, **o)
    target = o.pop("format", None)
    if operation == "resize":
        return resize_image(src, out, None, target=target, limits=limits, **o)
    if operation == "compress":
        return compress_image(src, out, None, target=target, limits=limits, **o)
    if operation == "rotate_flip":
        return rotate_flip_image(src, out, None, target=target, limits=limits, **o)
    if operation == "crop":
        return crop_image(src, out, None, target=target, limits=limits, **o)
    if operation == "adjust":
        from .edit import adjust_image

        return adjust_image(src, out, None, target=target, limits=limits, **o)
    if operation == "watermark":
        from .edit import watermark_image

        return watermark_image(src, out, None, target=target, limits=limits, **o)
    raise EngineError("invalid_argument", f"operation must be one of {list(OPERATIONS)}.")


def manifest_stem(operation: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"batch-{operation.replace('_', '-')}-{now.strftime('%Y%m%dT%H%M%SZ')}"


def write_batch_manifest(out: OutputDir, operation: str, record: dict) -> Path:
    """Write ``record`` (already free of host paths) as a new JSON file in the output folder."""
    payload = {"tool": "imagetoolbox-mcp", "version": __version__, **record}
    data = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return out.write_new(manifest_stem(operation), "json", lambda fh: fh.write(data))


# --- resume (M4 follow-up) ----------------------------------------------------------------

MAX_MANIFEST_BYTES = 5 * 1024 * 1024
RETRYABLE_CODES = frozenset({"output_unavailable", "out_of_memory", "internal_error"})
MAX_RETRIES = 3


def load_resume(out: OutputDir, name: str, operation: str, opts: _Opts) -> dict[str, dict]:
    """Read a previous manifest from the output folder for ``resume_from``.

    ``name`` must be a bare file name (no folders) of a manifest this tool wrote, for the
    same operation and the same options. Returns ``{source: record}`` for the files that run
    finished with status ``ok``. Anything else is ``[invalid_argument]``.
    """
    if not isinstance(name, str) or not name or "/" in name or "\\" in name or name[0] == ".":
        raise EngineError(
            "invalid_argument",
            "resume_from must be the file name of a manifest in the output folder, "
            "e.g. 'batch-convert-20261025T010203Z.json'.",
        )
    if not name.endswith(".json"):
        raise EngineError("invalid_argument", "resume_from must name a .json manifest.")
    p = out.path / name
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        raise EngineError("not_found", "That manifest is not in the output folder.") from None
    except OSError:
        raise EngineError("permission_denied", "The manifest cannot be read.") from None
    if not stat.S_ISREG(st.st_mode):
        raise EngineError("symlink_rejected", "The manifest must be a regular file.")
    if st.st_size > MAX_MANIFEST_BYTES:
        raise EngineError("file_too_large", "The manifest is too large to resume from.")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise EngineError("invalid_argument", "The manifest is not valid JSON.") from None
    if not isinstance(data, dict) or data.get("tool") != "imagetoolbox-mcp":
        raise EngineError("invalid_argument", "That file is not an imagetoolbox-mcp manifest.")
    if data.get("operation") != operation:
        raise EngineError(
            "invalid_argument",
            f"The manifest is for '{data.get('operation')}', not '{operation}'.",
        )
    if data.get("options") != opts.model_dump():
        raise EngineError(
            "invalid_argument",
            "The manifest used different options; resume only works with the same options.",
        )
    done: dict[str, dict] = {}
    for item in data.get("items") or []:
        if (
            isinstance(item, dict)
            and item.get("status") in ("ok", "resumed")
            and isinstance(item.get("source"), str)
            and isinstance(item.get("source_sha256"), str)
            and isinstance(item.get("output"), str)
        ):
            done[item["source"]] = item
    return done
