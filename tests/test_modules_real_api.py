"""
模块真实API集成测试

测试各个模块使用真实API的完整功能
运行前请确保配置了相应的API密钥
"""
import pytest
import asyncio
import sys
from pathlib import Path
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.modules.script_adapter import ScriptAdapterModule, ScriptAdapterInput
from src.modules.storyboard import StoryboardModule, StoryboardInput
from src.modules.character import CharacterDesignModule, CharacterDesignInput
from src.modules.image_gen import ImageGenModule, ImageGenInput
from src.modules.video_synth import VideoSynthModule, VideoSynthInput
from src.modules.audio_editing import AudioEditingModule, AudioEditingInput
from config import settings


class TestScriptAdapterRealAPI:
    """剧本改编模块真实API测试"""

    @pytest.fixture
    def test_output_dir(self, tmp_path):
        """创建测试输出目录"""
        output_dir = tmp_path / "test_script"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_adapt_script_with_claude(self, has_claude_api, sample_ip_content, test_project_id):
        """使用Claude测试剧本改编"""
        if not has_claude_api:
            pytest.skip("Claude API未配置")

        module = ScriptAdapterModule()

        input_data = ScriptAdapterInput(
            project_id=test_project_id,
            ip_content=sample_ip_content,
            total_episodes=1,
            episode_duration=60,
            target_audience="18-35岁年轻人",
            genre="悬疑/灵异"
        )

        result = await module.run(input_data)

        assert result.success, f"剧本改编失败: {result.error}"
        assert result.script is not None
        assert len(result.script.episodes) > 0

        print("\n[剧本改编结果]")
        print(f"标题: {result.script.title}")
        print(f"集数: {len(result.script.episodes)}")
        for ep in result.script.episodes:
            print(f"  第{ep.episode_id}集: {len(ep.scenes)}个场景")
            for scene in ep.scenes[:2]:  # 只显示前2个场景
                print(f"    场景{scene.scene_id}: {scene.location}")

        # 评估质量
        quality = await module.evaluate_quality(result)
        print(f"\n质量评分: {quality.score}")
        print(f"通过: {quality.passed}")

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_script_quality_evaluation(self, has_claude_api, sample_ip_content, test_project_id):
        """测试剧本质量评估"""
        if not has_claude_api:
            pytest.skip("Claude API未配置")

        module = ScriptAdapterModule()

        input_data = ScriptAdapterInput(
            project_id=test_project_id,
            ip_content=sample_ip_content,
            total_episodes=1,
            episode_duration=90
        )

        result = await module.run(input_data)

        if result.success:
            quality = await module.evaluate_quality(result)

            assert quality.score >= 0
            assert quality.score <= 100
            assert isinstance(quality.details, dict)

            print("\n[质量评估详情]")
            for key, value in quality.details.items():
                print(f"  {key}: {value}")
            print(f"建议: {quality.suggestions}")


class TestStoryboardRealAPI:
    """分镜生成模块真实API测试"""

    @pytest.mark.real_api
    @pytest.mark.asyncio
    async def test_generate_storyboard(self, has_claude_api, sample_ip_content, test_project_id):
        """测试分镜生成"""
        if not has_claude_api:
            pytest.skip("Claude API未配置")

        # 首先生成剧本
        script_module = ScriptAdapterModule()
        script_input = ScriptAdapterInput(
            project_id=test_project_id,
            ip_content=sample_ip_content,
            total_episodes=1,
            episode_duration=60
        )
        script_result = await script_module.run(script_input)

        assert script_result.success, "剧本生成失败"

        # 生成分镜
        storyboard_module = StoryboardModule()
        storyboard_input = StoryboardInput(
            project_id=test_project_id,
            script=script_result.script,
            episode_id=1,
            art_style="anime",
            shots_per_scene=3
        )

        result = await storyboard_module.run(storyboard_input)

        assert result.success, f"分镜生成失败: {result.error}"
        assert result.storyboard is not None

        all_shots = result.storyboard.get_all_shots()
        print(f"\n[分镜生成结果]")
        print(f"集数: {result.storyboard.episode_id}")
        print(f"总镜头数: {len(all_shots)}")
        print(f"总时长: {result.total_duration}秒")

        # 显示前3个镜头
        for shot in all_shots[:3]:
            print(f"\n镜头 {shot.shot_id}:")
            print(f"  描述: {shot.description[:50]}...")
            print(f"  时长: {shot.duration}秒")
            print(f"  Prompt: {shot.image_prompt[:50] if shot.image_prompt else 'N/A'}...")


class TestImageGenRealAPI:
    """图像生成模块真实API测试"""

    @pytest.mark.real_api
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_generate_images_single_shot(self, has_kling_api, test_project_id):
        """测试单镜头图像生成"""
        if not has_kling_api:
            pytest.skip("可灵API未配置")

        from src.models.shot import Shot, SceneStoryboard, EpisodeStoryboard

        # 创建测试分镜
        shot = Shot(
            shot_id=1,
            episode_id=1,
            scene_id=1,
            description="外卖员李明骑着电动车穿过夜晚的城市街道",
            duration=5.0,
            image_prompt="anime style, a young Chinese delivery man riding an electric scooter through city streets at night, neon lights, cinematic, high quality"
        )

        scene = SceneStoryboard(
            scene_id=1,
            scene_name="夜间送餐",
            location="城市街道",
            shots=[shot]
        )

        storyboard = EpisodeStoryboard(
            episode_id=1,
            scenes=[scene]
        )

        # 生成图像
        module = ImageGenModule()
        input_data = ImageGenInput(
            project_id=test_project_id,
            storyboard=storyboard,
            shot_ids=[1],  # 只生成第一个镜头
            art_style="anime"
        )

        result = await module.run(input_data)

        assert result.success, f"图像生成失败: {result.error}"
        assert len(result.generated_images) > 0

        print(f"\n[图像生成结果]")
        print(f"生成数量: {result.total_generated}")
        for img in result.generated_images:
            print(f"  镜头 {img['shot_id']}: {img.get('image_url', 'N/A')}")


class TestFullPipelineRealAPI:
    """完整流水线真实API测试"""

    @pytest.mark.real_api
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_script_to_storyboard_pipeline(self, has_claude_api, sample_ip_content, test_project_id):
        """测试从剧本到分镜的完整流程"""
        if not has_claude_api:
            pytest.skip("Claude API未配置")

        print("\n" + "="*60)
        print("开始完整流水线测试: 剧本 -> 分镜")
        print("="*60)

        # 步骤1: 剧本改编
        print("\n[步骤1] 剧本改编...")
        script_module = ScriptAdapterModule()
        script_result = await script_module.run(ScriptAdapterInput(
            project_id=test_project_id,
            ip_content=sample_ip_content,
            total_episodes=1,
            episode_duration=60
        ))

        assert script_result.success
        script_quality = await script_module.evaluate_quality(script_result)
        print(f"  剧本质量: {script_quality.score}/100")

        # 步骤2: 分镜生成
        print("\n[步骤2] 分镜生成...")
        storyboard_module = StoryboardModule()
        storyboard_result = await storyboard_module.run(StoryboardInput(
            project_id=test_project_id,
            script=script_result.script,
            episode_id=1,
            art_style="anime",
            shots_per_scene=2
        ))

        assert storyboard_result.success
        storyboard_quality = await storyboard_module.evaluate_quality(storyboard_result)
        print(f"  分镜质量: {storyboard_quality.score}/100")

        # 步骤3: 角色设计
        print("\n[步骤3] 角色设计...")
        character_module = CharacterDesignModule()
        character_result = await character_module.run(CharacterDesignInput(
            project_id=test_project_id,
            script=script_result.script,
            art_style="anime"
        ))

        assert character_result.success
        character_quality = await character_module.evaluate_quality(character_result)
        print(f"  角色设计质量: {character_quality.score}/100")

        # 汇总结果
        print("\n" + "="*60)
        print("流水线测试完成!")
        print("="*60)
        print(f"剧本: {len(script_result.script.episodes)}集, 质量={script_quality.score}")
        print(f"分镜: {len(storyboard_result.storyboard.get_all_shots())}个镜头, 质量={storyboard_quality.score}")
        print(f"角色: {len(character_result.characters)}个, 质量={character_quality.score}")

    @pytest.mark.real_api
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_full_pipeline_with_image_generation(
        self,
        has_claude_api,
        has_kling_api,
        sample_ip_content,
        test_project_id
    ):
        """完整流水线测试（包含图像生成）"""
        if not has_claude_api:
            pytest.skip("Claude API未配置")
        if not has_kling_api:
            pytest.skip("可灵API未配置")

        print("\n" + "="*60)
        print("开始完整流水线测试: 剧本 -> 分镜 -> 图像")
        print("="*60)

        # 步骤1-3: 剧本、分镜、角色
        script_module = ScriptAdapterModule()
        script_result = await script_module.run(ScriptAdapterInput(
            project_id=test_project_id,
            ip_content=sample_ip_content,
            total_episodes=1,
            episode_duration=60
        ))
        print(f"[步骤1] 剧本改编完成")

        storyboard_module = StoryboardModule()
        storyboard_result = await storyboard_module.run(StoryboardInput(
            project_id=test_project_id,
            script=script_result.script,
            episode_id=1,
            art_style="anime",
            shots_per_scene=2
        ))
        print(f"[步骤2] 分镜生成完成: {len(storyboard_result.storyboard.get_all_shots())}个镜头")

        # 步骤4: 图像生成（只生成前2个镜头以节省API额度）
        print(f"[步骤4] 开始图像生成（限制2个镜头）...")
        image_module = ImageGenModule()

        all_shots = storyboard_result.storyboard.get_all_shots()
        shot_ids = [s.shot_id for s in all_shots[:2]]

        image_result = await image_module.run(ImageGenInput(
            project_id=test_project_id,
            storyboard=storyboard_result.storyboard,
            shot_ids=shot_ids,
            art_style="anime"
        ))

        print(f"  图像生成完成: {image_result.total_generated}张")

        # 汇总
        print("\n" + "="*60)
        print("完整流水线测试完成!")
        print("="*60)
        for img in image_result.generated_images:
            print(f"  镜头{img['shot_id']}: {img.get('image_url', 'N/A')[:50]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
