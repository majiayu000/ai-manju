"""
Path safety helpers for web API project file access.

Rejects path-segment traversal and ensures resolved paths stay under a root.
"""
from __future__ import annotations

import re
from pathlib import Path

# Safe segment: alphanumeric, underscore, hyphen, dot. No separators or "..".
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class UnsafePathError(ValueError):
    """Raised when a path segment or resolved path is unsafe."""


def validate_path_segment(segment: str, *, field: str = "path") -> str:
    """
    Validate a single path segment used in project paths.

    Rejects empty values, ``..``, separators, and any character outside
    the allowed set (alphanumeric, ``_``, ``-``, ``.``).
    """
    if not segment or segment in {".", ".."}:
        raise UnsafePathError(f"Invalid {field}: empty or reserved segment")
    if "/" in segment or "\\" in segment:
        raise UnsafePathError(f"Invalid {field}: path separators not allowed")
    if not _SAFE_SEGMENT_RE.fullmatch(segment):
        raise UnsafePathError(f"Invalid {field}: disallowed characters")
    return segment


def safe_join_under(root: Path, *segments: str) -> Path:
    """
    Join ``segments`` under ``root`` after validating each segment.

    Resolves the result and rejects any path that escapes ``root``.
    """
    for i, segment in enumerate(segments):
        validate_path_segment(segment, field=f"segment[{i}]")

    root_resolved = root.resolve()
    candidate = root_resolved.joinpath(*segments).resolve()

    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafePathError("Path escapes projects directory") from exc

    return candidate
