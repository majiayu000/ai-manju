"""
分镜生成模块 - 将剧本转换为分镜脚本
"""
from pathlib import Path
from typing import Optional
from pydantic import Field

from src.modules.base import BaseModule, ModuleInput, ModuleOutput, QualityMetrics
from src.models.script import Script, Scene
from src.models.shot import Shot, Storyboard, EpisodeStoryboard, ShotType, CameraMovement
from src.ai.llm import get_llm_client
from src.utils.file_handler import FileHandler
from config import settings


class StoryboardInput(ModuleInput):
    """分镜生成输入"""
    script: Optional[Script] = Field(default=None, description="剧本对象")
    script_path: Optional[str] = Field(default=None, description="剧本文件路径")
    episode_ids: Optional[list[int]] = Field(default=None, description="要处理的集数，为空则处理全部")
    target_duration_per_episode: int = Field(default=90, description="每集目标时长(秒)")


class StoryboardOutput(ModuleOutput):
    """分镜生成输出"""
    storyboards: list[EpisodeStoryboard] = Field(default_factory=list, description="分镜列表")
    storyboard_paths: list[str] = Field(default_factory=list, description="保存路径")
    total_shots: int = Field(default=0, description="总镜头数")
    total_duration: float = Field(default=0.0, description="总时长")


class StoryboardModule(BaseModule[StoryboardInput, StoryboardOutput]):
    """
    分镜生成模块

    将剧本场景转换为详细的分镜脚本
    """

    name = "storyboard_generator"
    version = "1.0.0"
    description = "将剧本场景转换为分镜脚本"

    def __init__(self, llm_provider: Optional[str] = None):
        super().__init__()
        self.llm = get_llm_client(provider=llm_provider)
        self.file_handler = FileHandler()
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """加载Prompt模板"""
        template_path = settings.base_dir / "config" / "prompts" / "storyboard.txt"
        if template_path.exists():
            return self.file_handler.read_text_sync(template_path)
        return self._get_default_prompt_template()

    def _get_default_prompt_template(self) -> str:
        """默认Prompt模板"""
        return """请将以下场景转换为分镜脚本，每个镜头要有明确的画面描述。

场景信息：
- 地点：{location}
- 时间：{time}
- 出场角色：{characters}

场景描述：
{description}

对话内容：
{dialogues}

请输出JSON格式的分镜脚本，包含镜头类型、时长、画面描述、角色动作等。"""

    async def validate_input(self, input_data: StoryboardInput) -> tuple[bool, Optional[str]]:
        """验证输入"""
        if not input_data.script and not input_data.script_path:
            return False, "必须提供script或script_path"

        if input_data.script_path:
            path = Path(input_data.script_path)
            if not path.exists():
                return False, f"剧本文件不存在: {input_data.script_path}"

        return True, None

    async def process(self, input_data: StoryboardInput) -> StoryboardOutput:
        """执行分镜生成"""
        self.logger.info(f"开始分镜生成: project={input_data.project_id}")

        try:
            # 获取剧本
            script = input_data.script
            if not script and input_data.script_path:
                script_data = await self.file_handler.read_json(input_data.script_path)
                script = Script(**script_data)

            # 确定要处理的集数
            episode_ids = input_data.episode_ids
            if not episode_ids:
                episode_ids = [ep.episode_id for ep in script.episodes]

            # 处理每一集
            storyboards = []
            storyboard_paths = []
            total_shots = 0
            total_duration = 0.0

            for ep_id in episode_ids:
                episode = script.get_episode(ep_id)
                if not episode:
                    self.logger.warning(f"找不到第{ep_id}集，跳过")
                    continue

                self.logger.info(f"处理第{ep_id}集: {episode.title}")
                ep_storyboard = await self._generate_episode_storyboard(
                    input_data.project_id,
                    episode,
                    input_data.target_duration_per_episode
                )

                storyboards.append(ep_storyboard)
                total_shots += ep_storyboard.total_shots
                total_duration += ep_storyboard.total_duration

                # 保存
                save_path = await self._save_storyboard(input_data.project_id, ep_storyboard)
                storyboard_paths.append(str(save_path))

            self.logger.info(f"分镜生成完成: {len(storyboards)}集, {total_shots}个镜头")

            return StoryboardOutput(
                success=True,
                data={
                    "episodes_processed": len(storyboards),
                    "total_shots": total_shots,
                    "total_duration": total_duration
                },
                storyboards=storyboards,
                storyboard_paths=storyboard_paths,
                total_shots=total_shots,
                total_duration=total_duration
            )

        except Exception as e:
            self.logger.exception(f"分镜生成失败: {e}")
            return StoryboardOutput(
                success=False,
                error=str(e)
            )

    async def _generate_episode_storyboard(
        self,
        project_id: str,
        episode,
        target_duration: int
    ) -> EpisodeStoryboard:
        """生成单集分镜"""
        scene_storyboards = []

        # 计算每个场景的目标时长
        scene_count = len(episode.scenes)
        duration_per_scene = target_duration / max(1, scene_count)

        for scene in episode.scenes:
            self.logger.debug(f"处理场景 {scene.scene_id}")
            storyboard = await self._generate_scene_storyboard(
                project_id,
                episode.episode_id,
                scene,
                duration_per_scene
            )
            scene_storyboards.append(storyboard)

        ep_storyboard = EpisodeStoryboard(
            project_id=project_id,
            episode_id=episode.episode_id,
            title=episode.title,
            scenes=scene_storyboards
        )
        ep_storyboard.calculate_totals()

        return ep_storyboard

    async def _generate_scene_storyboard(
        self,
        project_id: str,
        episode_id: int,
        scene: Scene,
        target_duration: float
    ) -> Storyboard:
        """生成单场景分镜"""
        # 构建对话文本
        dialogues_text = "\n".join([
            f"{d.character}: {d.text} ({d.emotion})"
            for d in scene.dialogues
        ])

        prompt = self.prompt_template.format(
            location=scene.location,
            time=scene.time,
            characters=", ".join(scene.characters),
            description=scene.description,
            dialogues=dialogues_text or "无对话"
        )

        # 调用LLM
        response = await self.llm.chat_json(
            prompt=prompt,
            system="你是专业分镜师，擅长将剧本场景转换为详细的分镜脚本。请以JSON格式输出。",
            temperature=0.7
        )

        # 解析镜头
        shots = self._parse_shots_response(response, episode_id, scene.scene_id)

        # 调整时长
        shots = self._adjust_shot_durations(shots, target_duration)

        storyboard = Storyboard(
            project_id=project_id,
            episode_id=episode_id,
            scene_id=scene.scene_id,
            location=scene.location,
            time=scene.time,
            shots=shots
        )
        storyboard.calculate_duration()

        return storyboard

    def _parse_shots_response(
        self,
        response: dict,
        episode_id: int,
        scene_id: int
    ) -> list[Shot]:
        """解析LLM响应为Shot列表"""
        shots = []
        shots_data = response.get("shots", [])

        for i, shot_data in enumerate(shots_data):
            # 解析镜头类型
            shot_type_str = shot_data.get("type", "medium").lower().replace("_", "-")
            try:
                shot_type = ShotType(shot_type_str)
            except ValueError:
                shot_type = ShotType.MEDIUM

            # 解析镜头运动
            movement_str = shot_data.get("camera_movement", "static").lower().replace("_", "-")
            try:
                camera_movement = CameraMovement(movement_str)
            except ValueError:
                camera_movement = CameraMovement.STATIC

            shot = Shot(
                shot_id=i + 1,
                episode_id=episode_id,
                scene_id=scene_id,
                type=shot_type,
                duration=float(shot_data.get("duration", 3.0)),
                camera_movement=camera_movement,
                description=shot_data.get("description", ""),
                characters=shot_data.get("characters", []),
                character_positions=shot_data.get("character_positions", ""),
                character_actions=shot_data.get("character_actions", ""),
                character_expressions=shot_data.get("character_expressions", ""),
                dialogue=shot_data.get("dialogue"),
                dialogue_character=shot_data.get("dialogue_character"),
                emotion_tone=shot_data.get("emotion_tone", "neutral"),
                lighting=shot_data.get("lighting", "natural"),
                color_tone=shot_data.get("color_tone", "neutral"),
                prompt_hint=shot_data.get("prompt_hint", ""),
                negative_prompt_hint=shot_data.get("negative_prompt_hint", ""),
                sfx=shot_data.get("sfx", []),
                transition_to_next=shot_data.get("transition_to_next", "cut")
            )
            shots.append(shot)

        return shots

    def _adjust_shot_durations(self, shots: list[Shot], target_duration: float) -> list[Shot]:
        """调整镜头时长以匹配目标时长"""
        if not shots:
            return shots

        current_total = sum(shot.duration for shot in shots)
        if current_total <= 0:
            # 平均分配
            per_shot = target_duration / len(shots)
            for shot in shots:
                shot.duration = per_shot
        else:
            # 按比例调整
            ratio = target_duration / current_total
            for shot in shots:
                shot.duration = round(shot.duration * ratio, 1)

        return shots

    async def _save_storyboard(
        self,
        project_id: str,
        ep_storyboard: EpisodeStoryboard
    ) -> Path:
        """保存分镜到文件"""
        self.file_handler.ensure_project_structure(project_id)
        save_path = self.file_handler.get_storyboard_path(
            project_id,
            ep_storyboard.episode_id
        )
        await self.file_handler.write_json(save_path, ep_storyboard.model_dump())
        return save_path

    async def evaluate_quality(self, output: StoryboardOutput) -> QualityMetrics:
        """评估分镜质量"""
        if not output.success or not output.storyboards:
            return QualityMetrics(
                score=0,
                details={},
                suggestions=["分镜生成失败"],
                passed=False
            )

        details = {}

        # 1. 镜头多样性
        diversity = self._evaluate_shot_diversity(output.storyboards)
        details["shot_diversity"] = diversity

        # 2. 时长合理性
        duration = self._evaluate_duration(output.storyboards)
        details["duration"] = duration

        # 3. 描述完整度
        description = self._evaluate_descriptions(output.storyboards)
        details["description"] = description

        # 4. Prompt质量
        prompts = self._evaluate_prompts(output.storyboards)
        details["prompts"] = prompts

        return QualityMetrics.from_details(details)

    def _evaluate_shot_diversity(self, storyboards: list[EpisodeStoryboard]) -> float:
        """评估镜头类型多样性"""
        all_types = []
        for ep in storyboards:
            for scene in ep.scenes:
                for shot in scene.shots:
                    all_types.append(shot.type)

        if not all_types:
            return 0

        unique_types = len(set(all_types))
        # 至少使用3种镜头类型算及格
        return min(100, (unique_types / 3) * 100)

    def _evaluate_duration(self, storyboards: list[EpisodeStoryboard]) -> float:
        """评估时长分配"""
        score = 100.0
        for ep in storyboards:
            for scene in ep.scenes:
                for shot in scene.shots:
                    # 镜头太短或太长扣分
                    if shot.duration < 1:
                        score -= 2
                    elif shot.duration > 10:
                        score -= 1
        return max(0, score)

    def _evaluate_descriptions(self, storyboards: list[EpisodeStoryboard]) -> float:
        """评估描述完整度"""
        total = 0
        good = 0
        for ep in storyboards:
            for scene in ep.scenes:
                for shot in scene.shots:
                    total += 1
                    if shot.description and len(shot.description) > 20:
                        good += 1
        return (good / max(1, total)) * 100

    def _evaluate_prompts(self, storyboards: list[EpisodeStoryboard]) -> float:
        """评估Prompt质量"""
        total = 0
        good = 0
        for ep in storyboards:
            for scene in ep.scenes:
                for shot in scene.shots:
                    total += 1
                    if shot.prompt_hint and len(shot.prompt_hint) > 30:
                        good += 1
        return (good / max(1, total)) * 100


# 便捷函数
async def generate_storyboard(
    project_id: str,
    script: Script = None,
    script_path: str = None,
    episode_ids: list[int] = None,
    **kwargs
) -> StoryboardOutput:
    """
    便捷函数：生成分镜

    Args:
        project_id: 项目ID
        script: 剧本对象
        script_path: 剧本文件路径
        episode_ids: 要处理的集数

    Returns:
        分镜结果
    """
    module = StoryboardModule()
    input_data = StoryboardInput(
        project_id=project_id,
        script=script,
        script_path=script_path,
        episode_ids=episode_ids,
        **kwargs
    )
    return await module.run(input_data)
