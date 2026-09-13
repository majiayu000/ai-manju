"""
流水线控制器 - 编排和管理整个生产流程
"""
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any
from enum import Enum
from pydantic import BaseModel, Field
from loguru import logger

from src.models.project import Project, ProjectStatus, ProjectConfig
from src.models.script import Script
from src.models.character import CharacterDesignSet
from src.models.shot import EpisodeStoryboard
from src.modules.script_adapter import ScriptAdapterModule, ScriptAdapterInput
from src.modules.storyboard import StoryboardModule, StoryboardInput
from src.modules.character import CharacterDesignModule, CharacterDesignInput
from src.modules.image_gen import ImageGeneratorModule, ImageGenInput
from src.modules.video_synth import VideoSynthModule, VideoSynthInput
from src.modules.audio_editing import AudioEditingModule, AudioEditingInput
from src.utils.file_handler import FileHandler
from config import settings


class PipelineStage(str, Enum):
    """流水线阶段"""
    INIT = "init"
    SCRIPT_ADAPT = "script_adapt"
    STORYBOARD = "storyboard"
    CHARACTER_DESIGN = "character_design"
    IMAGE_GENERATION = "image_generation"
    VIDEO_SYNTHESIS = "video_synthesis"
    AUDIO_EDITING = "audio_editing"
    COMPLETED = "completed"


class PipelineConfig(BaseModel):
    """流水线配置"""
    # 基本配置
    total_episodes: int = Field(default=10, description="总集数")
    episode_duration: int = Field(default=90, description="每集时长(秒)")
    art_style: str = Field(default="anime", description="艺术风格")

    # 各阶段开关
    skip_script_adapt: bool = Field(default=False, description="跳过剧本改编")
    skip_storyboard: bool = Field(default=False, description="跳过分镜生成")
    skip_character_design: bool = Field(default=False, description="跳过角色设计")
    skip_image_generation: bool = Field(default=False, description="跳过图像生成")
    skip_video_synthesis: bool = Field(default=True, description="跳过视频合成")
    skip_audio_editing: bool = Field(default=True, description="跳过配音剪辑")

    # 处理范围
    episode_range: Optional[tuple[int, int]] = Field(default=None, description="处理的集数范围")

    # 质量控制
    min_quality_score: float = Field(default=70.0, description="最低质量分数")
    auto_retry: bool = Field(default=True, description="低质量自动重试")
    max_retries: int = Field(default=3, description="最大重试次数")

    # 模式
    mock_mode: bool = Field(default=False, description="模拟模式")
    dry_run: bool = Field(default=False, description="空运行（不实际执行）")


class PipelineResult(BaseModel):
    """流水线结果"""
    project_id: str
    success: bool
    current_stage: PipelineStage
    completed_stages: list[PipelineStage] = Field(default_factory=list)
    stage_results: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class PipelineController:
    """
    流水线控制器

    管理整个漫剧生产流程，支持：
    - 全流程执行
    - 单模块执行
    - 断点恢复
    - 质量监控
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.file_handler = FileHandler()
        self.logger = logger.bind(module="pipeline")

        # 初始化模块
        self.modules = {
            PipelineStage.SCRIPT_ADAPT: ScriptAdapterModule(),
            PipelineStage.STORYBOARD: StoryboardModule(),
            PipelineStage.CHARACTER_DESIGN: CharacterDesignModule(),
            PipelineStage.IMAGE_GENERATION: ImageGeneratorModule(),
            PipelineStage.VIDEO_SYNTHESIS: VideoSynthModule(),
            PipelineStage.AUDIO_EDITING: AudioEditingModule(),
        }

        # 回调函数
        self.on_stage_start: Optional[Callable[[PipelineStage], None]] = None
        self.on_stage_complete: Optional[Callable[[PipelineStage, Any], None]] = None
        self.on_progress: Optional[Callable[[float, str], None]] = None

    async def create_project(
        self,
        name: str,
        ip_content: Optional[str] = None,
        ip_content_path: Optional[str] = None,
        description: str = "",
        **kwargs
    ) -> Project:
        """
        创建新项目

        Args:
            name: 项目名称
            ip_content: IP原文内容
            ip_content_path: IP文件路径
            description: 项目描述

        Returns:
            创建的项目对象
        """
        project_id = f"proj_{uuid.uuid4().hex[:8]}"
        self.logger.info(f"创建项目: {name} ({project_id})")

        # 创建项目目录
        project_dir = self.file_handler.ensure_project_structure(project_id)

        # 如果有IP内容，保存到文件
        if ip_content:
            input_path = self.file_handler.get_input_path(project_id, "ip_content.txt")
            await self.file_handler.write_text(input_path, ip_content)
            ip_content_path = str(input_path)
        elif ip_content_path:
            # 复制到项目目录
            src_path = Path(ip_content_path)
            if src_path.exists():
                dest_path = self.file_handler.get_input_path(project_id, src_path.name)
                self.file_handler.copy_file(src_path, dest_path)
                ip_content_path = str(dest_path)

        # 创建项目配置
        project_config = ProjectConfig(
            total_episodes=self.config.total_episodes,
            episode_duration=self.config.episode_duration,
            art_style=self.config.art_style,
            **kwargs
        )

        # 创建项目
        project = Project(
            id=project_id,
            name=name,
            description=description,
            ip_name=name,
            ip_content_path=ip_content_path,
            config=project_config,
            project_dir=str(project_dir)
        )

        # 保存项目信息
        project_file = project_dir / "project.json"
        await self.file_handler.write_json(project_file, project.model_dump())

        self.logger.info(f"项目创建完成: {project_dir}")
        return project

    async def load_project(self, project_id: str) -> Project:
        """加载已有项目"""
        project_dir = self.file_handler.get_project_dir(project_id)
        project_file = project_dir / "project.json"

        if not project_file.exists():
            raise FileNotFoundError(f"项目不存在: {project_id}")

        project_data = await self.file_handler.read_json(project_file)
        return Project(**project_data)

    async def save_project(self, project: Project):
        """保存项目状态"""
        project.updated_at = datetime.now()
        project_file = Path(project.project_dir) / "project.json"
        await self.file_handler.write_json(project_file, project.model_dump())

    async def run_full_pipeline(
        self,
        project: Project,
        start_from: Optional[PipelineStage] = None
    ) -> PipelineResult:
        """
        执行完整流水线

        Args:
            project: 项目对象
            start_from: 从指定阶段开始（用于断点恢复）

        Returns:
            流水线执行结果
        """
        result = PipelineResult(
            project_id=project.id,
            success=False,
            current_stage=PipelineStage.INIT,
            started_at=datetime.now()
        )

        self.logger.info(f"开始执行流水线: {project.id}")

        try:
            # 确定要执行的阶段
            stages = self._get_stages_to_run(start_from)

            total_stages = len(stages)
            for i, stage in enumerate(stages):
                # 更新进度
                progress = (i / total_stages) * 100
                self._report_progress(progress, f"执行阶段: {stage.value}")
                result.current_stage = stage

                # 回调
                if self.on_stage_start:
                    self.on_stage_start(stage)

                # 执行阶段
                self.logger.info(f"执行阶段: {stage.value}")
                stage_result = await self._execute_stage(project, stage)

                # 记录结果
                result.stage_results[stage.value] = {
                    "success": stage_result.get("success", False),
                    "quality_score": stage_result.get("quality_score"),
                    "error": stage_result.get("error")
                }

                if not stage_result.get("success", False):
                    error_msg = stage_result.get("error", "Unknown error")
                    result.errors.append(f"{stage.value}: {error_msg}")
                    self.logger.error(f"阶段 {stage.value} 失败: {error_msg}")
                    break

                result.completed_stages.append(stage)

                # 回调
                if self.on_stage_complete:
                    self.on_stage_complete(stage, stage_result)

                # 保存项目状态
                await self.save_project(project)

            # 检查是否全部完成
            if len(result.completed_stages) == len(stages):
                result.success = True
                result.current_stage = PipelineStage.COMPLETED
                project.update_status(ProjectStatus.COMPLETED)
                # Persist terminal status (loop only saved AUDIO_EDITING before this).
                await self.save_project(project)

            result.completed_at = datetime.now()
            result.duration_seconds = (result.completed_at - result.started_at).total_seconds()

            self.logger.info(
                f"流水线完成: success={result.success}, "
                f"stages={len(result.completed_stages)}/{len(stages)}, "
                f"duration={result.duration_seconds:.1f}s"
            )

            return result

        except Exception as e:
            self.logger.exception(f"流水线执行异常: {e}")
            result.errors.append(str(e))
            result.completed_at = datetime.now()
            result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
            return result

    def _get_stages_to_run(self, start_from: Optional[PipelineStage]) -> list[PipelineStage]:
        """获取要执行的阶段列表"""
        all_stages = [
            (PipelineStage.SCRIPT_ADAPT, self.config.skip_script_adapt),
            (PipelineStage.STORYBOARD, self.config.skip_storyboard),
            (PipelineStage.CHARACTER_DESIGN, self.config.skip_character_design),
            (PipelineStage.IMAGE_GENERATION, self.config.skip_image_generation),
            (PipelineStage.VIDEO_SYNTHESIS, self.config.skip_video_synthesis),
            (PipelineStage.AUDIO_EDITING, self.config.skip_audio_editing),
        ]

        # 过滤跳过的阶段
        stages = [stage for stage, skip in all_stages if not skip]

        # 如果指定了起始阶段，截取
        if start_from:
            try:
                start_idx = stages.index(start_from)
                stages = stages[start_idx:]
            except ValueError:
                pass

        return stages

    async def _execute_stage(self, project: Project, stage: PipelineStage) -> dict:
        """执行单个阶段"""
        if self.config.dry_run:
            self.logger.info(f"[DRY RUN] 跳过实际执行: {stage.value}")
            return {"success": True, "dry_run": True}

        if stage == PipelineStage.SCRIPT_ADAPT:
            return await self._run_script_adapt(project)
        elif stage == PipelineStage.STORYBOARD:
            return await self._run_storyboard(project)
        elif stage == PipelineStage.CHARACTER_DESIGN:
            return await self._run_character_design(project)
        elif stage == PipelineStage.IMAGE_GENERATION:
            return await self._run_image_generation(project)
        elif stage == PipelineStage.VIDEO_SYNTHESIS:
            return await self._run_video_synthesis(project)
        elif stage == PipelineStage.AUDIO_EDITING:
            return await self._run_audio_editing(project)
        else:
            return {"success": False, "error": f"Unknown stage: {stage}"}

    async def _run_script_adapt(self, project: Project) -> dict:
        """执行剧本改编"""
        project.update_status(ProjectStatus.SCRIPT_ADAPTING, "script_adapter")

        module = self.modules[PipelineStage.SCRIPT_ADAPT]
        input_data = ScriptAdapterInput(
            project_id=project.id,
            ip_content_path=project.ip_content_path,
            total_episodes=project.config.total_episodes,
            episode_duration=project.config.episode_duration
        )

        output = await module.run(
            input_data,
            min_quality_score=self.config.min_quality_score,
            max_retries=self.config.max_retries,
            auto_retry=self.config.auto_retry
        )

        if output.success:
            project.update_status(ProjectStatus.SCRIPT_DONE)
            project.set_module_state("script_adapter", {
                "script_path": output.script_path,
                "episodes_count": len(output.script.episodes) if output.script else 0
            })
            if output.quality:
                project.set_quality_score("script_adapter", output.quality.score, output.quality.details)

        return {
            "success": output.success,
            "error": output.error,
            "quality_score": output.quality.score if output.quality else None,
            "script_path": output.script_path
        }

    async def _run_storyboard(self, project: Project) -> dict:
        """执行分镜生成"""
        project.update_status(ProjectStatus.STORYBOARD_GENERATING, "storyboard")

        # 获取剧本路径
        script_state = project.module_states.get("script_adapter", {})
        script_path = script_state.get("script_path")

        if not script_path:
            return {"success": False, "error": "没有找到剧本文件"}

        module = self.modules[PipelineStage.STORYBOARD]
        input_data = StoryboardInput(
            project_id=project.id,
            script_path=script_path,
            target_duration_per_episode=project.config.episode_duration
        )

        output = await module.run(
            input_data,
            min_quality_score=self.config.min_quality_score,
            max_retries=self.config.max_retries,
            auto_retry=self.config.auto_retry
        )

        if output.success:
            project.update_status(ProjectStatus.STORYBOARD_DONE)
            project.set_module_state("storyboard", {
                "storyboard_paths": output.storyboard_paths,
                "total_shots": output.total_shots,
                "total_duration": output.total_duration
            })
            if output.quality:
                project.set_quality_score("storyboard", output.quality.score, output.quality.details)

        return {
            "success": output.success,
            "error": output.error,
            "quality_score": output.quality.score if output.quality else None,
            "total_shots": output.total_shots
        }

    async def _run_character_design(self, project: Project) -> dict:
        """执行角色设计"""
        project.update_status(ProjectStatus.CHARACTER_DESIGNING, "character")

        # 获取剧本路径
        script_state = project.module_states.get("script_adapter", {})
        script_path = script_state.get("script_path")

        if not script_path:
            return {"success": False, "error": "没有找到剧本文件"}

        module = self.modules[PipelineStage.CHARACTER_DESIGN]
        input_data = CharacterDesignInput(
            project_id=project.id,
            script_path=script_path,
            art_style=project.config.art_style
        )

        output = await module.run(
            input_data,
            min_quality_score=self.config.min_quality_score,
            max_retries=self.config.max_retries,
            auto_retry=self.config.auto_retry
        )

        if output.success:
            project.update_status(ProjectStatus.CHARACTER_DONE)
            project.set_module_state("character", {
                "design_path": output.design_path,
                "character_count": output.character_count
            })
            if output.quality:
                project.set_quality_score("character", output.quality.score, output.quality.details)

        return {
            "success": output.success,
            "error": output.error,
            "quality_score": output.quality.score if output.quality else None,
            "character_count": output.character_count
        }

    async def _run_image_generation(self, project: Project) -> dict:
        """执行图像生成"""
        project.update_status(ProjectStatus.IMAGE_GENERATING, "image_gen")

        # 获取分镜和角色设计路径
        storyboard_state = project.module_states.get("storyboard", {})
        character_state = project.module_states.get("character", {})

        storyboard_paths = storyboard_state.get("storyboard_paths", [])
        character_path = character_state.get("design_path")

        if not storyboard_paths:
            return {"success": False, "error": "没有找到分镜文件"}

        module = self.modules[PipelineStage.IMAGE_GENERATION]

        # 处理每一集
        all_results = []
        total_generated = 0
        all_failed = []

        for sb_path in storyboard_paths:
            input_data = ImageGenInput(
                project_id=project.id,
                storyboard_path=sb_path,
                character_designs_path=character_path,
                aspect_ratio=project.config.aspect_ratio or "9:16",
                style=project.config.art_style,
                mock_mode=self.config.mock_mode
            )

            output = await module.run(
                input_data,
                min_quality_score=self.config.min_quality_score,
                max_retries=self.config.max_retries,
                auto_retry=self.config.auto_retry
            )

            all_results.append(output)
            if output.success:
                total_generated += output.total_generated
                all_failed.extend(output.failed_shots)

        # 汇总结果
        success = all(r.success for r in all_results)
        all_image_paths = []
        for r in all_results:
            all_image_paths.extend(getattr(r, "image_paths", []) or [])

        if success:
            project.update_status(ProjectStatus.IMAGE_DONE)
            project.set_module_state("image_gen", {
                "total_generated": total_generated,
                "failed_shots": all_failed,
                "image_paths": all_image_paths,
                "storyboard_paths": storyboard_paths,
            })

        return {
            "success": success,
            "error": None if success else "部分图像生成失败",
            "total_generated": total_generated,
            "failed_count": len(all_failed)
        }

    @staticmethod
    def _first_stage_error(results, fallback: str) -> str:
        """Prefer an actionable error from a failed result over the last result."""
        for result in results:
            if not getattr(result, "success", False) and getattr(result, "error", None):
                return result.error
        for result in results:
            if getattr(result, "error", None):
                return result.error
        return fallback

    async def _run_video_synthesis(self, project: Project) -> dict:
        """执行视频合成"""
        project.update_status(ProjectStatus.VIDEO_SYNTHESIZING, "video_synth")

        storyboard_state = project.module_states.get("storyboard", {})
        storyboard_paths = storyboard_state.get("storyboard_paths", [])

        if not storyboard_paths:
            return {"success": False, "error": "没有找到分镜文件"}

        module = self.modules[PipelineStage.VIDEO_SYNTHESIS]

        all_results = []
        total_generated = 0
        all_failed = []
        all_video_paths = []
        episode_results = []

        for sb_path in storyboard_paths:
            input_data = VideoSynthInput(
                project_id=project.id,
                storyboard_path=sb_path,
                mock_mode=self.config.mock_mode
            )

            output = await module.run(
                input_data,
                min_quality_score=self.config.min_quality_score,
                max_retries=self.config.max_retries,
                auto_retry=self.config.auto_retry
            )

            all_results.append(output)
            if output.success:
                total_generated += output.total_generated
                all_failed.extend(output.failed_shots)
                all_video_paths.extend(output.video_paths or [])
                episode_results.append({
                    "storyboard_path": sb_path,
                    "video_paths": list(output.video_paths or []),
                    "merged_video_path": output.merged_video_path,
                })

        # Module may report success=True with empty video_paths when every clip fails.
        has_clips = all(
            bool(getattr(r, "video_paths", None))
            for r in all_results
            if getattr(r, "success", False)
        )
        success = (
            bool(all_results)
            and all(r.success for r in all_results)
            and has_clips
            and total_generated > 0
        )

        if success:
            project.update_status(ProjectStatus.VIDEO_DONE)
            project.set_module_state("video_synth", {
                "total_generated": total_generated,
                "failed_shots": all_failed,
                "video_paths": all_video_paths,
                "episode_results": episode_results,
            })

        error = None
        if not success:
            if all_results and all(r.success for r in all_results) and not has_clips:
                error = "视频合成未生成任何片段"
            else:
                error = self._first_stage_error(all_results, "视频合成失败")

        return {
            "success": success,
            "error": error,
            "total_generated": total_generated,
            "failed_count": len(all_failed),
            "video_paths": all_video_paths,
        }

    async def _run_audio_editing(self, project: Project) -> dict:
        """执行配音剪辑"""
        project.update_status(ProjectStatus.AUDIO_EDITING, "audio_editing")

        storyboard_state = project.module_states.get("storyboard", {})
        video_state = project.module_states.get("video_synth", {})

        storyboard_paths = storyboard_state.get("storyboard_paths", [])
        if not storyboard_paths:
            return {"success": False, "error": "没有找到分镜文件"}

        had_upstream_video = bool(
            video_state.get("episode_results") or video_state.get("video_paths")
        )

        module = self.modules[PipelineStage.AUDIO_EDITING]

        all_results = []
        all_failed = []
        final_video_paths = []
        total_duration = 0.0

        for sb_path in storyboard_paths:
            # Do not pass a filtered unkeyed video_paths list — AudioEditingModule
            # pairs clips via shot.video_path persisted on the storyboard.
            input_data = AudioEditingInput(
                project_id=project.id,
                storyboard_path=sb_path,
                video_paths=None,
                mock_mode=self.config.mock_mode
            )

            output = await module.run(
                input_data,
                min_quality_score=self.config.min_quality_score,
                max_retries=self.config.max_retries,
                auto_retry=self.config.auto_retry
            )

            all_results.append(output)
            if output.success:
                all_failed.extend(output.failed_shots)
                total_duration += output.total_duration or 0.0
                if output.final_video_path:
                    final_video_paths.append(output.final_video_path)

        module_ok = bool(all_results) and all(r.success for r in all_results)
        # When video clips were supplied upstream, require a final deliverable.
        success = module_ok and (
            not had_upstream_video
            or (
                len(final_video_paths) == len(all_results)
                and all(getattr(r, "final_video_path", None) for r in all_results)
            )
        )

        if success:
            project.set_module_state("audio_editing", {
                "failed_shots": all_failed,
                "final_video_paths": final_video_paths,
                "total_duration": total_duration,
            })

        error = None
        if not success:
            if module_ok and had_upstream_video and not final_video_paths:
                error = "配音剪辑未产出最终视频"
            else:
                error = self._first_stage_error(all_results, "配音剪辑失败")

        return {
            "success": success,
            "error": error,
            "total_duration": total_duration,
            "failed_count": len(all_failed),
            "final_video_paths": final_video_paths,
        }

    def _report_progress(self, progress: float, message: str):
        """报告进度"""
        self.logger.info(f"进度: {progress:.1f}% - {message}")
        if self.on_progress:
            self.on_progress(progress, message)

    # ==================== 单模块运行接口 ====================

    async def run_single_module(
        self,
        project: Project,
        stage: PipelineStage,
        **kwargs
    ) -> dict:
        """
        运行单个模块

        Args:
            project: 项目
            stage: 要运行的阶段
            **kwargs: 额外参数

        Returns:
            模块运行结果
        """
        self.logger.info(f"单独运行模块: {stage.value}")
        result = await self._execute_stage(project, stage)
        # Persist handoff state (e.g. video_synth.episode_results) for later
        # standalone stages such as audio editing.
        if result.get("success"):
            await self.save_project(project)
        return result

    async def evaluate_module_output(
        self,
        project: Project,
        stage: PipelineStage
    ) -> dict:
        """
        评估模块输出质量

        Args:
            project: 项目
            stage: 阶段

        Returns:
            质量评估结果
        """
        module = self.modules.get(stage)
        if not module:
            return {"error": f"Unknown stage: {stage}"}

        # 加载模块输出
        # 这里需要根据具体模块实现...
        return {"message": "质量评估功能待完善"}


# 便捷函数
async def run_pipeline(
    name: str,
    ip_content: str = None,
    ip_content_path: str = None,
    config: PipelineConfig = None,
    **kwargs
) -> PipelineResult:
    """
    便捷函数：创建项目并运行流水线

    Args:
        name: 项目名称
        ip_content: IP原文
        ip_content_path: IP文件路径
        config: 流水线配置

    Returns:
        流水线结果
    """
    controller = PipelineController(config=config)

    # 创建项目
    project = await controller.create_project(
        name=name,
        ip_content=ip_content,
        ip_content_path=ip_content_path,
        **kwargs
    )

    # 运行流水线
    return await controller.run_full_pipeline(project)
