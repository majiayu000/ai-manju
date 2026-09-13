"""
Path containment helpers to prevent local-file inclusion.
"""
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
