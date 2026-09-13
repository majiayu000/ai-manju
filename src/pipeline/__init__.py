"""
流水线控制
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import PipelineController, PipelineConfig

__all__ = ["PipelineController", "PipelineConfig"]


def __getattr__(name: str):
    if name in ("PipelineController", "PipelineConfig"):
        from .controller import PipelineController, PipelineConfig

        return {
            "PipelineController": PipelineController,
            "PipelineConfig": PipelineConfig,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
