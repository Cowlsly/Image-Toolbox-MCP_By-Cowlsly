"""Output policy (ADR-0002): one fixed folder, flat safe names, never overwrite, atomic writes.

Files are only ever *created*. A name is claimed with ``O_CREAT | O_EXCL | O_NOFOLLOW``
(atomic, refuses existing files and planted symlinks), the content is written to a hidden
temp file in the same folder, fsynced and then ``os.replace``d onto the claimed name.
This works on Android shared storage (FUSE), where hard links are unavailable.
"""

from __future__ import annotations

import os
import re
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from .engine import EngineError

MAX_STEM_CHARS = 100
MAX_SUFFIX = 999
DEFAULT_DIRNAME = "imagetoolbox-out"
_STEM_RE = re.compile(r"^[A-Za-z0-9 ._-]+$")
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9 ._-]+")
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_BINARY = getattr(os, "O_BINARY", 0)


def validate_stem(stem: str) -> str:
    """Check a client-supplied output name stem; return it stripped, or raise."""
    if not isinstance(stem, str):
        raise EngineError("invalid_name", "The output name must be text.")
    s = stem.strip()
    if not s or len(s) > MAX_STEM_CHARS:
        raise EngineError("invalid_name", f"The output name must be 1-{MAX_STEM_CHARS} characters.")
    if not _STEM_RE.match(s):
        raise EngineError(
            "invalid_name",
            "The output name may only use letters, digits, space, '.', '_' and '-' "
            "(no folders or extensions are needed).",
        )
    if s.startswith(".") or s in (".", ".."):
        raise EngineError("invalid_name", "The output name may not start with '.'.")
    return s


def default_stem(source: Path) -> str:
    """Derive a safe stem from a source file name (never fails)."""
    s = _UNSAFE_CHARS.sub("_", source.stem).strip(" .")
    s = s[:MAX_STEM_CHARS].rstrip(" .")
    return s or "image"


class OutputDir:
    """The one folder tools may create files in. Configured once at startup."""

    def __init__(self, path: str | os.PathLike[str]):
        raw = Path(path).expanduser()
        if not raw.is_absolute():
            raw = Path.cwd() / raw
        resolved = raw.resolve(strict=False)
        if resolved.exists() and not resolved.is_dir():
            raise ValueError(f"Output folder exists but is not a directory: {raw}")
        if not resolved.exists() and not resolved.parent.is_dir():
            raise ValueError(f"Parent of the output folder does not exist: {raw}")
        self.path = resolved

    def _ensure_dir(self) -> None:
        try:
            os.mkdir(self.path, 0o755)
        except FileExistsError:
            pass
        except OSError:
            raise EngineError(
                "output_unavailable", "The output folder cannot be created."
            ) from None
        st = os.lstat(self.path)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise EngineError("output_unavailable", "The output folder is not a real directory.")

    def _claim(self, stem: str, ext: str) -> Path:
        for n in range(MAX_SUFFIX + 1):
            name = f"{stem}.{ext}" if n == 0 else f"{stem}-{n}.{ext}"
            target = self.path / name
            try:
                fd = os.open(
                    target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_BINARY, 0o644
                )
            except FileExistsError:
                continue
            except OSError:
                raise EngineError("output_unavailable", "Cannot create the output file.") from None
            os.close(fd)
            return target
        raise EngineError(
            "name_exhausted", f"'{stem}.{ext}' and {MAX_SUFFIX} numbered variants already exist."
        )

    def write_new(self, stem: str, ext: str, writer: Callable[[BinaryIO], None]) -> Path:
        """Create a new file ``<stem>[-N].<ext>``; ``writer`` fills it. Never overwrites."""
        stem = validate_stem(stem)
        if not re.fullmatch(r"[a-z0-9]{1,5}", ext):
            raise EngineError("invalid_name", "Unsupported output extension.")
        self._ensure_dir()
        target = self._claim(stem, ext)
        tmp_name = None
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=".itmcp-", suffix=".tmp", dir=self.path)
            with os.fdopen(fd, "wb") as fh:
                writer(fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, target)
            tmp_name = None
        except BaseException:
            if tmp_name is not None:
                _silent_unlink(Path(tmp_name))
            _silent_unlink(target)
            raise
        return target


def _silent_unlink(p: Path) -> None:
    try:
        os.unlink(p)
    except OSError:
        pass
