"""Tests for API ↔ storage module key resolution."""
from src.models.project import Project, ProjectConfig
from src.pipeline.module_keys import (
    STORAGE_AUDIO_EDITING,
    STORAGE_IMAGE_GEN,
    STORAGE_SCRIPT_ADAPTER,
    STORAGE_STORYBOARD,
    STORAGE_VIDEO_SYNTH,
    known_api_modules,
    resolve_module_key,
    resolve_stage_value,
)


def test_resolve_module_key_aliases():
    assert resolve_module_key("script") == STORAGE_SCRIPT_ADAPTER
    assert resolve_module_key("image") == STORAGE_IMAGE_GEN
    assert resolve_module_key("video") == STORAGE_VIDEO_SYNTH
    assert resolve_module_key("audio") == STORAGE_AUDIO_EDITING


def test_resolve_module_key_identity():
    assert resolve_module_key("storyboard") == STORAGE_STORYBOARD
    assert resolve_module_key("video_synth") == STORAGE_VIDEO_SYNTH
    assert resolve_module_key("audio_editing") == STORAGE_AUDIO_EDITING


def test_resolve_stage_value_for_run_module_routing():
    assert resolve_stage_value("script") == "script_adapt"
    assert resolve_stage_value("video") == "video_synthesis"
    assert resolve_stage_value("audio") == "audio_editing"
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


def test_get_module_output_lookup_returns_video_audio_under_api_aliases():
    project = Project(
        id="proj_test",
        name="key-mismatch",
        ip_name="test-ip",
        config=ProjectConfig(),
    )
    project.set_module_state(
        STORAGE_VIDEO_SYNTH,
        {"total_generated": 4, "video_paths": ["/tmp/a.mp4"]},
    )
    project.set_quality_score(STORAGE_VIDEO_SYNTH, 88.0, {"note": "ok"})
    project.set_module_state(
        STORAGE_AUDIO_EDITING,
        {"final_video_paths": ["/tmp/final.mp4"]},
    )
    project.set_quality_score(STORAGE_AUDIO_EDITING, 91.0, {"note": "audio"})

    video_out = _lookup_module_output(project, "video")
    assert video_out["storage_key"] == STORAGE_VIDEO_SYNTH
    assert video_out["state"]["total_generated"] == 4
    assert video_out["quality"]["score"] == 88.0

    audio_out = _lookup_module_output(project, "audio")
    assert audio_out["storage_key"] == STORAGE_AUDIO_EDITING
    assert audio_out["state"]["final_video_paths"] == ["/tmp/final.mp4"]
    assert audio_out["quality"]["score"] == 91.0
