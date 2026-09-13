"""
端到端流水线测试

完整测试从IP输入到视频输出的全流程
"""
import pytest
import asyncio
import sys
from pathlib import Path
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline.controller import PipelineController, PipelineConfig
from src.utils.file_handler import FileHandler
from config import settings


class TestE2EPipelineMock:
    """端到端流水线测试（模拟模式）"""

    @pytest.fixture
    def sample_ip(self):
        """示例IP内容"""
        return """
        《阴间外卖员》

        李明是一个普通的外卖员，每天穿梭在城市的大街小巷。

        一天深夜，他接到一个奇怪的订单，送餐地址是一个废弃的医院。
        当他到达时，发现接单的是一个穿着民国服装的老人。

        第一章：奇怪的订单
        李明骑着电动车穿过空无一人的街道。
        "谁会在这种地方点外卖？"他嘀咕着。
        医院大厅空荡荡的，月光从破碎的窗户照进来。
        "外卖到了。"李明喊了一声。
        "年轻人，你来了。"一个苍老的声音从黑暗中传来。
        """

    @pytest.mark.asyncio
    async def test_video_audio_modules_registered_and_not_stubbed(self, monkeypatch):
        """Video/audio stages must be wired; stubs that claim success are not allowed."""
        from src.pipeline.controller import PipelineStage
        from src.models.project import Project, ProjectConfig
        from config import settings as app_settings

        # Controller eagerly constructs LLM-backed modules; stub key for local mock tests.
        monkeypatch.setattr(app_settings, "claude_api_key", "test-key-for-mock")

        config = PipelineConfig(
            mock_mode=True,
            skip_video_synthesis=False,
            skip_audio_editing=False,
        )
        controller = PipelineController(config=config)

        assert PipelineStage.VIDEO_SYNTHESIS in controller.modules
        assert PipelineStage.AUDIO_EDITING in controller.modules

        project = Project(
            id="proj_stub_guard",
            name="stub-guard",
            ip_name="stub-guard",
            config=ProjectConfig(total_episodes=1),
            project_dir="/tmp/proj_stub_guard",
            module_states={},
        )

        video_result = await controller._run_video_synthesis(project)
        audio_result = await controller._run_audio_editing(project)

        stub_markers = ("待实现", "尚未实现")
        for result, stage in (
            (video_result, "video"),
            (audio_result, "audio"),
        ):
            message = str(result.get("message", ""))
            error = str(result.get("error", "") or "")
            combined = f"{message} {error}"
            assert not any(marker in combined for marker in stub_markers), (
                f"{stage} stage still returns stub wording: {result}"
            )
            # Missing upstream artifacts must fail, not fake success
            assert result.get("success") is False, (
                f"{stage} stage must not report success without inputs: {result}"
            )

    @pytest.mark.asyncio
    async def test_video_stage_rejects_empty_clips(self, monkeypatch):
        """Video stage must fail when modules report success with no clips."""
        from types import SimpleNamespace
        from src.pipeline.controller import PipelineStage
        from src.models.project import Project, ProjectConfig
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "claude_api_key", "test-key-for-mock")

        controller = PipelineController(config=PipelineConfig(mock_mode=True))
        project = Project(
            id="proj_empty_clips",
            name="empty-clips",
            ip_name="empty-clips",
            config=ProjectConfig(total_episodes=1),
            project_dir="/tmp/proj_empty_clips",
            module_states={
                "storyboard": {"storyboard_paths": ["/tmp/fake_storyboard.json"]},
            },
        )

        class FakeVideoModule:
            async def run(self, *args, **kwargs):
                return SimpleNamespace(
                    success=True,
                    error=None,
                    total_generated=0,
                    failed_shots=[1, 2],
                    video_paths=[],
                    merged_video_path=None,
                )

        controller.modules[PipelineStage.VIDEO_SYNTHESIS] = FakeVideoModule()
        result = await controller._run_video_synthesis(project)
        assert result["success"] is False
        assert "未生成" in (result.get("error") or "")

    @pytest.mark.asyncio
    async def test_audio_stage_requires_final_when_video_present(self, monkeypatch):
        """Audio stage must fail when upstream video exists but no final path."""
        from types import SimpleNamespace
        from src.pipeline.controller import PipelineStage
        from src.models.project import Project, ProjectConfig
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "claude_api_key", "test-key-for-mock")

        controller = PipelineController(config=PipelineConfig(mock_mode=True))
        project = Project(
            id="proj_audio_final",
            name="audio-final",
            ip_name="audio-final",
            config=ProjectConfig(total_episodes=1),
            project_dir="/tmp/proj_audio_final",
            module_states={
                "storyboard": {"storyboard_paths": ["/tmp/fake_storyboard.json"]},
                "video_synth": {
                    "video_paths": ["/tmp/clip.mp4"],
                    "episode_results": [{
                        "storyboard_path": "/tmp/fake_storyboard.json",
                        "video_paths": ["/tmp/clip.mp4"],
                    }],
                },
            },
        )

        class FakeAudioModule:
            async def run(self, *args, **kwargs):
                return SimpleNamespace(
                    success=True,
                    error=None,
                    failed_shots=[],
                    total_duration=1.0,
                    final_video_path=None,
                )

        controller.modules[PipelineStage.AUDIO_EDITING] = FakeAudioModule()
        result = await controller._run_audio_editing(project)
        assert result["success"] is False
        assert "最终视频" in (result.get("error") or "")

    @pytest.mark.asyncio
    async def test_video_error_uses_failed_episode_not_last(self, monkeypatch):
        """Multi-episode video errors should report the failed episode's message."""
        from types import SimpleNamespace
        from src.pipeline.controller import PipelineStage
        from src.models.project import Project, ProjectConfig
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "claude_api_key", "test-key-for-mock")

        controller = PipelineController(config=PipelineConfig(mock_mode=True))
        project = Project(
            id="proj_multi_ep_err",
            name="multi-ep-err",
            ip_name="multi-ep-err",
            config=ProjectConfig(total_episodes=2),
            project_dir="/tmp/proj_multi_ep_err",
            module_states={
                "storyboard": {
                    "storyboard_paths": ["/tmp/ep1.json", "/tmp/ep2.json"],
                },
            },
        )

        outputs = [
            SimpleNamespace(
                success=False,
                error="episode 1 provider timeout",
                total_generated=0,
                failed_shots=[1],
                video_paths=[],
                merged_video_path=None,
            ),
            SimpleNamespace(
                success=True,
                error=None,
                total_generated=2,
                failed_shots=[],
                video_paths=["/tmp/a.mp4", "/tmp/b.mp4"],
                merged_video_path="/tmp/merged.mp4",
            ),
        ]

        class FakeVideoModule:
            def __init__(self):
                self._i = 0

            async def run(self, *args, **kwargs):
                out = outputs[self._i]
                self._i += 1
                return out

        controller.modules[PipelineStage.VIDEO_SYNTHESIS] = FakeVideoModule()
        result = await controller._run_video_synthesis(project)
        assert result["success"] is False
        assert result["error"] == "episode 1 provider timeout"

    def test_normalize_kling_duration_maps_fractional_shots(self):
        """Fractional storyboard durations must map to Kling-supported 5 or 10."""
        from src.modules.video_synth.synthesizer import VideoSynthModule

        assert VideoSynthModule._normalize_kling_duration(6.7) == 5
        assert VideoSynthModule._normalize_kling_duration(3.0) == 5
        assert VideoSynthModule._normalize_kling_duration(8.0) == 10
        assert VideoSynthModule._normalize_kling_duration(10.0) == 10
        assert VideoSynthModule._normalize_kling_duration(5.0) == 5

    @pytest.mark.asyncio
    async def test_mock_audio_compose_skips_ffmpeg(self, monkeypatch, tmp_path):
        """Mock composition must write a placeholder final video without FFmpeg."""
        from src.modules.audio_editing.editor import AudioEditingModule
        from src.models.shot import Shot

        calls = []

        async def boom(*args, **kwargs):
            calls.append(args)
            raise AssertionError("FFmpeg must not run in mock_mode")

        monkeypatch.setattr(AudioEditingModule, "_merge_video_audio", boom)
        monkeypatch.setattr(AudioEditingModule, "_concat_videos", boom)

        clip = tmp_path / "clip.mp4"
        clip.write_bytes(b"mock video data")
        shot = Shot(
            shot_id=1,
            episode_id=1,
            scene_id=1,
            description="mock",
            duration=5.0,
            dialogue="你好",
            video_path=str(clip),
        )

        module = AudioEditingModule()
        result = await module._compose_final_video(
            project_id="proj_mock_compose",
            episode_id=1,
            video_paths=[str(clip)],
            audio_files=[],
            shots=[shot],
            add_bgm=False,
            bgm_path=None,
            bgm_volume=0.3,
            shot_video_segments=[(shot, str(clip))],
            mock_mode=True,
        )

        assert calls == []
        assert Path(result).exists()
        assert Path(result).read_bytes() == b"mock final video data"

    @pytest.mark.asyncio
    async def test_video_audio_stages_propagate_quality_score(self, monkeypatch):
        """Video/audio controller stages must expose quality_score like earlier stages."""
        from types import SimpleNamespace
        from src.pipeline.controller import PipelineStage
        from src.models.project import Project, ProjectConfig
        from src.modules.base import QualityMetrics
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "claude_api_key", "test-key-for-mock")

        controller = PipelineController(config=PipelineConfig(mock_mode=True))
        project = Project(
            id="proj_quality",
            name="quality",
            ip_name="quality",
            config=ProjectConfig(total_episodes=1),
            project_dir="/tmp/proj_quality",
            module_states={
                "storyboard": {"storyboard_paths": ["/tmp/fake_storyboard.json"]},
                "video_synth": {
                    "video_paths": ["/tmp/clip.mp4"],
                    "episode_results": [{
                        "storyboard_path": "/tmp/fake_storyboard.json",
                        "video_paths": ["/tmp/clip.mp4"],
                    }],
                },
            },
        )

        class FakeVideoModule:
            async def run(self, *args, **kwargs):
                return SimpleNamespace(
                    success=True,
                    error=None,
                    total_generated=1,
                    failed_shots=[],
                    video_paths=["/tmp/clip.mp4"],
                    merged_video_path=None,
                    quality=QualityMetrics(score=88.0, details={"ok": 88}, suggestions=[], passed=True),
                )

        class FakeAudioModule:
            async def run(self, *args, **kwargs):
                return SimpleNamespace(
                    success=True,
                    error=None,
                    failed_shots=[],
                    total_duration=1.0,
                    final_video_path="/tmp/final.mp4",
                    quality=QualityMetrics(score=91.0, details={"ok": 91}, suggestions=[], passed=True),
                )

        controller.modules[PipelineStage.VIDEO_SYNTHESIS] = FakeVideoModule()
        controller.modules[PipelineStage.AUDIO_EDITING] = FakeAudioModule()

        video_result = await controller._run_video_synthesis(project)
        audio_result = await controller._run_audio_editing(project)

        assert video_result["success"] is True
        assert video_result["quality_score"] == 88.0
        assert project.quality_scores["video_synth"]["score"] == 88.0
        assert audio_result["success"] is True
        assert audio_result["quality_score"] == 91.0
        assert project.quality_scores["audio_editing"]["score"] == 91.0

    @pytest.mark.asyncio
    async def test_run_single_module_persists_project(self, monkeypatch, tmp_path):
        """Standalone module success must call save_project for handoff state."""
        from src.pipeline.controller import PipelineStage
        from src.models.project import Project, ProjectConfig
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "claude_api_key", "test-key-for-mock")

        controller = PipelineController(config=PipelineConfig(mock_mode=True))
        project = Project(
            id="proj_persist",
            name="persist",
            ip_name="persist",
            config=ProjectConfig(total_episodes=1),
            project_dir=str(tmp_path / "proj_persist"),
            module_states={},
        )

        async def fake_stage(proj, stage):
            proj.set_module_state("video_synth", {"episode_results": [{"ok": True}]})
            return {"success": True}

        saved = {"count": 0}

        async def fake_save(proj):
            saved["count"] += 1
            saved["state"] = dict(proj.module_states.get("video_synth", {}))

        monkeypatch.setattr(controller, "_execute_stage", fake_stage)
        monkeypatch.setattr(controller, "save_project", fake_save)

        result = await controller.run_single_module(project, PipelineStage.VIDEO_SYNTHESIS)
        assert result["success"] is True
        assert saved["count"] == 1
        assert saved["state"].get("episode_results")

    @pytest.mark.asyncio
    async def test_audio_lookup_key_includes_scene(self):
        """Audio map must use episode/scene/shot so multi-scene shot_ids do not collide."""
        from src.modules.audio_editing.editor import AudioEditingModule
        from src.models.shot import Shot

        shot_a = Shot(
            shot_id=1, episode_id=1, scene_id=1, description="a", duration=5.0
        )
        shot_b = Shot(
            shot_id=1, episode_id=1, scene_id=2, description="b", duration=5.0
        )
        af_a = {"shot_id": 1, "episode_id": 1, "scene_id": 1, "audio_path": "/a.mp3"}
        af_b = {"shot_id": 1, "episode_id": 1, "scene_id": 2, "audio_path": "/b.mp3"}

        key_a = AudioEditingModule._audio_lookup_key(shot_a)
        key_b = AudioEditingModule._audio_lookup_key(shot_b)
        assert key_a != key_b
        audio_map = {
            AudioEditingModule._audio_lookup_key(af): af for af in (af_a, af_b)
        }
        assert audio_map[key_a]["audio_path"] == "/a.mp3"
        assert audio_map[key_b]["audio_path"] == "/b.mp3"

    @pytest.mark.asyncio
    async def test_standalone_audio_persists_completed_status(self, monkeypatch, tmp_path):
        """Successful standalone AUDIO_EDITING must save COMPLETED, not AUDIO_EDITING."""
        from types import SimpleNamespace
        from src.pipeline.controller import PipelineStage
        from src.models.project import Project, ProjectConfig, ProjectStatus
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "claude_api_key", "test-key-for-mock")

        controller = PipelineController(config=PipelineConfig(mock_mode=True))
        project = Project(
            id="proj_audio_terminal",
            name="audio-terminal",
            ip_name="audio-terminal",
            config=ProjectConfig(total_episodes=1),
            project_dir=str(tmp_path / "proj_audio_terminal"),
            module_states={
                "storyboard": {"storyboard_paths": ["/tmp/fake_storyboard.json"]},
                "video_synth": {
                    "video_paths": ["/tmp/clip.mp4"],
                    "episode_results": [{
                        "storyboard_path": "/tmp/fake_storyboard.json",
                        "video_paths": ["/tmp/clip.mp4"],
                    }],
                },
            },
        )

        class FakeAudioModule:
            async def run(self, *args, **kwargs):
                return SimpleNamespace(
                    success=True,
                    error=None,
                    failed_shots=[],
                    total_duration=1.0,
                    final_video_path="/tmp/final.mp4",
                    quality=None,
                )

        controller.modules[PipelineStage.AUDIO_EDITING] = FakeAudioModule()

        saved = {}

        async def fake_save(proj):
            saved["status"] = proj.status

        monkeypatch.setattr(controller, "save_project", fake_save)

        result = await controller.run_single_module(project, PipelineStage.AUDIO_EDITING)
        assert result["success"] is True
        assert project.status == ProjectStatus.COMPLETED
        assert saved["status"] == ProjectStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_audio_module_fails_when_all_tts_fail(self, monkeypatch, tmp_path):
        """When every dialogue TTS request fails, module must return success=False."""
        from src.modules.audio_editing.editor import AudioEditingModule, AudioEditingInput
        from src.models.shot import Shot, EpisodeStoryboard, Storyboard

        shot = Shot(
            shot_id=1,
            episode_id=1,
            scene_id=1,
            description="d",
            duration=5.0,
            dialogue="你好世界",
            video_path=str(tmp_path / "clip.mp4"),
        )
        (tmp_path / "clip.mp4").write_bytes(b"mock video data")
        scene = Storyboard(
            project_id="proj_tts_fail",
            episode_id=1,
            scene_id=1,
            shots=[shot],
        )
        storyboard = EpisodeStoryboard(
            project_id="proj_tts_fail",
            episode_id=1,
            scenes=[scene],
        )

        class BoomTTS:
            async def synthesize(self, *args, **kwargs):
                raise RuntimeError("tts down")

        monkeypatch.setattr(
            "src.modules.audio_editing.editor.get_tts_provider",
            lambda **kwargs: BoomTTS(),
        )

        module = AudioEditingModule()
        output = await module.process(
            AudioEditingInput(
                project_id="proj_tts_fail",
                storyboard=storyboard,
                mock_mode=True,
            )
        )
        assert output.success is False
        assert "配音合成全部失败" in (output.error or "")
        assert 1 in output.failed_shots

    @pytest.mark.asyncio
    async def test_implicit_mock_kling_rejected_without_mock_mode(self, monkeypatch, tmp_path):
        """Missing Kling key must not silently succeed with MockKling when mock_mode=False."""
        from src.modules.video_synth.synthesizer import VideoSynthModule, VideoSynthInput
        from src.models.shot import Shot, EpisodeStoryboard, Storyboard
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "kling_api_key", "")

        img = tmp_path / "implicit_mock_shot.png"
        img.write_bytes(b"fake")
        shot = Shot(
            shot_id=1,
            episode_id=1,
            scene_id=1,
            description="d",
            duration=5.0,
            image_path=str(img),
        )
        scene = Storyboard(
            project_id="proj_implicit_mock",
            episode_id=1,
            scene_id=1,
            shots=[shot],
        )
        storyboard = EpisodeStoryboard(
            project_id="proj_implicit_mock",
            episode_id=1,
            scenes=[scene],
        )

        module = VideoSynthModule()
        output = await module.process(
            VideoSynthInput(
                project_id="proj_implicit_mock",
                storyboard=storyboard,
                mock_mode=False,
            )
        )
        assert output.success is False
        assert "API key" in (output.error or "") or "kling" in (output.error or "").lower()

    @pytest.mark.asyncio
    async def test_compose_skips_ffmpeg_for_placeholder_bytes(self, monkeypatch, tmp_path):
        """Implicit mock placeholder clips must bypass FFmpeg even when mock_mode=False."""
        from src.modules.audio_editing.editor import AudioEditingModule
        from src.models.shot import Shot

        calls = []

        async def boom(*args, **kwargs):
            calls.append(args)
            raise AssertionError("FFmpeg must not run on placeholder media")

        monkeypatch.setattr(AudioEditingModule, "_merge_video_audio", boom)
        monkeypatch.setattr(AudioEditingModule, "_concat_videos", boom)

        clip = tmp_path / "clip.mp4"
        clip.write_bytes(b"mock video data")
        shot = Shot(
            shot_id=1,
            episode_id=1,
            scene_id=1,
            description="mock",
            duration=5.0,
            video_path=str(clip),
        )

        module = AudioEditingModule()
        result = await module._compose_final_video(
            project_id="proj_placeholder_compose",
            episode_id=1,
            video_paths=[str(clip)],
            audio_files=[],
            shots=[shot],
            add_bgm=False,
            bgm_path=None,
            bgm_volume=0.3,
            shot_video_segments=[(shot, str(clip))],
            mock_mode=False,
        )

        assert calls == []
        assert Path(result).exists()
        assert Path(result).read_bytes() == b"mock final video data"

    @pytest.mark.asyncio
    async def test_compose_excludes_stale_mock_from_mixed_clips(self, monkeypatch, tmp_path):
        """Mixed real+mock clips must not replace the episode with mock final bytes."""
        from src.modules.audio_editing.editor import AudioEditingModule
        from src.models.shot import Shot

        merge_inputs = []

        async def fake_merge(self, video_path, audio_path, output_path):
            merge_inputs.append(video_path)
            Path(output_path).write_bytes(b"merged-real")

        async def fake_concat(self, video_paths, output_path):
            Path(output_path).write_bytes(b"concat-real")

        monkeypatch.setattr(AudioEditingModule, "_merge_video_audio", fake_merge)
        monkeypatch.setattr(AudioEditingModule, "_concat_videos", fake_concat)

        mock_clip = tmp_path / "stale_mock.mp4"
        real_clip = tmp_path / "real.mp4"
        mock_clip.write_bytes(b"mock video data")
        real_clip.write_bytes(b"real video bytes that are not mock")

        mock_shot = Shot(
            shot_id=1, episode_id=1, scene_id=1, description="stale", duration=5.0,
            video_path=str(mock_clip),
        )
        real_shot = Shot(
            shot_id=2, episode_id=1, scene_id=1, description="real", duration=5.0,
            dialogue="你好",
            video_path=str(real_clip),
        )

        module = AudioEditingModule()
        result = await module._compose_final_video(
            project_id="proj_mixed_compose",
            episode_id=1,
            video_paths=[str(mock_clip), str(real_clip)],
            audio_files=[],
            shots=[mock_shot, real_shot],
            add_bgm=False,
            bgm_path=None,
            bgm_volume=0.3,
            shot_video_segments=[(mock_shot, str(mock_clip)), (real_shot, str(real_clip))],
            mock_mode=False,
        )

        assert Path(result).read_bytes() != b"mock final video data"
        assert str(mock_clip) not in merge_inputs
        assert Path(result).exists()

    def test_is_mock_placeholder_size_gate_avoids_full_read(self, tmp_path, monkeypatch):
        """Large non-mock clips must be rejected by size before reading file body."""
        from src.modules.audio_editing.editor import AudioEditingModule

        large = tmp_path / "large.mp4"
        large.write_bytes(b"x" * 1024 * 64)

        opened = {"count": 0}
        real_open = Path.open

        def counting_open(self, *args, **kwargs):
            opened["count"] += 1
            return real_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", counting_open)
        assert AudioEditingModule._is_mock_placeholder_file(str(large)) is False
        assert opened["count"] == 0

        marker = tmp_path / "mock.mp4"
        marker.write_bytes(b"mock video data")
        assert AudioEditingModule._is_mock_placeholder_file(str(marker)) is True
        assert opened["count"] >= 1

    @pytest.mark.asyncio
    async def test_failed_video_regen_clears_stale_video_path(self, monkeypatch, tmp_path):
        """Failed regenerations must clear prior video_path before storyboard persist."""
        from src.modules.video_synth.synthesizer import VideoSynthModule, VideoSynthInput
        from src.models.shot import Shot, Storyboard, EpisodeStoryboard

        img = tmp_path / "shot.png"
        img.write_bytes(b"fake-image")
        stale = tmp_path / "stale.mp4"
        stale.write_bytes(b"old clip")
        sb_path = tmp_path / "storyboard.json"

        shot = Shot(
            shot_id=1,
            episode_id=1,
            scene_id=1,
            description="regen",
            duration=5.0,
            image_path=str(img),
            video_path=str(stale),
        )
        storyboard = EpisodeStoryboard(
            project_id="proj_clear_stale",
            episode_id=1,
            scenes=[
                Storyboard(
                    project_id="proj_clear_stale",
                    episode_id=1,
                    scene_id=1,
                    shots=[shot],
                )
            ],
        )
        sb_path.write_text(storyboard.model_dump_json())

        class BoomProvider:
            async def image_to_video_and_wait(self, **kwargs):
                raise RuntimeError("provider down")

        monkeypatch.setattr(
            "src.modules.video_synth.synthesizer.get_kling_video_provider",
            lambda mock=False: BoomProvider(),
        )

        module = VideoSynthModule()
        output = await module.process(
            VideoSynthInput(
                project_id="proj_clear_stale",
                storyboard=storyboard,
                storyboard_path=str(sb_path),
                mock_mode=True,
            )
        )

        assert shot.video_path is None
        assert 1 in output.failed_shots
        persisted = EpisodeStoryboard.model_validate_json(sb_path.read_text())
        assert persisted.get_all_shots()[0].video_path is None

    @pytest.mark.asyncio
    async def test_full_pipeline_persists_failed_stage_status(self, monkeypatch, tmp_path):
        """Full-pipeline stage failure must persist ProjectStatus.FAILED before return."""
        from src.pipeline.controller import PipelineStage
        from src.models.project import Project, ProjectConfig, ProjectStatus
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "claude_api_key", "test-key-for-mock")

        controller = PipelineController(
            config=PipelineConfig(
                mock_mode=True,
                skip_script_adapt=True,
                skip_storyboard=True,
                skip_character_design=True,
                skip_image_generation=True,
                skip_video_synthesis=False,
                skip_audio_editing=True,
            )
        )
        project = Project(
            id="proj_full_fail",
            name="full-fail",
            ip_name="full-fail",
            config=ProjectConfig(total_episodes=1),
            project_dir=str(tmp_path / "proj_full_fail"),
            status=ProjectStatus.IMAGE_DONE,
            module_states={},
        )

        async def fake_stage(proj, stage):
            proj.update_status(ProjectStatus.VIDEO_SYNTHESIZING, "video_synth")
            return {"success": False, "error": "video stage boom"}

        saved = {}

        async def fake_save(proj):
            saved["status"] = proj.status
            saved["errors"] = list(proj.errors)

        monkeypatch.setattr(controller, "_execute_stage", fake_stage)
        monkeypatch.setattr(controller, "save_project", fake_save)

        result = await controller.run_full_pipeline(project)
        assert result.success is False
        assert saved["status"] == ProjectStatus.FAILED
        assert any("video stage boom" in (e.get("error") or "") for e in saved["errors"])
        assert project.status == ProjectStatus.FAILED

    @pytest.mark.asyncio
    async def test_run_single_module_persists_failure(self, monkeypatch, tmp_path):
        """Standalone module failure must save FAILED status and error."""
        from src.pipeline.controller import PipelineStage
        from src.models.project import Project, ProjectConfig, ProjectStatus
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "claude_api_key", "test-key-for-mock")

        controller = PipelineController(config=PipelineConfig(mock_mode=True))
        project = Project(
            id="proj_persist_fail",
            name="persist-fail",
            ip_name="persist-fail",
            config=ProjectConfig(total_episodes=1),
            project_dir=str(tmp_path / "proj_persist_fail"),
            module_states={},
        )

        async def fake_stage(proj, stage):
            proj.update_status(ProjectStatus.VIDEO_SYNTHESIZING, "video_synth")
            return {"success": False, "error": "provider timeout"}

        saved = {}

        async def fake_save(proj):
            saved["status"] = proj.status
            saved["errors"] = list(proj.errors)

        monkeypatch.setattr(controller, "_execute_stage", fake_stage)
        monkeypatch.setattr(controller, "save_project", fake_save)

        result = await controller.run_single_module(project, PipelineStage.VIDEO_SYNTHESIS)
        assert result["success"] is False
        assert saved["status"] == ProjectStatus.FAILED
        assert any("provider timeout" in (e.get("error") or "") for e in saved["errors"])

    @pytest.mark.asyncio
    async def test_failed_episode_failed_shots_count_in_totals(self, monkeypatch):
        """failed_shots on success=False episodes must still appear in failed_count."""
        from types import SimpleNamespace
        from src.pipeline.controller import PipelineStage
        from src.models.project import Project, ProjectConfig
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "claude_api_key", "test-key-for-mock")

        controller = PipelineController(config=PipelineConfig(mock_mode=True))
        project = Project(
            id="proj_fail_totals",
            name="fail-totals",
            ip_name="fail-totals",
            config=ProjectConfig(total_episodes=1),
            project_dir="/tmp/proj_fail_totals",
            module_states={
                "storyboard": {"storyboard_paths": ["/tmp/fake_storyboard.json"]},
                "video_synth": {
                    "video_paths": ["/tmp/clip.mp4"],
                    "episode_results": [{
                        "storyboard_path": "/tmp/fake_storyboard.json",
                        "video_paths": ["/tmp/clip.mp4"],
                    }],
                },
            },
        )

        class FakeVideoModule:
            async def run(self, *args, **kwargs):
                return SimpleNamespace(
                    success=False,
                    error="all clips failed",
                    total_generated=0,
                    failed_shots=[1, 2, 3],
                    video_paths=[],
                    merged_video_path=None,
                    quality=None,
                )

        class FakeAudioModule:
            async def run(self, *args, **kwargs):
                return SimpleNamespace(
                    success=False,
                    error="tts down",
                    failed_shots=[7, 8],
                    total_duration=0.0,
                    final_video_path=None,
                    quality=None,
                )

        controller.modules[PipelineStage.VIDEO_SYNTHESIS] = FakeVideoModule()
        controller.modules[PipelineStage.AUDIO_EDITING] = FakeAudioModule()

        video_result = await controller._run_video_synthesis(project)
        audio_result = await controller._run_audio_editing(project)

        assert video_result["success"] is False
        assert video_result["failed_count"] == 3
        assert audio_result["success"] is False
        assert audio_result["failed_count"] == 2

    @pytest.mark.asyncio
    async def test_pipeline_mock_mode(self, sample_ip, tmp_path):
        """测试完整流水线（模拟模式）"""
        # 配置
        config = PipelineConfig(
            total_episodes=1,
            episode_duration=30,
            art_style="anime",
            mock_mode=True,  # 模拟模式
            skip_video_synthesis=True,
            skip_audio_editing=True,
            min_quality_score=50
        )

        # 创建控制器
        controller = PipelineController(config=config)

        # 创建项目
        project = await controller.create_project(
            name="测试项目",
            ip_content=sample_ip,
            description="端到端测试"
        )

        assert project.id is not None
        print(f"\n[项目创建成功]: {project.id}")

        # 运行流水线
        result = await controller.run_full_pipeline(project)

        assert result.success, f"流水线执行失败: {result.errors}"
        print(f"\n[流水线完成]")
        print(f"  成功: {result.success}")
        print(f"  完成阶段: {len(result.completed_stages)}")
        print(f"  耗时: {result.duration_seconds:.1f}秒")

        # 检查各阶段结果
        for stage, stage_result in result.stage_results.items():
            status = "✓" if stage_result.get("success") else "✗"
            quality = stage_result.get("quality_score", "-")
            print(f"  {status} {stage}: 质量={quality}")

    @pytest.mark.asyncio
    async def test_pipeline_single_stage(self, sample_ip, tmp_path):
        """测试单阶段执行"""
        from src.pipeline.controller import PipelineStage

        config = PipelineConfig(
            total_episodes=1,
            episode_duration=30,
            mock_mode=True
        )

        controller = PipelineController(config=config)
        project = await controller.create_project(
            name="单阶段测试",
            ip_content=sample_ip
        )

        # 只执行剧本改编
        result = await controller.run_single_module(project, PipelineStage.SCRIPT_ADAPT)

        assert result.get("success"), "剧本改编失败"
        print(f"\n[单阶段测试完成]: 质量={result.get('quality_score', 'N/A')}")


class TestE2EPipelineRealAPI:
    """端到端流水线真实API测试"""

    @pytest.fixture
    def sample_ip(self):
        """示例IP内容"""
        return """
        《阴间外卖员》

        李明是一个普通的外卖员，每天穿梭在城市的大街小巷。

        一天深夜，他接到一个奇怪的订单，送餐地址是一个废弃的医院。
        当他到达时，发现接单的是一个穿着民国服装的老人。

        第一章：奇怪的订单
        李明骑着电动车穿过空无一人的街道。
        "谁会在这种地方点外卖？"他嘀咕着。
        医院大厅空荡荡的，月光从破碎的窗户照进来。
        "外卖到了。"李明喊了一声。
        "年轻人，你来了。"一个苍老的声音从黑暗中传来。
        """

    @pytest.mark.real_api
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_pipeline_script_and_storyboard(self, sample_ip, has_claude_api):
        """测试剧本和分镜生成（真实API）"""
        if not has_claude_api:
            pytest.skip("Claude API未配置")

        config = PipelineConfig(
            total_episodes=1,
            episode_duration=60,
            art_style="anime",
            mock_mode=False,  # 真实API
            skip_image_generation=True,  # 跳过图像生成以节省时间
            skip_video_synthesis=True,
            skip_audio_editing=True,
            min_quality_score=60
        )

        controller = PipelineController(config=config)

        project = await controller.create_project(
            name="真实API测试",
            ip_content=sample_ip,
            description="使用真实Claude API测试"
        )

        print(f"\n[开始真实API流水线测试]")
        print(f"项目ID: {project.id}")

        result = await controller.run_full_pipeline(project)

        print(f"\n[流水线结果]")
        print(f"成功: {result.success}")
        print(f"耗时: {result.duration_seconds:.1f}秒")

        for stage, stage_result in result.stage_results.items():
            status = "✓" if stage_result.get("success") else "✗"
            quality = stage_result.get("quality_score", "-")
            print(f"  {status} {stage}: 质量={quality}")

        if result.errors:
            print(f"\n错误:")
            for err in result.errors:
                print(f"  - {err}")

    @pytest.mark.real_api
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_pipeline_with_image_generation(
        self,
        sample_ip,
        has_claude_api,
        has_kling_api
    ):
        """完整流水线测试（包含图像生成）"""
        if not has_claude_api:
            pytest.skip("Claude API未配置")
        if not has_kling_api:
            pytest.skip("可灵API未配置")

        config = PipelineConfig(
            total_episodes=1,
            episode_duration=60,
            art_style="anime",
            mock_mode=False,
            skip_video_synthesis=True,  # 跳过视频以节省时间/额度
            skip_audio_editing=True,
            min_quality_score=60,
            max_shots_per_episode=3  # 限制镜头数以节省API额度
        )

        controller = PipelineController(config=config)

        project = await controller.create_project(
            name="完整流水线测试",
            ip_content=sample_ip
        )

        print(f"\n{'='*60}")
        print("开始完整流水线测试（包含图像生成）")
        print(f"{'='*60}")

        # 进度回调
        def on_progress(progress: float, message: str):
            print(f"[{progress:5.1f}%] {message}")

        controller.on_progress = on_progress

        result = await controller.run_full_pipeline(project)

        print(f"\n{'='*60}")
        print("流水线执行完成")
        print(f"{'='*60}")
        print(f"成功: {result.success}")
        print(f"耗时: {result.duration_seconds:.1f}秒")

        # 检查生成的文件
        project_dir = Path(project.project_dir)

        print(f"\n生成的文件:")
        for category in ["script", "storyboard", "characters", "images"]:
            cat_dir = project_dir / category
            if cat_dir.exists():
                files = list(cat_dir.glob("*"))
                if files:
                    print(f"  {category}/")
                    for f in files[:5]:
                        print(f"    - {f.name}")


class TestE2EPipelineQuality:
    """流水线质量评估测试"""

    @pytest.mark.asyncio
    async def test_quality_threshold(self):
        """测试质量阈值机制"""
        from src.modules.base import QualityMetrics

        # 测试从详情计算分数
        details = {
            "completeness": 80,
            "dialogue_quality": 70,
            "structure": 90
        }

        metrics = QualityMetrics.from_details(details)

        assert metrics.score == 80  # 平均值
        assert metrics.passed  # 默认阈值70

    @pytest.mark.asyncio
    async def test_quality_suggestions(self):
        """测试质量建议生成"""
        from src.modules.base import QualityMetrics

        # 低分详情
        details = {
            "completeness": 50,
            "dialogue_quality": 40,
            "structure": 60
        }

        metrics = QualityMetrics.from_details(details, pass_threshold=70)

        assert metrics.score == 50
        assert not metrics.passed
        assert len(metrics.suggestions) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
