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
