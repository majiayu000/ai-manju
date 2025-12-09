"""
项目模型
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ProjectStatus(str, Enum):
    """项目状态"""
    CREATED = "created"
    SCRIPT_ADAPTING = "script_adapting"
    SCRIPT_DONE = "script_done"
    STORYBOARD_GENERATING = "storyboard_generating"
    STORYBOARD_DONE = "storyboard_done"
    CHARACTER_DESIGNING = "character_designing"
    CHARACTER_DONE = "character_done"
    IMAGE_GENERATING = "image_generating"
    IMAGE_DONE = "image_done"
    VIDEO_SYNTHESIZING = "video_synthesizing"
    VIDEO_DONE = "video_done"
    AUDIO_EDITING = "audio_editing"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class ProjectConfig(BaseModel):
    """项目配置"""
    total_episodes: int = Field(default=10, description="总集数")
    episode_duration: int = Field(default=90, description="每集时长(秒)")
    art_style: str = Field(default="anime", description="艺术风格")
    target_platform: str = Field(default="douyin", description="目标平台")
    aspect_ratio: str = Field(default="9:16", description="画面比例")
    llm_provider: str = Field(default="claude", description="LLM服务商")
    image_provider: str = Field(default="kling", description="图像生成服务商")
    video_provider: str = Field(default="kling", description="视频生成服务商")


class Project(BaseModel):
    """项目模型"""
    id: str = Field(..., description="项目ID")
    name: str = Field(..., description="项目名称")
    description: Optional[str] = Field(default=None, description="项目描述")

    # IP信息
    ip_name: str = Field(..., description="IP名称")
    ip_source: str = Field(default="original", description="IP来源")
    ip_content_path: Optional[str] = Field(default=None, description="IP原文路径")

    # 状态
    status: ProjectStatus = Field(default=ProjectStatus.CREATED, description="项目状态")
    current_module: Optional[str] = Field(default=None, description="当前执行模块")
    progress: float = Field(default=0.0, description="总体进度(0-100)")

    # 配置
    config: ProjectConfig = Field(default_factory=ProjectConfig, description="项目配置")

    # 路径
    project_dir: Optional[str] = Field(default=None, description="项目目录")

    # 时间
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # 模块状态
    module_states: dict = Field(default_factory=dict, description="各模块状态")

    # 质量评分
    quality_scores: dict = Field(default_factory=dict, description="各模块质量评分")

    # 错误信息
    errors: list = Field(default_factory=list, description="错误记录")

    def update_status(self, status: ProjectStatus, module: Optional[str] = None):
        """更新项目状态"""
        self.status = status
        self.current_module = module
        self.updated_at = datetime.now()

    def update_progress(self, progress: float):
        """更新进度"""
        self.progress = min(100.0, max(0.0, progress))
        self.updated_at = datetime.now()

    def add_error(self, error: str, module: Optional[str] = None):
        """添加错误记录"""
        self.errors.append({
            "timestamp": datetime.now().isoformat(),
            "module": module,
            "error": error
        })

    def set_module_state(self, module: str, state: dict):
        """设置模块状态"""
        self.module_states[module] = {
            **state,
            "updated_at": datetime.now().isoformat()
        }

    def set_quality_score(self, module: str, score: float, details: dict = None):
        """设置模块质量评分"""
        self.quality_scores[module] = {
            "score": score,
            "details": details or {},
            "evaluated_at": datetime.now().isoformat()
        }
