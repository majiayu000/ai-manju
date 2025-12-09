"""
可灵AI API封装
"""
import time
import hashlib
import hmac
import base64
from typing import Optional
import httpx
from loguru import logger

from config import settings


class KlingImageProvider:
    """
    可灵AI图像生成API

    文档参考: https://platform.klingai.com/
    """

    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key or settings.kling_api_key
        self.api_secret = api_secret or settings.kling_api_secret
        self.base_url = "https://api.klingai.com"
        self.logger = logger.bind(service="kling_image")

    def _generate_signature(self, timestamp: str) -> str:
        """生成API签名"""
        message = f"{self.api_key}{timestamp}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode('utf-8')

    def _get_headers(self) -> dict:
        """获取请求头"""
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp)

        return {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "X-Timestamp": timestamp,
            "X-Signature": signature
        }

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        aspect_ratio: str = "9:16",
        style: str = "anime",
        quality: str = "high",
        num_images: int = 1
    ) -> dict:
        """
        生成图像

        Args:
            prompt: 正向提示词
            negative_prompt: 负向提示词
            aspect_ratio: 宽高比 (9:16, 16:9, 1:1, 4:3, 3:4)
            style: 风格 (anime, realistic, artistic)
            quality: 质量 (standard, high, ultra)
            num_images: 生成数量

        Returns:
            {
                "task_id": "xxx",
                "status": "pending/processing/completed/failed",
                "images": [{"url": "...", "seed": 123}]
            }
        """
        self.logger.info(f"提交图像生成任务: {prompt[:50]}...")

        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "aspect_ratio": aspect_ratio,
            "style": style,
            "quality": quality,
            "num_images": num_images
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/images/generate",
                headers=self._get_headers(),
                json=payload
            )

            if response.status_code != 200:
                self.logger.error(f"API错误: {response.status_code} - {response.text}")
                raise Exception(f"Kling API error: {response.status_code}")

            data = response.json()
            self.logger.info(f"任务已提交: {data.get('task_id')}")
            return data

    async def get_task_status(self, task_id: str) -> dict:
        """
        查询任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态和结果
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/v1/images/task/{task_id}",
                headers=self._get_headers()
            )

            if response.status_code != 200:
                raise Exception(f"Kling API error: {response.status_code}")

            return response.json()

    async def wait_for_completion(
        self,
        task_id: str,
        timeout: int = 300,
        poll_interval: int = 5
    ) -> dict:
        """
        等待任务完成

        Args:
            task_id: 任务ID
            timeout: 超时时间(秒)
            poll_interval: 轮询间隔(秒)

        Returns:
            完成的任务结果
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            result = await self.get_task_status(task_id)
            status = result.get("status")

            if status == "completed":
                self.logger.info(f"任务完成: {task_id}")
                return result
            elif status == "failed":
                error = result.get("error", "Unknown error")
                self.logger.error(f"任务失败: {task_id} - {error}")
                raise Exception(f"Image generation failed: {error}")

            self.logger.debug(f"任务进行中: {task_id} - {status}")
            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"Task {task_id} timed out after {timeout}s")

    async def generate_and_wait(
        self,
        prompt: str,
        negative_prompt: str = "",
        **kwargs
    ) -> list[dict]:
        """
        生成图像并等待完成

        Args:
            prompt: 正向提示词
            negative_prompt: 负向提示词
            **kwargs: 其他参数

        Returns:
            生成的图像列表 [{"url": "...", "seed": 123}]
        """
        # 提交任务
        task_result = await self.generate_image(
            prompt=prompt,
            negative_prompt=negative_prompt,
            **kwargs
        )

        task_id = task_result.get("task_id")
        if not task_id:
            raise Exception("No task_id returned")

        # 等待完成
        result = await self.wait_for_completion(task_id)

        return result.get("images", [])


# 为了避免导入问题，这里添加asyncio导入
import asyncio


class MockKlingProvider:
    """
    模拟的可灵AI提供商，用于测试
    """

    def __init__(self, *args, **kwargs):
        self.logger = logger.bind(service="mock_kling")

    async def generate_image(self, prompt: str, **kwargs) -> dict:
        """模拟生成图像"""
        self.logger.info(f"[MOCK] 生成图像: {prompt[:50]}...")
        return {
            "task_id": f"mock_task_{int(time.time())}",
            "status": "completed",
            "images": [
                {"url": "https://placeholder.com/image.png", "seed": 12345}
            ]
        }

    async def get_task_status(self, task_id: str) -> dict:
        """模拟查询状态"""
        return {
            "task_id": task_id,
            "status": "completed",
            "images": [
                {"url": "https://placeholder.com/image.png", "seed": 12345}
            ]
        }

    async def wait_for_completion(self, task_id: str, **kwargs) -> dict:
        """模拟等待完成"""
        return await self.get_task_status(task_id)

    async def generate_and_wait(self, prompt: str, **kwargs) -> list[dict]:
        """模拟生成并等待"""
        result = await self.generate_image(prompt, **kwargs)
        return result.get("images", [])


def get_kling_provider(mock: bool = False) -> KlingImageProvider:
    """
    获取可灵AI提供商实例

    Args:
        mock: 是否使用模拟提供商

    Returns:
        提供商实例
    """
    if mock or not settings.kling_api_key:
        return MockKlingProvider()
    return KlingImageProvider()
