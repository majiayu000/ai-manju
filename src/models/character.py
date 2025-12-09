"""
角色设计模型
"""
from typing import Optional
from pydantic import BaseModel, Field


class CharacterAppearance(BaseModel):
    """角色外貌"""
    face_shape: str = Field(default="oval", description="脸型")
    eyes: str = Field(..., description="眼睛描述")
    eyebrows: str = Field(default="", description="眉毛")
    nose: str = Field(default="", description="鼻子")
    mouth: str = Field(default="", description="嘴巴")
    hair_style: str = Field(..., description="发型")
    hair_color: str = Field(..., description="发色")
    skin_tone: str = Field(default="fair", description="肤色")
    body_type: str = Field(default="average", description="体型")
    height: str = Field(default="average", description="身高描述")
    distinctive_features: list[str] = Field(default_factory=list, description="标志性特征")


class CharacterOutfit(BaseModel):
    """角色服装"""
    main_clothing: str = Field(..., description="主要服装描述")
    style: str = Field(..., description="服装风格")
    colors: list[str] = Field(default_factory=list, description="主要颜色")
    accessories: list[str] = Field(default_factory=list, description="配饰")
    variations: list[str] = Field(default_factory=list, description="服装变体")


class CharacterExpressions(BaseModel):
    """角色表情"""
    default: str = Field(..., description="默认表情")
    happy: str = Field(default="", description="开心")
    angry: str = Field(default="", description="愤怒")
    sad: str = Field(default="", description="悲伤")
    surprised: str = Field(default="", description="惊讶")
    fearful: str = Field(default="", description="恐惧")
    disgusted: str = Field(default="", description="厌恶")


class CharacterPrompts(BaseModel):
    """角色Prompt"""
    base_prompt: str = Field(..., description="基础Prompt（英文）")
    style_tags: str = Field(default="", description="风格标签")
    quality_tags: str = Field(default="masterpiece, best quality, highly detailed", description="质量标签")
    negative_prompt: str = Field(
        default="low quality, blurry, deformed, bad anatomy, extra limbs",
        description="负面Prompt"
    )


class Character(BaseModel):
    """角色设计完整模型"""
    id: str = Field(..., description="角色ID")
    name: str = Field(..., description="角色名")
    name_en: str = Field(..., description="英文名")
    role: str = Field(..., description="角色类型")
    gender: str = Field(..., description="性别")
    age_range: str = Field(..., description="年龄段")
    personality_keywords: list[str] = Field(default_factory=list, description="性格关键词")

    # 外貌
    appearance: CharacterAppearance = Field(..., description="外貌设计")

    # 服装
    outfit: CharacterOutfit = Field(..., description="服装设计")

    # 表情
    expressions: CharacterExpressions = Field(..., description="表情设计")

    # Prompt
    prompts: CharacterPrompts = Field(..., description="生成Prompt")

    # 一致性控制
    consistency_seed: Optional[int] = Field(default=None, description="一致性种子")
    lora_model: Optional[str] = Field(default=None, description="LoRA模型路径")
    reference_images: list[str] = Field(default_factory=list, description="参考图路径")

    # 备注
    consistency_notes: str = Field(default="", description="一致性注意事项")
    reference_description: str = Field(default="", description="参考图详细描述")

    def get_full_prompt(self, expression: str = "default", outfit_variant: int = 0) -> str:
        """获取完整的生成Prompt"""
        parts = [
            self.prompts.base_prompt,
            self.prompts.style_tags,
            self.prompts.quality_tags,
        ]

        # 添加表情
        expr_map = {
            "default": self.expressions.default,
            "happy": self.expressions.happy,
            "angry": self.expressions.angry,
            "sad": self.expressions.sad,
            "surprised": self.expressions.surprised,
        }
        if expression in expr_map and expr_map[expression]:
            parts.append(expr_map[expression])

        return ", ".join(filter(None, parts))

    def get_negative_prompt(self) -> str:
        """获取负面Prompt"""
        return self.prompts.negative_prompt


class CharacterDesignSet(BaseModel):
    """角色设计集合"""
    project_id: str = Field(..., description="项目ID")
    characters: list[Character] = Field(default_factory=list, description="角色列表")
    art_style: str = Field(default="anime", description="整体艺术风格")
    visual_style: str = Field(default="", description="视觉风格描述")

    def get_character(self, name: str) -> Optional[Character]:
        """获取指定角色"""
        for char in self.characters:
            if char.name == name or char.id == name:
                return char
        return None

    def get_character_by_id(self, char_id: str) -> Optional[Character]:
        """通过ID获取角色"""
        for char in self.characters:
            if char.id == char_id:
                return char
        return None
