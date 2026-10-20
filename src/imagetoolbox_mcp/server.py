"""MCP server: stdio transport. Tools: ``image_inspect`` (M2, read-only), ``image_convert``,
``image_resize``, ``image_compress``, ``image_rotate_flip`` and ``image_crop`` (M3), and
``image_batch`` (M4).

Tool names use ``snake_case`` rather than the roadmap's ``image.inspect`` because several
model APIs only accept ``[A-Za-z0-9_-]`` in tool names; dots would break those clients.

Security posture (see SECURITY.md): no shell, no network, no arbitrary filesystem access.
Every path is resolved through :class:`~imagetoolbox_mcp.sandbox.InputRoot`.
"""

from __future__ import annotations

import functools
import inspect
import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

import anyio
import anyio.to_thread
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .batch import (
    DEFAULT_BATCH_FILES,
    MAX_BATCH_FILES,
    MAX_PATTERN_CHARS,
    parse_options,
    run_one,
    select_files,
    sha256_file,
    write_batch_manifest,
)
from .engine import (
    DEFAULT_LIMITS,
    DEFAULT_QUALITY,
    MAX_ASPECT_TERM,
    MAX_FILE_BYTES,
    MAX_SIDE,
    MIN_TARGET_BYTES,
    EngineError,
    Limits,
    compress_image,
    convert_image,
    crop_image,
    inspect_image,
    resize_image,
    rotate_flip_image,
)
from .output import DEFAULT_DIRNAME, MAX_STEM_CHARS, OutputDir, default_stem
from .sandbox import MAX_PATH_CHARS, InputRoot

log = logging.getLogger("imagetoolbox_mcp")

SERVER_NAME = "imagetoolbox-mcp"

INSTRUCTIONS = (
    "Safe, local image tools inspired by Image Toolbox (T8RIN). Paths are relative to the "
    "single input folder the user configured; '..', symlinks and absolute paths outside it "
    "are refused. Tools never modify original files: results are written as new files in "
    "one output folder and existing files are never overwritten."
)


class InspectResult(BaseModel):
    """Output schema of ``image_inspect`` (published to clients as ``outputSchema``)."""

    path: str = Field(description="Path relative to the input folder.")
    format: str | None = Field(description="Pillow format name, e.g. PNG, JPEG, WEBP.")
    width: int
    height: int
    mode: str = Field(description="Pillow colour mode, e.g. RGB, RGBA, L.")
    has_alpha: bool
    frames: int = Field(description="Number of frames (>1 for animations).")
    file_bytes: int
    orientation: int = Field(description="EXIF orientation (1 = normal).")
    exif: dict[str, int | str] = Field(description="Safe EXIF subset; never GPS or maker notes.")
    has_gps_metadata: bool = Field(description="True if the file carries location data.")


class ConvertResult(BaseModel):
    """Output schema of ``image_convert``."""

    source: str = Field(description="Input path relative to the input folder.")
    output: str = Field(
        description="New file: relative to the input folder if the output folder is inside "
        "it (so it can be passed to other tools), otherwise just the file name."
    )
    source_format: str | None
    format: str = Field(description="Output format: JPEG, PNG or WEBP.")
    width: int
    height: int
    mode: str
    input_bytes: int
    output_bytes: int
    metadata_stripped: bool = Field(description="EXIF/XMP/GPS were not copied to the output.")
    had_gps_metadata: bool = Field(description="The source carried location data.")
    icc_profile_kept: bool
    warnings: list[str] = Field(description="Lossy or lossy-looking side effects, if any.")


class ResizeResult(ConvertResult):
    """Output schema of ``image_resize``."""

    source_width: int = Field(description="Source width after applying EXIF orientation.")
    source_height: int = Field(description="Source height after applying EXIF orientation.")


class CompressResult(ConvertResult):
    """Output schema of ``image_compress``."""

    quality_used: int | None = Field(description="JPEG/WebP quality used (None for PNG).")
    colors_used: int | None = Field(description="PNG palette size, if colours were reduced.")
    max_bytes: int | None = Field(description="The requested size limit, if any.")
    target_met: bool | None = Field(description="Whether max_bytes was met (None if not set).")
    saved_bytes: int = Field(description="input_bytes - output_bytes (negative = larger).")


# Shared parameter types (module level: annotations are evaluated lazily by name).
SourcePath = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PATH_CHARS,
        description="Source image path relative to the input folder.",
    ),
]
OutFormat = Annotated[
    Literal["jpeg", "png", "webp"] | None,
    Field(description="Output format. Default: same as the source."),
]
Quality = Annotated[
    int, Field(ge=1, le=100, description="JPEG/WebP quality 1-100 (ignored for PNG).")
]
Lossless = Annotated[bool, Field(description="WebP only: lossless encoding.")]


class RotateFlipResult(ResizeResult):
    """Output schema of ``image_rotate_flip``."""

    rotate: int = Field(description="Degrees rotated clockwise (0, 90, 180 or 270).")
    flip: str | None = Field(description="'horizontal', 'vertical' or None.")


class CropResult(ResizeResult):
    """Output schema of ``image_crop``."""

    crop_left: int = Field(description="Left edge of the crop box in the upright source.")
    crop_top: int = Field(description="Top edge of the crop box in the upright source.")


class BatchItem(BaseModel):
    """One file of an ``image_batch`` run."""

    source: str = Field(description="Input path relative to the input folder.")
    status: Literal["ok", "failed", "planned", "not_run"]
    output: str | None = None
    input_bytes: int | None = None
    output_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    format: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error: str | None = None


class SkippedEntry(BaseModel):
    name: str
    reason: str


class BatchResult(BaseModel):
    """Output schema of ``image_batch``."""

    operation: str
    folder: str = Field(description="Folder relative to the input folder ('.' = the root).")
    pattern: str | None
    dry_run: bool
    matched: int = Field(description="Files selected for processing.")
    succeeded: int
    failed: int
    not_run: int = Field(description="Files left untouched because the batch stopped early.")
    stopped_reason: str | None = Field(description="Why the batch stopped early, if it did.")
    input_bytes_total: int
    output_bytes_total: int
    manifest: str | None = Field(description="JSON manifest written to the output folder.")
    skipped: list[SkippedEntry] = Field(description="Matching names not processed, and why.")
    items: list[BatchItem]


BATCH_DESCRIPTION = (
    "Apply ONE operation to every image directly inside a folder (no sub-folders) and save "
    "each result as a NEW file in the output folder; originals are never changed and "
    "existing files are never overwritten (a -1, -2 ... suffix is added). Files are "
    "processed one at a time; a failing file is reported and the rest continue. Use "
    "dry_run=true first to see which files would be processed. 'options' are the same as "
    "the single-file tool, without path/output_name: "
    "convert {format (required: jpeg|png|webp), quality, lossless}; "
    "resize {width, height, fit, resample, allow_upscale, format, quality}; "
    "compress {quality | max_bytes, min_quality, colors, format}; "
    "rotate_flip {rotate (90|180|270, clockwise), flip (horizontal|vertical), format, "
    "quality, lossless}; "
    "crop {left, top, width, height | aspect like '1:1', format, quality, lossless}. "
    "Without 'pattern', .jpg/.jpeg/.png/.webp/.gif/.bmp/.tif/.tiff files are used. A JSON "
    "manifest (sources, outputs, options, SHA-256 checksums, failures) is written unless "
    "write_manifest=false. EXIF/GPS metadata is removed from every output."
)


def _tool_error(err: EngineError) -> ToolError:
    # Stable, machine-readable prefix the model (and tests) can match on.
    return ToolError(f"[{err.code}] {err.message}")


INTERNAL_ERROR = (
    "[internal_error] Unexpected server error; nothing was overwritten. "
    "Try another file or report a bug."
)


def _guard(fn):
    """Turn any unexpected exception into a fixed ``[internal_error]`` tool error.

    The SDK would otherwise log the full traceback, whose message may contain host paths
    or file names (threat model T9). We log the exception *type* only. ``ToolError`` and
    cancellation (``BaseException``) pass through unchanged.
    """

    def _fail(exc: Exception):
        log.warning("%s internal error: %s", fn.__name__, type(exc).__name__)
        return ToolError(INTERNAL_ERROR)

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except ToolError:
                raise
            except Exception as exc:  # noqa: BLE001 - deliberate catch-all, see docstring
                raise _fail(exc) from None

    else:

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except ToolError:
                raise
            except Exception as exc:  # noqa: BLE001 - deliberate catch-all, see docstring
                raise _fail(exc) from None

    return wrapper


def _tool(server: MCPServer, **kwargs):
    """``server.tool(**kwargs)`` with :func:`_guard` applied first."""

    def register(fn):
        return server.tool(**kwargs)(_guard(fn))

    return register


def _display_output(root: InputRoot, path) -> str:
    if path.is_relative_to(root.path):
        return root.display(path)
    return path.name


def build_server(
    root: InputRoot,
    limits: Limits = DEFAULT_LIMITS,
    log_level: str = "WARNING",
    out: OutputDir | None = None,
) -> MCPServer:
    """Create a configured server. Separate from ``run`` so tests can connect in-process.

    ``out`` defaults to ``<root>/imagetoolbox-out`` (ADR-0002).
    """
    if out is None:
        out = OutputDir(root.path / DEFAULT_DIRNAME)
    server = MCPServer(
        log_level=log_level,
        name=SERVER_NAME,
        title="Image Toolbox MCP",
        version=__version__,
        instructions=INSTRUCTIONS,
        website_url="https://github.com/Cowlsly/Image-Toolbox-MCP_By-Cowlsly",
    )

    @_tool(
        server,
        name="image_inspect",
        title="Inspect image",
        description=(
            "Read an image file and report its format, width, height, colour mode, alpha, "
            "frame count, file size, orientation and a small safe EXIF subset. Location "
            "(GPS) data is never returned; only whether it is present. Read-only."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    def image_inspect(
        path: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_PATH_CHARS,
                description="Image path relative to the input folder, e.g. 'photos/cat.jpg'.",
            ),
        ],
    ) -> InspectResult:
        try:
            real = root.resolve(path)
            info = inspect_image(real, limits)
        except EngineError as err:
            # Log the code only; never the raw path (may contain personal names).
            log.info("image_inspect refused: %s", err.code)
            raise _tool_error(err) from None
        log.info("image_inspect ok: %s %sx%s", info["format"], info["width"], info["height"])
        return InspectResult(path=root.display(real), **info)

    @_tool(
        server,
        name="image_convert",
        title="Convert image format",
        description=(
            "Convert an image to JPEG, PNG or WebP and save it as a NEW file in the output "
            "folder; the original is never changed and existing files are never overwritten "
            "(a -1, -2 ... suffix is added). EXIF orientation is applied; EXIF/GPS metadata "
            "is removed. Transparency is filled with white for JPEG. Converting a JPEG to "
            "PNG does not restore detail. Animated images: first frame only."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    def image_convert(
        path: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_PATH_CHARS,
                description="Source image path relative to the input folder.",
            ),
        ],
        format: Annotated[Literal["jpeg", "png", "webp"], Field(description="Target format.")],
        quality: Annotated[
            int,
            Field(ge=1, le=100, description="JPEG/WebP quality 1-100 (ignored for PNG)."),
        ] = DEFAULT_QUALITY,
        lossless: Annotated[bool, Field(description="WebP only: lossless encoding.")] = False,
        output_name: Annotated[
            str | None,
            Field(
                max_length=MAX_STEM_CHARS,
                description="Optional file name WITHOUT extension, e.g. 'cat-small'. "
                "Letters, digits, space, '.', '_' and '-' only. Default: source name.",
            ),
        ] = None,
    ) -> ConvertResult:
        try:
            real = root.resolve(path)
            stem = output_name if output_name is not None else default_stem(real)
            info = convert_image(
                real, format, out, stem, quality=quality, lossless=lossless, limits=limits
            )
        except EngineError as err:
            log.info("image_convert refused: %s", err.code)
            raise _tool_error(err) from None
        dest = info.pop("output_file")
        log.info("image_convert ok: %s -> %s", info["source_format"], info["format"])
        return ConvertResult(source=root.display(real), output=_display_output(root, dest), **info)

    @_tool(
        server,
        name="image_resize",
        title="Resize image",
        description=(
            "Resize an image and save it as a NEW file in the output folder (original never "
            "changed, existing files never overwritten). Give width, height or both, in "
            "pixels of the upright image. fit='contain' (default) keeps the aspect ratio "
            "inside the box; 'cover' fills the box and centre-crops; 'exact' stretches. "
            "Images are not enlarged unless allow_upscale is true. Output keeps the source "
            "format (JPEG/PNG/WebP, otherwise PNG) unless 'format' is given. EXIF/GPS "
            "metadata is removed. Default name: '<source>-<W>x<H>'."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    def image_resize(
        path: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_PATH_CHARS,
                description="Source image path relative to the input folder.",
            ),
        ],
        width: Annotated[
            int | None, Field(ge=1, le=MAX_SIDE, description="Target width in pixels.")
        ] = None,
        height: Annotated[
            int | None, Field(ge=1, le=MAX_SIDE, description="Target height in pixels.")
        ] = None,
        fit: Annotated[
            Literal["contain", "cover", "exact"],
            Field(description="contain = fit inside; cover = fill and crop; exact = stretch."),
        ] = "contain",
        resample: Annotated[
            Literal["lanczos", "bicubic", "bilinear", "nearest"],
            Field(description="Interpolation filter. 'nearest' suits pixel art."),
        ] = "lanczos",
        allow_upscale: Annotated[
            bool, Field(description="Allow making the image larger than the source.")
        ] = False,
        format: Annotated[
            Literal["jpeg", "png", "webp"] | None,
            Field(description="Output format. Default: same as the source."),
        ] = None,
        quality: Annotated[
            int,
            Field(ge=1, le=100, description="JPEG/WebP quality 1-100 (ignored for PNG)."),
        ] = DEFAULT_QUALITY,
        output_name: Annotated[
            str | None,
            Field(
                max_length=MAX_STEM_CHARS,
                description="Optional file name WITHOUT extension. Letters, digits, space, "
                "'.', '_' and '-' only. Default: '<source name>-<W>x<H>'.",
            ),
        ] = None,
    ) -> ResizeResult:
        try:
            real = root.resolve(path)
            info = resize_image(
                real,
                out,
                output_name,
                width=width,
                height=height,
                fit=fit,
                resample=resample,
                allow_upscale=allow_upscale,
                target=format,
                quality=quality,
                limits=limits,
            )
        except EngineError as err:
            log.info("image_resize refused: %s", err.code)
            raise _tool_error(err) from None
        dest = info.pop("output_file")
        log.info("image_resize ok: %sx%s", info["width"], info["height"])
        return ResizeResult(source=root.display(real), output=_display_output(root, dest), **info)

    @_tool(
        server,
        name="image_compress",
        title="Compress image",
        description=(
            "Make an image file smaller and save it as a NEW file in the output folder "
            "(original never changed, existing files never overwritten). JPEG/WebP: give a "
            "quality (default 80) OR max_bytes, and the highest quality that fits is found "
            "automatically. PNG stays lossless unless 'colors' (2-256) or max_bytes asks for "
            "palette reduction. Reports before/after sizes; warns if the target cannot be met "
            "or the result is not smaller. Keeps the source format unless 'format' is given. "
            "EXIF/GPS metadata is removed. Default name: '<source>-compressed'."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    def image_compress(
        path: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_PATH_CHARS,
                description="Source image path relative to the input folder.",
            ),
        ],
        quality: Annotated[
            int | None,
            Field(ge=1, le=100, description="JPEG/WebP quality 1-100. Default 80."),
        ] = None,
        max_bytes: Annotated[
            int | None,
            Field(
                ge=MIN_TARGET_BYTES,
                le=MAX_FILE_BYTES,
                description="Target maximum file size in bytes (e.g. 200000 for ~200 KB). "
                "Do not combine with quality.",
            ),
        ] = None,
        min_quality: Annotated[
            int,
            Field(ge=1, le=95, description="Lowest JPEG/WebP quality max_bytes may go down to."),
        ] = 10,
        colors: Annotated[
            int | None,
            Field(ge=2, le=256, description="PNG only: reduce to this many colours (lossy)."),
        ] = None,
        format: Annotated[
            Literal["jpeg", "png", "webp"] | None,
            Field(description="Output format. Default: same as the source."),
        ] = None,
        output_name: Annotated[
            str | None,
            Field(
                max_length=MAX_STEM_CHARS,
                description="Optional file name WITHOUT extension. Letters, digits, space, "
                "'.', '_' and '-' only. Default: '<source name>-compressed'.",
            ),
        ] = None,
    ) -> CompressResult:
        try:
            real = root.resolve(path)
            info = compress_image(
                real,
                out,
                output_name,
                target=format,
                quality=quality,
                max_bytes=max_bytes,
                min_quality=min_quality,
                colors=colors,
                limits=limits,
            )
        except EngineError as err:
            log.info("image_compress refused: %s", err.code)
            raise _tool_error(err) from None
        dest = info.pop("output_file")
        log.info("image_compress ok: %s -> %s bytes", info["input_bytes"], info["output_bytes"])
        return CompressResult(source=root.display(real), output=_display_output(root, dest), **info)

    _write_hints = ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )

    @_tool(
        server,
        name="image_rotate_flip",
        title="Rotate or flip image",
        description=(
            "Rotate an image by 90, 180 or 270 degrees CLOCKWISE and/or flip it "
            "(horizontal = mirror left-right, vertical = upside-down mirror) and save it as "
            "a NEW file in the output folder (original never changed, existing files never "
            "overwritten). Directions refer to the photo as it is displayed (EXIF "
            "orientation is applied first). Rotation happens before the flip. Pixel moves "
            "are exact; JPEG output is re-encoded (use format 'png' for a pixel-exact "
            "copy). EXIF/GPS metadata is removed. Default name: '<source>-rot90-flipH'."
        ),
        annotations=_write_hints,
    )
    def image_rotate_flip(
        path: SourcePath,
        rotate: Annotated[
            Literal[0, 90, 180, 270],
            Field(description="Clockwise rotation in degrees."),
        ] = 0,
        flip: Annotated[
            Literal["horizontal", "vertical"] | None,
            Field(description="Optional mirror, applied after rotating."),
        ] = None,
        format: OutFormat = None,
        quality: Quality = DEFAULT_QUALITY,
        lossless: Lossless = False,
        output_name: Annotated[
            str | None,
            Field(
                max_length=MAX_STEM_CHARS,
                description="Optional file name WITHOUT extension. Letters, digits, space, "
                "'.', '_' and '-' only. Default: '<source name>-rot90' etc.",
            ),
        ] = None,
    ) -> RotateFlipResult:
        try:
            real = root.resolve(path)
            info = rotate_flip_image(
                real,
                out,
                output_name,
                rotate=rotate,
                flip=flip,
                target=format,
                quality=quality,
                lossless=lossless,
                limits=limits,
            )
        except EngineError as err:
            log.info("image_rotate_flip refused: %s", err.code)
            raise _tool_error(err) from None
        dest = info.pop("output_file")
        log.info("image_rotate_flip ok: rot %s flip %s", info["rotate"], info["flip"])
        return RotateFlipResult(
            source=root.display(real), output=_display_output(root, dest), **info
        )

    @_tool(
        server,
        name="image_crop",
        title="Crop image",
        description=(
            "Cut out a rectangle of an image and save it as a NEW file in the output folder "
            "(original never changed, existing files never overwritten). Either give "
            "width and height (plus left/top, default 0) in pixels of the image as it is "
            "displayed (EXIF orientation applied; use image_inspect for the size), or give "
            "only 'aspect' like '1:1' or '16:9' for the largest centred crop with that "
            "ratio. Boxes outside the image are refused, not clamped. Output keeps the "
            "source format (JPEG/PNG/WebP, otherwise PNG) unless 'format' is given. "
            "EXIF/GPS metadata is removed. Default name: '<source>-crop-<W>x<H>'."
        ),
        annotations=_write_hints,
    )
    def image_crop(
        path: SourcePath,
        left: Annotated[
            int | None, Field(ge=0, le=MAX_SIDE * 4, description="Left edge (default 0).")
        ] = None,
        top: Annotated[
            int | None, Field(ge=0, le=MAX_SIDE * 4, description="Top edge (default 0).")
        ] = None,
        width: Annotated[
            int | None, Field(ge=1, le=MAX_SIDE * 4, description="Box width in pixels.")
        ] = None,
        height: Annotated[
            int | None, Field(ge=1, le=MAX_SIDE * 4, description="Box height in pixels.")
        ] = None,
        aspect: Annotated[
            str | None,
            Field(
                min_length=3,
                max_length=2 * len(str(MAX_ASPECT_TERM)) + 1,
                pattern=r"^[0-9]+:[0-9]+$",
                description="Instead of a box: centred crop with this ratio, e.g. '1:1'.",
            ),
        ] = None,
        format: OutFormat = None,
        quality: Quality = DEFAULT_QUALITY,
        lossless: Lossless = False,
        output_name: Annotated[
            str | None,
            Field(
                max_length=MAX_STEM_CHARS,
                description="Optional file name WITHOUT extension. Letters, digits, space, "
                "'.', '_' and '-' only. Default: '<source name>-crop-<W>x<H>'.",
            ),
        ] = None,
    ) -> CropResult:
        try:
            real = root.resolve(path)
            info = crop_image(
                real,
                out,
                output_name,
                left=left,
                top=top,
                width=width,
                height=height,
                aspect=aspect,
                target=format,
                quality=quality,
                lossless=lossless,
                limits=limits,
            )
        except EngineError as err:
            log.info("image_crop refused: %s", err.code)
            raise _tool_error(err) from None
        dest = info.pop("output_file")
        log.info("image_crop ok: %sx%s", info["width"], info["height"])
        return CropResult(source=root.display(real), output=_display_output(root, dest), **info)

    @_tool(
        server,
        name="image_batch",
        title="Batch process a folder",
        description=BATCH_DESCRIPTION,
        annotations=_write_hints,
    )
    async def image_batch(
        operation: Annotated[
            Literal["convert", "resize", "compress", "rotate_flip", "crop"],
            Field(description="Which single-image operation to apply to every file."),
        ],
        ctx: Context,
        options: Annotated[
            dict[str, Any] | None,
            Field(description="Options for the operation (see the tool description)."),
        ] = None,
        folder: Annotated[
            str,
            Field(
                max_length=MAX_PATH_CHARS,
                description="Folder relative to the input folder, e.g. 'holiday'. "
                "'.' (default) = the input folder itself.",
            ),
        ] = ".",
        pattern: Annotated[
            str | None,
            Field(
                max_length=MAX_PATTERN_CHARS,
                description="Optional case-insensitive file-name glob, e.g. '*.jpg' or "
                "'IMG_2026*'. Names only, no folders.",
            ),
        ] = None,
        max_files: Annotated[
            int,
            Field(
                ge=1,
                le=MAX_BATCH_FILES,
                description="Refuse the batch if more files than this match "
                f"(default {DEFAULT_BATCH_FILES}, hard limit {MAX_BATCH_FILES}).",
            ),
        ] = DEFAULT_BATCH_FILES,
        dry_run: Annotated[
            bool, Field(description="Only list the files that would be processed.")
        ] = False,
        write_manifest: Annotated[
            bool,
            Field(
                description="Write a JSON manifest of the run to the output folder.",
            ),
        ] = True,
    ) -> BatchResult:
        try:
            opts = parse_options(operation, options)
            folder_path = root.resolve_dir(folder)
            sel = select_files(
                folder_path,
                pattern,
                max_files=max_files,
                output_dir=out.path,
                limits=limits,
            )
        except EngineError as err:
            log.info("image_batch refused: %s", err.code)
            raise _tool_error(err) from None

        folder_display = root.display(folder_path)  # "." for the root itself
        skipped = [SkippedEntry(**s) for s in sel.skipped]
        base = dict(
            operation=operation,
            folder=folder_display,
            pattern=pattern,
            dry_run=dry_run,
            matched=len(sel.files),
            skipped=skipped,
        )
        if dry_run or not sel.files:
            items = [
                BatchItem(source=root.display(p), status="planned", input_bytes=p.stat().st_size)
                for p in sel.files
            ]
            return BatchResult(
                **base,
                succeeded=0,
                failed=0,
                not_run=0,
                stopped_reason=None,
                input_bytes_total=sel.total_bytes,
                output_bytes_total=0,
                manifest=None,
                items=items,
            )

        started = datetime.now(timezone.utc)
        items: list[BatchItem] = []
        records: list[dict] = []
        stopped: str | None = None

        def process(src):
            src_hash = sha256_file(src)
            info = run_one(operation, opts, src, out, limits)
            info["output_sha256"] = sha256_file(info["output_file"])
            info["source_sha256"] = src_hash
            return info

        def record_manifest(status: str):
            if not write_manifest:
                return None
            record = {
                "status": status,
                "started_at": started.isoformat(timespec="seconds"),
                "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "operation": operation,
                "options": opts.model_dump(),
                "folder": folder_display,
                "pattern": pattern,
                "stopped_reason": stopped,
                "skipped": sel.skipped,
                "items": records,
            }
            try:
                return write_batch_manifest(out, operation, record)
            except EngineError as err:
                log.info("image_batch manifest not written: %s", err.code)
                return None

        total = len(sel.files)
        try:
            for i, src in enumerate(sel.files):
                rel = root.display(src)
                try:
                    info = await anyio.to_thread.run_sync(functools.partial(process, src))
                except EngineError as err:
                    items.append(
                        BatchItem(
                            source=rel, status="failed", error_code=err.code, error=err.message
                        )
                    )
                    records.append(
                        {
                            "source": rel,
                            "status": "failed",
                            "error_code": err.code,
                            "error": err.message,
                        }
                    )
                    if err.code == "invalid_argument":
                        # Argument problems are the same for every file: stop now.
                        stopped = "invalid_argument"
                        if not any(it.status == "ok" for it in items):
                            raise _tool_error(err) from None
                        break
                except Exception as exc:  # noqa: BLE001 - one bad file must not end the batch
                    log.warning("image_batch internal error: %s", type(exc).__name__)
                    msg = "Unexpected error while processing this file."
                    items.append(
                        BatchItem(
                            source=rel, status="failed", error_code="internal_error", error=msg
                        )
                    )
                    records.append(
                        {
                            "source": rel,
                            "status": "failed",
                            "error_code": "internal_error",
                            "error": msg,
                        }
                    )
                else:
                    dest = info["output_file"]
                    shown = _display_output(root, dest)
                    items.append(
                        BatchItem(
                            source=rel,
                            status="ok",
                            output=shown,
                            input_bytes=info["input_bytes"],
                            output_bytes=info["output_bytes"],
                            width=info["width"],
                            height=info["height"],
                            format=info["format"],
                            warnings=info["warnings"],
                        )
                    )
                    records.append(
                        {
                            "source": rel,
                            "status": "ok",
                            "output": shown,
                            "source_sha256": info["source_sha256"],
                            "output_sha256": info["output_sha256"],
                            "input_bytes": info["input_bytes"],
                            "output_bytes": info["output_bytes"],
                            "width": info["width"],
                            "height": info["height"],
                            "format": info["format"],
                            "warnings": info["warnings"],
                        }
                    )
                try:
                    await ctx.report_progress(i + 1, total, f"{i + 1}/{total} files")
                except Exception:  # noqa: BLE001 - progress is best effort
                    pass
        except anyio.get_cancelled_exc_class():
            # Every finished file is complete (atomic writes); record what was done.
            stopped = "cancelled"
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(record_manifest, "cancelled")
            log.info("image_batch cancelled after %s files", len(items))
            raise

        done = {it.source for it in items}
        for p in sel.files:
            rel = root.display(p)
            if rel not in done:
                items.append(BatchItem(source=rel, status="not_run"))
                records.append({"source": rel, "status": "not_run"})
        status = "stopped" if stopped else "complete"
        manifest_path = await anyio.to_thread.run_sync(record_manifest, status)
        ok = [it for it in items if it.status == "ok"]
        result = BatchResult(
            **base,
            succeeded=len(ok),
            failed=sum(it.status == "failed" for it in items),
            not_run=sum(it.status == "not_run" for it in items),
            stopped_reason=stopped,
            input_bytes_total=sum(it.input_bytes or 0 for it in ok),
            output_bytes_total=sum(it.output_bytes or 0 for it in ok),
            manifest=_display_output(root, manifest_path) if manifest_path else None,
            items=items,
        )
        log.info("image_batch %s: %s ok, %s failed", operation, result.succeeded, result.failed)
        return result

    return server


def run_stdio(
    root: InputRoot,
    limits: Limits = DEFAULT_LIMITS,
    log_level: str = "WARNING",
    out: OutputDir | None = None,
) -> None:
    build_server(root, limits, log_level, out).run("stdio")
