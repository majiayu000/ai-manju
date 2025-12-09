"""
pytest配置和共享fixtures
"""
import os
import sys
import pytest
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import settings


@pytest.fixture
def sample_ip_content():
    """示例IP内容"""
    return """
    《阴间外卖员》

    李明是一个普通的外卖员，每天穿梭在城市的大街小巷。

    一天深夜，他接到一个奇怪的订单，送餐地址是一个废弃的医院。当他到达时，
    发现接单的是一个穿着民国服装的老人。老人给了他一枚古铜钱作为小费。

    从那天起，李明的手机开始收到来自"阴间外卖"的订单。这些订单的客户都是
    已经去世的人，他们有的想吃生前最爱的食物，有的想给阳间的亲人传话。

    第一章：奇怪的订单
    李明骑着电动车穿过空无一人的街道。手机上的订单地址指向城郊一座废弃医院。
    "谁会在这种地方点外卖？"他嘀咕着，但还是硬着头皮走了进去。
    医院大厅空荡荡的，月光从破碎的窗户照进来，在地上投下斑驳的影子。
    "外卖到了。"李明喊了一声。
    "年轻人，你来了。"一个苍老的声音从黑暗中传来。
    李明打开手电，看到一个穿着民国长衫的老人坐在角落里。
    "您点的麻辣烫。"李明把外卖递过去，手却穿过了老人的身体。
    """


@pytest.fixture
def test_project_id():
    """测试项目ID"""
    return "test_project_001"


@pytest.fixture
def has_claude_api():
    """检查是否配置了Claude API"""
    return bool(settings.claude_api_key)


@pytest.fixture
def has_kling_api():
    """检查是否配置了可灵API"""
    return bool(settings.kling_api_key and settings.kling_api_secret)


@pytest.fixture
def has_openai_api():
    """检查是否配置了OpenAI API"""
    return bool(settings.openai_api_key)


@pytest.fixture
def has_deepseek_api():
    """检查是否配置了DeepSeek API"""
    return bool(settings.deepseek_api_key)


def pytest_configure(config):
    """pytest配置钩子"""
    config.addinivalue_line(
        "markers", "real_api: marks tests as requiring real API calls"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """根据环境变量跳过某些测试"""
    skip_real_api = pytest.mark.skip(reason="需要真实API密钥")

    for item in items:
        if "real_api" in item.keywords:
            # 检查是否有所需的API密钥
            if "claude" in item.name and not settings.claude_api_key:
                item.add_marker(skip_real_api)
            elif "kling" in item.name and not (settings.kling_api_key and settings.kling_api_secret):
                item.add_marker(skip_real_api)
            elif "openai" in item.name and not settings.openai_api_key:
                item.add_marker(skip_real_api)
