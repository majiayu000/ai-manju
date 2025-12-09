"""
全局配置管理
"""
from typing import Literal
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置"""

    # ==================== 项目路径 ====================
    base_dir: Path = Path(__file__).parent.parent
    data_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "data")
    inputs_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "data" / "inputs")
    projects_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "data" / "projects")
    outputs_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "data" / "outputs")

    # ==================== LLM配置 ====================
    claude_api_key: str = ""
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    default_llm_provider: Literal["claude", "openai", "deepseek"] = "claude"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096

    # ==================== 图像生成配置 ====================
    kling_api_key: str = ""
    kling_api_secret: str = ""
    midjourney_api_key: str = ""
    default_image_provider: Literal["kling", "midjourney", "stable_diffusion"] = "kling"
    image_quality: Literal["standard", "high", "ultra"] = "high"
    image_style: str = "anime"  # anime, realistic, comic
    image_aspect_ratio: str = "9:16"  # 短剧竖屏

    # ==================== 视频生成配置 ====================
    default_video_provider: Literal["kling"] = "kling"
    video_fps: int = 24
    video_duration_per_shot: float = 3.0  # 每个镜头默认时长（秒）

    # ==================== 配音配置 ====================
    tts_provider: Literal["xunfei", "elevenlabs"] = "xunfei"
    xunfei_app_id: str = ""
    xunfei_api_key: str = ""
    xunfei_api_secret: str = ""
    elevenlabs_api_key: str = ""

    # ==================== 数据库配置 ====================
    database_url: str = "sqlite:///./data/db.sqlite"
    redis_url: str = "redis://localhost:6379/0"

    # ==================== 服务配置 ====================
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    log_level: str = "INFO"

    # ==================== 质量控制 ====================
    min_quality_score: float = 70.0
    auto_retry_on_low_quality: bool = True
    max_retries: int = 3

    # ==================== 生产配置 ====================
    episodes_per_batch: int = 5  # 每批处理的集数
    shots_per_episode: int = 30  # 每集平均镜头数
    max_concurrent_tasks: int = 3  # 最大并发任务数

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# 全局配置实例
settings = Settings()
