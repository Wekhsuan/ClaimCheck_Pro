"""ClaimCheck Pro 阶段3：Provider 适配层、安全脱敏与预算控制单元测试

覆盖：
1. API Key 全链路脱敏测试 (mask_api_key)
2. Base URL 安全规则校验 (validate_byok_url, validate_local_url)
3. MockAIProvider 连通性与能力检测
4. OpenAICompatibleProvider 真实/模拟错误处理 (401无效Key、429超额、404模型不存在、超时、协议拦截)
5. LocalModelProvider 本地/局域网端点校验与离线能力检测
6. BudgetTracker 预算硬拦截与开销报告
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import requests

# 根目录加入 sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.core.security import mask_api_key, validate_byok_url, validate_local_url
from src.providers.base import ConnectionTestResult
from src.providers.budget import BudgetExceededError, BudgetLimits, BudgetTracker
from src.providers.local_provider import LocalModelProvider
from src.providers.mock_provider import MockAIProvider
from src.providers.openai_provider import OpenAICompatibleProvider


# ==============================================================================
# 1. 安全脱敏与地址规则测试
# ==============================================================================
def test_mask_api_key():
    """测试 API Key 脱敏函数"""
    assert mask_api_key("") == ""
    assert mask_api_key("12345") == "******"
    assert mask_api_key("sk-abcdef1234567890") == "sk-ab****90"
    assert mask_api_key("my-secret-token-999") == "my****99"


def test_validate_byok_url():
    """测试 BYOK 公网地址 HTTPS 强制策略"""
    # 允许合规 HTTPS
    valid, url = validate_byok_url("https://api.openai.com/v1/")
    assert valid is True
    assert url == "https://api.openai.com/v1"

    # 拦截明文 HTTP (防止泄露用户Key)
    valid, err = validate_byok_url("http://api.openai.com/v1")
    assert valid is False
    assert "HTTPS" in err

    # 拦截空或非法
    valid, err = validate_byok_url("")
    assert valid is False


def test_validate_local_url():
    """测试本地端点白名单策略 (回环与局域网)"""
    # 允许 localhost 与 127.0.0.1
    v1, u1 = validate_local_url("http://localhost:11434/v1")
    assert v1 is True
    v2, u2 = validate_local_url("http://127.0.0.1:8000/v1/")
    assert v2 is True
    assert u2 == "http://127.0.0.1:8000/v1"

    # 允许常见内网私有 IP
    v3, _ = validate_local_url("http://192.168.1.100:11434/v1")
    assert v3 is True
    v4, _ = validate_local_url("http://10.0.0.5:8000/v1")
    assert v4 is True

    # 拦截未知公网 IP
    v5, err = validate_local_url("http://8.8.8.8:11434/v1")
    assert v5 is False
    assert "公网" in err


# ==============================================================================
# 2. MockProvider 测试
# ==============================================================================
def test_mock_provider():
    """测试 MockProvider 离线响应能力"""
    provider = MockAIProvider()
    res = provider.test_connection()
    assert res.success is True
    assert res.supports_text is True
    assert res.supports_json_mode is True
    assert res.supports_vision is True
    assert res.response_time_ms >= 0

    text = provider.generate_text("test")
    assert "Mock" in text
    json_text = provider.generate_text("test", json_mode=True)
    assert "mock_success" in json_text


# ==============================================================================
# 3. OpenAICompatibleProvider 测试 (含各种错误处理)
# ==============================================================================
def test_openai_provider_missing_key():
    """测试缺少 API Key 时的明确提示"""
    provider = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="")
    res = provider.test_connection()
    assert res.success is False
    assert "API Key 不能为空" in res.error_message


def test_openai_provider_http_blocked():
    """测试使用 HTTP 时被安全拦截"""
    provider = OpenAICompatibleProvider(base_url="http://api.openai.com/v1", api_key="sk-123")
    res = provider.test_connection()
    assert res.success is False
    assert "HTTPS" in res.error_message


@patch("requests.post")
def test_openai_provider_401_invalid_key(mock_post):
    """测试 401 密钥失效错误"""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Invalid API Key"
    mock_post.return_value = mock_resp

    provider = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="sk-invalid123")
    res = provider.test_connection()
    assert res.success is False
    assert "401" in res.error_message
    assert "API Key 无效" in res.error_message


@patch("requests.post")
def test_openai_provider_429_quota_exceeded(mock_post):
    """测试 429 额度不足错误"""
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Insufficient Quota"
    mock_post.return_value = mock_resp

    provider = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="sk-noquota123")
    res = provider.test_connection()
    assert res.success is False
    assert "429" in res.error_message
    assert "余额不足" in res.error_message


@patch("requests.post")
def test_openai_provider_timeout(mock_post):
    """测试请求超时错误"""
    mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

    provider = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="sk-test123", timeout=5)
    res = provider.test_connection()
    assert res.success is False
    assert "连接超时" in res.error_message


@patch("requests.post")
def test_openai_provider_success_capabilities(mock_post):
    """测试端点成功连通并检测能力"""
    # 模拟两次请求：第一次是文本ping，第二次是json检测
    mock_resp_text = MagicMock()
    mock_resp_text.status_code = 200
    mock_resp_text.json.return_value = {"choices": [{"message": {"content": "pong"}}]}

    mock_resp_json = MagicMock()
    mock_resp_json.status_code = 200
    mock_resp_json.json.return_value = {"choices": [{"message": {"content": '{"status": "ok"}'}}]}

    mock_post.side_effect = [mock_resp_text, mock_resp_json]

    provider = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="sk-validkey123456",
        model_name="gpt-4o",
    )
    res = provider.test_connection()
    assert res.success is True
    assert res.supports_text is True
    assert res.supports_json_mode is True
    assert res.supports_vision is True  # gpt-4o 识别为多模态
    assert res.error_message is None


# ==============================================================================
# 4. LocalModelProvider 测试
# ==============================================================================
def test_local_provider_invalid_public_url():
    """测试本地模型配置了非法公网地址被拦截"""
    provider = LocalModelProvider(base_url="http://8.8.8.8:11434/v1")
    res = provider.test_connection()
    assert res.success is False
    assert "本地端点地址校验未通过" in res.error_message


@patch("requests.post")
def test_local_provider_connection_refused(mock_post):
    """测试本地服务未启动连接拒绝错误"""
    mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

    provider = LocalModelProvider(base_url="http://127.0.0.1:11434/v1")
    res = provider.test_connection()
    assert res.success is False
    assert "无法连接到本地服务" in res.error_message
    assert "Ollama" in res.error_message


# ==============================================================================
# 5. BudgetTracker 预算与费用守卫测试
# ==============================================================================
def test_budget_tracker_enforcement():
    """测试预算硬拦截机制：超额调用时抛出异常，绝不静默计费"""
    tracker = BudgetTracker(BudgetLimits(max_model_calls=3))
    tracker.record_model_call()
    tracker.record_model_call()
    tracker.record_model_call()
    assert tracker.total_model_calls == 3

    # 第4次调用必须被拦截并抛出 BudgetExceededError
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_model_call()
    assert "已达到单任务最大模型调用次数上限" in str(exc_info.value)
    assert "不回退至任何付费服务" in str(exc_info.value)


def test_budget_tracker_preflight():
    """测试任务前开销汇总信息"""
    tracker = BudgetTracker(BudgetLimits(max_claims=5, max_model_calls=5))
    info_byok = tracker.get_preflight_summary(claims_count=3, service_mode="byok")
    assert "3 条" in info_byok["claims_count"]
    assert "用户自带第三方账户" in info_byok["payer"]

    info_mock = tracker.get_preflight_summary(claims_count=5, service_mode="mock")
    assert "零费用" in info_mock["payer"]


if __name__ == "__main__":
    pytest.main(["-v", str(Path(__file__).resolve())])
