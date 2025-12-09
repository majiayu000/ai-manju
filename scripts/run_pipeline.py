#!/usr/bin/env python
"""
快速运行脚本 - 演示如何使用流水线
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline.controller import PipelineController, PipelineConfig
from src.utils.logger import setup_logger


async def main():
    """主函数"""
    setup_logger()

    # 示例IP内容
    sample_ip = """
    《阴间外卖员》

    李明是一个普通的外卖员，每天穿梭在城市的大街小巷。

    一天深夜，他接到一个奇怪的订单，送餐地址是一个废弃的医院。当他到达时，
    发现接单的是一个穿着民国服装的老人。老人给了他一枚古铜钱作为小费。

    从那天起，李明的手机开始收到来自"阴间外卖"的订单。这些订单的客户都是
    已经去世的人，他们有的想吃生前最爱的食物，有的想给阳间的亲人传话。

    李明发现，只要他完成这些订单，就能获得神秘的力量。但他也逐渐发现，
    阴间外卖背后隐藏着一个巨大的阴谋...

    第一章：奇怪的订单
    李明骑着电动车穿过空无一人的街道。手机上的订单地址指向城郊一座废弃医院。
    "谁会在这种地方点外卖？"他嘀咕着，但还是硬着头皮走了进去。
    医院大厅空荡荡的，月光从破碎的窗户照进来，在地上投下斑驳的影子。
    "外卖到了。"李明喊了一声。
    "年轻人，你来了。"一个苍老的声音从黑暗中传来。
    李明打开手电，看到一个穿着民国长衫的老人坐在角落里。
    "您点的麻辣烫。"李明把外卖递过去，手却穿过了老人的身体。
    他吓得后退一步，手机掉在地上。
    老人笑了笑："不用怕，我只是想尝尝生前最爱吃的味道。"
    他拿起筷子，夹起一块豆腐，放进嘴里，脸上露出满足的表情。
    "谢谢你，年轻人。这是给你的小费。"
    一枚古铜钱落在李明手心，冰凉刺骨。
    """

    # 配置流水线
    config = PipelineConfig(
        total_episodes=5,           # 生成5集
        episode_duration=90,        # 每集90秒
        art_style="anime",          # 动漫风格
        mock_mode=True,             # 模拟模式（不调用真实API）
        skip_video_synthesis=True,  # 跳过视频合成
        skip_audio_editing=True,    # 跳过配音
        min_quality_score=60,       # 降低质量阈值（测试用）
    )

    # 创建控制器
    controller = PipelineController(config=config)

    # 进度回调
    def on_progress(progress: float, message: str):
        print(f"[{progress:5.1f}%] {message}")

    def on_stage_start(stage):
        print(f"\n{'='*50}")
        print(f"开始阶段: {stage.value}")
        print('='*50)

    def on_stage_complete(stage, result):
        success = result.get("success", False)
        quality = result.get("quality_score", "-")
        status = "✓" if success else "✗"
        print(f"{status} 阶段完成: {stage.value}, 质量={quality}")

    controller.on_progress = on_progress
    controller.on_stage_start = on_stage_start
    controller.on_stage_complete = on_stage_complete

    # 创建项目
    print("\n创建项目...")
    project = await controller.create_project(
        name="阴间外卖员",
        ip_content=sample_ip,
        description="一个关于外卖员获得神秘能力的悬疑故事"
    )
    print(f"项目ID: {project.id}")
    print(f"项目目录: {project.project_dir}")

    # 运行流水线
    print("\n开始运行流水线...")
    result = await controller.run_full_pipeline(project)

    # 输出结果
    print("\n" + "="*50)
    print("流水线执行结果")
    print("="*50)
    print(f"成功: {result.success}")
    print(f"完成阶段: {len(result.completed_stages)}")
    print(f"耗时: {result.duration_seconds:.1f}秒")

    if result.errors:
        print("\n错误:")
        for err in result.errors:
            print(f"  - {err}")

    print("\n各阶段结果:")
    for stage, stage_result in result.stage_results.items():
        success = "✓" if stage_result.get("success") else "✗"
        quality = stage_result.get("quality_score", "-")
        print(f"  {success} {stage}: 质量={quality}")

    # 显示输出文件
    print(f"\n输出目录: {project.project_dir}")
    print("生成的文件:")

    project_path = Path(project.project_dir)
    for category in ["script", "storyboard", "characters", "images"]:
        cat_path = project_path / category
        if cat_path.exists():
            files = list(cat_path.glob("*"))
            if files:
                print(f"  {category}/")
                for f in files[:5]:
                    print(f"    - {f.name}")
                if len(files) > 5:
                    print(f"    ... 共 {len(files)} 个文件")


if __name__ == "__main__":
    asyncio.run(main())
