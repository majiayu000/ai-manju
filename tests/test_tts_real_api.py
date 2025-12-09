"""
TTS真实API测试

测试Edge TTS等语音合成功能
"""
import pytest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.modules.audio_editing.providers.tts import EdgeTTSProvider, get_tts_provider


class TestEdgeTTSRealAPI:
    """Edge TTS真实API测试"""

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_edge_tts_basic(self, tmp_path):
        """测试Edge TTS基本功能"""
        try:
            import edge_tts
        except ImportError:
            pytest.skip("edge-tts未安装，请运行: pip install edge-tts")

        provider = EdgeTTSProvider()

        output_path = tmp_path / "test_audio.mp3"

        result = await provider.synthesize(
            text="你好，我是外卖员李明，请问是您点的麻辣烫吗？",
            output_path=output_path,
            voice="zh-CN-XiaoxiaoNeural"
        )

        assert result["success"]
        assert output_path.exists()
        assert output_path.stat().st_size > 0

        print(f"\n[Edge TTS测试结果]")
        print(f"  输出路径: {output_path}")
        print(f"  文件大小: {output_path.stat().st_size} bytes")
        print(f"  时长: {result.get('duration', 'N/A')}秒")

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_edge_tts_multiple_voices(self, tmp_path):
        """测试不同语音"""
        try:
            import edge_tts
        except ImportError:
            pytest.skip("edge-tts未安装")

        provider = EdgeTTSProvider()

        test_cases = [
            ("zh-CN-XiaoxiaoNeural", "晓晓", "你好，我是晓晓"),
            ("zh-CN-YunxiNeural", "云希", "你好，我是云希"),
            ("zh-CN-YunjianNeural", "云健", "你好，我是云健"),
        ]

        print("\n[多语音测试]")
        for voice_id, voice_name, text in test_cases:
            output_path = tmp_path / f"test_{voice_id}.mp3"

            result = await provider.synthesize(
                text=text,
                output_path=output_path,
                voice=voice_id
            )

            assert result["success"]
            print(f"  {voice_name} ({voice_id}): {output_path.stat().st_size} bytes")

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_edge_tts_speed_and_pitch(self, tmp_path):
        """测试语速和音高调整"""
        try:
            import edge_tts
        except ImportError:
            pytest.skip("edge-tts未安装")

        provider = EdgeTTSProvider()

        test_text = "测试语速和音高调整"

        # 正常语速
        normal_path = tmp_path / "normal.mp3"
        await provider.synthesize(
            text=test_text,
            output_path=normal_path,
            rate="+0%",
            pitch="+0Hz"
        )

        # 快语速
        fast_path = tmp_path / "fast.mp3"
        await provider.synthesize(
            text=test_text,
            output_path=fast_path,
            rate="+20%",
            pitch="+0Hz"
        )

        # 慢语速
        slow_path = tmp_path / "slow.mp3"
        await provider.synthesize(
            text=test_text,
            output_path=slow_path,
            rate="-20%",
            pitch="+0Hz"
        )

        print("\n[语速测试]")
        print(f"  正常: {normal_path.stat().st_size} bytes")
        print(f"  快速: {fast_path.stat().st_size} bytes")
        print(f"  慢速: {slow_path.stat().st_size} bytes")

        assert fast_path.stat().st_size < normal_path.stat().st_size
        assert slow_path.stat().st_size > normal_path.stat().st_size

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_edge_tts_long_text(self, tmp_path):
        """测试长文本合成"""
        try:
            import edge_tts
        except ImportError:
            pytest.skip("edge-tts未安装")

        provider = EdgeTTSProvider()

        long_text = """
        李明骑着电动车穿过空无一人的街道。
        手机上的订单地址指向城郊一座废弃医院。
        谁会在这种地方点外卖？他嘀咕着，但还是硬着头皮走了进去。
        医院大厅空荡荡的，月光从破碎的窗户照进来，在地上投下斑驳的影子。
        外卖到了。李明喊了一声。
        年轻人，你来了。一个苍老的声音从黑暗中传来。
        """

        output_path = tmp_path / "long_text.mp3"

        result = await provider.synthesize(
            text=long_text,
            output_path=output_path
        )

        assert result["success"]
        assert output_path.exists()

        print(f"\n[长文本测试]")
        print(f"  文本长度: {len(long_text)} 字符")
        print(f"  文件大小: {output_path.stat().st_size} bytes")
        print(f"  预估时长: {result.get('duration', 'N/A')}秒")


class TestTTSProviderFactory:
    """TTS提供商工厂测试"""

    @pytest.mark.asyncio
    async def test_get_edge_provider(self):
        """测试获取Edge TTS提供商"""
        provider = get_tts_provider(provider="edge", mock=False)
        assert isinstance(provider, EdgeTTSProvider)

    @pytest.mark.asyncio
    async def test_get_mock_provider(self, tmp_path):
        """测试获取模拟提供商"""
        from src.modules.audio_editing.providers.tts import MockTTSProvider

        provider = get_tts_provider(mock=True)
        assert isinstance(provider, MockTTSProvider)

        # 测试模拟合成
        output_path = tmp_path / "mock_audio.mp3"
        result = await provider.synthesize(
            text="测试文本",
            output_path=output_path
        )

        assert result["success"]
        assert output_path.exists()

    @pytest.mark.asyncio
    async def test_available_voices(self):
        """测试获取可用语音列表"""
        provider = EdgeTTSProvider()
        voices = provider.get_available_voices()

        assert len(voices) > 0
        assert all("id" in v and "name" in v for v in voices)

        print("\n[可用语音]")
        for voice in voices:
            print(f"  {voice['name']} ({voice['id']}): {voice.get('style', 'N/A')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
