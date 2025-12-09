"""
Web API应用
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from src.pipeline.controller import PipelineController, PipelineConfig, PipelineStage, PipelineResult
from src.models.project import Project
from src.utils.logger import setup_logger
from config import settings


# 全局控制器和任务存储
controller: PipelineController = None
running_tasks: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global controller
    setup_logger()
    controller = PipelineController()
    yield


app = FastAPI(
    title="AI漫剧生产流水线",
    description="模块化的AI漫剧生产系统API",
    version="0.1.0",
    lifespan=lifespan
)

# 静态文件和模板
templates_path = Path(__file__).parent / "templates"
static_path = Path(__file__).parent / "static"

if templates_path.exists():
    templates = Jinja2Templates(directory=str(templates_path))
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


# ==================== 数据模型 ====================

class CreateProjectRequest(BaseModel):
    name: str
    ip_content: Optional[str] = None
    ip_content_path: Optional[str] = None
    description: str = ""
    total_episodes: int = 10
    art_style: str = "anime"


class RunPipelineRequest(BaseModel):
    mock_mode: bool = False
    skip_images: bool = False
    skip_video: bool = True
    skip_audio: bool = True
    start_from: Optional[str] = None


class RunModuleRequest(BaseModel):
    stage: str
    mock_mode: bool = False


# ==================== 项目管理API ====================

@app.post("/api/projects", response_model=dict)
async def create_project(request: CreateProjectRequest):
    """创建新项目"""
    config = PipelineConfig(
        total_episodes=request.total_episodes,
        art_style=request.art_style
    )
    ctrl = PipelineController(config=config)

    project = await ctrl.create_project(
        name=request.name,
        ip_content=request.ip_content,
        ip_content_path=request.ip_content_path,
        description=request.description
    )

    return {
        "success": True,
        "project_id": project.id,
        "project_dir": project.project_dir
    }


@app.get("/api/projects", response_model=list)
async def list_projects():
    """列出所有项目"""
    projects_dir = settings.projects_dir
    if not projects_dir.exists():
        return []

    projects = []
    for proj_dir in projects_dir.iterdir():
        if proj_dir.is_dir():
            project_file = proj_dir / "project.json"
            if project_file.exists():
                try:
                    project = await controller.load_project(proj_dir.name)
                    projects.append({
                        "id": project.id,
                        "name": project.name,
                        "status": project.status.value,
                        "progress": project.progress,
                        "updated_at": project.updated_at.isoformat()
                    })
                except Exception:
                    pass

    return projects


@app.get("/api/projects/{project_id}", response_model=dict)
async def get_project(project_id: str):
    """获取项目详情"""
    try:
        project = await controller.load_project(project_id)
        return project.model_dump()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    """删除项目"""
    import shutil
    project_dir = settings.projects_dir / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")

    shutil.rmtree(project_dir)
    return {"success": True}


# ==================== 流水线API ====================

@app.post("/api/projects/{project_id}/pipeline/start")
async def start_pipeline(
    project_id: str,
    request: RunPipelineRequest,
    background_tasks: BackgroundTasks
):
    """启动流水线"""
    try:
        project = await controller.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 检查是否已在运行
    if project_id in running_tasks:
        raise HTTPException(status_code=400, detail="项目正在运行中")

    # 配置
    config = PipelineConfig(
        mock_mode=request.mock_mode,
        skip_image_generation=request.skip_images,
        skip_video_synthesis=request.skip_video,
        skip_audio_editing=request.skip_audio
    )

    ctrl = PipelineController(config=config)

    # 记录任务
    running_tasks[project_id] = {
        "status": "running",
        "started_at": None,
        "result": None
    }

    # 后台运行
    async def run_task():
        from datetime import datetime
        running_tasks[project_id]["started_at"] = datetime.now()
        try:
            start_from = PipelineStage(request.start_from) if request.start_from else None
            result = await ctrl.run_full_pipeline(project, start_from=start_from)
            running_tasks[project_id]["status"] = "completed" if result.success else "failed"
            running_tasks[project_id]["result"] = result.model_dump()
        except Exception as e:
            running_tasks[project_id]["status"] = "error"
            running_tasks[project_id]["error"] = str(e)

    background_tasks.add_task(run_task)

    return {"success": True, "message": "流水线已启动"}


@app.get("/api/projects/{project_id}/pipeline/status")
async def get_pipeline_status(project_id: str):
    """获取流水线状态"""
    if project_id not in running_tasks:
        try:
            project = await controller.load_project(project_id)
            return {
                "status": "idle",
                "project_status": project.status.value,
                "progress": project.progress
            }
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="项目不存在")

    return running_tasks[project_id]


# ==================== 模块API ====================

@app.post("/api/projects/{project_id}/modules/{module}/run")
async def run_module(project_id: str, module: str, request: RunModuleRequest):
    """运行单个模块"""
    stage_map = {
        "script": PipelineStage.SCRIPT_ADAPT,
        "storyboard": PipelineStage.STORYBOARD,
        "character": PipelineStage.CHARACTER_DESIGN,
        "image": PipelineStage.IMAGE_GENERATION,
        "video": PipelineStage.VIDEO_SYNTHESIS,
        "audio": PipelineStage.AUDIO_EDITING,
    }

    if module not in stage_map:
        raise HTTPException(status_code=400, detail=f"未知模块: {module}")

    try:
        project = await controller.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")

    config = PipelineConfig(mock_mode=request.mock_mode)
    ctrl = PipelineController(config=config)

    result = await ctrl.run_single_module(project, stage_map[module])
    return result


@app.get("/api/projects/{project_id}/modules/{module}/output")
async def get_module_output(project_id: str, module: str):
    """获取模块输出"""
    try:
        project = await controller.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")

    module_state = project.module_states.get(module)
    quality_score = project.quality_scores.get(module)

    return {
        "module": module,
        "state": module_state,
        "quality": quality_score
    }


# ==================== 预览API ====================

@app.get("/api/projects/{project_id}/preview/script")
async def preview_script(project_id: str):
    """预览剧本"""
    try:
        project = await controller.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")

    script_state = project.module_states.get("script_adapter", {})
    script_path = script_state.get("script_path")

    if not script_path or not Path(script_path).exists():
        raise HTTPException(status_code=404, detail="剧本文件不存在")

    from src.utils.file_handler import FileHandler
    fh = FileHandler()
    script_data = await fh.read_json(script_path)

    return script_data


@app.get("/api/projects/{project_id}/preview/images")
async def preview_images(project_id: str, episode: int = 1):
    """预览图像"""
    project_dir = settings.projects_dir / project_id / "images"
    if not project_dir.exists():
        return {"images": []}

    images = []
    for img_file in sorted(project_dir.glob(f"ep{episode:02d}_*.png")):
        images.append({
            "name": img_file.name,
            "path": f"/api/projects/{project_id}/files/images/{img_file.name}"
        })

    return {"images": images}


# ==================== 文件服务 ====================

@app.get("/api/projects/{project_id}/files/{category}/{filename}")
async def get_file(project_id: str, category: str, filename: str):
    """获取项目文件"""
    from fastapi.responses import FileResponse

    file_path = settings.projects_dir / project_id / category / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(file_path)


# ==================== 页面路由 ====================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页"""
    if not templates_path.exists():
        return HTMLResponse(content="""
        <html>
        <head><title>AI漫剧生产流水线</title></head>
        <body>
        <h1>AI漫剧生产流水线</h1>
        <p>API文档: <a href="/docs">/docs</a></p>
        </body>
        </html>
        """)
    return templates.TemplateResponse("index.html", {"request": request})


# ==================== 启动 ====================

def start_server(host: str = "0.0.0.0", port: int = 8000):
    """启动服务器"""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
