"""
剧本改编模块 - 将IP原文转换为结构化剧本
"""
from pathlib import Path
from typing import Optional
from pydantic import Field

from src.modules.base import BaseModule, ModuleInput, ModuleOutput, QualityMetrics
from src.models.script import Script, Episode, Scene, Dialogue, MainCharacter
from src.ai.llm import get_llm_client
from src.utils.file_handler import FileHandler
from config import settings


class ScriptAdapterInput(ModuleInput):
    """剧本改编输入"""
    ip_content: Optional[str] = Field(default=None, description="IP原文内容")
    ip_content_path: Optional[str] = Field(default=None, description="IP原文文件路径")
    total_episodes: int = Field(default=10, description="目标集数")
    episode_duration: int = Field(default=90, description="每集时长(秒)")
    genre: Optional[str] = Field(default=None, description="题材类型")
    special_requirements: str = Field(default="", description="特殊要求")


class ScriptAdapterOutput(ModuleOutput):
    """剧本改编输出"""
    script: Optional[Script] = Field(default=None, description="生成的剧本")
    script_path: Optional[str] = Field(default=None, description="剧本保存路径")


class ScriptAdapterModule(BaseModule[ScriptAdapterInput, ScriptAdapterOutput]):
    """
    剧本改编模块

    将IP原文（小说、故事等）转换为结构化的短剧剧本
    """

    name = "script_adapter"
    version = "1.0.0"
    description = "将IP原文改编为结构化短剧剧本"

    def __init__(self, llm_provider: Optional[str] = None):
        super().__init__()
        self.llm = get_llm_client(provider=llm_provider)
        self.file_handler = FileHandler()
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """加载Prompt模板"""
        template_path = settings.base_dir / "config" / "prompts" / "script_adapter.txt"
        if template_path.exists():
            return self.file_handler.read_text_sync(template_path)
        return self._get_default_prompt_template()

    def _get_default_prompt_template(self) -> str:
        """默认Prompt模板"""
        return """你是一位专业的短剧编剧，请将以下IP原文改编为结构化的短剧剧本。

要求：
1. 总集数：{total_episodes}集
2. 每集时长：{episode_duration}秒
3. 每集3-5个场景
4. 每集结尾设置悬念钩子
5. 对话简洁有力

请以JSON格式输出完整剧本。

IP原文：
{ip_content}

{special_requirements}"""

    async def validate_input(self, input_data: ScriptAdapterInput) -> tuple[bool, Optional[str]]:
        """验证输入"""
        # 检查IP内容
        if not input_data.ip_content and not input_data.ip_content_path:
            return False, "必须提供ip_content或ip_content_path"

        if input_data.ip_content_path:
            path = Path(input_data.ip_content_path)
            if not path.exists():
                return False, f"IP文件不存在: {input_data.ip_content_path}"

        # 检查集数
        if input_data.total_episodes < 1 or input_data.total_episodes > 200:
            return False, "集数必须在1-200之间"

        return True, None

    async def process(self, input_data: ScriptAdapterInput) -> ScriptAdapterOutput:
        """执行剧本改编"""
        self.logger.info(f"开始剧本改编: project={input_data.project_id}")

        try:
            # 获取IP内容
            ip_content = input_data.ip_content
            if not ip_content and input_data.ip_content_path:
                ip_content = await self.file_handler.read_text(input_data.ip_content_path)

            # 如果内容太长，进行分段处理
            if len(ip_content) > 50000:
                ip_content = await self._summarize_long_content(ip_content)

            # 构建Prompt
            prompt = self.prompt_template.format(
                total_episodes=input_data.total_episodes,
                episode_duration=input_data.episode_duration,
                ip_content=ip_content,
                special_requirements=input_data.special_requirements or "无"
            )

            # 调用LLM生成剧本
            self.logger.info("调用LLM生成剧本...")
            response = await self.llm.chat_json(
                prompt=prompt,
                system="你是专业的短剧编剧，擅长将小说改编为紧凑的短剧剧本。请严格按照JSON格式输出。",
                temperature=0.7,
                max_tokens=8192
            )

            # 解析响应
            script = self._parse_script_response(response, input_data)

            # 保存剧本
            script_path = await self._save_script(input_data.project_id, script)

            self.logger.info(f"剧本改编完成: {len(script.episodes)}集")

            return ScriptAdapterOutput(
                success=True,
                data={"episodes_count": len(script.episodes)},
                script=script,
                script_path=str(script_path)
            )

        except Exception as e:
            self.logger.exception(f"剧本改编失败: {e}")
            return ScriptAdapterOutput(
                success=False,
                error=str(e)
            )

    async def _summarize_long_content(self, content: str) -> str:
        """对超长内容进行摘要"""
        self.logger.info(f"内容过长({len(content)}字)，进行摘要处理")

        # 分段
        chunk_size = 30000
        chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]

        summaries = []
        for i, chunk in enumerate(chunks):
            self.logger.info(f"处理分段 {i+1}/{len(chunks)}")
            summary = await self.llm.chat(
                prompt=f"请简要总结以下内容的核心剧情，保留关键人物和事件：\n\n{chunk}",
                max_tokens=2000
            )
            summaries.append(summary)

        return "\n\n---\n\n".join(summaries)

    def _parse_script_response(self, response: dict, input_data: ScriptAdapterInput) -> Script:
        """解析LLM响应为Script对象"""
        # 解析主要角色
        main_characters = []
        for char_data in response.get("main_characters", []):
            main_characters.append(MainCharacter(
                name=char_data.get("name", "未知"),
                role=char_data.get("role", "supporting"),
                description=char_data.get("description", ""),
                appearance=char_data.get("appearance", ""),
                personality=char_data.get("personality", ""),
                background=char_data.get("background")
            ))

        # 解析剧集
        episodes = []
        for ep_data in response.get("episodes", []):
            scenes = []
            for sc_data in ep_data.get("scenes", []):
                dialogues = []
                for dlg_data in sc_data.get("dialogues", []):
                    dialogues.append(Dialogue(
                        character=dlg_data.get("character", ""),
                        text=dlg_data.get("text", ""),
                        emotion=dlg_data.get("emotion", "neutral"),
                        action=dlg_data.get("action")
                    ))

                scenes.append(Scene(
                    scene_id=sc_data.get("scene_id", len(scenes) + 1),
                    location=sc_data.get("location", "未知"),
                    time=sc_data.get("time", "day"),
                    description=sc_data.get("description", ""),
                    characters=sc_data.get("characters", []),
                    dialogues=dialogues,
                    narration=sc_data.get("narration"),
                    mood=sc_data.get("mood", "neutral")
                ))

            episodes.append(Episode(
                episode_id=ep_data.get("episode_id", len(episodes) + 1),
                title=ep_data.get("title", f"第{len(episodes)+1}集"),
                synopsis=ep_data.get("synopsis", ""),
                duration_estimate=ep_data.get("duration_estimate", "60-90s"),
                scenes=scenes,
                end_hook=ep_data.get("end_hook", ""),
                highlight_moments=ep_data.get("highlight_moments", [])
            ))

        return Script(
            title=response.get("title", "未命名剧本"),
            genre=response.get("genre", input_data.genre or "unknown"),
            total_episodes=len(episodes),
            synopsis=response.get("synopsis", ""),
            main_characters=main_characters,
            episodes=episodes,
            themes=response.get("themes", []),
            target_audience=response.get("target_audience", "general")
        )

    async def _save_script(self, project_id: str, script: Script) -> Path:
        """保存剧本到文件"""
        self.file_handler.ensure_project_structure(project_id)
        script_path = self.file_handler.get_script_path(project_id)
        await self.file_handler.write_json(script_path, script.model_dump())
        return script_path

    async def evaluate_quality(self, output: ScriptAdapterOutput) -> QualityMetrics:
        """评估剧本质量"""
        if not output.success or not output.script:
            return QualityMetrics(
                score=0,
                details={},
                suggestions=["剧本生成失败"],
                passed=False
            )

        script = output.script
        details = {}

        # 1. 完整度评估
        completeness = self._evaluate_completeness(script)
        details["completeness"] = completeness

        # 2. 节奏评估
        pacing = self._evaluate_pacing(script)
        details["pacing"] = pacing

        # 3. 钩子有效性
        hooks = self._evaluate_hooks(script)
        details["hooks"] = hooks

        # 4. 角色鲜明度
        characters = self._evaluate_characters(script)
        details["characters"] = characters

        # 5. 对话质量
        dialogue = self._evaluate_dialogue(script)
        details["dialogue"] = dialogue

        return QualityMetrics.from_details(details)

    def _evaluate_completeness(self, script: Script) -> float:
        """评估完整度"""
        score = 100.0

        # 检查基本信息
        if not script.title:
            score -= 10
        if not script.synopsis:
            score -= 10
        if not script.main_characters:
            score -= 20

        # 检查剧集
        if not script.episodes:
            return 0

        for episode in script.episodes:
            if not episode.scenes:
                score -= 5
            if not episode.end_hook:
                score -= 2

        return max(0, score)

    def _evaluate_pacing(self, script: Script) -> float:
        """评估节奏"""
        if not script.episodes:
            return 0

        score = 100.0

        for episode in script.episodes:
            scene_count = len(episode.scenes)
            if scene_count < 2:
                score -= 5
            elif scene_count > 6:
                score -= 3

        return max(0, score)

    def _evaluate_hooks(self, script: Script) -> float:
        """评估钩子有效性"""
        if not script.episodes:
            return 0

        hooks_with_content = sum(
            1 for ep in script.episodes
            if ep.end_hook and len(ep.end_hook) > 10
        )
        return (hooks_with_content / len(script.episodes)) * 100

    def _evaluate_characters(self, script: Script) -> float:
        """评估角色鲜明度"""
        if not script.main_characters:
            return 0

        score = 0
        for char in script.main_characters:
            char_score = 0
            if char.name:
                char_score += 20
            if char.description and len(char.description) > 20:
                char_score += 30
            if char.appearance and len(char.appearance) > 10:
                char_score += 25
            if char.personality:
                char_score += 25
            score += char_score

        return score / len(script.main_characters)

    def _evaluate_dialogue(self, script: Script) -> float:
        """评估对话质量"""
        total_dialogues = 0
        good_dialogues = 0

        for episode in script.episodes:
            for scene in episode.scenes:
                for dialogue in scene.dialogues:
                    total_dialogues += 1
                    # 好的对话：简洁（<30字）且有情绪
                    if len(dialogue.text) <= 30 and dialogue.emotion != "neutral":
                        good_dialogues += 1
                    elif len(dialogue.text) <= 20:
                        good_dialogues += 0.5

        if total_dialogues == 0:
            return 50  # 没有对话给中等分

        return (good_dialogues / total_dialogues) * 100


# 便捷函数
async def adapt_script(
    project_id: str,
    ip_content: str = None,
    ip_content_path: str = None,
    total_episodes: int = 10,
    **kwargs
) -> ScriptAdapterOutput:
    """
    便捷函数：执行剧本改编

    Args:
        project_id: 项目ID
        ip_content: IP原文
        ip_content_path: IP文件路径
        total_episodes: 目标集数

    Returns:
        改编结果
    """
    module = ScriptAdapterModule()
    input_data = ScriptAdapterInput(
        project_id=project_id,
        ip_content=ip_content,
        ip_content_path=ip_content_path,
        total_episodes=total_episodes,
        **kwargs
    )
    return await module.run(input_data)
