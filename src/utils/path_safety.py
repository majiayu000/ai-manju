"""
Path containment helpers to prevent local-file inclusion.
"""
from __future__ import annotations

import errno
import os
import shutil
import stat
from pathlib import Path
from typing import Union


class UnsafePathError(ValueError):
    """Raised when a path escapes an allowed root directory."""


def resolve_under_root(
    path: Union[str, Path],
    root: Union[str, Path],
) -> Path:
    """
    Resolve ``path`` and ensure it is contained under ``root``.

    Both paths are resolved to absolute form (following symlinks).
    Raises ``UnsafePathError`` if the resolved path is outside ``root``.

    Note: this check alone is not TOCTOU-safe against a symlink swap before
    a later open/copy. Prefer :func:`open_under_root` / :func:`copy_under_root`
    when reading or copying untrusted paths.
    """
    root_resolved = Path(root).resolve()
    candidate = Path(path).expanduser().resolve()

    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafePathError(
            f"Path escapes allowed root {root_resolved}: {path}"
        ) from exc

    return candidate


def open_under_root(
    path: Union[str, Path],
    root: Union[str, Path],
) -> int:
    """
    Open ``path`` for reading only if it is a regular file under ``root``.

    Uses ``O_NOFOLLOW`` so a TOCTOU replacement of the final path component
    with a symlink cannot open a file outside ``root``. The caller owns the
    returned file descriptor and must close it.
    """
    root_resolved = Path(root).resolve()
    raw = Path(path).expanduser()

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    try:
        fd = os.open(os.fspath(raw), flags)
    except OSError as exc:
        # Final component is a symlink (or symlink loop) when O_NOFOLLOW is set.
        if exc.errno in (errno.ELOOP, getattr(errno, "EMLINK", errno.ELOOP)):
            raise UnsafePathError(
                f"Refusing to follow symlink for path under {root_resolved}: {path}"
            ) from exc
        raise

    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise UnsafePathError(
                f"Path is not a regular file under {root_resolved}: {path}"
            )

        # Leaf was opened without following a final symlink; resolve the parent
        # and re-join the leaf name to locate the opened entry under root.
        opened_path = raw.parent.resolve() / raw.name
        try:
            opened_path.relative_to(root_resolved)
        except ValueError as exc:
            raise UnsafePathError(
                f"Path escapes allowed root {root_resolved}: {path}"
            ) from exc

        return fd
    except Exception:
        os.close(fd)
        raise


def copy_under_root(
    src: Union[str, Path],
    root: Union[str, Path],
    dst: Union[str, Path],
) -> Path:
    """
    Validate+open ``src`` under ``root`` atomically (``O_NOFOLLOW``) and copy
    to ``dst``. Preserves mode and mtime from the opened source descriptor.
    """
    dst_path = Path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    fd = open_under_root(src, root)
    try:
        with os.fdopen(fd, "rb") as src_file:
            fd = -1  # ownership transferred to src_file
            file_stat = os.fstat(src_file.fileno())
            with open(dst_path, "wb") as dst_file:
                shutil.copyfileobj(src_file, dst_file)
        os.chmod(dst_path, stat.S_IMODE(file_stat.st_mode))
        os.utime(dst_path, ns=(file_stat.st_atime_ns, file_stat.st_mtime_ns))
    finally:
        if fd >= 0:
            os.close(fd)

    return dst_path
