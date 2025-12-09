"""
可灵AI 视频生成API封装
"""
import asyncio
import time
import hashlib
import hmac
import base64
import jwt
from typing import Optional
import httpx
from loguru import logger

from config import settings


class KlingVideoProvider:
    """
    可灵AI视频生成API

    支持:
    - 图生视频 (image-to-video)
    - 文生视频 (text-to-video)

    文档: https://platform.klingai.com/
    """

    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key or settings.kling_api_key
        self.api_secret = api_secret or settings.kling_api_secret
        self.base_url = "https://api.klingai.com/v1"
        self.logger = logger.bind(service="kling_video")

    def _generate_jwt_token(self) -> str:
        """生成JWT Token"""
        now = int(time.time())
        payload = {
            "iss": self.api_key,
            "exp": now + 1800,  # 30分钟过期
            "nbf": now - 5
        }
        token = jwt.encode(payload, self.api_secret, algorithm="HS256")
        return token

    def _get_headers(self) -> dict:
        """获取请求头"""
        token = self._generate_jwt_token()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

    async def image_to_video(
        self,
        image_url: str,
        prompt: str = "",
        negative_prompt: str = "",
        duration: float = 5.0,
        cfg_scale: float = 0.5,
        mode: str = "std",  # std / pro
        camera_control: Optional[dict] = None
    ) -> dict:
        """
        图生视频

        Args:
            image_url: 图像URL或Base64
            prompt: 运动描述提示词
            negative_prompt: 负向提示词
            duration: 视频时长 (5 或 10 秒)
            cfg_scale: 提示词相关性 (0-1)
            mode: 模式 (std标准/pro专业)
            camera_control: 镜头控制参数

        Returns:
            {"task_id": "xxx", "status": "submitted"}
        """
        self.logger.info(f"提交图生视频任务: duration={duration}s")

        payload = {
            "model_name": "kling-v1",
            "image": image_url,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration": str(int(duration)),
            "cfg_scale": cfg_scale,
            "mode": mode
        }

        if camera_control:
            payload["camera_control"] = camera_control

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/videos/image2video",
                headers=self._get_headers(),
                json=payload
            )

            if response.status_code != 200:
                self.logger.error(f"API错误: {response.status_code} - {response.text}")
                raise Exception(f"Kling API error: {response.status_code} - {response.text}")

            data = response.json()
            if data.get("code") != 0:
                raise Exception(f"Kling API error: {data.get('message')}")

            task_id = data.get("data", {}).get("task_id")
            self.logger.info(f"任务已提交: {task_id}")

            return {
                "task_id": task_id,
                "status": "submitted"
            }

    async def text_to_video(
        self,
        prompt: str,
        negative_prompt: str = "",
        duration: float = 5.0,
        cfg_scale: float = 0.5,
        mode: str = "std",
        aspect_ratio: str = "9:16"
    ) -> dict:
        """
        文生视频

        Args:
            prompt: 视频描述提示词
            negative_prompt: 负向提示词
            duration: 视频时长 (5 或 10 秒)
            cfg_scale: 提示词相关性 (0-1)
            mode: 模式 (std标准/pro专业)
            aspect_ratio: 宽高比

        Returns:
            {"task_id": "xxx", "status": "submitted"}
        """
        self.logger.info(f"提交文生视频任务: {prompt[:50]}...")

        payload = {
            "model_name": "kling-v1",
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration": str(int(duration)),
            "cfg_scale": cfg_scale,
            "mode": mode,
            "aspect_ratio": aspect_ratio
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/videos/text2video",
                headers=self._get_headers(),
                json=payload
            )

            if response.status_code != 200:
                self.logger.error(f"API错误: {response.status_code} - {response.text}")
                raise Exception(f"Kling API error: {response.status_code}")

            data = response.json()
            if data.get("code") != 0:
                raise Exception(f"Kling API error: {data.get('message')}")

            task_id = data.get("data", {}).get("task_id")
            self.logger.info(f"任务已提交: {task_id}")

            return {
                "task_id": task_id,
                "status": "submitted"
            }

    async def get_task_status(self, task_id: str) -> dict:
        """
        查询任务状态

        Returns:
            {
                "task_id": "xxx",
                "status": "submitted/processing/succeed/failed",
                "video_url": "...",  # 成功时返回
                "error": "..."       # 失败时返回
            }
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/videos/image2video/{task_id}",
                headers=self._get_headers()
            )

            if response.status_code != 200:
                raise Exception(f"Kling API error: {response.status_code}")

            data = response.json()
            if data.get("code") != 0:
                raise Exception(f"Kling API error: {data.get('message')}")

            task_data = data.get("data", {})
            status = task_data.get("task_status")

            result = {
                "task_id": task_id,
                "status": status
            }

            if status == "succeed":
                videos = task_data.get("task_result", {}).get("videos", [])
                if videos:
                    result["video_url"] = videos[0].get("url")
                    result["duration"] = videos[0].get("duration")

            elif status == "failed":
                result["error"] = task_data.get("task_status_msg", "Unknown error")

            return result

    async def wait_for_completion(
        self,
        task_id: str,
        timeout: int = 600,
        poll_interval: int = 10
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

            if status == "succeed":
                self.logger.info(f"视频生成完成: {task_id}")
                return result
            elif status == "failed":
                error = result.get("error", "Unknown error")
                self.logger.error(f"视频生成失败: {task_id} - {error}")
                raise Exception(f"Video generation failed: {error}")

            self.logger.debug(f"任务进行中: {task_id} - {status}")
            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"Task {task_id} timed out after {timeout}s")

    async def image_to_video_and_wait(
        self,
        image_url: str,
        prompt: str = "",
        **kwargs
    ) -> dict:
        """
        图生视频并等待完成

        Returns:
            {"task_id": "xxx", "video_url": "...", "duration": 5}
        """
        # 提交任务
        task_result = await self.image_to_video(
            image_url=image_url,
            prompt=prompt,
            **kwargs
        )

        task_id = task_result.get("task_id")
        if not task_id:
            raise Exception("No task_id returned")

        # 等待完成
        return await self.wait_for_completion(task_id)


class MockKlingVideoProvider:
    """
    模拟的可灵视频提供商，用于测试
    """

    def __init__(self, *args, **kwargs):
        self.logger = logger.bind(service="mock_kling_video")

    async def image_to_video(self, image_url: str, **kwargs) -> dict:
        """模拟图生视频"""
        self.logger.info(f"[MOCK] 图生视频: {image_url[:50]}...")
        return {
            "task_id": f"mock_video_task_{int(time.time())}",
            "status": "submitted"
        }

    async def text_to_video(self, prompt: str, **kwargs) -> dict:
        """模拟文生视频"""
        self.logger.info(f"[MOCK] 文生视频: {prompt[:50]}...")
        return {
            "task_id": f"mock_video_task_{int(time.time())}",
            "status": "submitted"
        }

    async def get_task_status(self, task_id: str) -> dict:
        """模拟查询状态"""
        return {
            "task_id": task_id,
            "status": "succeed",
            "video_url": "https://placeholder.com/video.mp4",
            "duration": 5
        }

    async def wait_for_completion(self, task_id: str, **kwargs) -> dict:
        """模拟等待完成"""
        await asyncio.sleep(0.5)  # 模拟一点延迟
        return await self.get_task_status(task_id)

    async def image_to_video_and_wait(self, image_url: str, **kwargs) -> dict:
        """模拟图生视频并等待"""
        result = await self.image_to_video(image_url, **kwargs)
        return await self.wait_for_completion(result["task_id"])


def get_kling_video_provider(mock: bool = False) -> KlingVideoProvider:
    """
    获取可灵视频提供商实例

    Args:
        mock: 是否使用模拟提供商

    Returns:
        提供商实例
    """
    if mock or not settings.kling_api_key:
        return MockKlingVideoProvider()
    return KlingVideoProvider()
