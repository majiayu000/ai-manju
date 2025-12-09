"""
模块基类定义
"""
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from loguru import logger


# 泛型类型
InputT = TypeVar("InputT", bound="ModuleInput")
OutputT = TypeVar("OutputT", bound="ModuleOutput")


class ModuleInput(BaseModel):
    """模块输入基类"""
    project_id: str = Field(..., description="项目ID")

    class Config:
        extra = "allow"


class QualityMetrics(BaseModel):
    """质量指标"""
    score: float = Field(..., ge=0, le=100, description="总分(0-100)")
    details: dict[str, float] = Field(default_factory=dict, description="分项得分")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")
    passed: bool = Field(default=True, description="是否通过质量检查")

    @classmethod
    def from_details(cls, details: dict[str, float], threshold: float = 70.0) -> "QualityMetrics":
        """从分项得分计算总分"""
        if not details:
            return cls(score=0, details={}, suggestions=["无评估数据"], passed=False)

        score = sum(details.values()) / len(details)
        suggestions = []

        for key, value in details.items():
            if value < threshold:
                suggestions.append(f"{key} 得分较低({value:.1f})，建议优化")

        return cls(
            score=score,
            details=details,
            suggestions=suggestions,
            passed=score >= threshold
        )


class ModuleOutput(BaseModel):
    """模块输出基类"""
    success: bool = Field(default=True, description="是否成功")
    error: Optional[str] = Field(default=None, description="错误信息")
    data: Any = Field(default=None, description="输出数据")
    quality: Optional[QualityMetrics] = Field(default=None, description="质量评估")

    # 执行信息
    started_at: Optional[datetime] = Field(default=None, description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    duration_seconds: Optional[float] = Field(default=None, description="执行耗时(秒)")

    # 元数据
    module_name: str = Field(default="", description="模块名称")
    module_version: str = Field(default="", description="模块版本")

    class Config:
        extra = "allow"


class BaseModule(ABC, Generic[InputT, OutputT]):
    """
    模块基类

    所有处理模块都应继承此类，实现以下方法：
    - process: 核心处理逻辑
    - validate_input: 输入验证
    - evaluate_quality: 质量评估
    """

    name: str = "base_module"
    version: str = "1.0.0"
    description: str = "Base module"

    def __init__(self):
        self.logger = logger.bind(module=self.name)

    @abstractmethod
    async def process(self, input_data: InputT) -> OutputT:
        """
        处理输入，返回输出

        Args:
            input_data: 模块输入

        Returns:
            模块输出
        """
        pass

    @abstractmethod
    async def validate_input(self, input_data: InputT) -> tuple[bool, Optional[str]]:
        """
        验证输入是否有效

        Args:
            input_data: 模块输入

        Returns:
            (是否有效, 错误信息)
        """
        pass

    @abstractmethod
    async def evaluate_quality(self, output_data: OutputT) -> QualityMetrics:
        """
        评估输出质量

        Args:
            output_data: 模块输出

        Returns:
            质量指标
        """
        pass

    async def run(
        self,
        input_data: InputT,
        min_quality_score: float = 70.0,
        max_retries: int = 3,
        auto_retry: bool = True
    ) -> OutputT:
        """
        运行模块（带重试和质量检查）

        Args:
            input_data: 输入数据
            min_quality_score: 最低质量分数
            max_retries: 最大重试次数
            auto_retry: 是否自动重试

        Returns:
            输出数据
        """
        self.logger.info(f"开始运行模块: {self.name}")
        started_at = datetime.now()

        # 验证输入
        is_valid, error_msg = await self.validate_input(input_data)
        if not is_valid:
            self.logger.error(f"输入验证失败: {error_msg}")
            return self._create_error_output(error_msg, started_at)

        # 执行处理（带重试）
        last_error = None
        for attempt in range(max_retries):
            try:
                self.logger.info(f"执行处理 (尝试 {attempt + 1}/{max_retries})")
                output = await self.process(input_data)

                # 设置模块信息
                output.module_name = self.name
                output.module_version = self.version
                output.started_at = started_at
                output.completed_at = datetime.now()
                output.duration_seconds = (output.completed_at - started_at).total_seconds()

                if not output.success:
                    last_error = output.error
                    if auto_retry and attempt < max_retries - 1:
                        self.logger.warning(f"处理失败，准备重试: {output.error}")
                        continue
                    break

                # 质量评估
                quality = await self.evaluate_quality(output)
                output.quality = quality

                if quality.score < min_quality_score and auto_retry and attempt < max_retries - 1:
                    self.logger.warning(
                        f"质量评分 {quality.score:.1f} 低于阈值 {min_quality_score}，准备重试"
                    )
                    last_error = f"质量评分不足: {quality.score:.1f}"
                    continue

                self.logger.info(
                    f"模块完成: 质量={quality.score:.1f}, 耗时={output.duration_seconds:.2f}s"
                )
                return output

            except Exception as e:
                last_error = str(e)
                self.logger.exception(f"处理异常: {e}")
                if attempt < max_retries - 1:
                    continue

        # 所有重试都失败
        return self._create_error_output(
            f"达到最大重试次数，最后错误: {last_error}",
            started_at
        )

    def _create_error_output(self, error: str, started_at: datetime) -> OutputT:
        """创建错误输出"""
        completed_at = datetime.now()
        # 使用基类创建，具体模块可以重写
        return ModuleOutput(
            success=False,
            error=error,
            data=None,
            module_name=self.name,
            module_version=self.version,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=(completed_at - started_at).total_seconds()
        )

    async def dry_run(self, input_data: InputT) -> dict:
        """
        空运行，仅验证输入和返回预期信息

        Args:
            input_data: 输入数据

        Returns:
            预期信息
        """
        is_valid, error = await self.validate_input(input_data)
        return {
            "module": self.name,
            "version": self.version,
            "input_valid": is_valid,
            "validation_error": error,
            "description": self.description
        }

    def get_info(self) -> dict:
        """获取模块信息"""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description
        }
