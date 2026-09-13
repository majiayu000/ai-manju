"""
图像生成模块 - 根据分镜生成关键帧图像
"""
import asyncio
from pathlib import Path
from typing import Optional
import httpx
from pydantic import Field

from src.modules.base import BaseModule, ModuleInput, ModuleOutput, QualityMetrics
from src.models.shot import Shot, EpisodeStoryboard
from src.models.character import CharacterDesignSet, Character
from src.modules.image_gen.providers.kling import get_kling_provider
from src.utils.file_handler import FileHandler
from config import settings


class ImageGenInput(ModuleInput):
    """图像生成输入"""
    storyboard: Optional[EpisodeStoryboard] = Field(default=None, description="分镜对象")
    storyboard_path: Optional[str] = Field(default=None, description="分镜文件路径")
    character_designs: Optional[CharacterDesignSet] = Field(default=None, description="角色设计")
    character_designs_path: Optional[str] = Field(default=None, description="角色设计文件路径")
    episode_id: Optional[int] = Field(default=None, description="集数")
    shot_ids: Optional[list[int]] = Field(default=None, description="指定镜头ID，为空则处理全部")
    aspect_ratio: str = Field(default="9:16", description="画面比例")
    style: str = Field(default="anime", description="艺术风格")
    quality: str = Field(default="high", description="图像质量")
    mock_mode: bool = Field(default=False, description="模拟模式（不调用真实API）")


class ImageGenOutput(ModuleOutput):
    """图像生成输出"""
    generated_images: list[dict] = Field(default_factory=list, description="生成的图像信息")
    image_paths: list[str] = Field(default_factory=list, description="图像保存路径")
    total_generated: int = Field(default=0, description="生成总数")
    failed_shots: list[int] = Field(default_factory=list, description="失败的镜头ID")


class ImageGeneratorModule(BaseModule[ImageGenInput, ImageGenOutput]):
    """
    图像生成模块

    根据分镜脚本和角色设计生成关键帧图像
    """

    name = "image_generator"
    version = "1.0.0"
    description = "根据分镜生成关键帧图像"

    def __init__(self):
        super().__init__()
        self.file_handler = FileHandler()

    async def validate_input(self, input_data: ImageGenInput) -> tuple[bool, Optional[str]]:
        """验证输入"""
        if not input_data.storyboard and not input_data.storyboard_path:
            return False, "必须提供storyboard或storyboard_path"

        if input_data.storyboard_path:
            path = Path(input_data.storyboard_path)
            if not path.exists():
                return False, f"分镜文件不存在: {input_data.storyboard_path}"

        return True, None

    async def process(self, input_data: ImageGenInput) -> ImageGenOutput:
        """执行图像生成"""
        self.logger.info(f"开始图像生成: project={input_data.project_id}")

        try:
            # 获取分镜数据
            storyboard = input_data.storyboard
            if not storyboard and input_data.storyboard_path:
                sb_data = await self.file_handler.read_json(input_data.storyboard_path)
                storyboard = EpisodeStoryboard(**sb_data)

            # 获取角色设计
            char_designs = input_data.character_designs
            if not char_designs and input_data.character_designs_path:
                char_data = await self.file_handler.read_json(input_data.character_designs_path)
                char_designs = CharacterDesignSet(**char_data)

            # 获取图像提供商
            provider = get_kling_provider(mock=input_data.mock_mode)

            # 收集要处理的镜头
            all_shots = storyboard.get_all_shots()
            if input_data.shot_ids:
                shots_to_process = [s for s in all_shots if s.shot_id in input_data.shot_ids]
            else:
                shots_to_process = all_shots

            self.logger.info(f"需要生成 {len(shots_to_process)} 张图像")

            # 并发生成（限制并发数）
            generated_images = []
            image_paths = []
            failed_shots = []

            # 分批处理，每批3个
            batch_size = 3
            for i in range(0, len(shots_to_process), batch_size):
                batch = shots_to_process[i:i + batch_size]
                self.logger.info(f"处理批次 {i // batch_size + 1}/{(len(shots_to_process) + batch_size - 1) // batch_size}")

                tasks = [
                    self._generate_shot_image(
                        shot=shot,
                        char_designs=char_designs,
                        provider=provider,
                        project_id=input_data.project_id,
                        aspect_ratio=input_data.aspect_ratio,
                        style=input_data.style,
                        quality=input_data.quality
                    )
                    for shot in batch
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for shot, result in zip(batch, results):
                    if isinstance(result, Exception):
                        self.logger.error(f"镜头 {shot.shot_id} 生成失败: {result}")
                        failed_shots.append(shot.shot_id)
                    else:
                        generated_images.append(result["info"])
                        image_paths.append(result["path"])

            self.logger.info(f"图像生成完成: 成功 {len(generated_images)}, 失败 {len(failed_shots)}")

            # Persist image_path onto storyboard so video synthesis can load it
            if input_data.storyboard_path and storyboard:
                await self.file_handler.write_json(
                    input_data.storyboard_path,
                    storyboard.model_dump(mode="json")
                )

            return ImageGenOutput(
                success=True,
                data={
                    "total_generated": len(generated_images),
                    "failed_count": len(failed_shots)
                },
                generated_images=generated_images,
                image_paths=image_paths,
                total_generated=len(generated_images),
                failed_shots=failed_shots
            )

        except Exception as e:
            self.logger.exception(f"图像生成失败: {e}")
            return ImageGenOutput(
                success=False,
                error=str(e)
            )

    async def _generate_shot_image(
        self,
        shot: Shot,
        char_designs: Optional[CharacterDesignSet],
        provider,
        project_id: str,
        aspect_ratio: str,
        style: str,
        quality: str
    ) -> dict:
        """生成单个镜头的图像"""
        # 构建Prompt
        prompt = self._build_prompt(shot, char_designs)
        negative_prompt = self._build_negative_prompt(shot, char_designs)

        self.logger.debug(f"生成镜头 {shot.shot_id}: {prompt[:100]}...")

        # 调用API生成
        images = await provider.generate_and_wait(
            prompt=prompt,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            style=style,
            quality=quality,
            num_images=1
        )

        if not images:
            raise Exception("No image generated")

        image_info = images[0]
        image_url = image_info.get("url")

        # 下载并保存图像
        self.file_handler.ensure_project_structure(project_id)
        save_path = self.file_handler.get_image_path(
            project_id,
            shot.episode_id,
            shot.scene_id,
            shot.shot_id
        )

        await self._download_image(image_url, save_path)

        # 更新镜头信息
        shot.image_path = str(save_path)

        return {
            "info": {
                "shot_id": shot.shot_id,
                "episode_id": shot.episode_id,
                "scene_id": shot.scene_id,
                "url": image_url,
                "seed": image_info.get("seed"),
                "prompt": prompt[:200]
            },
            "path": str(save_path)
        }

    def _build_prompt(self, shot: Shot, char_designs: Optional[CharacterDesignSet]) -> str:
        """构建完整的生成Prompt"""
        parts = []

        # 基础质量标签
        parts.append("masterpiece, best quality, highly detailed")

        # 场景描述
        if shot.description:
            parts.append(shot.description)

        # 角色信息
        if char_designs and shot.characters:
            for char_name in shot.characters[:2]:  # 最多2个角色
                char = char_designs.get_character(char_name)
                if char:
                    # 使用角色的base_prompt
                    char_prompt = char.prompts.base_prompt
                    if char_prompt:
                        parts.append(char_prompt)

        # 角色动作和表情
        if shot.character_actions:
            parts.append(shot.character_actions)
        if shot.character_expressions:
            parts.append(shot.character_expressions)

        # 光线和色调
        if shot.lighting and shot.lighting != "natural":
            parts.append(f"{shot.lighting} lighting")
        if shot.color_tone and shot.color_tone != "neutral":
            parts.append(f"{shot.color_tone} color tone")

        # 镜头信息
        shot_type_map = {
            "establishing": "wide angle, establishing shot",
            "wide": "wide shot",
            "medium": "medium shot",
            "close-up": "close-up shot",
            "extreme-close-up": "extreme close-up",
            "pov": "first person view, pov",
            "over-shoulder": "over the shoulder shot"
        }
        if shot.type.value in shot_type_map:
            parts.append(shot_type_map[shot.type.value])

        # 分镜中的Prompt提示
        if shot.prompt_hint:
            parts.append(shot.prompt_hint)

        return ", ".join(filter(None, parts))

    def _build_negative_prompt(self, shot: Shot, char_designs: Optional[CharacterDesignSet]) -> str:
        """构建负面Prompt"""
        parts = [
            "low quality",
            "blurry",
            "deformed",
            "bad anatomy",
            "extra limbs",
            "missing limbs",
            "disfigured",
            "ugly",
            "watermark",
            "text"
        ]

        # 分镜中的负面Prompt
        if shot.negative_prompt_hint:
            parts.append(shot.negative_prompt_hint)

        # 角色的负面Prompt
        if char_designs and shot.characters:
            for char_name in shot.characters[:1]:
                char = char_designs.get_character(char_name)
                if char and char.prompts.negative_prompt:
                    parts.append(char.prompts.negative_prompt)

        return ", ".join(parts)

    async def _download_image(self, url: str, save_path: Path):
        """下载图像到本地"""
        if url.startswith("https://placeholder"):
            # 模拟模式，创建空文件
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(b"mock image data")
            return

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(response.content)

        self.logger.debug(f"图像已保存: {save_path}")

    async def evaluate_quality(self, output: ImageGenOutput) -> QualityMetrics:
        """评估图像生成质量"""
        if not output.success:
            return QualityMetrics(
                score=0,
                details={},
                suggestions=["图像生成失败"],
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

        # 2. 图像完整性（检查文件是否存在）
        existing = sum(1 for p in output.image_paths if Path(p).exists())
        if output.image_paths:
            integrity = (existing / len(output.image_paths)) * 100
        else:
            integrity = 0
        details["integrity"] = integrity

        # 3. 简单的质量评估（这里可以扩展为真正的图像质量评估）
        # 暂时使用成功率作为质量指标
        details["quality"] = success_rate

        return QualityMetrics.from_details(details)


# 便捷函数
async def generate_images(
    project_id: str,
    storyboard: EpisodeStoryboard = None,
    storyboard_path: str = None,
    character_designs: CharacterDesignSet = None,
    character_designs_path: str = None,
    mock_mode: bool = False,
    **kwargs
) -> ImageGenOutput:
    """
    便捷函数：生成图像

    Args:
        project_id: 项目ID
        storyboard: 分镜对象
        storyboard_path: 分镜文件路径
        character_designs: 角色设计
        character_designs_path: 角色设计文件路径
        mock_mode: 模拟模式

    Returns:
        图像生成结果
    """
    module = ImageGeneratorModule()
    input_data = ImageGenInput(
        project_id=project_id,
        storyboard=storyboard,
        storyboard_path=storyboard_path,
        character_designs=character_designs,
        character_designs_path=character_designs_path,
        mock_mode=mock_mode,
        **kwargs
    )
    return await module.run(input_data)
