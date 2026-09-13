# AI漫剧生产流水线 - 架构设计文档

## 项目概述

一个模块化的AI漫剧生产系统，支持从IP输入到成片输出的全流程自动化，每个模块独立可测试。

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Web Dashboard                                  │
│                    (项目管理 / 进度追踪 / 预览)                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Pipeline Controller                              │
│                    (流程编排 / 状态管理 / 任务队列)                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│   Module 1    │           │   Module 2    │           │   Module 3    │
│   剧本改编     │ ────────▶ │   分镜生成     │ ────────▶ │   角色设计    │
└───────────────┘           └───────────────┘           └───────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│   Module 4    │           │   Module 5    │           │   Module 6    │
│   图像生成     │ ────────▶ │   视频合成     │ ────────▶ │   配音剪辑    │
└───────────────┘           └───────────────┘           └───────────────┘
                                                                │
                                                                ▼
                                                        ┌───────────────┐
                                                        │    Output     │
                                                        │   成品输出     │
                                                        └───────────────┘
```

---

## 模块设计

### Module 1: 剧本改编 (Script Adapter)

**输入**: 原始IP文本（小说/故事）
**输出**: 结构化剧本JSON

```json
{
  "title": "剧名",
  "episodes": [
    {
      "episode_id": 1,
      "title": "第一集标题",
      "duration": "60-90s",
      "scenes": [
        {
          "scene_id": 1,
          "description": "场景描述",
          "characters": ["角色A", "角色B"],
          "dialogues": [
            {"character": "角色A", "text": "台词", "emotion": "愤怒"}
          ],
          "camera": "中景",
          "hook": "本场钩子"
        }
      ],
      "end_hook": "集末悬念"
    }
  ]
}
```

**功能**:
- IP文本解析
- 剧情提取与压缩
- 分集规划
- 爽点/钩子设计
- 质量评分

---

### Module 2: 分镜生成 (Storyboard Generator)

**输入**: 结构化剧本JSON
**输出**: 分镜脚本JSON

```json
{
  "episode_id": 1,
  "shots": [
    {
      "shot_id": 1,
      "scene_id": 1,
      "type": "establishing",  // establishing/medium/close-up/pov
      "duration": 3,
      "description": "画面描述",
      "camera_movement": "推进",
      "characters": ["角色A"],
      "character_actions": "角色动作描述",
      "dialogue": "台词内容",
      "emotion": "情绪",
      "prompt_hint": "图像生成提示词建议"
    }
  ]
}
```

**功能**:
- 场景到镜头拆分
- 镜头类型规划
- 时长分配
- Prompt预生成

---

### Module 3: 角色设计 (Character Designer)

**输入**: 剧本中的角色信息
**输出**: 角色设计卡

```json
{
  "characters": [
    {
      "name": "角色名",
      "role": "protagonist/antagonist/supporting",
      "description": "角色描述",
      "appearance": {
        "gender": "male",
        "age": "25",
        "hair": "黑色短发",
        "clothing": "现代休闲装",
        "features": "特征描述"
      },
      "base_prompt": "基础Prompt",
      "reference_images": ["path/to/ref1.png"],
      "consistency_seed": 12345,
      "lora_model": "path/to/lora" // 可选
    }
  ]
}
```

**功能**:
- 角色信息提取
- 外观设计生成
- 参考图生成
- 一致性参数管理

---

### Module 4: 图像生成 (Image Generator)

**输入**: 分镜脚本 + 角色设计
**输出**: 关键帧图像

```
output/
├── episode_01/
│   ├── shot_001.png
│   ├── shot_001_metadata.json
│   ├── shot_002.png
│   └── ...
```

**功能**:
- Prompt组装
- 批量图像生成（调用MJ/SD API）
- 角色一致性控制
- 质量检测与重试
- 图像后处理

---

### Module 5: 视频合成 (Video Synthesizer)

**输入**: 关键帧图像 + 分镜脚本
**输出**: 视频片段

```
output/
├── episode_01/
│   ├── shot_001.mp4
│   ├── shot_002.mp4
│   └── episode_01_raw.mp4  // 拼接版
```

**功能**:
- 图生视频（调用可灵AI API）
- 镜头运动添加
- 转场效果
- 片段拼接

---

### Module 6: 配音剪辑 (Audio & Editing)

**输入**: 视频片段 + 剧本台词
**输出**: 最终成片

```
output/
├── episode_01/
│   ├── audio/
│   │   ├── dialogue_001.mp3
│   │   └── bgm.mp3
│   ├── episode_01_final.mp4
│   └── episode_01_subtitles.srt
```

**功能**:
- AI配音生成
- 音效/BGM添加
- 字幕生成
- 最终剪辑合成

---

## 目录结构

```
AI-manhua/
├── README.md
├── ARCHITECTURE.md
├── requirements.txt
├── .env.example
│
├── config/
│   ├── __init__.py
│   ├── settings.py          # 全局配置
│   └── prompts/              # Prompt模板
│       ├── script_adapter.txt
│       ├── storyboard.txt
│       └── character.txt
│
├── src/
│   ├── __init__.py
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── controller.py     # 流程控制器
│   │   ├── task_queue.py     # 任务队列
│   │   └── state_manager.py  # 状态管理
│   │
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── base.py           # 模块基类
│   │   ├── script_adapter/   # Module 1
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py
│   │   │   ├── parser.py
│   │   │   └── quality.py
│   │   ├── storyboard/       # Module 2
│   │   │   ├── __init__.py
│   │   │   ├── generator.py
│   │   │   └── shot_planner.py
│   │   ├── character/        # Module 3
│   │   │   ├── __init__.py
│   │   │   ├── designer.py
│   │   │   └── consistency.py
│   │   ├── image_gen/        # Module 4
│   │   │   ├── __init__.py
│   │   │   ├── generator.py
│   │   │   ├── prompt_builder.py
│   │   │   └── providers/
│   │   │       ├── midjourney.py
│   │   │       ├── stable_diffusion.py
│   │   │       └── kling.py
│   │   ├── video_synth/      # Module 5
│   │   │   ├── __init__.py
│   │   │   ├── synthesizer.py
│   │   │   └── providers/
│   │   │       └── kling.py
│   │   └── audio_edit/       # Module 6
│   │       ├── __init__.py
│   │       ├── tts.py
│   │       ├── editor.py
│   │       └── subtitle.py
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── llm.py            # LLM调用封装
│   │   └── providers/
│   │       ├── claude.py
│   │       ├── openai.py
│   │       └── deepseek.py
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── file_handler.py
│   │   ├── image_utils.py
│   │   ├── video_utils.py
│   │   └── logger.py
│   │
│   └── models/
│       ├── __init__.py
│       ├── project.py        # 项目模型
│       ├── script.py         # 剧本模型
│       ├── character.py      # 角色模型
│       └── shot.py           # 镜头模型
│
├── web/
│   ├── __init__.py
│   ├── app.py                # FastAPI应用
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── projects.py
│   │   ├── pipeline.py
│   │   └── preview.py
│   ├── static/
│   │   ├── css/
│   │   └── js/
│   └── templates/
│       ├── index.html
│       ├── project.html
│       └── preview.html
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_script_adapter.py
│   ├── test_storyboard.py
│   ├── test_character.py
│   ├── test_image_gen.py
│   ├── test_video_synth.py
│   └── test_audio_edit.py
│
├── cli/
│   ├── __init__.py
│   └── main.py               # CLI入口
│
├── data/
│   ├── inputs/               # IP原文输入
│   ├── projects/             # 项目数据
│   └── outputs/              # 输出成品
│
└── scripts/
    ├── setup.sh
    └── run_pipeline.py
```

---

## 数据流设计

```
[IP原文.txt]
     │
     ▼
┌─────────────────────────────────────────┐
│  Module 1: Script Adapter               │
│  ┌─────────────────────────────────┐    │
│  │ 1. 解析原文                      │    │
│  │ 2. 提取核心剧情                  │    │
│  │ 3. 分集规划（60-100集）          │    │
│  │ 4. 每集分场景                    │    │
│  │ 5. 添加钩子/爽点                 │    │
│  │ 6. 质量评分                      │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
     │
     ▼
[script.json] ─────────────────────────────┐
     │                                     │
     ▼                                     │
┌─────────────────────────────────────────┐│
│  Module 2: Storyboard Generator         ││
│  ┌─────────────────────────────────┐    ││
│  │ 1. 场景→镜头拆分                 │    ││
│  │ 2. 镜头类型规划                  │    ││
│  │ 3. 时长分配                      │    ││
│  │ 4. Prompt预生成                  │    ││
│  └─────────────────────────────────┘    ││
└─────────────────────────────────────────┘│
     │                                     │
     ▼                                     │
[storyboard.json]                          │
     │                                     │
     │    ┌────────────────────────────────┘
     │    │
     │    ▼
     │  ┌─────────────────────────────────────────┐
     │  │  Module 3: Character Designer           │
     │  │  ┌─────────────────────────────────┐    │
     │  │  │ 1. 提取角色信息                  │    │
     │  │  │ 2. 生成角色设计                  │    │
     │  │  │ 3. 生成参考图                    │    │
     │  │  │ 4. 设置一致性参数                │    │
     │  │  └─────────────────────────────────┘    │
     │  └─────────────────────────────────────────┘
     │         │
     │         ▼
     │  [characters.json + reference_images/]
     │         │
     ▼         ▼
┌─────────────────────────────────────────┐
│  Module 4: Image Generator              │
│  ┌─────────────────────────────────┐    │
│  │ 1. 组装完整Prompt                │    │
│  │ 2. 调用图像生成API               │    │
│  │ 3. 角色一致性检查                │    │
│  │ 4. 质量评分                      │    │
│  │ 5. 不合格重试                    │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
     │
     ▼
[images/shot_*.png]
     │
     ▼
┌─────────────────────────────────────────┐
│  Module 5: Video Synthesizer            │
│  ┌─────────────────────────────────┐    │
│  │ 1. 图生视频（可灵AI）            │    │
│  │ 2. 添加镜头运动                  │    │
│  │ 3. 转场效果                      │    │
│  │ 4. 片段拼接                      │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
     │
     ▼
[videos/shot_*.mp4]
     │
     ▼
┌─────────────────────────────────────────┐
│  Module 6: Audio & Editing              │
│  ┌─────────────────────────────────┐    │
│  │ 1. AI配音生成                    │    │
│  │ 2. 音效/BGM                      │    │
│  │ 3. 字幕生成                      │    │
│  │ 4. 最终合成                      │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
     │
     ▼
[episode_01_final.mp4]
```

---

## 模块接口规范

### 基类定义

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel

class ModuleInput(BaseModel):
    """模块输入基类"""
    pass

class ModuleOutput(BaseModel):
    """模块输出基类"""
    success: bool
    error: Optional[str] = None
    data: Any = None

class QualityMetrics(BaseModel):
    """质量指标"""
    score: float  # 0-100
    details: Dict[str, float]
    suggestions: list[str]

class BaseModule(ABC):
    """模块基类"""

    name: str
    version: str

    @abstractmethod
    async def process(self, input: ModuleInput) -> ModuleOutput:
        """处理输入，返回输出"""
        pass

    @abstractmethod
    async def validate_input(self, input: ModuleInput) -> bool:
        """验证输入"""
        pass

    @abstractmethod
    async def evaluate_quality(self, output: ModuleOutput) -> QualityMetrics:
        """评估输出质量"""
        pass

    async def retry_on_failure(self, input: ModuleInput, max_retries: int = 3) -> ModuleOutput:
        """失败重试机制"""
        pass
```

---

## 质量评估系统

每个模块都有独立的质量评估：

### Module 1 - 剧本质量
- 剧情完整度（0-100）
- 节奏紧凑度（0-100）
- 钩子有效性（0-100）
- 角色鲜明度（0-100）

### Module 2 - 分镜质量
- 镜头多样性（0-100）
- 时长合理性（0-100）
- 叙事流畅度（0-100）

### Module 3 - 角色设计质量
- 描述完整度（0-100）
- 特征区分度（0-100）
- Prompt可用性（0-100）

### Module 4 - 图像质量
- 画面质量（0-100）
- 角色一致性（0-100）
- 场景匹配度（0-100）

### Module 5 - 视频质量
- 动作流畅度（0-100）
- 转场自然度（0-100）
- 时长准确度（0-100）

### Module 6 - 成片质量
- 音画同步（0-100）
- 配音质量（0-100）
- 整体观感（0-100）

---

## API设计

### RESTful API

```
# 项目管理
POST   /api/projects                    # 创建项目
GET    /api/projects                    # 列出项目
GET    /api/projects/{id}               # 获取项目详情
DELETE /api/projects/{id}               # 删除项目

# 流水线控制
POST   /api/projects/{id}/pipeline/start           # 启动流水线
POST   /api/projects/{id}/pipeline/pause           # 暂停
POST   /api/projects/{id}/pipeline/resume          # 恢复
GET    /api/projects/{id}/pipeline/status          # 获取状态

# 模块单独运行
POST   /api/projects/{id}/modules/{module}/run     # 运行单个模块
GET    /api/projects/{id}/modules/{module}/output  # 获取模块输出
POST   /api/projects/{id}/modules/{module}/retry   # 重试模块

# 质量检查
GET    /api/projects/{id}/modules/{module}/quality # 获取质量评分
POST   /api/projects/{id}/modules/{module}/review  # 人工审核

# 预览
GET    /api/projects/{id}/preview/script           # 预览剧本
GET    /api/projects/{id}/preview/storyboard       # 预览分镜
GET    /api/projects/{id}/preview/images           # 预览图像
GET    /api/projects/{id}/preview/video            # 预览视频
```

---

## 配置文件示例

### .env

```bash
# LLM API
CLAUDE_API_KEY=your_claude_api_key
OPENAI_API_KEY=your_openai_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key

# 图像生成
MIDJOURNEY_API_KEY=your_mj_api_key
KLING_API_KEY=your_kling_api_key

# 配音
TTS_API_KEY=your_tts_api_key

# 数据库
DATABASE_URL=sqlite:///./data/db.sqlite

# 服务配置
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

### config/settings.py

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # LLM配置
    default_llm: str = "claude"
    llm_temperature: float = 0.7

    # 图像生成配置
    default_image_provider: str = "midjourney"
    image_quality: str = "high"
    image_style: str = "anime"

    # 视频生成配置
    default_video_provider: str = "kling"
    video_fps: int = 24

    # 质量阈值
    min_quality_score: float = 70.0
    auto_retry_on_low_quality: bool = True
    max_retries: int = 3

    # 输出配置
    episodes_per_batch: int = 5
    shots_per_episode: int = 30

    class Config:
        env_file = ".env"
```

---

## 技术选型

| 组件 | 技术选择 | 说明 |
|------|----------|------|
| 后端框架 | FastAPI | 异步支持好，API文档自动生成 |
| 任务队列 | Celery + Redis | 异步任务处理 |
| 数据库 | SQLite/PostgreSQL | 项目数据存储 |
| 前端 | Vue3 + TailwindCSS | 现代化UI |
| LLM调用 | Claude API | 剧本生成 |
| 图像生成 | 可灵AI API | 图像+视频 |
| 配音 | 讯飞/11Labs API | TTS |
| 视频处理 | FFmpeg | 剪辑合成 |

---

## 开发计划

### Phase 1: 基础架构（Week 1）
- [x] 项目结构搭建
- [ ] 配置系统
- [ ] 模块基类
- [ ] 数据模型
- [ ] 基础API

### Phase 2: 核心模块（Week 2-3）
- [ ] Module 1: 剧本改编
- [ ] Module 2: 分镜生成
- [ ] Module 3: 角色设计

### Phase 3: 生成模块（Week 4-5）
- [x] Module 4: 图像生成（已接入 `PipelineController`）
- [x] Module 5: 视频合成（已接入 `PipelineController`；默认跳过以控制 API 成本）
- [x] Module 6: 配音剪辑（已接入 `PipelineController`；默认跳过以控制 API 成本）

### Phase 4: Web界面（Week 6）
- [ ] 项目管理页面
- [ ] 流水线控制
- [ ] 预览功能

### Phase 5: 优化完善（Week 7-8）
- [ ] 质量评估系统
- [ ] 批量处理
- [ ] 性能优化
- [ ] 文档完善
