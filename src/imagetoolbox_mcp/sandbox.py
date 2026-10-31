"""Input path policy: every file an MCP client names must live inside one allowlisted root.

The client sends a path *relative to the root* (an absolute path is accepted only if it
already lies inside the root). We refuse, before touching the file:

* empty paths, NUL bytes and over-long paths;
* any ``..`` component (even one that would stay inside the root);
* any symlink anywhere between the root and the file;
* anything that resolves outside the root.

Error messages never echo the absolute root, so a client cannot learn the host layout.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path, PurePath

from .engine import EngineError

MAX_PATH_CHARS = 1024


class InputRoot:
    """A directory the server may read from. Created once at startup."""

    def __init__(self, root: str | os.PathLike[str]):
        raw = Path(root).expanduser()
        if not raw.is_absolute():
            raw = Path.cwd() / raw
        # The root itself may be reached via a symlink (common in Termux: ~/storage/...);
        # we resolve it once here and then forbid symlinks *below* it.
        resolved = raw.resolve(strict=False)
        if not resolved.is_dir():
            raise ValueError(f"Input root is not an existing directory: {raw}")
        self.path = resolved

    def resolve(self, user_path: str) -> Path:
        """Map a client-supplied path to a real file path inside the root, or raise."""
        parts = self._parts(user_path)
        if not parts:
            raise EngineError("not_a_file", "The path names the input folder, not a file.")
        return self._walk(parts, want_dir=False)

    def resolve_dir(self, user_path: str) -> Path:
        """Like :meth:`resolve`, for a folder. ``""`` or ``"."`` means the root itself."""
        if isinstance(user_path, str) and user_path.strip() in ("", "."):
            return self.path
        parts = self._parts(user_path)
        if not parts:
            return self.path
        return self._walk(parts, want_dir=True)

    def _parts(self, user_path: str) -> tuple[str, ...]:
        if not isinstance(user_path, str) or not user_path.strip():
            raise EngineError("invalid_path", "A non-empty path is required.")
        if "\x00" in user_path:
            raise EngineError("invalid_path", "The path contains a NUL byte.")
        if len(user_path) > MAX_PATH_CHARS:
            raise EngineError("invalid_path", f"The path is longer than {MAX_PATH_CHARS} chars.")

        candidate = PurePath(user_path)
        # Check lexical traversal before normpath can erase it from absolute paths.
        if ".." in candidate.parts:
            raise EngineError("outside_root", "Paths may not contain '..'.")
        # Windows rooted-relative (\\photo.png) and drive-relative (C:photo.png)
        # paths are anchored but not absolute. Joining them can reset the current
        # drive/folder, so reject them before any filesystem lookup.
        if candidate.anchor and not candidate.is_absolute():
            raise EngineError("outside_root", "The path is outside the allowed input folder.")
        if candidate.is_absolute():
            try:
                candidate = PurePath(os.path.normpath(candidate)).relative_to(self.path)
            except ValueError:
                raise EngineError(
                    "outside_root", "The path is outside the allowed input folder."
                ) from None
        parts = candidate.parts
        if any(p == ".." for p in parts):
            raise EngineError("outside_root", "Paths may not contain '..'.")
        return tuple(p for p in parts if p not in ("", "."))

    def _walk(self, parts: tuple[str, ...], *, want_dir: bool) -> Path:
        what = "folder" if want_dir else "image file"
        # Walk component by component with lstat so a symlink at any level is caught.
        current = self.path
        for i, part in enumerate(parts):
            current = current / part
            try:
                st = os.lstat(current)
            except FileNotFoundError:
                raise EngineError("not_found", f"The {what} does not exist.") from None
            except PermissionError:
                raise EngineError("permission_denied", f"The {what} cannot be read.") from None
            if stat.S_ISLNK(st.st_mode):
                raise EngineError("symlink_rejected", "Symbolic links are not accepted.")
            is_last = i == len(parts) - 1
            if (not is_last or want_dir) and not stat.S_ISDIR(st.st_mode):
                if is_last:
                    raise EngineError("not_a_folder", "The path is not a folder.")
                raise EngineError("not_found", f"The {what} does not exist.")

        # Belt and braces: the fully resolved path must still be under the root.
        real = current.resolve(strict=True)
        if not real.is_relative_to(self.path):
            raise EngineError("outside_root", "The path is outside the allowed input folder.")
        return real

    def display(self, path: Path) -> str:
        """Root-relative POSIX form of a path, safe to show to clients and logs."""
        return path.relative_to(self.path).as_posix()
