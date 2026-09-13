"""
配音剪辑模块 - 语音合成与最终视频合成
"""
import asyncio
import subprocess
from pathlib import Path
from typing import Optional
from pydantic import Field

from src.modules.base import BaseModule, ModuleInput, ModuleOutput, QualityMetrics
from src.models.shot import Shot, EpisodeStoryboard
from src.modules.audio_editing.providers.tts import get_tts_provider
from src.utils.file_handler import FileHandler
from config import settings


class AudioEditingInput(ModuleInput):
    """配音剪辑输入"""
    storyboard: Optional[EpisodeStoryboard] = Field(default=None, description="分镜对象")
    storyboard_path: Optional[str] = Field(default=None, description="分镜文件路径")
    video_paths: Optional[list[str]] = Field(default=None, description="视频片段路径列表")
    episode_id: Optional[int] = Field(default=None, description="集数")
    tts_provider: str = Field(default="edge", description="TTS提供商 edge/fish")
    voice_mapping: Optional[dict[str, str]] = Field(default=None, description="角色语音映射")
    add_bgm: bool = Field(default=True, description="是否添加背景音乐")
    bgm_path: Optional[str] = Field(default=None, description="背景音乐路径")
    bgm_volume: float = Field(default=0.3, description="背景音乐音量 0-1")
    mock_mode: bool = Field(default=False, description="模拟模式")


class AudioEditingOutput(ModuleOutput):
    """配音剪辑输出"""
    audio_files: list[dict] = Field(default_factory=list, description="生成的音频文件")
    final_video_path: Optional[str] = Field(default=None, description="最终合成视频路径")
    total_duration: float = Field(default=0.0, description="总时长(秒)")
    failed_shots: list[int] = Field(default_factory=list, description="失败的镜头ID")


class AudioEditingModule(BaseModule[AudioEditingInput, AudioEditingOutput]):
    """
    配音剪辑模块

    功能:
    1. 为每个镜头的台词生成配音
    2. 将配音与视频片段合成
    3. 添加背景音乐
    4. 输出最终视频
    """

    name = "audio_editor"
    version = "1.0.0"
    description = "语音合成与视频剪辑"

    def __init__(self):
        super().__init__()
        self.file_handler = FileHandler()

    async def validate_input(self, input_data: AudioEditingInput) -> tuple[bool, Optional[str]]:
        """验证输入"""
        if not input_data.storyboard and not input_data.storyboard_path:
            return False, "必须提供storyboard或storyboard_path"

        if input_data.storyboard_path:
            path = Path(input_data.storyboard_path)
            if not path.exists():
                return False, f"分镜文件不存在: {input_data.storyboard_path}"

        return True, None

    async def process(self, input_data: AudioEditingInput) -> AudioEditingOutput:
        """执行配音剪辑"""
        self.logger.info(f"开始配音剪辑: project={input_data.project_id}")

        try:
            # 获取分镜数据
            storyboard = input_data.storyboard
            if not storyboard and input_data.storyboard_path:
                sb_data = await self.file_handler.read_json(input_data.storyboard_path)
                storyboard = EpisodeStoryboard(**sb_data)

            # 获取TTS提供商
            tts_provider = get_tts_provider(
                provider=input_data.tts_provider,
                mock=input_data.mock_mode
            )

            # 收集需要配音的镜头
            all_shots = storyboard.get_all_shots()
            shots_with_dialogue = [s for s in all_shots if s.dialogue]

            self.logger.info(f"需要配音的镜头: {len(shots_with_dialogue)}")

            # 生成配音
            audio_files = []
            failed_shots = []
            total_duration = 0.0

            for shot in shots_with_dialogue:
                try:
                    result = await self._generate_shot_audio(
                        shot=shot,
                        tts_provider=tts_provider,
                        project_id=input_data.project_id,
                        voice_mapping=input_data.voice_mapping
                    )
                    audio_files.append(result)
                    total_duration += result.get("duration", 0)
                    self.logger.info(f"镜头 {shot.shot_id} 配音完成")
                except Exception as e:
                    self.logger.error(f"镜头 {shot.shot_id} 配音失败: {e}")
                    failed_shots.append(shot.shot_id)

            # 合成最终视频 — prefer shot.video_path (shot-keyed) over an unkeyed list
            final_video_path = None
            shot_video_segments = [
                (s, s.video_path)
                for s in all_shots
                if s.video_path and Path(s.video_path).exists()
            ]
            compose_error = None
            if shot_video_segments or input_data.video_paths:
                try:
                    final_video_path = await self._compose_final_video(
                        project_id=input_data.project_id,
                        episode_id=storyboard.episode_id,
                        video_paths=input_data.video_paths or [],
                        audio_files=audio_files,
                        shots=all_shots,
                        add_bgm=input_data.add_bgm,
                        bgm_path=input_data.bgm_path,
                        bgm_volume=input_data.bgm_volume,
                        shot_video_segments=shot_video_segments or None,
                    )
                except Exception as e:
                    compose_error = str(e)
                    self.logger.error(f"视频合成失败: {e}")

            # When clips were available, a missing final path is a hard failure.
            expected_composition = bool(shot_video_segments or input_data.video_paths)
            if expected_composition and not final_video_path:
                return AudioEditingOutput(
                    success=False,
                    error=compose_error or "配音剪辑未产出最终视频",
                    audio_files=audio_files,
                    total_duration=total_duration,
                    failed_shots=failed_shots,
                )

            self.logger.info(f"配音剪辑完成: 音频 {len(audio_files)}, 失败 {len(failed_shots)}")

            return AudioEditingOutput(
                success=True,
                data={
                    "audio_count": len(audio_files),
                    "failed_count": len(failed_shots),
                    "total_duration": total_duration
                },
                audio_files=audio_files,
                final_video_path=final_video_path,
                total_duration=total_duration,
                failed_shots=failed_shots
            )

        except Exception as e:
            self.logger.exception(f"配音剪辑失败: {e}")
            return AudioEditingOutput(
                success=False,
                error=str(e)
            )

    async def _generate_shot_audio(
        self,
        shot: Shot,
        tts_provider,
        project_id: str,
        voice_mapping: Optional[dict] = None
    ) -> dict:
        """为单个镜头生成配音"""
        # 确定使用的语音
        voice = "zh-CN-XiaoxiaoNeural"  # 默认女声

        if voice_mapping and shot.characters:
            # 尝试匹配角色语音
            for char in shot.characters:
                if char in voice_mapping:
                    voice = voice_mapping[char]
                    break

        # 生成音频路径
        self.file_handler.ensure_project_structure(project_id)
        audio_path = self.file_handler.get_audio_path(
            project_id,
            shot.episode_id,
            shot.scene_id,
            shot.shot_id
        )

        # 合成语音
        result = await tts_provider.synthesize(
            text=shot.dialogue,
            output_path=audio_path,
            voice=voice
        )

        # 更新镜头信息
        shot.audio_path = str(audio_path)

        return {
            "shot_id": shot.shot_id,
            "episode_id": shot.episode_id,
            "scene_id": shot.scene_id,
            "audio_path": str(audio_path),
            "duration": result.get("duration", 0),
            "dialogue": shot.dialogue[:50] + "..." if len(shot.dialogue) > 50 else shot.dialogue
        }

    async def _compose_final_video(
        self,
        project_id: str,
        episode_id: int,
        video_paths: list[str],
        audio_files: list[dict],
        shots: list[Shot],
        add_bgm: bool,
        bgm_path: Optional[str],
        bgm_volume: float,
        shot_video_segments: Optional[list[tuple]] = None,
    ) -> str:
        """合成最终视频"""
        # 创建音频到镜头的映射
        audio_map = {af["shot_id"]: af for af in audio_files}

        # 输出路径
        output_path = self.file_handler.get_video_path(
            project_id,
            episode_id,
            ext="mp4",
            suffix="_final"
        )

        # 临时目录
        temp_dir = output_path.parent / "temp"
        temp_dir.mkdir(exist_ok=True)

        try:
            # 步骤1: 为每个视频片段添加对应配音
            processed_videos = []

            # Prefer shot-keyed segments from persisted storyboard video_path fields
            # so missing earlier shots do not shift later clips onto the wrong dialogue.
            if shot_video_segments:
                iterable = [
                    (shot, video_path)
                    for shot, video_path in shot_video_segments
                    if video_path and Path(video_path).exists()
                ]
            else:
                iterable = []
                for i, video_path in enumerate(video_paths):
                    if not Path(video_path).exists():
                        continue
                    shot = shots[i] if i < len(shots) else None
                    iterable.append((shot, video_path))

            for i, (shot, video_path) in enumerate(iterable):
                audio_info = audio_map.get(shot.shot_id) if shot else None

                if audio_info and Path(audio_info["audio_path"]).exists():
                    # 合并视频和音频
                    temp_output = temp_dir / f"segment_{i:03d}.mp4"
                    await self._merge_video_audio(
                        video_path,
                        audio_info["audio_path"],
                        str(temp_output)
                    )
                    processed_videos.append(str(temp_output))
                else:
                    processed_videos.append(video_path)

            # 步骤2: 拼接所有视频片段
            if len(processed_videos) > 1:
                concat_output = temp_dir / "concat.mp4"
                await self._concat_videos(processed_videos, str(concat_output))
            elif processed_videos:
                concat_output = Path(processed_videos[0])
            else:
                raise Exception("没有可用的视频片段")

            # 步骤3: 添加背景音乐（如果需要）
            if add_bgm and bgm_path and Path(bgm_path).exists():
                await self._add_background_music(
                    str(concat_output),
                    bgm_path,
                    str(output_path),
                    bgm_volume
                )
            else:
                # 直接复制
                import shutil
                shutil.copy(str(concat_output), str(output_path))

            self.logger.info(f"最终视频合成完成: {output_path}")
            return str(output_path)

        finally:
            # 清理临时文件
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    async def _merge_video_audio(
        self,
        video_path: str,
        audio_path: str,
        output_path: str
    ):
        """合并视频和音频"""
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"FFmpeg合并失败: {stderr.decode()}")

    async def _concat_videos(self, video_paths: list[str], output_path: str):
        """拼接视频"""
        # 创建文件列表
        list_file = Path(output_path).parent / "concat_list.txt"
        with open(list_file, "w") as f:
            for vp in video_paths:
                f.write(f"file '{vp}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        # 清理列表文件
        list_file.unlink(missing_ok=True)

        if process.returncode != 0:
            raise Exception(f"FFmpeg拼接失败: {stderr.decode()}")

    async def _add_background_music(
        self,
        video_path: str,
        bgm_path: str,
        output_path: str,
        volume: float
    ):
        """添加背景音乐"""
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", bgm_path,
            "-filter_complex",
            f"[1:a]volume={volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first[out]",
            "-map", "0:v",
            "-map", "[out]",
            "-c:v", "copy",
            "-c:a", "aac",
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"FFmpeg添加BGM失败: {stderr.decode()}")

    async def evaluate_quality(self, output: AudioEditingOutput) -> QualityMetrics:
        """评估配音剪辑质量"""
        if not output.success:
            return QualityMetrics(
                score=0,
                details={},
                suggestions=["配音剪辑失败"],
                passed=False
            )

        details = {}

        # 1. 音频生成成功率
        total = len(output.audio_files) + len(output.failed_shots)
        if total > 0:
            success_rate = (len(output.audio_files) / total) * 100
        else:
            success_rate = 100
        details["audio_success_rate"] = success_rate

        # 2. 最终视频是否生成
        if output.final_video_path and Path(output.final_video_path).exists():
            details["final_video"] = 100
        else:
            details["final_video"] = 0

        # 3. 音频文件完整性
        existing = sum(1 for af in output.audio_files if Path(af["audio_path"]).exists())
        if output.audio_files:
            integrity = (existing / len(output.audio_files)) * 100
        else:
            integrity = 100
        details["audio_integrity"] = integrity

        return QualityMetrics.from_details(details)


# 便捷函数
async def edit_audio(
    project_id: str,
    storyboard: EpisodeStoryboard = None,
    storyboard_path: str = None,
    video_paths: list[str] = None,
    mock_mode: bool = False,
    **kwargs
) -> AudioEditingOutput:
    """
    便捷函数：配音剪辑

    Args:
        project_id: 项目ID
        storyboard: 分镜对象
        storyboard_path: 分镜文件路径
        video_paths: 视频片段路径列表
        mock_mode: 模拟模式

    Returns:
        配音剪辑结果
    """
    module = AudioEditingModule()
    input_data = AudioEditingInput(
        project_id=project_id,
        storyboard=storyboard,
        storyboard_path=storyboard_path,
        video_paths=video_paths,
        mock_mode=mock_mode,
        **kwargs
    )
    return await module.run(input_data)
