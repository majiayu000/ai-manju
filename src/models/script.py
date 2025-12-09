"""
剧本模型
"""
from typing import Optional
from pydantic import BaseModel, Field


class Dialogue(BaseModel):
    """对话模型"""
    character: str = Field(..., description="角色名")
    text: str = Field(..., description="台词内容")
    emotion: str = Field(default="neutral", description="情绪")
    action: Optional[str] = Field(default=None, description="动作描述")


class Scene(BaseModel):
    """场景模型"""
    scene_id: int = Field(..., description="场景ID")
    location: str = Field(..., description="场景地点")
    time: str = Field(default="day", description="时间")
    description: str = Field(..., description="场景描述")
    characters: list[str] = Field(default_factory=list, description="出场角色")
    dialogues: list[Dialogue] = Field(default_factory=list, description="对话列表")
    narration: Optional[str] = Field(default=None, description="旁白")
    mood: str = Field(default="neutral", description="场景氛围")
    key_actions: list[str] = Field(default_factory=list, description="关键动作")


class Episode(BaseModel):
    """单集模型"""
    episode_id: int = Field(..., description="集数")
    title: str = Field(..., description="本集标题")
    synopsis: str = Field(..., description="本集简介")
    duration_estimate: str = Field(default="60-90s", description="预估时长")
    scenes: list[Scene] = Field(default_factory=list, description="场景列表")
    end_hook: str = Field(..., description="结尾悬念")
    highlight_moments: list[str] = Field(default_factory=list, description="高光时刻")


class MainCharacter(BaseModel):
    """主要角色（剧本中的定义）"""
    name: str = Field(..., description="角色名")
    role: str = Field(..., description="角色类型 protagonist/antagonist/supporting")
    description: str = Field(..., description="角色简介")
    appearance: str = Field(..., description="外貌描述")
    personality: str = Field(..., description="性格特点")
    background: Optional[str] = Field(default=None, description="背景故事")


class Script(BaseModel):
    """完整剧本模型"""
    title: str = Field(..., description="剧名")
    genre: str = Field(..., description="题材类型")
    total_episodes: int = Field(..., description="总集数")
    synopsis: str = Field(..., description="整体剧情简介")

    # 角色
    main_characters: list[MainCharacter] = Field(default_factory=list, description="主要角色")

    # 剧集
    episodes: list[Episode] = Field(default_factory=list, description="剧集列表")

    # 元数据
    themes: list[str] = Field(default_factory=list, description="主题标签")
    target_audience: str = Field(default="general", description="目标受众")
    content_warnings: list[str] = Field(default_factory=list, description="内容警告")

    # 质量指标
    quality_metrics: Optional[dict] = Field(default=None, description="质量指标")

    def get_all_characters(self) -> list[str]:
        """获取所有出场角色"""
        characters = set()
        for char in self.main_characters:
            characters.add(char.name)
        for episode in self.episodes:
            for scene in episode.scenes:
                characters.update(scene.characters)
        return list(characters)

    def get_episode(self, episode_id: int) -> Optional[Episode]:
        """获取指定集"""
        for episode in self.episodes:
            if episode.episode_id == episode_id:
                return episode
        return None

    def get_character_info(self, name: str) -> Optional[MainCharacter]:
        """获取角色信息"""
        for char in self.main_characters:
            if char.name == name:
                return char
        return None
