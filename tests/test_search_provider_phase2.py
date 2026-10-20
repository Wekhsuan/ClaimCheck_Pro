"""ClaimCheck Pro 第二阶段：独立 Search Provider 抽象、Tavily 自带 API 与手动证据测试套件
100% 离线 Mock 测试，零真实网络请求，零 API 费用消耗
"""

import pytest
from unittest.mock import MagicMock, patch
import requests

from src.core.security import mask_search_api_key, mask_key_in_text
from src.search.base import (
    SearchResultItem,
    ManualEvidenceItem,
    SearchConnectionResult,
    clean_suspicious_control_characters,
    validate_web_url,
)
from src.search.no_search_provider import NoSearchProvider
from src.search.tavily_provider import TavilySearchProvider
from src.search.manual_provider import ManualEvidenceProvider
from src.providers.budget import BudgetLimits, BudgetTracker


# -----------------------------------------------------------------------------
# 1. 基础工具与脱敏函数测试
# -----------------------------------------------------------------------------
def test_mask_search_api_key():
    """测试不同格式的搜索 Key 脱敏"""
    assert mask_search_api_key("tvly-abcdefgh1234") == "tvly-****1234"
    assert mask_search_api_key("tvly-1234567890abcdef") == "tvly-****cdef"
    assert mask_search_api_key("sk-short") == "sk****rt"
    assert mask_search_api_key("123456789") == "1234****6789"
    assert mask_search_api_key("") == ""


def test_mask_key_in_text():
    """测试异常日志与报错信息中搜索 Key 脱敏"""
    raw_key = "tvly-secret-9999-ABCD"
    text = f"HTTPConnectionPool: request to https://api.tavily.com failed with key {raw_key} unauthorized"
    sanitized = mask_key_in_text(text, raw_key)
    assert raw_key not in sanitized
    assert "tvly-****ABCD" in sanitized


def test_search_base_url_validation():
    """测试证据与搜索 URL 校验"""
    # 合法公网链接
    assert validate_web_url("https://www.apple.com/airpods-pro/specs/")[0] is True
    assert validate_web_url("http://example.org/item/10086")[0] is True

    # 非法协议与空值
    assert validate_web_url("")[0] is False
    assert validate_web_url("ftp://example.com/file")[0] is False
    assert validate_web_url("javascript:alert(1)")[0] is False
    assert validate_web_url("file:///etc/passwd")[0] is False
    assert validate_web_url("not_a_url")[0] is False


def test_clean_control_characters():
    """测试非法控制字符过滤"""
    dirty = "SoundPro\x00 X1\x08 旗舰版\x1f - 48dB降噪\n真实可用"
    cleaned = clean_suspicious_control_characters(dirty)
    assert "\x00" not in cleaned
    assert "\x08" not in cleaned
    assert "\x1f" not in cleaned
    assert "SoundPro X1 旗舰版 - 48dB降噪\n真实可用" == cleaned


# -----------------------------------------------------------------------------
# 2. NoSearchProvider (未配置搜索) 测试
# -----------------------------------------------------------------------------
def test_no_search_provider_not_configured():
    """NoSearchProvider 必须标记为未配置"""
    provider = NoSearchProvider()
    assert provider.is_configured() is False
    assert provider.provider_name() == "NoSearchProvider"
    caps = provider.capabilities()
    assert caps["can_search"] is False


def test_no_search_provider_search_empty():
    """NoSearchProvider 执行搜索时必须返回空列表，绝对不捏造任何假数据"""
    provider = NoSearchProvider()
    results = provider.search("SoundPro X1 降噪48dB")
    assert results == []
    assert len(results) == 0


def test_no_search_provider_test_connection():
    """NoSearchProvider 测试连接应返回清晰的未配置中文说明"""
    provider = NoSearchProvider()
    res = provider.test_connection()
    assert res.success is False
    assert res.provider_name == "NoSearchProvider"
    assert "未配置" in res.error_message
    assert "不会发起实时网络检索" in res.error_message


# -----------------------------------------------------------------------------
# 3. TavilySearchProvider 测试
# -----------------------------------------------------------------------------
def test_tavily_provider_not_configured_without_key():
    """未传 API Key 时 is_configured 应返回 False"""
    p = TavilySearchProvider(api_key="")
    assert p.is_configured() is False
    assert p.provider_name() == "TavilySearchProvider"


def test_tavily_provider_configured_with_key():
    """传入合法 API Key 时 is_configured 应返回 True"""
    p = TavilySearchProvider(api_key="tvly-valid-test-key-1234")
    assert p.is_configured() is True
    assert p.provider_name() == "TavilySearchProvider"


def test_tavily_fixed_endpoint():
    """固定端点不可篡改"""
    assert TavilySearchProvider.FIXED_SEARCH_ENDPOINT == "https://api.tavily.com/search"


@patch("requests.post")
def test_tavily_test_connection_success(mock_post):
    """测试 Tavily 连接成功 (200 OK)"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": []}
    mock_post.return_value = mock_resp

    p = TavilySearchProvider(api_key="tvly-mock-secret-9999")
    res = p.test_connection()

    assert res.success is True
    assert res.status_code == 200
    assert res.response_time_ms >= 0
    assert "tvly-****9999" in res.masked_api_key
    assert "正常" in res.error_message

    # 验证请求参数
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.tavily.com/search"
    assert kwargs["json"]["query"] == "ping"
    assert kwargs["json"]["max_results"] == 1


@patch("requests.post")
def test_tavily_test_connection_401(mock_post):
    """测试 Tavily 401 凭证错误转换中文友好提示"""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized: Invalid API key"
    mock_post.return_value = mock_resp

    p = TavilySearchProvider(api_key="tvly-invalid-key")
    res = p.test_connection()

    assert res.success is False
    assert res.status_code == 401
    assert "搜索API Key无效或未正确提交" in res.error_message


@patch("requests.post")
def test_tavily_test_connection_403(mock_post):
    """测试 Tavily 403 权限受限转换中文友好提示"""
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    mock_post.return_value = mock_resp

    p = TavilySearchProvider(api_key="tvly-key-no-perm")
    res = p.test_connection()

    assert res.success is False
    assert res.status_code == 403
    assert "权限" in res.error_message


@patch("requests.post")
def test_tavily_test_connection_404(mock_post):
    """测试 Tavily 404 端点错误转换中文友好提示"""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"
    mock_post.return_value = mock_resp

    p = TavilySearchProvider(api_key="tvly-key-404")
    res = p.test_connection()

    assert res.success is False
    assert res.status_code == 404
    assert "接口地址或Provider配置错误" in res.error_message


@patch("requests.post")
def test_tavily_test_connection_429(mock_post):
    """测试 Tavily 429 额度超限转换中文友好提示"""
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Rate limit exceeded / Usage limit reached"
    mock_post.return_value = mock_resp

    p = TavilySearchProvider(api_key="tvly-key-over-quota")
    res = p.test_connection()

    assert res.success is False
    assert res.status_code == 429
    assert "账户配额、余额或速率限制" in res.error_message


@patch("requests.post")
def test_tavily_test_connection_500(mock_post):
    """测试 Tavily 500 服务端异常转换中文友好提示"""
    mock_resp = MagicMock()
    mock_resp.status_code = 502
    mock_resp.text = "Bad Gateway"
    mock_post.return_value = mock_resp

    p = TavilySearchProvider(api_key="tvly-key-500")
    res = p.test_connection()

    assert res.success is False
    assert res.status_code == 502
    assert "搜索服务暂时异常" in res.error_message


@patch("requests.post")
def test_tavily_test_connection_timeout(mock_post):
    """测试 Tavily 超时异常捕获并提示"""
    mock_post.side_effect = requests.exceptions.Timeout("Connection timed out after 10s")

    p = TavilySearchProvider(api_key="tvly-timeout-key", timeout=10)
    res = p.test_connection()

    assert res.success is False
    assert "超时" in res.error_message


@patch("requests.post")
def test_tavily_search_result_parsing_and_sanitizing(mock_post):
    """测试真实搜索结果解析与归一化格式"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "title": "极客声学 SoundPro X1 评测\x00 - 音质与降噪",
                "url": "https://www.geekacoustic.com/reviews/soundpro-x1",
                "content": "实测最大降噪深度为46.2dB，官方标称48dB略有保守...",
                "score": 0.92,
            },
            {
                "title": "SoundPro X1 官方规格参数",
                "url": "https://brand-audio.com/products/soundpro-x1/specs",
                "content": "支持LHDC 5.0高清音频传输协议，续航时间达到40小时。",
                "score": 0.88,
            },
        ]
    }
    mock_post.return_value = mock_resp

    p = TavilySearchProvider(api_key="tvly-test-parse-key", max_results=5)
    results = p.search("SoundPro X1 降噪48dB")

    assert len(results) == 2
    r1: SearchResultItem = results[0]
    assert r1.title == "极客声学 SoundPro X1 评测 - 音质与降噪"
    assert "\x00" not in r1.title
    assert r1.domain == "www.geekacoustic.com"
    assert r1.provider == "tavily"
    assert r1.result_rank == 1
    assert "46.2dB" in r1.snippet

    r2: SearchResultItem = results[1]
    assert r2.domain == "brand-audio.com"
    assert r2.result_rank == 2


def test_tavily_key_masking_in_exceptions():
    """测试异常回溯中绝对不泄露 API Key"""
    raw_key = "tvly-super-confidential-key-1234"
    with patch("requests.post") as mock_post:
        mock_post.side_effect = Exception(f"Failed to connect to Tavily with api_key={raw_key}")
        p = TavilySearchProvider(api_key=raw_key)
        res = p.test_connection()
        assert res.success is False
        assert raw_key not in res.error_message
        assert "tvly-****1234" in res.error_message


# -----------------------------------------------------------------------------
# 4. ManualEvidenceProvider (手动证据管理) 测试
# -----------------------------------------------------------------------------
def test_manual_evidence_provider_lifecycle():
    """测试手动证据的添加、排重、删除与转换"""
    p = ManualEvidenceProvider()
    assert p.is_configured() is False
    assert len(p.get_items()) == 0

    # 1. 成功添加合法链接
    succ1, msg1 = p.add_evidence(
        url="https://www.brand.com/products/soundpro/manual.pdf",
        title="官方使用指南",
        source_type="manual",
        user_note="第12页写明降噪深度48dB",
    )
    assert succ1 is True
    assert p.is_configured() is True
    assert len(p.get_items()) == 1

    # 2. 重复添加相同 URL 触发排重
    succ2, msg2 = p.add_evidence(
        url="https://www.brand.com/products/soundpro/manual.pdf",
        title="重复的指南",
    )
    assert succ2 is False
    assert "已存在" in msg2
    assert len(p.get_items()) == 1

    # 3. 添加非法格式 URL
    succ3, msg3 = p.add_evidence(
        url="ftp://illegal-url.com/doc",
        title="非法链接",
    )
    assert succ3 is False
    assert "仅支持" in msg3
    assert len(p.get_items()) == 1

    # 4. 再次添加一个合法评测链接
    succ4, _ = p.add_evidence(
        url="https://www.audiophile-review.com/soundpro-x1",
        title="专业音频媒体拆解评测",
        source_type="review",
    )
    assert succ4 is True
    assert len(p.get_items()) == 2

    # 5. 执行 search() 应返回对应的归一化 SearchResultItem
    search_res = p.search("任意查询词")
    assert len(search_res) == 2
    assert search_res[0].domain == "www.brand.com"
    assert search_res[0].provider == "manual"
    assert search_res[1].domain == "www.audiophile-review.com"

    # 6. 删除一条
    rem_succ = p.remove_evidence(0)
    assert rem_succ is True
    assert len(p.get_items()) == 1
    assert p.get_items()[0].title == "专业音频媒体拆解评测"

    # 7. 清空全部
    p.clear_evidence()
    assert len(p.get_items()) == 0
    assert p.is_configured() is False


# -----------------------------------------------------------------------------
# 5. 调用预算与搜索模式联动测试
# -----------------------------------------------------------------------------
def test_budget_tracker_preflight_summary_search_modes():
    """测试不同搜索模式下的开销与请求数预计"""
    tracker = BudgetTracker(BudgetLimits())

    # 未配置搜索模式
    sum_none = tracker.get_preflight_summary(claims_count=5, service_mode="byok", search_mode="none")
    assert "0 次" in sum_none["search_requests_count"]
    assert "零费用" in sum_none["search_payer"]

    # Tavily 自带 API 模式
    sum_tavily = tracker.get_preflight_summary(claims_count=5, service_mode="byok", search_mode="tavily")
    assert "最多 5 次" in sum_tavily["search_requests_count"]
    assert "Tavily" in sum_tavily["search_payer"]

    # 手动证据模式
    sum_manual = tracker.get_preflight_summary(claims_count=5, service_mode="byok", search_mode="manual", manual_evidence_count=3)
    assert "0 次" in sum_manual["search_requests_count"]
    assert "已载入 3 条" in sum_manual["search_results_cap"]
    assert "零费用" in sum_manual["search_payer"]
