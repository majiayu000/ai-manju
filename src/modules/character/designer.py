"""
角色设计模块 - 为角色生成详细的视觉设计
"""
from pathlib import Path
from typing import Optional
from pydantic import Field

from src.modules.base import BaseModule, ModuleInput, ModuleOutput, QualityMetrics
from src.models.script import Script, MainCharacter
from src.models.character import (
    Character, CharacterAppearance, CharacterOutfit,
    CharacterExpressions, CharacterPrompts, CharacterDesignSet
)
from src.ai.llm import get_llm_client
from src.utils.file_handler import FileHandler
from config import settings


class CharacterDesignInput(ModuleInput):
    """角色设计输入"""
    script: Optional[Script] = Field(default=None, description="剧本对象")
    script_path: Optional[str] = Field(default=None, description="剧本文件路径")
    characters: Optional[list[MainCharacter]] = Field(default=None, description="角色信息列表")
    art_style: str = Field(default="anime", description="艺术风格")
    visual_style: str = Field(default="", description="视觉风格描述")


class CharacterDesignOutput(ModuleOutput):
    """角色设计输出"""
    character_designs: Optional[CharacterDesignSet] = Field(default=None, description="角色设计集")
    design_path: Optional[str] = Field(default=None, description="保存路径")
    character_count: int = Field(default=0, description="角色数量")


class CharacterDesignModule(BaseModule[CharacterDesignInput, CharacterDesignOutput]):
    """
    角色设计模块

    为剧本中的角色生成详细的视觉设计，用于后续图像生成
    """

    name = "character_designer"
    version = "1.0.0"
    description = "为角色生成详细的视觉设计和Prompt"

    def __init__(self, llm_provider: Optional[str] = None):
        super().__init__()
        self.llm = get_llm_client(provider=llm_provider)
        self.file_handler = FileHandler()
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """加载Prompt模板"""
        template_path = settings.base_dir / "config" / "prompts" / "character.txt"
        if template_path.exists():
            return self.file_handler.read_text_sync(template_path)
        return self._get_default_prompt_template()

    def _get_default_prompt_template(self) -> str:
        """默认Prompt模板"""
        return """请为以下角色生成详细的视觉设计，用于AI图像生成。

角色信息：
{character_info}

艺术风格：{art_style}
视觉风格：{visual_style}

请为每个角色生成：
1. 详细的外貌描述
2. 服装设计
3. 表情设计
4. 英文Prompt（用于图像生成）
5. 负面Prompt

请以JSON格式输出。"""

    async def validate_input(self, input_data: CharacterDesignInput) -> tuple[bool, Optional[str]]:
        """验证输入"""
        if not input_data.script and not input_data.script_path and not input_data.characters:
            return False, "必须提供script、script_path或characters"

        if input_data.script_path:
            path = Path(input_data.script_path)
            if not path.exists():
                return False, f"剧本文件不存在: {input_data.script_path}"

        return True, None

    async def process(self, input_data: CharacterDesignInput) -> CharacterDesignOutput:
        """执行角色设计"""
        self.logger.info(f"开始角色设计: project={input_data.project_id}")

        try:
            # 获取角色信息
            characters = input_data.characters
            if not characters:
                if input_data.script:
                    characters = input_data.script.main_characters
                elif input_data.script_path:
                    script_data = await self.file_handler.read_json(input_data.script_path)
                    script = Script(**script_data)
                    characters = script.main_characters

            if not characters:
                return CharacterDesignOutput(
                    success=False,
                    error="没有找到角色信息"
                )

            # 构建角色信息文本
            char_info_text = self._format_character_info(characters)

            # 构建Prompt
            prompt = self.prompt_template.format(
                character_info=char_info_text,
                art_style=input_data.art_style,
                visual_style=input_data.visual_style or "清晰、精致的2D动漫风格"
            )

            # 调用LLM生成设计
            self.logger.info("调用LLM生成角色设计...")
            response = await self.llm.chat_json(
                prompt=prompt,
                system="你是专业的角色设计师，擅长为动漫/漫画角色创建详细的视觉设计。请以JSON格式输出。",
                temperature=0.7,
                max_tokens=8192
            )

            # 解析响应
            design_set = self._parse_design_response(
                response,
                input_data.project_id,
                input_data.art_style,
                input_data.visual_style
            )

            # 保存设计
            save_path = await self._save_designs(input_data.project_id, design_set)

            self.logger.info(f"角色设计完成: {len(design_set.characters)}个角色")

            return CharacterDesignOutput(
                success=True,
                data={"character_count": len(design_set.characters)},
                character_designs=design_set,
                design_path=str(save_path),
                character_count=len(design_set.characters)
            )

        except Exception as e:
            self.logger.exception(f"角色设计失败: {e}")
            return CharacterDesignOutput(
                success=False,
                error=str(e)
            )

    def _format_character_info(self, characters: list[MainCharacter]) -> str:
        """格式化角色信息"""
        lines = []
        for i, char in enumerate(characters, 1):
            lines.append(f"角色{i}:")
            lines.append(f"  姓名: {char.name}")
            lines.append(f"  类型: {char.role}")
            lines.append(f"  描述: {char.description}")
            lines.append(f"  外貌: {char.appearance}")
            lines.append(f"  性格: {char.personality}")
            if char.background:
                lines.append(f"  背景: {char.background}")
            lines.append("")
        return "\n".join(lines)

    def _parse_design_response(
        self,
        response: dict,
        project_id: str,
        art_style: str,
        visual_style: str
    ) -> CharacterDesignSet:
        """解析LLM响应为CharacterDesignSet"""
        characters = []
        chars_data = response.get("characters", [])

        for i, char_data in enumerate(chars_data):
            # 解析外貌
            appearance_data = char_data.get("appearance", {})
            appearance = CharacterAppearance(
                face_shape=appearance_data.get("face_shape", "oval"),
                eyes=appearance_data.get("eyes", ""),
                eyebrows=appearance_data.get("eyebrows", ""),
                nose=appearance_data.get("nose", ""),
                mouth=appearance_data.get("mouth", ""),
                hair_style=appearance_data.get("hair_style", ""),
                hair_color=appearance_data.get("hair_color", "black"),
                skin_tone=appearance_data.get("skin_tone", "fair"),
                body_type=appearance_data.get("body_type", "average"),
                height=appearance_data.get("height", "average"),
                distinctive_features=appearance_data.get("distinctive_features", [])
            )

            # 解析服装
            outfit_data = char_data.get("outfit", {})
            outfit = CharacterOutfit(
                main_clothing=outfit_data.get("main_clothing", ""),
                style=outfit_data.get("style", "casual"),
                colors=outfit_data.get("colors", []),
                accessories=outfit_data.get("accessories", []),
                variations=outfit_data.get("variations", [])
            )

            # 解析表情
            expressions_data = char_data.get("expressions", {})
            expressions = CharacterExpressions(
                default=expressions_data.get("default", "neutral expression"),
                happy=expressions_data.get("happy", ""),
                angry=expressions_data.get("angry", ""),
                sad=expressions_data.get("sad", ""),
                surprised=expressions_data.get("surprised", ""),
                fearful=expressions_data.get("fearful", ""),
                disgusted=expressions_data.get("disgusted", "")
            )

            # 解析Prompts
            prompts_data = char_data.get("prompts", {})
            prompts = CharacterPrompts(
                base_prompt=prompts_data.get("base_prompt", ""),
                style_tags=prompts_data.get("style_tags", f"{art_style} style"),
                quality_tags=prompts_data.get("quality_tags", "masterpiece, best quality, highly detailed"),
                negative_prompt=prompts_data.get("negative_prompt", "low quality, blurry, deformed")
            )

            # 如果没有生成base_prompt，自动生成
            if not prompts.base_prompt:
                prompts.base_prompt = self._generate_base_prompt(char_data, appearance, outfit)

            character = Character(
                id=char_data.get("id", f"char_{i+1:03d}"),
                name=char_data.get("name", f"角色{i+1}"),
                name_en=char_data.get("name_en", f"Character{i+1}"),
                role=char_data.get("role", "supporting"),
                gender=char_data.get("gender", "unknown"),
                age_range=char_data.get("age_range", "unknown"),
                personality_keywords=char_data.get("personality_keywords", []),
                appearance=appearance,
                outfit=outfit,
                expressions=expressions,
                prompts=prompts,
                consistency_notes=char_data.get("consistency_notes", ""),
                reference_description=char_data.get("reference_description", "")
            )
            characters.append(character)

        return CharacterDesignSet(
            project_id=project_id,
            characters=characters,
            art_style=art_style,
            visual_style=visual_style
        )

    def _generate_base_prompt(
        self,
        char_data: dict,
        appearance: CharacterAppearance,
        outfit: CharacterOutfit
    ) -> str:
        """自动生成基础Prompt"""
        parts = []

        # 性别和年龄
        gender = char_data.get("gender", "")
        if gender == "male":
            parts.append("1 man")
        elif gender == "female":
            parts.append("1 woman")
        else:
            parts.append("1 person")

        age = char_data.get("age_range", "")
        if age:
            parts.append(age)

        # 发型发色
        if appearance.hair_color:
            parts.append(f"{appearance.hair_color} hair")
        if appearance.hair_style:
            parts.append(appearance.hair_style)

        # 眼睛
        if appearance.eyes:
            parts.append(appearance.eyes)

        # 服装
        if outfit.main_clothing:
            parts.append(outfit.main_clothing)

        # 特征
        for feature in appearance.distinctive_features[:2]:
            parts.append(feature)

        return ", ".join(parts)

    async def _save_designs(
        self,
        project_id: str,
        design_set: CharacterDesignSet
    ) -> Path:
        """保存角色设计到文件"""
        self.file_handler.ensure_project_structure(project_id)
        save_path = self.file_handler.get_character_path(project_id)
        await self.file_handler.write_json(save_path, design_set.model_dump())
        return save_path

    async def evaluate_quality(self, output: CharacterDesignOutput) -> QualityMetrics:
        """评估角色设计质量"""
        if not output.success or not output.character_designs:
            return QualityMetrics(
                score=0,
                details={},
                suggestions=["角色设计生成失败"],
                passed=False
            )

        details = {}
        design_set = output.character_designs

        # 1. 描述完整度
        completeness = self._evaluate_completeness(design_set)
        details["completeness"] = completeness

        # 2. 特征区分度
        distinction = self._evaluate_distinction(design_set)
        details["distinction"] = distinction

        # 3. Prompt质量
        prompt_quality = self._evaluate_prompts(design_set)
        details["prompt_quality"] = prompt_quality

        # 4. 一致性信息
        consistency = self._evaluate_consistency_info(design_set)
        details["consistency"] = consistency

        return QualityMetrics.from_details(details)

    def _evaluate_completeness(self, design_set: CharacterDesignSet) -> float:
        """评估描述完整度"""
        if not design_set.characters:
            return 0

        total_score = 0
        for char in design_set.characters:
            score = 0
            # 检查各项是否完整
            if char.appearance.hair_style:
                score += 15
            if char.appearance.hair_color:
                score += 10
            if char.appearance.eyes:
                score += 10
            if char.outfit.main_clothing:
                score += 20
            if char.prompts.base_prompt:
                score += 30
            if char.expressions.default:
                score += 15
            total_score += score

        return total_score / len(design_set.characters)

    def _evaluate_distinction(self, design_set: CharacterDesignSet) -> float:
        """评估角色特征区分度"""
        if len(design_set.characters) < 2:
            return 100  # 单个角色无需区分

        # 检查关键特征是否有区分
        hair_colors = set()
        hair_styles = set()
        outfits = set()

        for char in design_set.characters:
            if char.appearance.hair_color:
                hair_colors.add(char.appearance.hair_color.lower())
            if char.appearance.hair_style:
                hair_styles.add(char.appearance.hair_style.lower())
            if char.outfit.main_clothing:
                outfits.add(char.outfit.main_clothing.lower()[:20])

        # 计算区分度
        total_chars = len(design_set.characters)
        distinction_score = (
            (len(hair_colors) / total_chars) * 30 +
            (len(hair_styles) / total_chars) * 30 +
            (len(outfits) / total_chars) * 40
        )

        return min(100, distinction_score)

    def _evaluate_prompts(self, design_set: CharacterDesignSet) -> float:
        """评估Prompt质量"""
        if not design_set.characters:
            return 0

        total_score = 0
        for char in design_set.characters:
            score = 0
            # 检查base_prompt
            if char.prompts.base_prompt:
                length = len(char.prompts.base_prompt)
                if length > 50:
                    score += 50
                elif length > 20:
                    score += 30
                else:
                    score += 10

            # 检查style_tags
            if char.prompts.style_tags:
                score += 20

            # 检查quality_tags
            if char.prompts.quality_tags:
                score += 15

            # 检查negative_prompt
            if char.prompts.negative_prompt:
                score += 15

            total_score += score

        return total_score / len(design_set.characters)

    def _evaluate_consistency_info(self, design_set: CharacterDesignSet) -> float:
        """评估一致性信息"""
        if not design_set.characters:
            return 0

        score = 0
        for char in design_set.characters:
            # 检查一致性相关信息
            if char.consistency_notes:
                score += 30
            if char.distinctive_features := char.appearance.distinctive_features:
                score += 40
            if char.reference_description:
                score += 30

        return score / len(design_set.characters)


# 便捷函数
async def design_characters(
    project_id: str,
    script: Script = None,
    script_path: str = None,
    characters: list[MainCharacter] = None,
    art_style: str = "anime",
    **kwargs
) -> CharacterDesignOutput:
    """
    便捷函数：设计角色

    Args:
        project_id: 项目ID
        script: 剧本对象
        script_path: 剧本文件路径
        characters: 角色信息列表
        art_style: 艺术风格

    Returns:
        角色设计结果
    """
    module = CharacterDesignModule()
    input_data = CharacterDesignInput(
        project_id=project_id,
        script=script,
        script_path=script_path,
        characters=characters,
        art_style=art_style,
        **kwargs
    )
    return await module.run(input_data)
