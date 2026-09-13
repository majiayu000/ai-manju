"""
Path containment helpers to prevent local-file inclusion.
"""
from __future__ import annotations

import errno
import os
import shutil
import stat
from pathlib import Path
from typing import List, Union


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
    try:
        candidate = Path(path).expanduser().resolve()
    except ValueError as exc:
        # e.g. embedded NUL in path → client error, not 500
        raise UnsafePathError(f"Invalid path under {root_resolved}: {path!r}") from exc

    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafePathError(
            f"Path escapes allowed root {root_resolved}: {path}"
        ) from exc

    return candidate


def _require_nofollow() -> int:
    """Return ``O_NOFOLLOW`` or fail closed when the platform lacks it."""
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise UnsafePathError(
            "Refusing to open path: O_NOFOLLOW is unavailable on this platform"
        )
    return nofollow


def _cloexec_flag() -> int:
    return getattr(os, "O_CLOEXEC", 0)


def _directory_flag() -> int:
    return getattr(os, "O_DIRECTORY", 0)


def _components_under_root(
    path: Union[str, Path],
    root_resolved: Path,
) -> List[str]:
    """
    Return path components to walk from ``root_resolved``.

    Absolute paths are resolved for containment (handles platform prefix
    aliases such as macOS ``/var`` -> ``/private/var``). Relative paths are
    anchored at the trusted root. The subsequent ``openat`` + ``O_NOFOLLOW``
    walk is what closes TOCTOU races after this check.
    """
    raw = Path(path).expanduser()

    if not raw.is_absolute():
        rel = os.path.normpath(os.fspath(raw))
        if rel in ("", "."):
            raise UnsafePathError(
                f"Path must name a file under {root_resolved}: {path}"
            )
        if rel == ".." or rel.startswith(".." + os.sep):
            raise UnsafePathError(
                f"Path escapes allowed root {root_resolved}: {path}"
            )
        return [part for part in rel.split(os.sep) if part and part != "."]

    # Resolve for stable prefix comparison; openat walk still enforces no-follow.
    candidate = raw.resolve(strict=False)
    try:
        relative = candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafePathError(
            f"Path escapes allowed root {root_resolved}: {path}"
        ) from exc

    parts = list(relative.parts)
    if not parts or parts == ["."]:
        raise UnsafePathError(
            f"Path must name a file under {root_resolved}: {path}"
        )
    if ".." in parts:
        raise UnsafePathError(
            f"Path escapes allowed root {root_resolved}: {path}"
        )
    return parts


def open_under_root(
    path: Union[str, Path],
    root: Union[str, Path],
) -> int:
    """
    Open ``path`` for reading only if it is a regular file under ``root``.

    Walks from a root directory descriptor with ``openat`` + ``O_NOFOLLOW`` so
    neither leaf nor intermediate directory components can be swapped for
    symlinks that escape ``root``. Fails closed when ``O_NOFOLLOW`` (or
    ``dir_fd``) is unavailable. The caller owns the returned file descriptor
    and must close it.
    """
    nofollow = _require_nofollow()
    cloexec = _cloexec_flag()
    directory = _directory_flag()

    root_resolved = Path(root).resolve()
    components = _components_under_root(path, root_resolved)

    root_flags = os.O_RDONLY | cloexec
    if directory:
        root_flags |= directory

    try:
        walk_fd = os.open(os.fspath(root_resolved), root_flags)
    except OSError:
        raise
    except TypeError as exc:
        raise UnsafePathError(
            "Refusing to open path: secure directory open is unavailable "
            f"on this platform for root {root_resolved}"
        ) from exc

    owned = [walk_fd]
    try:
        for index, component in enumerate(components):
            is_last = index == len(components) - 1
            flags = os.O_RDONLY | nofollow | cloexec
            if not is_last and directory:
                flags |= directory

            try:
                next_fd = os.open(component, flags, dir_fd=walk_fd)
            except TypeError as exc:
                raise UnsafePathError(
                    "Refusing to open path: openat/dir_fd is unavailable "
                    f"on this platform under {root_resolved}"
                ) from exc
            except OSError as exc:
                # Linux typically returns ELOOP for O_NOFOLLOW on a symlink;
                # macOS may return ENOTDIR when O_DIRECTORY|O_NOFOLLOW hits a
                # symlink. Both must fail closed rather than following.
                if exc.errno in (
                    errno.ELOOP,
                    errno.ENOTDIR,
                    getattr(errno, "EMLINK", errno.ELOOP),
                ):
                    raise UnsafePathError(
                        f"Refusing to follow symlink for path under "
                        f"{root_resolved}: {path}"
                    ) from exc
                raise

            os.close(walk_fd)
            owned.remove(walk_fd)
            walk_fd = next_fd
            owned.append(walk_fd)

            file_stat = os.fstat(walk_fd)
            if is_last:
                if not stat.S_ISREG(file_stat.st_mode):
                    raise UnsafePathError(
                        f"Path is not a regular file under {root_resolved}: {path}"
                    )
            elif not stat.S_ISDIR(file_stat.st_mode):
                raise UnsafePathError(
                    f"Intermediate path component is not a directory under "
                    f"{root_resolved}: {path}"
                )

        owned.remove(walk_fd)
        return walk_fd
    finally:
        for fd in owned:
            os.close(fd)


def copy_under_root(
    src: Union[str, Path],
    root: Union[str, Path],
    dst: Union[str, Path],
) -> Path:
    """
    Validate+open ``src`` under ``root`` atomically (root-fd walk +
    ``O_NOFOLLOW``) and copy to ``dst``. Preserves mode and mtime from the
    opened source descriptor.
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
