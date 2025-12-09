"""
命令行入口
"""
import asyncio
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.pipeline.controller import PipelineController, PipelineConfig, PipelineStage
from src.utils.logger import setup_logger

app = typer.Typer(
    name="ai-manhua",
    help="AI漫剧生产流水线CLI工具"
)
console = Console()


@app.command()
def create(
    name: str = typer.Argument(..., help="项目名称"),
    ip_file: str = typer.Option(None, "--ip", "-i", help="IP原文文件路径"),
    episodes: int = typer.Option(10, "--episodes", "-e", help="目标集数"),
    style: str = typer.Option("anime", "--style", "-s", help="艺术风格")
):
    """创建新项目"""
    setup_logger()

    config = PipelineConfig(
        total_episodes=episodes,
        art_style=style
    )
    controller = PipelineController(config=config)

    async def _create():
        ip_content = None
        if ip_file:
            ip_content = Path(ip_file).read_text(encoding="utf-8")

        project = await controller.create_project(
            name=name,
            ip_content=ip_content
        )
        return project

    project = asyncio.run(_create())

    console.print(f"\n[green]✓ 项目创建成功[/green]")
    console.print(f"  项目ID: {project.id}")
    console.print(f"  目录: {project.project_dir}")


@app.command()
def run(
    project_id: str = typer.Argument(..., help="项目ID"),
    mock: bool = typer.Option(False, "--mock", "-m", help="模拟模式"),
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="空运行"),
    skip_images: bool = typer.Option(False, "--skip-images", help="跳过图像生成"),
    skip_video: bool = typer.Option(True, "--skip-video", help="跳过视频合成"),
):
    """运行项目流水线"""
    setup_logger()

    config = PipelineConfig(
        mock_mode=mock,
        dry_run=dry_run,
        skip_image_generation=skip_images,
        skip_video_synthesis=skip_video,
        skip_audio_editing=True
    )
    controller = PipelineController(config=config)

    async def _run():
        # 加载项目
        project = await controller.load_project(project_id)

        # 设置进度回调
        def on_progress(progress, message):
            console.print(f"[blue]{progress:.0f}%[/blue] {message}")

        controller.on_progress = on_progress

        # 运行
        result = await controller.run_full_pipeline(project)
        return result

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("运行流水线...", total=None)
        result = asyncio.run(_run())

    # 显示结果
    if result.success:
        console.print(f"\n[green]✓ 流水线执行成功[/green]")
    else:
        console.print(f"\n[red]✗ 流水线执行失败[/red]")

    console.print(f"  完成阶段: {len(result.completed_stages)}")
    console.print(f"  耗时: {result.duration_seconds:.1f}秒")

    if result.errors:
        console.print("\n[red]错误:[/red]")
        for err in result.errors:
            console.print(f"  - {err}")


@app.command()
def module(
    project_id: str = typer.Argument(..., help="项目ID"),
    stage: str = typer.Argument(..., help="模块名称"),
    mock: bool = typer.Option(False, "--mock", "-m", help="模拟模式"),
):
    """运行单个模块"""
    setup_logger()

    stage_map = {
        "script": PipelineStage.SCRIPT_ADAPT,
        "storyboard": PipelineStage.STORYBOARD,
        "character": PipelineStage.CHARACTER_DESIGN,
        "image": PipelineStage.IMAGE_GENERATION,
        "video": PipelineStage.VIDEO_SYNTHESIS,
        "audio": PipelineStage.AUDIO_EDITING,
    }

    if stage not in stage_map:
        console.print(f"[red]未知模块: {stage}[/red]")
        console.print(f"可用模块: {', '.join(stage_map.keys())}")
        return

    config = PipelineConfig(mock_mode=mock)
    controller = PipelineController(config=config)

    async def _run():
        project = await controller.load_project(project_id)
        result = await controller.run_single_module(project, stage_map[stage])
        return result

    result = asyncio.run(_run())

    if result.get("success"):
        console.print(f"\n[green]✓ 模块 {stage} 执行成功[/green]")
    else:
        console.print(f"\n[red]✗ 模块 {stage} 执行失败[/red]")
        console.print(f"  错误: {result.get('error')}")


@app.command()
def status(
    project_id: str = typer.Argument(..., help="项目ID"),
):
    """查看项目状态"""
    setup_logger()

    config = PipelineConfig()
    controller = PipelineController(config=config)

    async def _load():
        return await controller.load_project(project_id)

    project = asyncio.run(_load())

    # 显示项目信息
    console.print(f"\n[bold]项目信息[/bold]")
    console.print(f"  ID: {project.id}")
    console.print(f"  名称: {project.name}")
    console.print(f"  状态: {project.status.value}")
    console.print(f"  进度: {project.progress:.1f}%")
    console.print(f"  更新时间: {project.updated_at}")

    # 显示模块状态
    if project.module_states:
        console.print(f"\n[bold]模块状态[/bold]")
        table = Table()
        table.add_column("模块")
        table.add_column("状态")

        for module, state in project.module_states.items():
            table.add_row(module, str(state.get("updated_at", "-")))

        console.print(table)

    # 显示质量评分
    if project.quality_scores:
        console.print(f"\n[bold]质量评分[/bold]")
        table = Table()
        table.add_column("模块")
        table.add_column("评分")

        for module, score_info in project.quality_scores.items():
            score = score_info.get("score", 0)
            table.add_row(module, f"{score:.1f}")

        console.print(table)


@app.command()
def list_projects():
    """列出所有项目"""
    from config import settings

    projects_dir = settings.projects_dir
    if not projects_dir.exists():
        console.print("[yellow]暂无项目[/yellow]")
        return

    table = Table(title="项目列表")
    table.add_column("ID")
    table.add_column("名称")
    table.add_column("状态")
    table.add_column("更新时间")

    for proj_dir in projects_dir.iterdir():
        if proj_dir.is_dir():
            project_file = proj_dir / "project.json"
            if project_file.exists():
                import json
                data = json.loads(project_file.read_text())
                table.add_row(
                    data.get("id", "-"),
                    data.get("name", "-"),
                    data.get("status", "-"),
                    data.get("updated_at", "-")[:19]
                )

    console.print(table)


@app.command()
def quick_test(
    ip_text: str = typer.Argument(..., help="IP原文（短文本测试）"),
    mock: bool = typer.Option(True, "--mock", "-m", help="模拟模式"),
):
    """快速测试：直接输入文本运行"""
    setup_logger()

    config = PipelineConfig(
        total_episodes=3,
        mock_mode=mock,
        skip_video_synthesis=True,
        skip_audio_editing=True
    )
    controller = PipelineController(config=config)

    async def _run():
        project = await controller.create_project(
            name="quick_test",
            ip_content=ip_text
        )
        result = await controller.run_full_pipeline(project)
        return project, result

    project, result = asyncio.run(_run())

    if result.success:
        console.print(f"\n[green]✓ 测试完成[/green]")
        console.print(f"  项目ID: {project.id}")
        console.print(f"  输出目录: {project.project_dir}")
    else:
        console.print(f"\n[red]✗ 测试失败[/red]")
        for err in result.errors:
            console.print(f"  - {err}")


def main():
    app()


if __name__ == "__main__":
    main()
