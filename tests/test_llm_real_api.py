"""
LLM真实API测试

使用真实的Claude/OpenAI/DeepSeek API进行测试
运行前请确保配置了相应的API密钥
"""
import pytest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.llm import LLMClient
from config import settings


class TestClaudeRealAPI:
    """Claude真实API测试"""

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_claude_simple_completion(self, has_claude_api):
        """测试Claude简单文本生成"""
        if not has_claude_api:
            pytest.skip("Claude API未配置")

        client = LLMClient(provider="claude")

        response = await client.complete(
            prompt="用一句话描述春天的景色",
            max_tokens=100
        )

        assert response is not None
        assert len(response) > 0
        print(f"\n[Claude响应]: {response}")

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_claude_json_output(self, has_claude_api):
        """测试Claude JSON输出"""
        if not has_claude_api:
            pytest.skip("Claude API未配置")

        client = LLMClient(provider="claude")

        response = await client.complete_json(
            prompt="""
            生成一个简单的角色描述，包含以下字段：
            - name: 角色名称
            - age: 年龄
            - description: 外貌描述

            只返回JSON，不要其他内容
            """,
            max_tokens=200
        )

        assert response is not None
        assert isinstance(response, dict)
        assert "name" in response
        print(f"\n[Claude JSON响应]: {response}")

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_claude_script_adaptation(self, has_claude_api, sample_ip_content):
        """测试Claude剧本改编能力"""
        if not has_claude_api:
            pytest.skip("Claude API未配置")

        client = LLMClient(provider="claude")

        prompt = f"""
        请将以下IP内容改编为短剧剧本的第一场戏，输出JSON格式：

        {{
            "scene_id": 1,
            "scene_name": "场景名称",
            "location": "地点",
            "time": "时间",
            "characters": ["角色列表"],
            "description": "场景描述",
            "dialogue": [
                {{"character": "角色", "line": "台词"}}
            ]
        }}

        IP内容：
        {sample_ip_content[:500]}

        只返回JSON
        """

        response = await client.complete_json(
            prompt=prompt,
            max_tokens=1000
        )

        assert response is not None
        assert "scene_id" in response
        assert "dialogue" in response
        print(f"\n[剧本改编结果]: {response}")


class TestOpenAIRealAPI:
    """OpenAI真实API测试"""

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_openai_simple_completion(self, has_openai_api):
        """测试OpenAI简单文本生成"""
        if not has_openai_api:
            pytest.skip("OpenAI API未配置")

        client = LLMClient(provider="openai")

        response = await client.complete(
            prompt="用一句话描述春天的景色",
            max_tokens=100
        )

        assert response is not None
        assert len(response) > 0
        print(f"\n[OpenAI响应]: {response}")

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_openai_json_output(self, has_openai_api):
        """测试OpenAI JSON输出"""
        if not has_openai_api:
            pytest.skip("OpenAI API未配置")

        client = LLMClient(provider="openai")

        response = await client.complete_json(
            prompt="""
            生成一个简单的角色描述，包含以下字段：
            - name: 角色名称
            - age: 年龄
            - description: 外貌描述

            只返回JSON，不要其他内容
            """,
            max_tokens=200
        )

        assert response is not None
        assert isinstance(response, dict)
        print(f"\n[OpenAI JSON响应]: {response}")


class TestDeepSeekRealAPI:
    """DeepSeek真实API测试"""

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_deepseek_simple_completion(self, has_deepseek_api):
        """测试DeepSeek简单文本生成"""
        if not has_deepseek_api:
            pytest.skip("DeepSeek API未配置")

        client = LLMClient(provider="deepseek")

        response = await client.complete(
            prompt="用一句话描述春天的景色",
            max_tokens=100
        )

        assert response is not None
        assert len(response) > 0
        print(f"\n[DeepSeek响应]: {response}")


class TestLLMProviderFallback:
    """测试LLM提供商回退机制"""

    @pytest.mark.asyncio
    async def test_auto_select_provider(self):
        """测试自动选择可用的提供商"""
        # 尝试创建客户端，会自动选择配置的提供商
        try:
            client = LLMClient()

            response = await client.complete(
                prompt="说'测试成功'",
                max_tokens=20
            )

            assert response is not None
            print(f"\n[自动选择提供商响应]: {response}")
            print(f"[使用的提供商]: {client.provider}")

        except ValueError as e:
            pytest.skip(f"没有配置任何LLM提供商: {e}")


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v", "-s", "--tb=short"])
