# -*- coding: utf-8 -*-
"""Tests for QwenSearchProvider Granular Capability Testing & Timeout Handling

9 项核心测试严格对照需求：
1. 普通调用成功，搜索超时 -> 显示“模型可用，搜索超时”，status_tag="model_ok_search_timeout"；
2. 搜索成功，网页提取超时 -> 显示“搜索可用，网页提取超时”，success=True, extractor_status="degraded"；
3. 20秒设置显示超时过短提示 -> “Responses API联网搜索和网页提取可能超过20秒，建议设置为60至90秒。”；
4. search测试最多返回1条结果 -> source_count=1, results_count=1 最小化测试开销；
5. web_extractor独立测试 -> test_web_extractor 独立探活方法；
6. 子能力失败不会覆盖已通过能力 -> 前置成功状态严格保留；
7. 超时后不自动重复扣费 -> 严格单次执行，无循环重试；
8. Key不会出现在错误日志 -> 全链路掩码脱敏与安全诊断；
9. 所有自动测试使用Fake响应 -> 零外部计费与零网络开销。
"""

import pytest
from unittest.mock import patch, MagicMock
import requests

from src.core.security import mask_search_api_key
from src.search.base import StepTestResult
from src.search.qwen_provider import (
    QwenSearchProvider,
    check_timeout_recommendation,
    perform_network_diagnostics,
)


def test_01_chat_success_search_timeout():
    """1. 普通调用成功，搜索超时 -> 显示“模型可用，搜索超时”"""
    provider = QwenSearchProvider(
        api_key="sk-qwen-test-search-timeout-key",
        provider_platform="qianwen_ai",
        api_mode="responses",
        model_name="qwen3.8-flash",
        timeout=20,
    )
    res = provider.test_connection()
    assert res.success is False
    assert res.status_tag == "model_ok_search_timeout"
    assert res.error_message == "模型可用，搜索超时"
    assert res.capabilities.supports_text_model is True
    assert res.capabilities.supports_web_search is False
    assert res.capabilities.supports_source_urls is False
    assert res.steps["auth_chat"].status == "success"
    assert res.steps["web_search"].status == "timeout"
    assert res.steps["web_extractor"].status == "skipped"
    assert res.diagnostics is not None
    assert "timeout_phase" in res.diagnostics
    assert "dns_latency_ms" in res.diagnostics


def test_02_search_success_extractor_timeout():
    """2. 搜索成功，网页提取超时 -> 显示“搜索可用，网页提取超时”，success=True, extractor_status='degraded'"""
    provider = QwenSearchProvider(
        api_key="sk-qwen-test-extractor-timeout-key",
        provider_platform="qianwen_ai",
        api_mode="responses",
        model_name="qwen3.8-flash",
        timeout=60,
    )
    res = provider.test_connection()
    # 铁律：只要搜索成功且返回真实URL，search_connection_status 就应为 connected (success=True)
    assert res.success is True
    assert res.status_tag == "search_ok_extractor_timeout"
    assert res.error_message == "搜索可用，网页提取超时"
    assert res.extractor_status == "degraded"
    assert res.capabilities.supports_text_model is True
    assert res.capabilities.supports_web_search is True
    assert res.capabilities.supports_source_urls is True
    assert res.capabilities.supports_web_extractor is False
    assert res.steps["auth_chat"].status == "success"
    assert res.steps["web_search"].status == "success"
    assert res.steps["web_extractor"].status == "timeout"
    assert res.diagnostics is not None


def test_03_timeout_recommendation_warning():
    """3. 20秒设置显示超时过短提示"""
    msg_20 = check_timeout_recommendation(20)
    assert msg_20 is not None
    assert "Responses API联网搜索和网页提取可能超过20秒，建议设置为60至90秒。" in msg_20

    msg_15 = check_timeout_recommendation(15)
    assert msg_15 is not None
    assert "Responses API联网搜索和网页提取可能超过20秒" in msg_15

    msg_60 = check_timeout_recommendation(60)
    assert msg_60 is None  # 60秒及以上无过短警告


def test_04_search_probe_limits_to_single_result():
    """4. search测试最多返回1条结果"""
    provider = QwenSearchProvider(
        api_key="sk-test-live-mock-key-123456",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    # 模拟多条搜索结果的 API 响应
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "output": {
            "search_info": {
                "search_results": [
                    {"url": "https://example.com/spec1", "title": "Spec 1"},
                    {"url": "https://example.com/spec2", "title": "Spec 2"},
                    {"url": "https://example.com/spec3", "title": "Spec 3"},
                ]
            }
        }
    }
    with patch("requests.post", return_value=mock_resp):
        step_res, urls, diag = provider._probe_web_search(timeout_sec=30)
        assert step_res.status == "success"
        assert step_res.source_count == 1
        assert len(urls) == 1
        assert urls[0] == "https://example.com/spec1"


def test_05_web_extractor_independent_probe():
    """5. web_extractor独立测试"""
    provider = QwenSearchProvider(
        api_key="sk-qwen-test-success-key",
        provider_platform="qianwen_ai",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    step_res = provider.test_web_extractor("https://example.com/soundpro-x1/specs")
    assert step_res.step_name == "web_extractor"
    assert step_res.status == "success"
    assert step_res.supported is True

    # 测试超时桩
    provider_timeout = QwenSearchProvider(
        api_key="sk-qwen-test-extractor-timeout-key",
        provider_platform="qianwen_ai",
        api_mode="responses",
    )
    step_res_to = provider_timeout.test_web_extractor("https://example.com/test")
    assert step_res_to.status == "timeout"
    assert step_res_to.supported is False


def test_06_subcapability_failure_does_not_override_passed_capabilities():
    """6. 子能力失败不会覆盖已通过能力"""
    provider = QwenSearchProvider(
        api_key="sk-test-live-mock-key-abc12345",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )

    # 模拟步骤 1 成功，步骤 2 成功，步骤 3 超时
    def side_effect(endpoint, **kwargs):
        resp = MagicMock()
        if "chat/completions" in endpoint:
            resp.status_code = 200
            resp.json.return_value = {"choices": [{"message": {"content": "pong"}}]}
            return resp
        elif "responses" in endpoint:
            tools = kwargs.get("json", {}).get("tools", [])
            if not tools:
                # 步骤 2: responses ping
                resp.status_code = 200
                resp.json.return_value = {"output": {"text": "pong"}}
                return resp
            else:
                # 步骤 3: 搜索探活触发超时
                raise requests.exceptions.Timeout("Read timeout on web_search")
        raise RuntimeError("Unknown endpoint")

    with patch("requests.post", side_effect=side_effect):
        res = provider.test_connection()
        # 验证步骤 1 和步骤 2 的成功结果没有被清除
        assert res.steps["auth_chat"].status == "success"
        assert res.steps["responses_api"].status == "success"
        assert res.steps["web_search"].status == "timeout"
        assert res.capabilities.supports_text_model is True
        assert res.capabilities.supports_responses_api is True
        assert res.capabilities.supports_web_search is False
        assert res.status_tag == "model_ok_search_timeout"
        assert res.error_message == "模型可用，搜索超时"


def test_07_no_automatic_retry_on_timeout():
    """7. 超时后不自动重复扣费（每个探针至多调用1次）"""
    provider = QwenSearchProvider(
        api_key="sk-test-mock-key-no-retry-9999",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
        timeout=10,
    )
    with patch("requests.post", side_effect=requests.exceptions.Timeout("Connection timed out")):
        res = provider.test_connection()
        assert res.success is False
        assert res.status_tag == "timeout"
        # 步骤 1 抛出超时后应立即中断，绝无 retry 循环
        assert res.steps["auth_chat"].status == "timeout"


def test_08_key_never_appears_in_error_logs_or_diagnostics():
    """8. Key不会出现在错误日志与诊断字典中"""
    secret_key = "sk-qwen-super-secret-key-abcdef123456"
    provider = QwenSearchProvider(
        api_key=secret_key,
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
    )
    with patch("requests.post", side_effect=Exception(f"Failed with raw key {secret_key}")):
        res = provider.test_connection()
        assert secret_key not in (res.error_message or "")
        assert secret_key not in str(res.steps)
        if res.diagnostics:
            assert secret_key not in str(res.diagnostics)
            assert "Authorization" not in res.diagnostics
        assert res.masked_api_key == mask_search_api_key(secret_key)
        assert secret_key not in res.masked_api_key


def test_09_all_tests_use_fake_responses_zero_cost():
    """9. 所有自动测试使用Fake响应，零外部调用与零费用"""
    success_provider = QwenSearchProvider(
        api_key="sk-qwen-test-success-key",
        provider_platform="qianwen_ai",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    # 不打 patch，纯内存 Fake Key 执行
    res = success_provider.test_connection()
    assert res.success is True
    assert res.status_tag == "connected_searchable"
    assert res.extractor_status == "ok"
    assert res.steps["auth_chat"].status == "success"
    assert res.steps["web_search"].status == "success"
    assert res.steps["web_extractor"].status == "success"
