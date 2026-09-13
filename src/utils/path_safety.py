"""
Path safety helpers for web API project file access.

Rejects path-segment traversal and ensures resolved paths stay under a root.
"""
from __future__ import annotations

from pathlib import Path


class UnsafePathError(ValueError):
    """Raised when a path segment or resolved path is unsafe."""


def validate_path_segment(segment: str, *, field: str = "path") -> str:
    """
    Validate a single path segment used in project paths.

    Rejects empty values, ``..``, ``.``, separators, and NUL. Allows ordinary
    filesystem basename characters (spaces, CJK, parentheses, etc.).
    """
    if not segment or segment in {".", ".."}:
        raise UnsafePathError(f"Invalid {field}: empty or reserved segment")
    if "/" in segment or "\\" in segment:
        raise UnsafePathError(f"Invalid {field}: path separators not allowed")
    if "\x00" in segment:
        raise UnsafePathError(f"Invalid {field}: null byte not allowed")
    return segment


def _is_strict_descendant(path: Path, root: Path) -> bool:
    """True when ``path`` is strictly under ``root`` (not equal to it)."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return rel != Path(".")


def safe_join_under(root: Path, *segments: str) -> Path:
    """
    Join ``segments`` under ``root`` after validating each segment.

    Resolves the result and rejects any path that escapes ``root``, equals
    ``root``, or traverses a symlink component (so DELETE cannot follow a
    project-dir symlink onto the projects root or a sibling project).
    """
    if not segments:
        raise UnsafePathError("Path requires at least one segment under root")

    for i, segment in enumerate(segments):
        validate_path_segment(segment, field=f"segment[{i}]")

    root_resolved = root.resolve()
    current = root_resolved
    for i, segment in enumerate(segments):
        current = current / segment
        if current.is_symlink():
            raise UnsafePathError(
                f"Symlink not allowed in path: segment[{i}]"
            )

    candidate = current.resolve()
    if not _is_strict_descendant(candidate, root_resolved):
        raise UnsafePathError("Path escapes projects directory")

    return candidate
