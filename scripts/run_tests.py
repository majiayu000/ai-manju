#!/usr/bin/env python
"""
测试运行脚本

提供便捷的测试运行命令
"""
import subprocess
import sys
import argparse
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def run_command(cmd: list[str], description: str):
    """运行命令并打印结果"""
    print(f"\n{'='*60}")
    print(f"运行: {description}")
    print(f"命令: {' '.join(cmd)}")
    print('='*60 + "\n")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="AI漫剧流水线测试运行器")

    parser.add_argument(
        "--mode",
        choices=["mock", "real", "all", "quick"],
        default="mock",
        help="测试模式: mock=模拟测试, real=真实API测试, all=全部, quick=快速测试"
    )

    parser.add_argument(
        "--module",
        choices=["llm", "kling", "tts", "pipeline", "e2e"],
        help="指定测试模块"
    )

    parser.add_argument(
        "-k",
        "--keyword",
        help="pytest -k 过滤关键字"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细输出"
    )

    args = parser.parse_args()

    # 构建pytest命令
    cmd = [sys.executable, "-m", "pytest"]

    # 详细模式
    if args.verbose:
        cmd.extend(["-v", "-s"])

    # 测试模式
    if args.mode == "mock":
        cmd.extend(["-m", "not real_api"])
    elif args.mode == "real":
        cmd.extend(["-m", "real_api"])
    elif args.mode == "quick":
        cmd.extend(["-m", "not (real_api or slow)"])
    # all 模式不添加过滤

    # 指定模块
    if args.module:
        module_map = {
            "llm": "tests/test_llm_real_api.py",
            "kling": "tests/test_kling_real_api.py",
            "tts": "tests/test_tts_real_api.py",
            "pipeline": "tests/test_modules_real_api.py",
            "e2e": "tests/test_e2e_pipeline.py"
        }
        cmd.append(module_map[args.module])

    # 关键字过滤
    if args.keyword:
        cmd.extend(["-k", args.keyword])

    # 运行测试
    return run_command(cmd, f"测试模式: {args.mode}")


if __name__ == "__main__":
    sys.exit(main())
