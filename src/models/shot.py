"""
镜头和分镜模型
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ShotType(str, Enum):
    """镜头类型"""
    ESTABLISHING = "establishing"  # 建立镜头
    WIDE = "wide"  # 全景
    MEDIUM = "medium"  # 中景
    CLOSE_UP = "close-up"  # 特写
    EXTREME_CLOSE_UP = "extreme-close-up"  # 大特写
    POV = "pov"  # 主观视角
    OVER_SHOULDER = "over-shoulder"  # 过肩镜头
    TWO_SHOT = "two-shot"  # 双人镜头
    GROUP = "group"  # 群像


class CameraMovement(str, Enum):
    """镜头运动"""
    STATIC = "static"  # 静止
    PAN = "pan"  # 横摇
    TILT = "tilt"  # 纵摇
    ZOOM_IN = "zoom-in"  # 推进
    ZOOM_OUT = "zoom-out"  # 拉远
    TRACKING = "tracking"  # 跟踪
    DOLLY = "dolly"  # 推轨
    CRANE = "crane"  # 升降


class Shot(BaseModel):
    """单个镜头"""
    shot_id: int = Field(..., description="镜头ID")
    episode_id: int = Field(..., description="所属集数")
    scene_id: int = Field(..., description="所属场景")

    # 镜头信息
    type: ShotType = Field(default=ShotType.MEDIUM, description="镜头类型")
    duration: float = Field(default=3.0, description="时长(秒)")
    camera_movement: CameraMovement = Field(default=CameraMovement.STATIC, description="镜头运动")

    # 画面描述
    description: str = Field(..., description="画面详细描述")
    characters: list[str] = Field(default_factory=list, description="出场角色")
    character_positions: str = Field(default="", description="角色位置")
    character_actions: str = Field(default="", description="角色动作")
    character_expressions: str = Field(default="", description="角色表情")

    # 台词/音频
    dialogue: Optional[str] = Field(default=None, description="台词")
    dialogue_character: Optional[str] = Field(default=None, description="说话角色")
    narration: Optional[str] = Field(default=None, description="旁白")

    # 情绪/氛围
    emotion_tone: str = Field(default="neutral", description="情绪基调")
    lighting: str = Field(default="natural", description="光线")
    color_tone: str = Field(default="neutral", description="色调")

    # 生成用
    prompt_hint: str = Field(default="", description="图像生成提示词建议")
    negative_prompt_hint: str = Field(default="", description="负面提示词建议")

    # 音效
    sfx: list[str] = Field(default_factory=list, description="音效")
    bgm_note: Optional[str] = Field(default=None, description="BGM备注")

    # 转场
    transition_to_next: str = Field(default="cut", description="到下一镜头的转场")

    # 生成结果
    image_path: Optional[str] = Field(default=None, description="生成的图像路径")
    video_path: Optional[str] = Field(default=None, description="生成的视频路径")
    audio_path: Optional[str] = Field(default=None, description="生成的音频路径")

    # 质量
    quality_score: Optional[float] = Field(default=None, description="质量评分")
    generation_attempts: int = Field(default=0, description="生成尝试次数")

    def get_full_id(self) -> str:
        """获取完整ID"""
        return f"ep{self.episode_id:02d}_sc{self.scene_id:02d}_shot{self.shot_id:03d}"


class Storyboard(BaseModel):
    """分镜板（一个场景的所有镜头）"""
    project_id: str = Field(..., description="项目ID")
    episode_id: int = Field(..., description="集数")
    scene_id: int = Field(..., description="场景ID")
    location: str = Field(default="", description="场景地点")
    time: str = Field(default="day", description="时间")

    total_duration: float = Field(default=0.0, description="总时长")
    shots: list[Shot] = Field(default_factory=list, description="镜头列表")

    def calculate_duration(self) -> float:
        """计算总时长"""
        self.total_duration = sum(shot.duration for shot in self.shots)
        return self.total_duration

    def get_shot(self, shot_id: int) -> Optional[Shot]:
        """获取指定镜头"""
        for shot in self.shots:
            if shot.shot_id == shot_id:
                return shot
        return None


class EpisodeStoryboard(BaseModel):
    """一集的完整分镜"""
    project_id: str = Field(..., description="项目ID")
    episode_id: int = Field(..., description="集数")
    title: str = Field(default="", description="集标题")

    scenes: list[Storyboard] = Field(default_factory=list, description="场景分镜列表")
    total_duration: float = Field(default=0.0, description="总时长")
    total_shots: int = Field(default=0, description="总镜头数")

    def calculate_totals(self):
        """计算总数"""
        self.total_duration = sum(scene.calculate_duration() for scene in self.scenes)
        self.total_shots = sum(len(scene.shots) for scene in self.scenes)

    def get_all_shots(self) -> list[Shot]:
        """获取所有镜头"""
        shots = []
        for scene in self.scenes:
            shots.extend(scene.shots)
        return shots

    def get_scene(self, scene_id: int) -> Optional[Storyboard]:
        """获取指定场景"""
        for scene in self.scenes:
            if scene.scene_id == scene_id:
                return scene
        return None
