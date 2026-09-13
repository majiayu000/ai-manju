"""
Canonical API module aliases ↔ storage keys used by PipelineController.

Web routes accept short aliases (`script`, `image`); the controller persists
state/quality under storage keys (`script_adapter`, `image_gen`). All read and
write paths should resolve through this module.
"""
from __future__ import annotations

from typing import Optional

# Storage keys written into Project.module_states / quality_scores
STORAGE_SCRIPT_ADAPTER = "script_adapter"
STORAGE_STORYBOARD = "storyboard"
STORAGE_CHARACTER = "character"
STORAGE_IMAGE_GEN = "image_gen"
STORAGE_VIDEO = "video"
STORAGE_AUDIO = "audio"

# URL/API aliases (and identity storage keys) → canonical storage key
API_TO_STORAGE_KEY: dict[str, str] = {
    "script": STORAGE_SCRIPT_ADAPTER,
    "script_adapter": STORAGE_SCRIPT_ADAPTER,
    "storyboard": STORAGE_STORYBOARD,
    "character": STORAGE_CHARACTER,
    "image": STORAGE_IMAGE_GEN,
    "image_gen": STORAGE_IMAGE_GEN,
    "video": STORAGE_VIDEO,
    "audio": STORAGE_AUDIO,
}

# API aliases → PipelineStage.value strings (see controller.PipelineStage)
API_TO_STAGE_VALUE: dict[str, str] = {
    "script": "script_adapt",
    "storyboard": "storyboard",
    "character": "character_design",
    "image": "image_generation",
    "video": "video_synthesis",
    "audio": "audio_editing",
}


def resolve_module_key(module: str) -> str:
    """
    Resolve an API alias or storage key to the canonical storage key.

    Unknown values are returned unchanged so callers can decide how to handle them.
    """
    return API_TO_STORAGE_KEY.get(module, module)


def resolve_stage_value(module: str) -> Optional[str]:
    """Map an API module alias to a PipelineStage.value, or None if unknown."""
    return API_TO_STAGE_VALUE.get(module)


def known_api_modules() -> frozenset[str]:
    """API aliases accepted by run/output endpoints."""
    return frozenset(API_TO_STAGE_VALUE.keys())
