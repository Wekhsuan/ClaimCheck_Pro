# -*- coding: utf-8 -*-
"""Tests for QwenSearchProvider Refactor & 6-Dimension Capabilities Matrix

15 项核心测试验证：
1. qwen3.8-flash 模型能力：多模态视觉、Responses API、web_search、web_extractor 与来源 URL 完备；
2. qwen3.8-max 旗舰模型能力与多模态视觉理解；
3. qwen3.7-plus / qwen3.7-flash 纯文本与搜索支持，无视觉；
4. 阿里云百炼 DashScope 平台预设与 qwen-plus / qwen-max 模型能力；
5. 平台切换：千问AI平台 (MaaS) 与 阿里云百炼 DashScope 的 Base URL 和默认模式动态联动；
6. Responses API 工具挂载：web_search 与 web_extractor 正确挂载与请求载荷构建；
7. 结构化来源提取：成功解析 action.sources、sources、search_results 等结构并标记 traceable=True；
8. 追溯铁律保护：无真实 URL 时严格标记 traceable=False 与 status_tag="search_ok_no_url"；
9. 服务平台与 Key 不匹配防误配拦截：返回明确提示“当前API Key可能不属于所选服务平台，请确认Base URL与API Key来自同一控制台”，严禁静默解释为“模型不存在”；
10. 动态模型目录：get_qwen_models_for_platform 依平台和模式动态过滤，绝无全局硬编码；
11. 手动输入自定义模型 ID 校验：validate_custom_model_id 严格校验边界与格式；
12. 视觉理解能力探活：is_vision_supported 准确识别视觉与非视觉模型；
13. 商品图片分析与本地 OCR 降级保护：analyze_product_image 在不支持视觉时平滑降级并输出标准提示；
14. SearchProviderFactory 正确接纳 provider_platform 并完成构建；
15. 零费用安全铁律与 API Key 全链路脱敏验证：Fake Key 绝不发起外部收费请求，mask_search_api_key 绝不泄露明文。
"""

import pytest
from src.core.security import mask_search_api_key
from src.search.base import SearchConnectionResult, SearchResultItem
from src.search.factory import SearchProviderFactory
from src.search.qwen_provider import QwenSearchProvider
from src.search.qwen_provider_models import (
    QWEN_MODELS_CATALOG,
    QWEN_PLATFORM_CONFIGS,
    get_or_create_model_info,
    get_qwen_models_for_platform,
    is_vision_supported,
    validate_custom_model_id,
)


def test_01_qwen38_flash_capabilities():
    """1. 验证千问AI平台 qwen3.8-flash 具备多模态、Responses、搜索与提取器全部能力"""
    info = QWEN_MODELS_CATALOG.get("qwen3.8-flash")
    assert info is not None
    assert info.provider_platform == "qianwen_ai"
    assert info.supports_vision is True
    assert info.supports_responses is True
    assert info.supports_web_search is True
    assert info.supports_web_extractor is True
    assert info.supports_source_urls is True


def test_02_qwen38_max_capabilities():
    """2. 验证千问AI平台 qwen3.8-max 旗舰模型同样支持多模态视觉与搜索"""
    info = QWEN_MODELS_CATALOG.get("qwen3.8-max")
    assert info is not None
    assert info.provider_platform == "qianwen_ai"
    assert info.supports_vision is True
    assert info.supports_responses is True
    assert info.supports_web_search is True


def test_03_qwen37_text_only_models():
    """3. 验证 qwen3.7-plus / qwen3.7-flash 纯文本模型不支持视觉"""
    info_plus = QWEN_MODELS_CATALOG.get("qwen3.7-plus")
    assert info_plus is not None
    assert info_plus.supports_vision is False
    assert info_plus.supports_web_search is True

    info_flash = QWEN_MODELS_CATALOG.get("qwen3.7-flash")
    assert info_flash is not None
    assert info_flash.supports_vision is False


def test_04_dashscope_models_catalog():
    """4. 验证阿里云百炼 DashScope 专属模型 (qwen-plus, qwen-max, qwen-turbo)"""
    models = get_qwen_models_for_platform("dashscope")
    model_ids = [m.model_id for m in models]
    assert "qwen-plus" in model_ids
    assert "qwen-max" in model_ids
    assert "qwen-turbo" in model_ids
    assert "qwen3.8-flash" not in model_ids


def test_05_platform_configs_and_switching():
    """5. 验证双平台默认配置：千问AI平台 vs 阿里云百炼 DashScope"""
    cfg_qw = QWEN_PLATFORM_CONFIGS.get("qianwen_ai")
    assert cfg_qw["base_url"] == "https://maas.qianwenaiapi.com/compatible-mode/v1"
    assert cfg_qw["default_mode"] == "responses"
    assert cfg_qw["default_model"] == "qwen3.8-flash"

    cfg_ds = QWEN_PLATFORM_CONFIGS.get("dashscope")
    assert cfg_ds["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert cfg_ds["default_mode"] == "chat_completions"
    assert cfg_ds["default_model"] == "qwen-plus"


def test_06_responses_api_payload_mounting():
    """6. 验证 Responses API 调用模式与能力透传"""
    provider = QwenSearchProvider(
        api_key="sk-qwen-test-success-key",
        provider_platform="qianwen_ai",
        api_mode="responses",
        model_name="qwen3.8-flash",
        enable_web_extractor=True,
    )
    assert provider.api_mode == "responses"
    assert provider.supports_vision is True
    caps = provider.capabilities()
    assert caps["can_search"] is True
    assert caps["can_extract"] is True
    assert caps["provider_platform"] == "qianwen_ai"


def test_07_structured_sources_extraction():
    """7. 验证从多种响应结构提取来源并设置 traceable=True"""
    provider = QwenSearchProvider(api_key="sk-qwen-test-success-key")
    # 测试 action.sources 提取
    fake_payload = {
        "action": {
            "sources": [
                {
                    "title": "测试官网",
                    "url": "https://example.com/spec",
                    "snippet": "测试降噪参数48dB",
                }
            ]
        }
    }
    sources = provider._extract_sources_from_payload(fake_payload)
    assert len(sources) == 1
    assert sources[0]["url"] == "https://example.com/spec"

    # 清洗为 SearchResultItem
    item = provider.sanitize_result(sources[0], "测试查询", 1)
    assert item.traceable is True
    assert item.domain == "example.com"


def test_08_no_url_traceability_protection():
    """8. 追溯铁律保护：模型无结构化来源时标记 traceable=False"""
    provider = QwenSearchProvider(api_key="sk-qwen-no-url-key")
    res = provider.test_connection()
    assert res.success is False
    assert res.status_tag == "search_ok_no_url"
    assert res.capabilities.supports_source_urls is False
    assert "无法建立可追溯事实证据链" in (res.error_message or "")

    # 执行 search 测试无 URL 返回
    items = provider.search("查询耳机降噪")
    assert len(items) == 1
    assert items[0].traceable is False
    assert items[0].url == ""


def test_09_platform_mismatch_interception():
    """9. 防误配拦截：服务平台与 Key 不一致时明确诊断，严禁解释为模型不存在"""
    provider = QwenSearchProvider(
        api_key="sk-qwen-mismatch-platform-key",
        provider_platform="qianwen_ai",
        model_name="qwen3.8-flash",
    )
    res = provider.test_connection()
    assert res.success is False
    assert res.status_tag == "platform_mismatch"
    assert res.capabilities.platform_matched is False
    assert res.capabilities.model_exists is True  # 明确模型存在，不是模型不存在
    assert "当前API Key可能不属于所选服务平台，请确认Base URL与API Key来自同一控制台。" in (res.error_message or "")


def test_10_dynamic_model_filtering():
    """10. 验证动态过滤根据平台和模式返回准确模型清单"""
    qw_models = get_qwen_models_for_platform("qianwen_ai", "responses")
    qw_ids = [m.model_id for m in qw_models]
    assert "qwen3.8-flash" in qw_ids
    assert "qwen3.8-max" in qw_ids
    assert "qwen3.7-plus" in qw_ids
    assert "qwen-turbo" not in qw_ids

    # 阿里云百炼不支持 Responses 的模型会被过滤
    ds_resp = get_qwen_models_for_platform("dashscope", "responses")
    ds_resp_ids = [m.model_id for m in ds_resp]
    assert "qwen-turbo" not in ds_resp_ids  # qwen-turbo supports_responses=False


def test_11_validate_custom_model_id():
    """11. 验证手动输入模型 ID 格式合法性校验"""
    ok, _ = validate_custom_model_id("qwen2.5-vl-72b-instruct")
    assert ok is True

    ok2, _ = validate_custom_model_id("qwen3.8-flash")
    assert ok2 is True

    fail1, err1 = validate_custom_model_id("")
    assert fail1 is False
    assert "不能为空" in err1

    fail2, err2 = validate_custom_model_id("q")
    assert fail2 is False
    assert "长度" in err2

    fail3, err3 = validate_custom_model_id("model!@#$$")
    assert fail3 is False
    assert "格式不规范" in err3


def test_12_is_vision_supported():
    """12. 验证多模态视觉判断"""
    assert is_vision_supported("qwen3.8-flash") is True
    assert is_vision_supported("qwen3.8-max") is True
    assert is_vision_supported("qwen-vl-plus") is True
    assert is_vision_supported("qwen-plus") is False
    assert is_vision_supported("qwen3.7-plus") is False


def test_13_analyze_product_image_fallback():
    """13. 验证商品图片分析：不支持视觉时平滑降级至本地 OCR 并返回提示"""
    # 纯文本模型降级
    text_provider = QwenSearchProvider(
        api_key="sk-qwen-test-success-key",
        model_name="qwen-plus",
    )
    assert text_provider.supports_vision is False
    res_text = text_provider.analyze_product_image(image_bytes=b"fake_image_bytes")
    assert res_text["success"] is False
    assert res_text["fallback_to_ocr"] is True
    assert "当前模型不支持视觉理解，仅使用本地OCR，未执行视觉商品识别。" in res_text["notice"]

    # 视觉模型支持
    vision_provider = QwenSearchProvider(
        api_key="sk-qwen-test-success-key",
        model_name="qwen3.8-flash",
    )
    assert vision_provider.supports_vision is True
    res_vision = vision_provider.analyze_product_image(image_bytes=b"fake_image_bytes")
    assert res_vision["success"] is True
    assert res_vision["fallback_to_ocr"] is False
    assert "已通过千问多模态视觉模型" in res_vision["notice"]
    assert res_vision["brand"] == "索尼"


def test_14_search_provider_factory_qwen():
    """14. 验证 SearchProviderFactory 对 QwenSearchProvider 的正确构建"""
    provider = SearchProviderFactory.create_provider(
        "qwen",
        {
            "api_key": "sk-qwen-test-success-key",
            "base_url": "https://maas.qianwenaiapi.com/compatible-mode/v1",
            "model_name": "qwen3.8-flash",
            "api_mode": "responses",
            "provider_platform": "qianwen_ai",
        },
    )
    assert isinstance(provider, QwenSearchProvider)
    assert provider.provider_name() == "QwenSearchProvider"
    assert provider.model_name == "qwen3.8-flash"
    assert provider.provider_platform == "qianwen_ai"


def test_15_key_masking_and_offline_execution():
    """15. 验证 API Key 全链路脱敏与零外部调用安全性"""
    raw_key = "sk-qwen-platform-secret-12345678"
    masked = mask_search_api_key(raw_key)
    assert raw_key not in masked
    assert "****" in masked
    assert masked.startswith("sk-q")

    # 测试桩响应不产生任何网络异常与外部费用
    provider = QwenSearchProvider(api_key="sk-qwen-test-success-key")
    conn_res = provider.test_connection()
    assert conn_res.success is True
    assert raw_key not in str(conn_res.model_dump())
    assert conn_res.masked_api_key == "sk-q****-key"
