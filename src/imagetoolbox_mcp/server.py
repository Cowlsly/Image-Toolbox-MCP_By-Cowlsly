"""MCP server (milestone M2): stdio transport, one read-only tool, ``image_inspect``.

Tool names use ``snake_case`` rather than the roadmap's ``image.inspect`` because several
model APIs only accept ``[A-Za-z0-9_-]`` in tool names; dots would break those clients.

Security posture (see SECURITY.md): no shell, no network, no arbitrary filesystem access.
Every path is resolved through :class:`~imagetoolbox_mcp.sandbox.InputRoot`.
"""

from __future__ import annotations

import logging
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .engine import DEFAULT_LIMITS, EngineError, Limits, inspect_image
from .sandbox import MAX_PATH_CHARS, InputRoot

log = logging.getLogger("imagetoolbox_mcp")

SERVER_NAME = "imagetoolbox-mcp"

INSTRUCTIONS = (
    "Safe, local image tools inspired by Image Toolbox (T8RIN). Paths are relative to the "
    "single input folder the user configured; '..', symlinks and absolute paths outside it "
    "are refused. Tools never modify original files."
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


def _tool_error(err: EngineError) -> ToolError:
    # Stable, machine-readable prefix the model (and tests) can match on.
    return ToolError(f"[{err.code}] {err.message}")


def build_server(
    root: InputRoot, limits: Limits = DEFAULT_LIMITS, log_level: str = "WARNING"
) -> MCPServer:
    """Create a configured server. Separate from ``run`` so tests can connect in-process."""
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

    return server


def run_stdio(root: InputRoot, limits: Limits = DEFAULT_LIMITS, log_level: str = "WARNING") -> None:
    build_server(root, limits, log_level).run("stdio")
