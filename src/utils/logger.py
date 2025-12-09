"""
日志配置
"""
import sys
from pathlib import Path
from loguru import logger

from config import settings


def setup_logger(log_file: str = None):
    """
    配置日志

    Args:
        log_file: 日志文件路径，默认为 data/logs/app.log
    """
    # 移除默认处理器
    logger.remove()

    # 控制台输出
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[module]:^15}</cyan> | "
        "<level>{message}</level>"
    )

    logger.configure(extra={"module": "main"})

    logger.add(
        sys.stderr,
        format=log_format,
        level=settings.log_level,
        colorize=True,
        backtrace=True,
        diagnose=True
    )

    # 文件输出
    if log_file is None:
        log_dir = settings.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"

    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[module]:^15} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        encoding="utf-8"
    )

    logger.info("日志系统初始化完成")
    return logger
