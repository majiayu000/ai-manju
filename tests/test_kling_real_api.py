"""
可灵AI真实API测试

使用真实的可灵AI API进行图像和视频生成测试
运行前请确保配置了 KLING_API_KEY 和 KLING_API_SECRET

注意：这些测试会消耗API额度，请谨慎运行
"""
import pytest
import asyncio
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.modules.image_gen.providers.kling import KlingImageProvider, get_kling_image_provider
from src.modules.video_synth.providers.kling import KlingVideoProvider, get_kling_video_provider
from config import settings


class TestKlingImageRealAPI:
    """可灵图像生成真实API测试"""

    @pytest.mark.real_api
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_text_to_image_basic(self, has_kling_api):
        """测试文生图基本功能"""
        if not has_kling_api:
            pytest.skip("可灵API未配置")

        provider = get_kling_image_provider(mock=False)

        # 提交任务
        result = await provider.text_to_image(
            prompt="一个年轻的中国外卖员，穿着蓝色工作服，骑着电动车，夜晚的城市街道背景，电影级画质",
            negative_prompt="低质量, 模糊, 变形",
            aspect_ratio="9:16"  # 竖屏
        )

        assert result is not None
        assert "task_id" in result
        print(f"\n[文生图任务已提交]: task_id={result['task_id']}")

        # 等待完成
        final_result = await provider.wait_for_completion(
            result["task_id"],
            timeout=300,
            poll_interval=5
        )

        assert final_result["status"] == "succeed"
        assert "image_url" in final_result
        print(f"\n[文生图完成]: {final_result['image_url']}")

    @pytest.mark.real_api
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_text_to_image_anime_style(self, has_kling_api):
        """测试动漫风格文生图"""
        if not has_kling_api:
            pytest.skip("可灵API未配置")

        provider = get_kling_image_provider(mock=False)

        result = await provider.text_to_image_and_wait(
            prompt="动漫风格，一个神秘的老人，穿着民国时期的长衫，坐在废弃医院的角落，月光透过窗户照进来，气氛阴森",
            negative_prompt="真人, 写实, 低质量",
            aspect_ratio="16:9"
        )

        assert result is not None
        assert result["status"] == "succeed"
        print(f"\n[动漫风格图像生成完成]: {result.get('image_url', 'N/A')}")

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_kling_image_api_auth(self, has_kling_api):
        """测试可灵图像API认证"""
        if not has_kling_api:
            pytest.skip("可灵API未配置")

        provider = KlingImageProvider()

        # 测试JWT token生成
        token = provider._generate_jwt_token()
        assert token is not None
        assert len(token) > 0
        print(f"\n[JWT Token生成成功]: {token[:50]}...")


class TestKlingVideoRealAPI:
    """可灵视频生成真实API测试"""

    @pytest.mark.real_api
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_text_to_video_basic(self, has_kling_api):
        """测试文生视频基本功能"""
        if not has_kling_api:
            pytest.skip("可灵API未配置")

        provider = get_kling_video_provider(mock=False)

        # 提交任务
        result = await provider.text_to_video(
            prompt="一个外卖员骑着电动车穿过夜晚的城市街道，霓虹灯闪烁，镜头跟随",
            negative_prompt="低质量, 抖动",
            duration=5.0,
            mode="std",
            aspect_ratio="9:16"
        )

        assert result is not None
        assert "task_id" in result
        print(f"\n[文生视频任务已提交]: task_id={result['task_id']}")

        # 等待完成（视频生成较慢，设置较长超时）
        final_result = await provider.wait_for_completion(
            result["task_id"],
            timeout=600,
            poll_interval=10
        )

        assert final_result["status"] == "succeed"
        assert "video_url" in final_result
        print(f"\n[文生视频完成]: {final_result['video_url']}")

    @pytest.mark.real_api
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_image_to_video_with_test_image(self, has_kling_api, tmp_path):
        """测试图生视频（使用测试图像）"""
        if not has_kling_api:
            pytest.skip("可灵API未配置")

        # 首先生成一张测试图像
        image_provider = get_kling_image_provider(mock=False)

        image_result = await image_provider.text_to_image_and_wait(
            prompt="一个年轻人站在废弃医院的大厅中，月光照射，神秘氛围",
            aspect_ratio="9:16"
        )

        assert image_result["status"] == "succeed"
        image_url = image_result["image_url"]
        print(f"\n[测试图像生成完成]: {image_url}")

        # 使用图像生成视频
        video_provider = get_kling_video_provider(mock=False)

        result = await video_provider.image_to_video_and_wait(
            image_url=image_url,
            prompt="人物轻微呼吸，微风吹动衣角，镜头缓慢推进",
            duration=5.0,
            mode="std"
        )

        assert result["status"] == "succeed"
        assert "video_url" in result
        print(f"\n[图生视频完成]: {result['video_url']}")


class TestKlingAPIIntegration:
    """可灵API集成测试"""

    @pytest.mark.real_api
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_full_image_to_video_pipeline(self, has_kling_api):
        """完整的图像到视频生成流程测试"""
        if not has_kling_api:
            pytest.skip("可灵API未配置")

        print("\n开始完整的图生视频流程测试...")

        # 步骤1：生成角色图像
        image_provider = get_kling_image_provider(mock=False)

        print("步骤1: 生成角色图像...")
        image_result = await image_provider.text_to_image_and_wait(
            prompt="""
            动漫风格，一个25岁的中国男性外卖员，
            穿着蓝色外卖工作服，戴着头盔，
            表情认真，站在电动车旁，
            夜晚城市街道背景，霓虹灯光，
            高质量，精细画面
            """,
            negative_prompt="变形, 低质量, 模糊, 真人",
            aspect_ratio="9:16"
        )

        assert image_result["status"] == "succeed"
        image_url = image_result["image_url"]
        print(f"  图像生成完成: {image_url}")

        # 步骤2：将图像转为视频
        video_provider = get_kling_video_provider(mock=False)

        print("步骤2: 将图像转换为视频...")
        video_result = await video_provider.image_to_video_and_wait(
            image_url=image_url,
            prompt="人物轻微移动，眨眼，环顾四周，背景霓虹灯闪烁",
            duration=5.0,
            mode="std"
        )

        assert video_result["status"] == "succeed"
        video_url = video_result["video_url"]
        print(f"  视频生成完成: {video_url}")

        # 输出结果
        print("\n" + "="*50)
        print("流程测试完成!")
        print(f"图像URL: {image_url}")
        print(f"视频URL: {video_url}")
        print("="*50)

        return {
            "image_url": image_url,
            "video_url": video_url
        }


class TestKlingAPIQuota:
    """可灵API额度检查（不消耗额度）"""

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_check_api_connection(self, has_kling_api):
        """测试API连接是否正常"""
        if not has_kling_api:
            pytest.skip("可灵API未配置")

        # 仅测试认证，不实际调用生成API
        provider = KlingImageProvider()

        # 验证JWT token生成
        token = provider._generate_jwt_token()
        assert token is not None

        # 验证headers
        headers = provider._get_headers()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

        print("\n[API认证检查通过]")
        print(f"API Key: {settings.kling_api_key[:8]}...")
        print(f"Base URL: {provider.base_url}")


if __name__ == "__main__":
    # 直接运行测试
    # 使用 -k 参数可以选择特定测试
    # 例如: python test_kling_real_api.py -k "test_check_api"
    pytest.main([__file__, "-v", "-s", "--tb=short"])
