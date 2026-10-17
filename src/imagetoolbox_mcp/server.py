"""MCP server: stdio transport. Tools: ``image_inspect`` (M2, read-only), ``image_convert`` and
``image_resize`` (M3).

Tool names use ``snake_case`` rather than the roadmap's ``image.inspect`` because several
model APIs only accept ``[A-Za-z0-9_-]`` in tool names; dots would break those clients.

Security posture (see SECURITY.md): no shell, no network, no arbitrary filesystem access.
Every path is resolved through :class:`~imagetoolbox_mcp.sandbox.InputRoot`.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .engine import (
    DEFAULT_LIMITS,
    DEFAULT_QUALITY,
    MAX_SIDE,
    EngineError,
    Limits,
    convert_image,
    inspect_image,
    resize_image,
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


def _tool_error(err: EngineError) -> ToolError:
    # Stable, machine-readable prefix the model (and tests) can match on.
    return ToolError(f"[{err.code}] {err.message}")


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

    @server.tool(
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

    @server.tool(
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

    @server.tool(
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

    return server


def run_stdio(
    root: InputRoot,
    limits: Limits = DEFAULT_LIMITS,
    log_level: str = "WARNING",
    out: OutputDir | None = None,
) -> None:
    build_server(root, limits, log_level, out).run("stdio")
