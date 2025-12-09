"""
TTS (Text-to-Speech) 提供商封装
支持多种TTS服务
"""
import asyncio
import time
from typing import Optional
from pathlib import Path
import httpx
from loguru import logger

from config import settings


class EdgeTTSProvider:
    """
    Microsoft Edge TTS 提供商

    免费、高质量的TTS服务
    """

    def __init__(self):
        self.logger = logger.bind(service="edge_tts")

    async def synthesize(
        self,
        text: str,
        output_path: Path,
        voice: str = "zh-CN-XiaoxiaoNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz"
    ) -> dict:
        """
        合成语音

        Args:
            text: 要转换的文本
            output_path: 输出音频路径
            voice: 语音选择
            rate: 语速调整
            pitch: 音高调整

        Returns:
            {"success": True, "duration": float, "path": str}
        """
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            await communicate.save(str(output_path))

            # 获取音频时长
            duration = await self._get_audio_duration(output_path)

            self.logger.info(f"TTS合成完成: {output_path}, 时长={duration:.1f}s")

            return {
                "success": True,
                "duration": duration,
                "path": str(output_path)
            }

        except ImportError:
            self.logger.error("edge-tts未安装，请运行: pip install edge-tts")
            raise
        except Exception as e:
            self.logger.error(f"TTS合成失败: {e}")
            raise

    async def _get_audio_duration(self, audio_path: Path) -> float:
        """获取音频时长"""
        try:
            import subprocess
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                 str(audio_path)],
                capture_output=True,
                text=True
            )
            return float(result.stdout.strip())
        except:
            return 0.0

    def get_available_voices(self) -> list[dict]:
        """获取可用的语音列表"""
        return [
            {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓", "gender": "女", "style": "温柔"},
            {"id": "zh-CN-YunxiNeural", "name": "云希", "gender": "男", "style": "阳光"},
            {"id": "zh-CN-YunjianNeural", "name": "云健", "gender": "男", "style": "成熟"},
            {"id": "zh-CN-XiaoyiNeural", "name": "晓伊", "gender": "女", "style": "活泼"},
            {"id": "zh-CN-YunyangNeural", "name": "云扬", "gender": "男", "style": "新闻"},
            {"id": "zh-CN-XiaochenNeural", "name": "晓辰", "gender": "女", "style": "知性"},
        ]


class FishAudioProvider:
    """
    Fish Audio TTS 提供商

    高质量AI语音合成，支持声音克隆
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.fish_audio_api_key
        self.base_url = "https://api.fish.audio/v1"
        self.logger = logger.bind(service="fish_audio")

    async def synthesize(
        self,
        text: str,
        output_path: Path,
        reference_id: str = None,  # 参考音频ID
        format: str = "mp3"
    ) -> dict:
        """
        合成语音

        Args:
            text: 要转换的文本
            output_path: 输出音频路径
            reference_id: 参考音频ID（用于声音克隆）
            format: 输出格式

        Returns:
            {"success": True, "duration": float, "path": str}
        """
        if not self.api_key:
            raise ValueError("Fish Audio API key not configured")

        payload = {
            "text": text,
            "format": format
        }

        if reference_id:
            payload["reference_id"] = reference_id

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/tts",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload
            )

            if response.status_code != 200:
                raise Exception(f"Fish Audio API error: {response.status_code}")

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.content)

            # 获取音频时长
            duration = await self._get_audio_duration(output_path)

            self.logger.info(f"TTS合成完成: {output_path}")

            return {
                "success": True,
                "duration": duration,
                "path": str(output_path)
            }

    async def _get_audio_duration(self, audio_path: Path) -> float:
        """获取音频时长"""
        try:
            import subprocess
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                 str(audio_path)],
                capture_output=True,
                text=True
            )
            return float(result.stdout.strip())
        except:
            return 0.0


class MockTTSProvider:
    """
    模拟TTS提供商，用于测试
    """

    def __init__(self, *args, **kwargs):
        self.logger = logger.bind(service="mock_tts")

    async def synthesize(
        self,
        text: str,
        output_path: Path,
        **kwargs
    ) -> dict:
        """模拟语音合成"""
        self.logger.info(f"[MOCK] TTS合成: {text[:30]}...")

        # 创建模拟音频文件
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"mock audio data")

        # 估算时长（按中文每秒5个字）
        duration = len(text) / 5.0

        await asyncio.sleep(0.1)  # 模拟一点延迟

        return {
            "success": True,
            "duration": duration,
            "path": str(output_path)
        }

    def get_available_voices(self) -> list[dict]:
        """获取可用的语音列表"""
        return [
            {"id": "mock-female", "name": "模拟女声", "gender": "女"},
            {"id": "mock-male", "name": "模拟男声", "gender": "男"},
        ]


def get_tts_provider(provider: str = "edge", mock: bool = False):
    """
    获取TTS提供商实例

    Args:
        provider: 提供商名称 (edge/fish)
        mock: 是否使用模拟提供商

    Returns:
        TTS提供商实例
    """
    if mock:
        return MockTTSProvider()

    if provider == "fish":
        return FishAudioProvider()
    else:
        return EdgeTTSProvider()
