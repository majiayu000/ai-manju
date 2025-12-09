"""
视频生成提供商
"""
from .kling import KlingVideoProvider, MockKlingVideoProvider, get_kling_video_provider

__all__ = ["KlingVideoProvider", "MockKlingVideoProvider", "get_kling_video_provider"]
