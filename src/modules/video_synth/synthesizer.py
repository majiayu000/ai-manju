"""
视频合成模块 - 将关键帧图像转换为视频
"""
import asyncio
from pathlib import Path
from typing import Optional
import httpx
from pydantic import Field

from src.modules.base import BaseModule, ModuleInput, ModuleOutput, QualityMetrics
from src.models.shot import Shot, EpisodeStoryboard
from src.modules.video_synth.providers.kling import get_kling_video_provider
from src.utils.file_handler import FileHandler
from config import settings


class VideoSynthInput(ModuleInput):
    """视频合成输入"""
    storyboard: Optional[EpisodeStoryboard] = Field(default=None, description="分镜对象")
    storyboard_path: Optional[str] = Field(default=None, description="分镜文件路径")
    images_dir: Optional[str] = Field(default=None, description="图像目录")
    episode_id: Optional[int] = Field(default=None, description="集数")
    shot_ids: Optional[list[int]] = Field(default=None, description="指定镜头ID")
    duration_per_shot: float = Field(default=5.0, description="每个镜头视频时长")
    mode: str = Field(default="std", description="生成模式 std/pro")
    mock_mode: bool = Field(default=False, description="模拟模式")


class VideoSynthOutput(ModuleOutput):
    """视频合成输出"""
    generated_videos: list[dict] = Field(default_factory=list, description="生成的视频信息")
    video_paths: list[str] = Field(default_factory=list, description="视频保存路径")
    total_generated: int = Field(default=0, description="生成总数")
    failed_shots: list[int] = Field(default_factory=list, description="失败的镜头ID")
    merged_video_path: Optional[str] = Field(default=None, description="合并后的视频路径")


class VideoSynthModule(BaseModule[VideoSynthInput, VideoSynthOutput]):
    """
    视频合成模块

    将关键帧图像通过可灵AI转换为视频片段，并拼接成完整视频
    """

    name = "video_synthesizer"
    version = "1.0.0"
    description = "将关键帧图像转换为视频"

    def __init__(self):
        super().__init__()
        self.file_handler = FileHandler()

    async def validate_input(self, input_data: VideoSynthInput) -> tuple[bool, Optional[str]]:
        """验证输入"""
        if not input_data.storyboard and not input_data.storyboard_path:
            return False, "必须提供storyboard或storyboard_path"

        if input_data.storyboard_path:
            path = Path(input_data.storyboard_path)
            if not path.exists():
                return False, f"分镜文件不存在: {input_data.storyboard_path}"

        return True, None

    async def process(self, input_data: VideoSynthInput) -> VideoSynthOutput:
        """执行视频合成"""
        self.logger.info(f"开始视频合成: project={input_data.project_id}")

        try:
            # 获取分镜数据
            storyboard = input_data.storyboard
            if not storyboard and input_data.storyboard_path:
                sb_data = await self.file_handler.read_json(input_data.storyboard_path)
                storyboard = EpisodeStoryboard(**sb_data)

            # 获取视频提供商
            provider = get_kling_video_provider(mock=input_data.mock_mode)

            # 收集要处理的镜头
            all_shots = storyboard.get_all_shots()
            if input_data.shot_ids:
                shots_to_process = [s for s in all_shots if s.shot_id in input_data.shot_ids]
            else:
                shots_to_process = all_shots

            # 只处理有图像的镜头
            shots_with_images = [s for s in shots_to_process if s.image_path and Path(s.image_path).exists()]

            if not shots_with_images:
                return VideoSynthOutput(
                    success=False,
                    error="没有找到可用的图像文件"
                )

            self.logger.info(f"需要生成 {len(shots_with_images)} 个视频片段")

            # 生成视频
            generated_videos = []
            video_paths = []
            failed_shots = []

            # 串行处理（视频生成较慢，避免API限制）
            for shot in shots_with_images:
                try:
                    # Prefer per-shot storyboard duration over the input default,
                    # then map to Kling-supported 5s/10s before the provider call.
                    shot_duration = shot.duration if shot.duration else input_data.duration_per_shot
                    provider_duration = self._normalize_kling_duration(shot_duration)
                    result = await self._generate_shot_video(
                        shot=shot,
                        provider=provider,
                        project_id=input_data.project_id,
                        duration=provider_duration,
                        mode=input_data.mode
                    )
                    generated_videos.append(result["info"])
                    video_paths.append(result["path"])
                    self.logger.info(f"镜头 {shot.shot_id} 视频生成成功")
                except Exception as e:
                    self.logger.error(f"镜头 {shot.shot_id} 视频生成失败: {e}")
                    failed_shots.append(shot.shot_id)

            # 合并视频（如果有多个）
            merged_path = None
            if len(video_paths) > 1:
                try:
                    merged_path = await self._merge_videos(
                        input_data.project_id,
                        storyboard.episode_id,
                        video_paths
                    )
                except Exception as e:
                    self.logger.error(f"视频合并失败: {e}")

            self.logger.info(f"视频合成完成: 成功 {len(generated_videos)}, 失败 {len(failed_shots)}")

            # Persist video_path onto storyboard for downstream audio editing
            if input_data.storyboard_path and storyboard:
                await self.file_handler.write_json(
                    input_data.storyboard_path,
                    storyboard.model_dump(mode="json")
                )

            if not video_paths:
                return VideoSynthOutput(
                    success=False,
                    error="视频合成未生成任何片段",
                    failed_shots=failed_shots,
                    total_generated=0,
                )

            return VideoSynthOutput(
                success=True,
                data={
                    "total_generated": len(generated_videos),
                    "failed_count": len(failed_shots)
                },
                generated_videos=generated_videos,
                video_paths=video_paths,
                total_generated=len(generated_videos),
                failed_shots=failed_shots,
                merged_video_path=merged_path
            )

        except Exception as e:
            self.logger.exception(f"视频合成失败: {e}")
            return VideoSynthOutput(
                success=False,
                error=str(e)
            )

    @staticmethod
    def _normalize_kling_duration(duration: float) -> int:
        """Map arbitrary storyboard durations to Kling-supported 5 or 10 seconds."""
        value = float(duration) if duration else 5.0
        return min((5, 10), key=lambda supported: abs(supported - value))

    async def _generate_shot_video(
        self,
        shot: Shot,
        provider,
        project_id: str,
        duration: float,
        mode: str
    ) -> dict:
        """生成单个镜头的视频"""
        # 读取图像并转为Base64或使用URL
        image_path = Path(shot.image_path)

        # 如果是本地文件，需要转为Base64
        if image_path.exists():
            import base64
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            image_url = f"data:image/png;base64,{image_data}"
        else:
            image_url = shot.image_path  # 假设是URL

        # 构建运动提示词
        motion_prompt = self._build_motion_prompt(shot)

        self.logger.debug(f"生成镜头 {shot.shot_id} 视频: {motion_prompt[:50]}...")

        # 调用API生成
        result = await provider.image_to_video_and_wait(
            image_url=image_url,
            prompt=motion_prompt,
            duration=duration,
            mode=mode
        )

        video_url = result.get("video_url")

        # 下载并保存视频
        self.file_handler.ensure_project_structure(project_id)
        save_path = self.file_handler.get_video_path(
            project_id,
            shot.episode_id,
            shot.scene_id,
            shot.shot_id
        )

        await self._download_video(video_url, save_path)

        # 更新镜头信息
        shot.video_path = str(save_path)

        return {
            "info": {
                "shot_id": shot.shot_id,
                "episode_id": shot.episode_id,
                "scene_id": shot.scene_id,
                "video_url": video_url,
                "duration": result.get("duration", duration)
            },
            "path": str(save_path)
        }

    def _build_motion_prompt(self, shot: Shot) -> str:
        """构建运动描述提示词"""
        parts = []

        # 镜头运动
        camera_movements = {
            "static": "camera stays still",
            "pan": "camera pans horizontally",
            "tilt": "camera tilts vertically",
            "zoom-in": "camera zooms in slowly",
            "zoom-out": "camera zooms out slowly",
            "tracking": "camera tracks the subject",
            "dolly": "camera moves forward"
        }
        if shot.camera_movement:
            movement = camera_movements.get(shot.camera_movement.value, "")
            if movement:
                parts.append(movement)

        # 角色动作
        if shot.character_actions:
            parts.append(shot.character_actions)

        # 场景描述中的动态元素
        dynamic_keywords = ["走", "跑", "跳", "飞", "转", "挥", "打", "踢"]
        if shot.description:
            for kw in dynamic_keywords:
                if kw in shot.description:
                    parts.append("subtle movement")
                    break

        # 默认添加轻微运动
        if not parts:
            parts.append("subtle breathing motion, slight movement")

        return ", ".join(parts)

    async def _download_video(self, url: str, save_path: Path):
        """下载视频到本地"""
        if url.startswith("https://placeholder"):
            # 模拟模式，创建空文件
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(b"mock video data")
            return

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(response.content)

        self.logger.debug(f"视频已保存: {save_path}")

    async def _merge_videos(
        self,
        project_id: str,
        episode_id: int,
        video_paths: list[str]
    ) -> str:
        """
        合并视频片段

        使用FFmpeg进行视频拼接
        """
        import subprocess

        output_path = self.file_handler.get_video_path(
            project_id,
            episode_id,
            ext="mp4"
        )

        # 创建文件列表
        list_file = output_path.parent / f"ep{episode_id:02d}_list.txt"
        with open(list_file, "w") as f:
            for vp in video_paths:
                f.write(f"file '{vp}'\n")

        # FFmpeg合并命令
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output_path)
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            self.logger.info(f"视频合并完成: {output_path}")
            return str(output_path)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg合并失败: {e.stderr.decode()}")
            raise
        finally:
            # 清理临时文件
            if list_file.exists():
                list_file.unlink()

    async def evaluate_quality(self, output: VideoSynthOutput) -> QualityMetrics:
        """评估视频合成质量"""
        if not output.success:
            return QualityMetrics(
                score=0,
                details={},
                suggestions=["视频合成失败"],
                passed=False
            )

        details = {}

        # 1. 生成成功率
        total = output.total_generated + len(output.failed_shots)
        if total > 0:
            success_rate = (output.total_generated / total) * 100
        else:
            success_rate = 0
        details["success_rate"] = success_rate

        # 2. 视频完整性
        existing = sum(1 for p in output.video_paths if Path(p).exists())
        if output.video_paths:
            integrity = (existing / len(output.video_paths)) * 100
        else:
            integrity = 0
        details["integrity"] = integrity

        # 3. 合并视频是否存在
        if output.merged_video_path and Path(output.merged_video_path).exists():
            details["merged"] = 100
        else:
            details["merged"] = 50 if output.video_paths else 0

        return QualityMetrics.from_details(details)


# 便捷函数
async def synthesize_videos(
    project_id: str,
    storyboard: EpisodeStoryboard = None,
    storyboard_path: str = None,
    mock_mode: bool = False,
    **kwargs
) -> VideoSynthOutput:
    """
    便捷函数：合成视频

    Args:
        project_id: 项目ID
        storyboard: 分镜对象
        storyboard_path: 分镜文件路径
        mock_mode: 模拟模式

    Returns:
        视频合成结果
    """
    module = VideoSynthModule()
    input_data = VideoSynthInput(
        project_id=project_id,
        storyboard=storyboard,
        storyboard_path=storyboard_path,
        mock_mode=mock_mode,
        **kwargs
    )
    return await module.run(input_data)
