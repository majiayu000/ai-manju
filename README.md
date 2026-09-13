# AI漫剧生产流水线

一个模块化的AI漫剧生产系统，支持从IP输入到成片输出的全流程自动化。

## 功能特性

- **模块化设计**：每个环节独立可测，支持单独运行和质量评估
- **全流程自动化**：从IP原文到成片的一键生成
- **质量控制**：每个模块都有质量评估，支持自动重试
- **灵活配置**：支持多种AI服务商，可按需配置
- **Web界面**：提供可视化操作界面

## 系统架构

```
IP原文 → 剧本改编 → 分镜生成 → 角色设计 → 图像生成 → 视频合成 → 配音剪辑 → 成片
```

### 模块说明

| 模块 | 功能 | 状态 |
|------|------|------|
| Script Adapter | 将IP原文改编为结构化剧本 | ✅ 完成 |
| Storyboard Generator | 将剧本转换为分镜脚本 | ✅ 完成 |
| Character Designer | 为角色生成视觉设计 | ✅ 完成 |
| Image Generator | 根据分镜生成关键帧（可灵AI） | ✅ 完成（已接入流水线） |
| Video Synthesizer | 图生视频，片段拼接（可灵AI） | ✅ 完成（已接入流水线；默认 `skip_video_synthesis=True` 以控制成本） |
| Audio Editor | AI配音（Edge TTS），最终合成 | ✅ 完成（已接入流水线；默认 `skip_audio_editing=True` 以控制成本） |

## 快速开始

### 1. 安装依赖

```bash
cd AI-manhua
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入API密钥
```

### 3. 使用CLI

```bash
# 创建项目
python -m cli.main create "我的漫剧" --ip ./story.txt --episodes 10

# 运行流水线
python -m cli.main run proj_xxxxx --mock

# 查看状态
python -m cli.main status proj_xxxxx

# 运行单个模块
python -m cli.main module proj_xxxxx script

# 列出所有项目
python -m cli.main list-projects

# 快速测试
python -m cli.main quick-test "一个外卖员意外获得了给阴间送外卖的能力..."
```

### 4. 使用Web界面

```bash
# 启动服务
python -m web.app

# 访问 http://localhost:8000
# API文档 http://localhost:8000/docs
```

## API使用示例

### Python代码调用

```python
import asyncio
from src.pipeline.controller import PipelineController, PipelineConfig

async def main():
    # 配置
    config = PipelineConfig(
        total_episodes=10,
        art_style="anime",
        mock_mode=True  # 测试模式
    )

    # 创建控制器
    controller = PipelineController(config=config)

    # 创建项目
    project = await controller.create_project(
        name="测试漫剧",
        ip_content="你的IP原文内容..."
    )

    # 运行流水线
    result = await controller.run_full_pipeline(project)

    print(f"成功: {result.success}")
    print(f"完成阶段: {result.completed_stages}")

asyncio.run(main())
```

### 单模块调用

```python
from src.modules.script_adapter import ScriptAdapterModule, ScriptAdapterInput

async def adapt_script():
    module = ScriptAdapterModule()

    input_data = ScriptAdapterInput(
        project_id="test",
        ip_content="你的IP原文...",
        total_episodes=10
    )

    output = await module.run(input_data)

    if output.success:
        print(f"剧本已生成: {output.script_path}")
        print(f"质量评分: {output.quality.score}")
```

## 目录结构

```
AI-manhua/
├── config/              # 配置文件
│   ├── settings.py      # 全局配置
│   └── prompts/         # Prompt模板
├── src/
│   ├── pipeline/        # 流水线控制
│   ├── modules/         # 处理模块
│   │   ├── script_adapter/
│   │   ├── storyboard/
│   │   ├── character/
│   │   └── image_gen/
│   ├── ai/              # AI服务封装
│   ├── models/          # 数据模型
│   └── utils/           # 工具函数
├── web/                 # Web应用
├── cli/                 # 命令行工具
├── data/
│   ├── inputs/          # 输入文件
│   ├── projects/        # 项目数据
│   └── outputs/         # 输出成品
└── tests/               # 测试文件
```

## 配置说明

### 环境变量

```bash
# LLM服务
CLAUDE_API_KEY=xxx          # Claude API密钥
OPENAI_API_KEY=xxx          # OpenAI API密钥（可选）
DEEPSEEK_API_KEY=xxx        # DeepSeek API密钥（可选）

# 图像/视频生成
KLING_API_KEY=xxx           # 可灵AI密钥
KLING_API_SECRET=xxx        # 可灵AI密钥

# 配音服务
XUNFEI_APP_ID=xxx           # 讯飞配音
XUNFEI_API_KEY=xxx
```

### 流水线配置

```python
config = PipelineConfig(
    total_episodes=10,          # 总集数
    episode_duration=90,        # 每集时长(秒)
    art_style="anime",          # 艺术风格
    mock_mode=False,            # 模拟模式
    skip_video_synthesis=True,  # 跳过视频合成
    min_quality_score=70,       # 最低质量分数
    auto_retry=True,            # 自动重试
    max_retries=3               # 最大重试次数
)
```

## 质量评估

每个模块都有独立的质量评估系统：

| 模块 | 评估维度 |
|------|----------|
| 剧本改编 | 完整度、节奏、钩子有效性、角色鲜明度、对话质量 |
| 分镜生成 | 镜头多样性、时长合理性、描述完整度、Prompt质量 |
| 角色设计 | 描述完整度、特征区分度、Prompt质量、一致性信息 |
| 图像生成 | 成功率、图像完整性、质量评分 |

## 开发指南

### 添加新模块

1. 继承 `BaseModule` 基类
2. 实现 `process`、`validate_input`、`evaluate_quality` 方法
3. 在 `PipelineController` 中注册模块

```python
from src.modules.base import BaseModule, ModuleInput, ModuleOutput

class MyModule(BaseModule[MyInput, MyOutput]):
    name = "my_module"
    version = "1.0.0"

    async def process(self, input_data: MyInput) -> MyOutput:
        # 实现处理逻辑
        pass

    async def validate_input(self, input_data: MyInput) -> tuple[bool, str]:
        # 输入验证
        pass

    async def evaluate_quality(self, output: MyOutput) -> QualityMetrics:
        # 质量评估
        pass
```

### 运行测试

```bash
# 运行所有模拟测试（不消耗API额度）
pytest tests/ -v -m "not real_api"

# 运行真实API测试（会消耗API额度）
pytest tests/ -v -m "real_api"

# 使用测试运行脚本
python scripts/run_tests.py --mode mock    # 模拟模式
python scripts/run_tests.py --mode real    # 真实API
python scripts/run_tests.py --module llm   # 只测试LLM模块
python scripts/run_tests.py --module kling # 只测试可灵API
python scripts/run_tests.py --module e2e   # 端到端测试
```

## 许可证

MIT License
