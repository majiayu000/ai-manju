"""
LLM客户端封装
"""
import json
from typing import Optional, Literal
from abc import ABC, abstractmethod
import httpx
from loguru import logger

from config import settings


class BaseLLMProvider(ABC):
    """LLM提供商基类"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False
    ) -> str:
        """发送聊天请求"""
        pass


class ClaudeProvider(BaseLLMProvider):
    """Claude API提供商"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.anthropic.com/v1"
        self.model = "claude-sonnet-4-20250514"

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False
    ) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            # 分离system消息
            system_content = ""
            chat_messages = []

            for msg in messages:
                if msg["role"] == "system":
                    system_content = msg["content"]
                else:
                    chat_messages.append(msg)

            payload = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": chat_messages
            }

            if system_content:
                payload["system"] = system_content

            response = await client.post(
                f"{self.base_url}/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01"
                },
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API提供商"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openai.com/v1"
        self.model = "gpt-4o"

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False
    ) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }

            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek API提供商"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com/v1"
        self.model = "deepseek-chat"

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False
    ) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }

            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


class LLMClient:
    """
    统一的LLM客户端

    支持多个提供商，自动选择或手动指定
    """

    def __init__(
        self,
        provider: Optional[Literal["claude", "openai", "deepseek"]] = None
    ):
        self.provider_name = provider or settings.default_llm_provider
        self.provider = self._create_provider()
        self.logger = logger.bind(service="llm")

    def _create_provider(self) -> BaseLLMProvider:
        """创建提供商实例"""
        if self.provider_name == "claude":
            if not settings.claude_api_key:
                raise ValueError("CLAUDE_API_KEY not configured")
            return ClaudeProvider(settings.claude_api_key)
        elif self.provider_name == "openai":
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY not configured")
            return OpenAIProvider(settings.openai_api_key)
        elif self.provider_name == "deepseek":
            if not settings.deepseek_api_key:
                raise ValueError("DEEPSEEK_API_KEY not configured")
            return DeepSeekProvider(settings.deepseek_api_key)
        else:
            raise ValueError(f"Unknown provider: {self.provider_name}")

    async def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = None,
        max_tokens: int = None,
        json_mode: bool = False
    ) -> str:
        """
        发送聊天请求

        Args:
            prompt: 用户提示
            system: 系统提示
            temperature: 温度参数
            max_tokens: 最大token数
            json_mode: 是否JSON模式

        Returns:
            模型响应文本
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        temp = temperature if temperature is not None else settings.llm_temperature
        tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens

        self.logger.debug(f"发送LLM请求: provider={self.provider_name}, tokens={tokens}")

        try:
            response = await self.provider.chat(
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
                json_mode=json_mode
            )
            self.logger.debug(f"LLM响应长度: {len(response)}")
            return response
        except Exception as e:
            self.logger.error(f"LLM请求失败: {e}")
            raise

    async def chat_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = None,
        max_tokens: int = None
    ) -> dict:
        """
        发送请求并解析JSON响应

        Args:
            prompt: 用户提示
            system: 系统提示
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            解析后的JSON对象
        """
        response = await self.chat(
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True
        )

        # 尝试提取JSON
        try:
            # 直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取代码块中的JSON
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
                return json.loads(json_str)
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                json_str = response[start:end].strip()
                return json.loads(json_str)
            else:
                self.logger.error(f"无法解析JSON响应: {response[:500]}")
                raise ValueError("无法解析JSON响应")


def get_llm_client(
    provider: Optional[Literal["claude", "openai", "deepseek"]] = None
) -> LLMClient:
    """获取LLM客户端实例"""
    return LLMClient(provider=provider)
