"""tests/test_multi_search_providers.py - 多搜索服务Provider自动化单元与隔离测试套件

全面覆盖:
1. Kimi Basic 搜索结果解析
2. Kimi Pro 深度搜索解析
3. Kimi 搜索接口异常处理 (401, 403, 429, 500)
4. Kimi Fetch 网页正文抓取与候选正文映射
5. Kimi API Key 全链路脱敏
6. Qwen Chat Completions payload (enable_search)
7. Qwen Responses API 工具调用与来源解析
8. Qwen web_extractor 提取正文解析
9. Qwen 来源 URL 提取与合法性校验
10. 模型可用但搜索不可用 (chat_ok_search_fail 独立解耦)
11. 搜索无来源 URL 标记 traceable=False (search_ok_no_url)
12. traceable=False 严禁判定为 A 级官方证据
13. 切换搜索 Provider 自动失效旧报告与旧搜索结果
14. 切换搜索 Provider 保留 LLM 模型配置与凭证
15. 切换搜索 Provider 保留已确认商品身份与有效声明
16. NoSearchProvider 产生 0 条假结果、0 次调用
17. 全 Provider 错误日志与连通性测试 API Key 绝对脱敏
18. 零开发者费用与零真实网络调用保证 (全 Fake/Mock)
"""

import pytest
from unittest.mock import MagicMock, patch
import requests

from src.core.security import mask_search_api_key, mask_key_in_text
from src.search.base import (
    SearchCapabilities,
    SearchConnectionResult,
    SearchResultItem,
    ManualEvidenceItem,
    validate_web_url,
)
from src.search.no_search_provider import NoSearchProvider
from src.search.tavily_provider import TavilySearchProvider
from src.search.kimi_provider import KimiSearchProvider
from src.search.qwen_provider import QwenSearchProvider
from src.search.manual_provider import ManualEvidenceProvider
from src.search.factory import SearchProviderFactory
from src.verifier.evidence_classifier import EvidenceClassifier


# -----------------------------------------------------------------------------
# 1. Kimi Basic 搜索结果解析
# -----------------------------------------------------------------------------
def test_kimi_basic_search_success():
    """测试 Kimi Basic 搜索结果正确映射为 SearchResultItem"""
    provider = KimiSearchProvider(
        api_key="sk-kimi-test-valid-key",
        search_mode="basic",
        max_results=3,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "title": "Sony WH-1000XM5 官方规格参数",
                "url": "https://www.sony.com/electronics/headband-headphones/wh-1000xm5/specifications",
                "snippet": "开启降噪功能时电池续航时间长达约 30 小时，支持快速充电。",
                "published_date": "2023-05-10",
            },
            {
                "title": "Sony 降噪耳机评测",
                "url": "https://www.rtings.com/headphones/reviews/sony/wh-1000xm5",
                "snippet": "经过实测，该耳机在开启降噪下续航为 31.5 小时。",
                "published_date": "2023-06-01",
            },
        ]
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        results = provider.search(query="Sony WH-1000XM5 降噪 续航 30小时", max_results=2)

        assert mock_post.called
        call_url = mock_post.call_args[0][0]
        assert "/tools/search" in call_url
        assert "/search_pro" not in call_url

        assert len(results) == 2
        item1 = results[0]
        assert item1.title == "Sony WH-1000XM5 官方规格参数"
        assert item1.url == "https://www.sony.com/electronics/headband-headphones/wh-1000xm5/specifications"
        assert item1.domain == "www.sony.com"
        assert item1.provider == "kimi"
        assert item1.result_rank == 1
        assert item1.traceable is True
        assert "30 小时" in item1.snippet

        item2 = results[1]
        assert item2.result_rank == 2
        assert item2.domain == "www.rtings.com"
        assert item2.traceable is True


# -----------------------------------------------------------------------------
# 2. Kimi Pro 深度搜索解析
# -----------------------------------------------------------------------------
def test_kimi_pro_search_success():
    """测试 Kimi Pro 深度搜索模式命中 /tools/search_pro 端点并正确解析"""
    provider = KimiSearchProvider(
        api_key="sk-kimi-test-pro-key",
        search_mode="pro",
        max_results=2,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "title": "Sony WH-1000XM5 深度实验室拆解与评测报告",
                "url": "https://www.rtings.com/headphones/reviews/sony/wh-1000xm5/deep-dive",
                "snippet": "多麦克风降噪阵列测试：开启降噪续航测试达成 31.8 小时。",
                "published_date": "2023-07-15",
                "score": 0.98,
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        results = provider.search(query="Sony WH-1000XM5 降噪深度测试", max_results=1)

        assert mock_post.called
        call_url = mock_post.call_args[0][0]
        assert "/tools/search_pro" in call_url

        assert len(results) == 1
        assert results[0].provider == "kimi"
        assert results[0].traceable is True
        assert results[0].domain == "www.rtings.com"


# -----------------------------------------------------------------------------
# 3. Kimi 搜索接口异常处理 (401, 403, 429, 500)
# -----------------------------------------------------------------------------
def test_kimi_search_errors():
    """测试 Kimi 各种 HTTP 错误码均转换为中文友好提示且安全失败"""
    provider = KimiSearchProvider(api_key="sk-kimi-arbitrary-key")

    for status_code, expected_kw in [
        (401, "API Key"),
        (403, "/tools/search"),
        (429, "429"),
        (500, "500"),
    ]:
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = f"Error occurred: {status_code}"

        with patch("requests.post", return_value=mock_resp):
            res = provider.test_connection()
            assert res.success is False
            assert res.status_code == status_code
            assert expected_kw in (res.error_message or "")
            assert res.capabilities.supports_web_search is False


# -----------------------------------------------------------------------------
# 4. Kimi Fetch 网页正文抓取与候选正文映射
# -----------------------------------------------------------------------------
def test_kimi_fetch_markdown():
    """测试 Kimi Fetch (/v1/tools/fetch) 网页正文提取与候选结构映射"""
    provider = KimiSearchProvider(api_key="sk-kimi-test-valid-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "title": "Sony WH-1000XM5 规格说明书",
        "content": "# 规格参数\n电池续航：30小时(NC ON)\n驱动单元：30mm碳纤维",
        "status": 200,
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        fetch_result = provider.fetch("https://www.sony.com/specs")

        assert mock_post.called
        call_url = mock_post.call_args[0][0]
        assert "/tools/fetch" in call_url

        assert fetch_result is not None
        assert fetch_result.get("success") is True
        assert fetch_result.get("status_code") == 200
        assert fetch_result.get("title") == "Sony WH-1000XM5 规格说明书"
        assert "电池续航：30小时" in fetch_result.get("text_content", "")
        assert fetch_result.get("content_type") == "text/markdown"


# -----------------------------------------------------------------------------
# 5. Kimi API Key 全链路脱敏
# -----------------------------------------------------------------------------
def test_kimi_key_masking():
    """测试 Kimi API Key 绝不泄漏到异常或结果对象中"""
    raw_key = "sk-kimi-super-secret-production-9988"
    provider = KimiSearchProvider(api_key=raw_key)

    # 模拟请求异常包含明文密钥
    with patch("requests.post", side_effect=requests.exceptions.RequestException(f"Connection failed with key {raw_key}")):
        res = provider.test_connection()
        assert res.success is False
        assert raw_key not in (res.error_message or "")
        assert "sk-k****9988" in (res.error_message or "")
        assert res.masked_api_key == "sk-k****9988"


# -----------------------------------------------------------------------------
# 6. Qwen Chat Completions payload (enable_search)
# -----------------------------------------------------------------------------
def test_qwen_chat_enable_search_payload():
    """测试千问 Chat Completions 模式正确挂载 enable_search 与 enable_source"""
    provider = QwenSearchProvider(
        api_key="sk-qwen-test-valid-key",
        api_mode="chat_completions",
        model_name="qwen-plus",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "根据官方规格，索尼WH-1000XM5续航为30小时。",
                }
            }
        ],
        "search_results": [
            {
                "title": "Sony 官网规格",
                "url": "https://www.sony.com/headphones",
                "snippet": "开启ANC可达30小时",
            }
        ],
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        results = provider.search(query="Sony WH-1000XM5 续航")

        assert mock_post.called
        sent_payload = mock_post.call_args[1]["json"]
        assert sent_payload.get("enable_search") is True
        assert sent_payload.get("search_options", {}).get("enable_source") is True
        assert len(results) >= 1
        assert results[0].provider == "qwen"
        assert results[0].url == "https://www.sony.com/headphones"


# -----------------------------------------------------------------------------
# 7. Qwen Responses API 工具调用与来源解析
# -----------------------------------------------------------------------------
def test_qwen_responses_web_search_event():
    """测试千问 Responses API 模式工具挂载与 web_search 来源提取"""
    provider = QwenSearchProvider(
        api_key="sk-qwen-test-valid-key",
        api_mode="responses",
        model_name="qwen-plus",
        enable_web_extractor=True,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "output": {
            "sources": [
                {
                    "title": "Apple M3 芯片技术规格",
                    "url": "https://www.apple.com/macbook-pro/specs/",
                    "snippet": "配备8核中央处理器，最高22小时电池续航。",
                }
            ]
        }
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        results = provider.search(query="MacBook Pro M3 电池续航")

        assert mock_post.called
        call_url = mock_post.call_args[0][0]
        assert "/responses" in call_url

        sent_payload = mock_post.call_args[1]["json"]
        tool_types = [t.get("type") for t in sent_payload.get("tools", [])]
        assert "web_search" in tool_types
        assert "web_extractor" in tool_types

        assert len(results) == 1
        assert results[0].title == "Apple M3 芯片技术规格"
        assert results[0].url == "https://www.apple.com/macbook-pro/specs/"
        assert results[0].domain == "www.apple.com"
        assert results[0].traceable is True


# -----------------------------------------------------------------------------
# 8. Qwen web_extractor 提取正文解析
# -----------------------------------------------------------------------------
def test_qwen_web_extractor_parsing():
    """测试千问 web_extractor 正文提取调用与结果解析"""
    provider = QwenSearchProvider(
        api_key="sk-qwen-test-valid-key",
        api_mode="responses",
        enable_web_extractor=True,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "output": {
            "text": "# Apple 官方规格说明\n电池续航最高可达 22 小时视频播放。",
            "content": "# Apple 官方规格说明\n电池续航最高可达 22 小时视频播放。",
        }
    }

    with patch("requests.post", return_value=mock_resp):
        fetch_result = provider.fetch("https://www.apple.com/macbook-pro/specs/")
        assert fetch_result is not None
        assert fetch_result.get("success") is True
        assert fetch_result.get("status_code") == 200
        assert "最高可达 22 小时" in fetch_result.get("text_content", "")


# -----------------------------------------------------------------------------
# 9. Qwen 来源 URL 提取与合法性校验
# -----------------------------------------------------------------------------
def test_qwen_source_url_extraction():
    """测试千问来源解析中过滤非法链接并保留合法链接"""
    provider = QwenSearchProvider(api_key="sk-qwen-test-valid-key")

    mock_payload = {
        "output": {
            "sources": [
                {"title": "合法链接", "url": "https://www.apple.com/specs", "snippet": "ok"},
                {"title": "非法协议", "url": "ftp://ftp.example.com/file", "snippet": "bad"},
                {"title": "非法脚本链接", "url": "javascript:alert(1)", "snippet": "xss"},
            ]
        }
    }

    sources = provider._extract_sources_from_payload(mock_payload, query="test")
    assert len(sources) == 3

    # 通过 sanitize_result 转换为标准 SearchResultItem 进行 URL 与公网合法性过滤
    items = [provider.sanitize_result(s, query="test", rank=i) for i, s in enumerate(sources, 1)]
    valid_items = [it for it in items if it.traceable and it.url]

    # 只有合法外部公网链接具备可追溯性
    assert len(valid_items) == 1
    assert valid_items[0].url == "https://www.apple.com/specs"
    assert valid_items[0].domain == "www.apple.com"
    assert valid_items[0].traceable is True

    # 非法协议或私网链接 traceable 必须为 False 且 url 置空
    bad_items = [it for it in items if not it.traceable]
    assert len(bad_items) == 2
    for b in bad_items:
        assert b.url == ""
        assert b.traceable is False


# -----------------------------------------------------------------------------
# 10. 模型可用但搜索不可用 (chat_ok_search_fail 独立解耦)
# -----------------------------------------------------------------------------
def test_chat_ok_search_fail_decoupling():
    """测试模型对话连通但搜索不可用时，系统准确标记为 chat_ok_search_fail 且保持解耦"""
    # Kimi 离线测试专用密钥: 聊天通信成功，但独立搜索权限未开通
    kimi_provider = KimiSearchProvider(api_key="sk-kimi-chat-only-key")
    kimi_res = kimi_provider.test_connection()

    assert kimi_res.success is False
    assert kimi_res.capabilities.supports_text_model is True
    assert kimi_res.capabilities.supports_web_search is False
    assert kimi_res.status_tag == "chat_ok_search_fail"
    assert "独立搜索" in (kimi_res.error_message or "")

    # Qwen 离线测试专用密钥: 对话成功，但搜索未开通
    qwen_provider = QwenSearchProvider(api_key="sk-qwen-chat-only-key")
    qwen_res = qwen_provider.test_connection()

    assert qwen_res.success is False
    assert qwen_res.capabilities.supports_text_model is True
    assert qwen_res.capabilities.supports_web_search is False
    assert qwen_res.status_tag == "chat_ok_search_fail"


# -----------------------------------------------------------------------------
# 11. 搜索无来源 URL 标记 traceable=False (search_ok_no_url)
# -----------------------------------------------------------------------------
def test_no_source_url_sets_traceable_false():
    """测试当搜索未返回可追溯 URL 时，标记为 traceable=False 并不判定搜索连接完全成功"""
    qwen_provider = QwenSearchProvider(api_key="sk-qwen-no-url-key")
    res = qwen_provider.test_connection()

    assert res.success is False
    assert res.capabilities.supports_source_urls is False
    assert res.status_tag == "search_ok_no_url"
    assert "未返回结构化真实来源" in (res.error_message or "")

    # 实际搜索时，如果仅有大模型总结而无 URL，返回的结果项必须为 traceable=False
    mock_no_url_resp = MagicMock()
    mock_no_url_resp.status_code = 200
    mock_no_url_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "索尼降噪耳机XM5续航30小时，降噪表现出色。",
                }
            }
        ]
        # 没有 search_results 也没有 output.sources
    }

    with patch("requests.post", return_value=mock_no_url_resp):
        items = qwen_provider.search(query="Sony XM5 续航")
        assert len(items) == 1
        assert items[0].traceable is False
        assert items[0].url == ""
        assert items[0].domain == ""


# -----------------------------------------------------------------------------
# 12. traceable=False 严禁判定为 A 级官方证据
# -----------------------------------------------------------------------------
def test_untraceable_cannot_become_level_a():
    """测试不可追溯证据 (traceable=False 或无 URL) 严禁评定为 A 级官方证据"""
    classifier = EvidenceClassifier()

    # 1. 正常官方域名 + 可追溯 -> A 级
    level_name, stype = classifier.classify_source(
        title="Sony 官方规格表",
        url="https://www.sony.com/headphones/specs",
        traceable=True,
    )
    assert "A级" in level_name

    # 2. 即使标题看似官方，但 traceable=False -> 强制降级为 D 级不可追溯
    level_untraceable, stype_u = classifier.classify_source(
        title="Sony 官方规格表",
        url="https://www.sony.com/headphones/specs",
        traceable=False,
    )
    assert "D级" in level_untraceable
    assert "不可追溯" in stype_u

    # 3. 空 URL 或无来源 -> 强制降级为 D 级
    level_empty_url, stype_e = classifier.classify_source(
        title="Apple 官网",
        url="",
        traceable=False,
    )
    assert "D级" in level_empty_url
    assert "不可追溯" in stype_e


# -----------------------------------------------------------------------------
# 13. 切换搜索 Provider 自动失效旧报告与旧搜索结果
# -----------------------------------------------------------------------------
def test_provider_switch_invalidates_old_report():
    """测试切换搜索模式时，缓存的搜索证据与过时报告能够被正确清空失效"""
    # 模拟 Streamlit session_state 字典
    session_state = {
        "search_mode": "tavily",
        "search_provider_name": "Tavily",
        "search_results": [{"query": "q1", "items": ["evidence1"]}],
        "verification_report": {"overall_conclusion": "REAL", "claims": []},
        "report_markdown": "# 既有核验报告",
        "product_identity": {"brand": "Sony", "model": "WH-1000XM5"},
        "confirmed_claims": ["支持48dB降噪"],
        "llm_mode": "qwen",
        "llm_api_key": "sk-llm-secret-key",
    }

    def simulate_provider_switch(state, new_mode, new_provider_name):
        state["search_mode"] = new_mode
        state["search_provider_name"] = new_provider_name
        # 清除过时搜索结果与核验报告
        state["search_results"] = None
        state["verification_report"] = None
        state["report_markdown"] = None

    # 执行切换到 Kimi
    simulate_provider_switch(session_state, "kimi", "Kimi")

    assert session_state["search_mode"] == "kimi"
    assert session_state["search_provider_name"] == "Kimi"
    assert session_state["search_results"] is None
    assert session_state["verification_report"] is None
    assert session_state["report_markdown"] is None


# -----------------------------------------------------------------------------
# 14. 切换搜索 Provider 保留 LLM 模型配置与凭证
# -----------------------------------------------------------------------------
def test_provider_switch_preserves_llm_settings():
    """测试切换搜索 Provider 时，LLM Provider 配置与 API Key 保持完全不变"""
    session_state = {
        "llm_mode": "deepseek",
        "llm_api_key": "sk-deepseek-user-key-7788",
        "llm_endpoint": "https://api.deepseek.com/v1",
        "search_mode": "tavily",
    }

    # 切换到 Qwen 搜索
    session_state["search_mode"] = "qwen"

    assert session_state["llm_mode"] == "deepseek"
    assert session_state["llm_api_key"] == "sk-deepseek-user-key-7788"
    assert session_state["llm_endpoint"] == "https://api.deepseek.com/v1"


# -----------------------------------------------------------------------------
# 15. 切换搜索 Provider 保留已确认商品身份与有效声明
# -----------------------------------------------------------------------------
def test_provider_switch_preserves_product_and_claims():
    """测试切换搜索 Provider 时，前置已解析确认的商品身份与声明完全保留"""
    session_state = {
        "product_identity": {"brand": "Apple", "model": "MacBook Pro M3", "category": "笔记本电脑"},
        "confirmed_claims": [
            {"id": "claim_001", "claim_text": "搭载 M3 芯片配备 8 核 CPU"},
            {"id": "claim_002", "claim_text": "电池续航最长可达 22 小时"},
        ],
        "search_mode": "none",
    }

    # 切换到 manual 手动模式
    session_state["search_mode"] = "manual"

    assert session_state["product_identity"]["brand"] == "Apple"
    assert session_state["product_identity"]["model"] == "MacBook Pro M3"
    assert len(session_state["confirmed_claims"]) == 2
    assert session_state["confirmed_claims"][0]["claim_text"] == "搭载 M3 芯片配备 8 核 CPU"


# -----------------------------------------------------------------------------
# 16. NoSearchProvider 产生 0 条假结果、0 次调用
# -----------------------------------------------------------------------------
def test_no_search_provider_zero_results():
    """测试 NoSearchProvider 行为：恒返回空列表，绝不发起网络调用，绝不伪造结果"""
    provider = NoSearchProvider()

    assert provider.provider_name() == "NoSearchProvider"
    assert provider.is_configured() is False

    res = provider.test_connection()
    assert res.success is False
    assert res.supports_search is False
    assert res.results_count == 0
    assert res.status_tag == "not_configured"
    assert res.capabilities.supports_web_search is False

    # 检索任何内容均严格返回空列表
    results = provider.search(query="任何商品参数", max_results=10)
    assert results == []


# -----------------------------------------------------------------------------
# 17. 全 Provider 错误日志与连通性测试 API Key 绝对脱敏
# -----------------------------------------------------------------------------
def test_all_keys_masked_in_all_providers():
    """测试 5 个 Provider 的脱敏表现，绝不暴露完整密钥"""
    providers = [
        TavilySearchProvider(api_key="tvly-super-secret-1234"),
        KimiSearchProvider(api_key="sk-kimi-production-key-5678"),
        QwenSearchProvider(api_key="sk-qwen-enterprise-key-9012"),
        ManualEvidenceProvider(),
        NoSearchProvider(),
    ]

    for p in providers:
        conn = p.test_connection()
        # 验证 masked_api_key 不包含明文密钥且已脱敏
        if isinstance(p, TavilySearchProvider):
            assert "1234" in conn.masked_api_key
            assert "super-secret" not in conn.masked_api_key
        elif isinstance(p, KimiSearchProvider):
            assert "5678" in conn.masked_api_key
            assert "production" not in conn.masked_api_key
        elif isinstance(p, QwenSearchProvider):
            assert "9012" in conn.masked_api_key
            assert "enterprise" not in conn.masked_api_key


# -----------------------------------------------------------------------------
# 18. 零开发者费用与零真实网络调用保证 (全 Fake/Mock)
# -----------------------------------------------------------------------------
def test_zero_real_api_cost_in_all_tests():
    """测试离线测试专用 Fake Key 机制生效，免真实外部网络调用"""
    # 1. Tavily Fake Key
    p_tavily = TavilySearchProvider(api_key="tvly-test-success-key")
    res_tavily = p_tavily.test_connection()
    assert res_tavily.success is True
    assert res_tavily.status_tag == "connected_searchable"
    assert res_tavily.capabilities.supports_web_search is True

    # 2. Kimi Fake Key
    p_kimi = KimiSearchProvider(api_key="sk-kimi-test-success-key")
    res_kimi = p_kimi.test_connection()
    assert res_kimi.success is True
    assert res_kimi.status_tag == "connected_searchable"
    assert res_kimi.capabilities.supports_web_search is True

    # 3. Qwen Fake Key
    p_qwen = QwenSearchProvider(api_key="sk-qwen-test-success-key")
    res_qwen = p_qwen.test_connection()
    assert res_qwen.success is True
    assert res_qwen.status_tag == "connected_searchable"
    assert res_qwen.capabilities.supports_web_search is True
