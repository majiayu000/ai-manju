"""Tests for API ↔ storage module key resolution."""
from src.models.project import Project, ProjectConfig
from src.pipeline.module_keys import (
    STORAGE_CHARACTER,
    STORAGE_IMAGE_GEN,
    STORAGE_SCRIPT_ADAPTER,
    STORAGE_STORYBOARD,
    known_api_modules,
    resolve_module_key,
    resolve_stage_value,
)


def test_resolve_module_key_aliases():
    assert resolve_module_key("script") == STORAGE_SCRIPT_ADAPTER
    assert resolve_module_key("image") == STORAGE_IMAGE_GEN


def test_resolve_module_key_identity():
    assert resolve_module_key("storyboard") == STORAGE_STORYBOARD
    assert resolve_module_key("character") == STORAGE_CHARACTER
    assert resolve_module_key("script_adapter") == STORAGE_SCRIPT_ADAPTER
    assert resolve_module_key("image_gen") == STORAGE_IMAGE_GEN


def test_resolve_stage_value_for_run_module_routing():
    assert resolve_stage_value("script") == "script_adapt"
    assert resolve_stage_value("image") == "image_generation"
    assert resolve_stage_value("storyboard") == "storyboard"
    assert resolve_stage_value("unknown") is None
    assert known_api_modules() == frozenset(
        {"script", "storyboard", "character", "image", "video", "audio"}
    )


def _lookup_module_output(project: Project, module: str) -> dict:
    """Mirror get_module_output storage-key resolution."""
    storage_key = resolve_module_key(module)
    return {
        "module": module,
        "storage_key": storage_key,
        "state": project.module_states.get(storage_key),
        "quality": project.quality_scores.get(storage_key),
    }


def test_get_module_output_lookup_returns_stored_state_and_quality():
    project = Project(
        id="proj_test",
        name="key-mismatch",
        ip_name="test-ip",
        config=ProjectConfig(),
    )
    project.set_module_state(
        STORAGE_SCRIPT_ADAPTER,
        {"script_path": "/tmp/script.json", "episodes_count": 3},
    )
    project.set_quality_score(STORAGE_SCRIPT_ADAPTER, 88.5, {"note": "ok"})
    project.set_module_state(
        STORAGE_IMAGE_GEN,
        {"total_generated": 12, "failed_shots": []},
    )
    project.set_quality_score(STORAGE_IMAGE_GEN, 91.0, {"note": "images"})

    script_out = _lookup_module_output(project, "script")
    assert script_out["storage_key"] == STORAGE_SCRIPT_ADAPTER
    assert script_out["state"]["script_path"] == "/tmp/script.json"
    assert script_out["quality"]["score"] == 88.5

    image_out = _lookup_module_output(project, "image")
    assert image_out["storage_key"] == STORAGE_IMAGE_GEN
    assert image_out["state"]["total_generated"] == 12
    assert image_out["quality"]["score"] == 91.0

    # Identity keys still work for modules whose API and storage names match.
    project.set_module_state(STORAGE_STORYBOARD, {"total_shots": 40})
    storyboard_out = _lookup_module_output(project, "storyboard")
    assert storyboard_out["state"]["total_shots"] == 40
