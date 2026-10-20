# -*- coding: utf-8 -*-
"""14项针对通义千问 Responses API 来源结构解析与路由修正专项测试 (零外部调用与离线 Fake Key)

1. dict形态output单web_search_call解析成功
2. object形态output单web_search_call解析成功
3. 多个web_search_call合并解析
4. sources中URL去重与非http/https过滤
5. output无web_search_call返回web_search_tool_not_called
6. sources存在但URL格式全无效返回source_parse_failed
7. sources完全为空时正确返回search_ok_no_url (不出现误导性切换建议)
8. UI选择responses时后端严格请求/responses
9. 鉴权探针在responses模式下请求/responses而非/chat/completions
10. 修改服务来源重置测试状态
11. 修改模型重置测试状态
12. 修改API模式重置测试状态
13. 修改web_extractor开关重置测试状态
14. call_debug_info和source_diagnostics不泄露任何API Key
"""

import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from src.search.base import SearchConnectionResult
from src.search.qwen_provider import (
    QwenSearchProvider,
    extract_responses_sources_and_summary,
)
from streamlit_app.ui.layout import clear_search_test_state


# 1. dict形态output单web_search_call解析成功
def test_01_extract_sources_dict_single_web_search_call():
    payload = {
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "sources": [
                        {
                            "title": "官方声学实验室测评",
                            "url": "https://specs.example.com/soundpro-x1",
                            "snippet": "实测最大降噪深度为48dB，达到标称规格。",
                        }
                    ]
                },
            },
            {
                "type": "message",
                "role": "assistant",
                "content": "根据检索到的资料，该产品降噪确实达到48dB。",
            },
        ]
    }
    valid_sources, summary, raw_sources = extract_responses_sources_and_summary(payload)
    assert len(valid_sources) == 1
    assert valid_sources[0]["url"] == "https://specs.example.com/soundpro-x1"
    assert valid_sources[0]["title"] == "官方声学实验室测评"
    assert summary["output_item_count"] == 2
    assert summary["has_web_search_call"] is True
    assert summary["has_action"] is True
    assert summary["sources_count"] == 1
    assert summary["valid_url_count"] == 1
    assert summary["sources_have_url"] is True
    assert summary["web_search_tool_count"] == 1


# 2. object形态output单web_search_call解析成功
def test_02_extract_sources_object_single_web_search_call():
    source_obj = SimpleNamespace(
        title="官方声学实验室测评(对象)",
        url="https://specs.example.com/soundpro-obj",
        snippet="对象属性解析测试，最大降噪深度48dB。",
        site_name="Example Official",
    )
    action_obj = SimpleNamespace(sources=[source_obj])
    item_search = SimpleNamespace(type="web_search_call", action=action_obj)
    item_msg = SimpleNamespace(type="message", role="assistant", content="回答内容")
    response_obj = SimpleNamespace(output=[item_search, item_msg])

    valid_sources, summary, raw_sources = extract_responses_sources_and_summary(response_obj)
    assert len(valid_sources) == 1
    assert valid_sources[0]["url"] == "https://specs.example.com/soundpro-obj"
    assert valid_sources[0]["title"] == "官方声学实验室测评(对象)"
    assert summary["output_item_count"] == 2
    assert summary["has_web_search_call"] is True
    assert summary["valid_url_count"] == 1


# 3. 多个web_search_call合并解析
def test_03_extract_sources_multiple_web_search_calls_merged():
    payload = {
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "sources": [
                        {
                            "title": "来源1",
                            "url": "https://site1.example.com/a",
                            "snippet": "内容1",
                        }
                    ]
                },
            },
            {
                "type": "web_search_call",
                "action": {
                    "sources": [
                        {
                            "title": "来源2",
                            "url": "https://site2.example.com/b",
                            "snippet": "内容2",
                        }
                    ]
                },
            },
        ]
    }
    valid_sources, summary, raw_sources = extract_responses_sources_and_summary(payload)
    assert len(valid_sources) == 2
    assert summary["output_item_count"] == 2
    assert summary["web_search_tool_count"] == 2
    assert summary["valid_url_count"] == 2
    urls = [s["url"] for s in valid_sources]
    assert "https://site1.example.com/a" in urls
    assert "https://site2.example.com/b" in urls


# 4. sources中URL去重与非http/https过滤
def test_04_extract_sources_deduplication_and_non_http_filtered():
    payload = {
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "sources": [
                        {"title": "条目1", "url": "https://site1.example.com/test"},
                        {"title": "条目1重复", "url": "https://site1.example.com/test/"},  # 末尾斜杠去重
                        {"title": "非法协议", "url": "ftp://files.example.com/doc"},
                        {"title": "JavaScript伪协议", "url": "javascript:alert(1)"},
                        {"title": "无域名URL", "url": "not-a-valid-url"},
                        {"title": "空URL", "url": ""},
                        {"title": "合法HTTP条目", "url": "http://site2.example.com/spec"},
                    ]
                },
            }
        ]
    }
    valid_sources, summary, raw_sources = extract_responses_sources_and_summary(payload)
    assert summary["sources_count"] == 7
    assert len(valid_sources) == 2
    assert summary["valid_url_count"] == 2
    urls = [s["url"] for s in valid_sources]
    assert "https://site1.example.com/test" in urls
    assert "http://site2.example.com/spec" in urls


# 5. output无web_search_call返回web_search_tool_not_called
def test_05_status_web_search_tool_not_called():
    # 使用测试桩 Key 验证
    provider = QwenSearchProvider(
        api_key="sk-qwen-no-tool-call-key",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    res = provider.test_connection(ui_selected_mode="responses")
    assert res.success is False
    assert res.status_tag == "web_search_tool_not_called"
    assert "web_search_tool_not_called" in res.error_message
    assert res.source_diagnostics["has_web_search_call"] is False

    # 验证真实 probe 逻辑下 mock requests 返回无 web_search_call
    live_prov = QwenSearchProvider(
        api_key="sk-live-mock-test-key-12345",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    with patch("requests.post") as mock_post:
        # step 1 auth_chat ping 成功
        mock_auth_resp = MagicMock()
        mock_auth_resp.status_code = 200
        mock_auth_resp.json.return_value = {"output": [{"type": "message", "content": "pong"}]}

        # step 2 responses ping 成功
        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = {"output": []}

        # step 3 web_search 返回无 web_search_call 的纯 message
        mock_search_resp = MagicMock()
        mock_search_resp.status_code = 200
        mock_search_resp.json.return_value = {
            "output": [
                {"type": "message", "role": "assistant", "content": "我直接生成了回答，没有调用工具。"}
            ]
        }

        mock_post.side_effect = [mock_auth_resp, mock_resp2, mock_search_resp]
        real_res = live_prov.test_connection(ui_selected_mode="responses")
        assert real_res.status_tag == "web_search_tool_not_called"
        assert real_res.success is False


# 6. sources存在但URL格式全无效返回source_parse_failed
def test_06_status_source_parse_failed():
    # 测试桩 Key 验证
    provider = QwenSearchProvider(
        api_key="sk-qwen-source-parse-fail-key",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    res = provider.test_connection(ui_selected_mode="responses")
    assert res.success is False
    assert res.status_tag == "source_parse_failed"
    assert res.source_diagnostics["sources_count"] > 0
    assert res.source_diagnostics["valid_url_count"] == 0

    # 验证真实 probe 逻辑下 mock requests 返回无效 URL sources
    live_prov = QwenSearchProvider(
        api_key="sk-live-mock-test-key-12345",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    with patch("requests.post") as mock_post:
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {"output": []}

        mock_search_resp = MagicMock()
        mock_search_resp.status_code = 200
        mock_search_resp.json.return_value = {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [
                            {"title": "错误标题", "url": "invalid-url-schema"},
                            {"title": "第二条", "url": "javascript:void(0)"},
                        ]
                    },
                }
            ]
        }
        mock_post.side_effect = [mock_ok, mock_ok, mock_search_resp]
        real_res = live_prov.test_connection(ui_selected_mode="responses")
        assert real_res.status_tag == "source_parse_failed"
        assert real_res.success is False


# 7. sources完全为空时正确返回search_ok_no_url (不出现误导性切换建议)
def test_07_status_search_ok_no_url():
    # 测试桩 Key 验证：在 responses 模式下，提示语不得建议切换至 Responses API 模式
    provider_resp = QwenSearchProvider(
        api_key="sk-qwen-no-url-key",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    res_resp = provider_resp.test_connection(ui_selected_mode="responses")
    assert res_resp.success is False
    assert res_resp.status_tag == "search_ok_no_url"
    assert "建议切换至 Responses API" not in res_resp.error_message
    assert "建议更换检索词" in res_resp.error_message

    # 在 chat_completions 模式下，才允许建议切换为 Responses API
    provider_chat = QwenSearchProvider(
        api_key="sk-qwen-no-url-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_mode="chat_completions",
        model_name="qwen-plus",
    )
    res_chat = provider_chat.test_connection(ui_selected_mode="chat_completions")
    assert res_chat.status_tag == "search_ok_no_url"
    assert "建议切换至 Responses API" in res_chat.error_message


# 8. UI选择responses时后端严格请求/responses
def test_08_ui_selected_responses_routes_to_responses_endpoint():
    provider = QwenSearchProvider(
        api_key="sk-live-mock-test-key-12345",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [{"title": "来源", "url": "https://example.com/ok"}]
                    },
                }
            ]
        }
        mock_post.return_value = mock_resp

        res = provider.test_connection(ui_selected_mode="responses")
        assert res.success is True
        for call_args in mock_post.call_args_list:
            endpoint_called = call_args[0][0]
            assert endpoint_called.endswith("/responses")
            assert not endpoint_called.endswith("/chat/completions")

    # 若 UI 选择了 responses 但 provider 传了 chat_completions，触发 responses_mode_not_applied
    mismatch_prov = QwenSearchProvider(
        api_key="sk-live-mock-test-key-12345",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="chat_completions",
        model_name="qwen-plus",
    )
    res_mismatch = mismatch_prov.test_connection(ui_selected_mode="responses")
    assert res_mismatch.status_tag == "responses_mode_not_applied"
    assert res_mismatch.success is False


# 9. 鉴权探针在responses模式下请求/responses而非/chat/completions
def test_09_auth_probe_in_responses_mode_targets_responses_not_chat():
    provider = QwenSearchProvider(
        api_key="sk-live-mock-test-key-12345",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"output": []}
        mock_post.return_value = mock_resp

        step_res, diag = provider._probe_chat_completion(timeout_sec=10)
        assert step_res.status == "success"
        call_url = mock_post.call_args[0][0]
        call_json = mock_post.call_args[1]["json"]
        assert call_url == "https://maas.qianwenaiapi.com/compatible-mode/v1/responses"
        assert call_json["input"] == "ping"
        assert "messages" not in call_json


# 10. 修改服务来源重置测试状态
def test_10_state_reset_on_platform_change():
    mock_session = {
        "search_test_result": SearchConnectionResult(
            success=True, provider_name="Qwen", status_tag="connected_searchable"
        ),
        "search_connection_status": "connected",
        "search_connection_latency": 150,
    }
    with patch("streamlit.session_state", mock_session):
        clear_search_test_state()
        assert mock_session["search_test_result"] is None
        assert mock_session["search_connection_status"] == "not_tested"
        assert mock_session["search_connection_latency"] == 0


# 11. 修改模型重置测试状态
def test_11_state_reset_on_model_change():
    mock_session = {
        "qwen_search_model": "qwen3.8-flash",
        "search_test_result": SearchConnectionResult(
            success=True, provider_name="Qwen", status_tag="connected_searchable"
        ),
        "search_connection_status": "connected",
    }
    with patch("streamlit.session_state", mock_session):
        # 模拟用户变更模型
        new_model = "qwen3.8-max"
        if new_model != mock_session["qwen_search_model"]:
            mock_session["qwen_search_model"] = new_model
            clear_search_test_state()
        assert mock_session["search_test_result"] is None
        assert mock_session["search_connection_status"] == "not_tested"


# 12. 修改API模式重置测试状态
def test_12_state_reset_on_api_mode_change():
    mock_session = {
        "qwen_search_api_mode": "chat_completions",
        "search_test_result": SearchConnectionResult(
            success=False, provider_name="Qwen", status_tag="search_ok_no_url"
        ),
        "search_connection_status": "failed",
    }
    with patch("streamlit.session_state", mock_session):
        # 模拟用户将模式切换为 responses
        new_mode = "responses"
        if new_mode != mock_session["qwen_search_api_mode"]:
            mock_session["qwen_search_api_mode"] = new_mode
            clear_search_test_state()
        assert mock_session["search_test_result"] is None
        assert mock_session["search_connection_status"] == "not_tested"


# 13. 修改web_extractor开关重置测试状态
def test_13_state_reset_on_web_extractor_change():
    mock_session = {
        "qwen_enable_web_extractor": True,
        "search_test_result": SearchConnectionResult(
            success=True, provider_name="Qwen", status_tag="connected_searchable"
        ),
        "search_connection_status": "connected",
    }
    with patch("streamlit.session_state", mock_session):
        # 模拟用户关闭提取器
        new_extractor = False
        if new_extractor != mock_session["qwen_enable_web_extractor"]:
            mock_session["qwen_enable_web_extractor"] = new_extractor
            clear_search_test_state()
        assert mock_session["search_test_result"] is None
        assert mock_session["search_connection_status"] == "not_tested"


# 14. call_debug_info和source_diagnostics不泄露任何API Key
def test_14_call_debug_and_source_diagnostics_no_key_leak():
    fake_secret = "sk-super-secret-key-1234567890abcdef"
    provider = QwenSearchProvider(
        api_key=fake_secret,
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [{"title": "标题", "url": "https://example.com/item"}]
                    },
                }
            ]
        }
        mock_post.return_value = mock_resp

        res = provider.test_connection(ui_selected_mode="responses")

        # 检查 debug 字典和诊断字段中均未出现原始密钥
        assert res.call_debug_info is not None
        assert res.source_diagnostics is not None

        call_debug_str = str(res.call_debug_info)
        source_diag_str = str(res.source_diagnostics)

        assert fake_secret not in call_debug_str
        assert fake_secret not in source_diag_str
        assert fake_secret not in str(res.model_dump())
        # 允许脱敏后的 Key
        assert res.masked_api_key.startswith("sk-")
        assert res.masked_api_key != fake_secret


# 15. web_search_tool_not_attached 状态标签与诊断
def test_15_status_tag_web_search_tool_not_attached():
    provider = QwenSearchProvider(
        api_key="sk-qwen-tool-not-attached-key",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    res = provider.test_connection(ui_selected_mode="responses")
    assert res.success is False
    assert res.status_tag == "web_search_tool_not_attached"
    assert "web_search_tool_not_attached" in res.error_message
    assert res.call_debug_info is not None
    assert res.call_debug_info.get("tools_array") == []


# 16. web_search_called_no_sources 状态标签与诊断
def test_16_status_tag_web_search_called_no_sources():
    provider = QwenSearchProvider(
        api_key="sk-qwen-called-no-sources-key",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    res = provider.test_connection(ui_selected_mode="responses")
    assert res.success is False
    assert res.status_tag == "web_search_called_no_sources"
    assert "web_search_called_no_sources" in res.error_message
    assert res.source_diagnostics is not None
    assert res.source_diagnostics.get("has_web_search_call") is True
    assert res.source_diagnostics.get("sources_count") == 0


# 17. output 项脱敏结构摘要 output_items_summary 符合规范四
def test_17_output_items_summary_structure():
    payload = {
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "type": "web_search",
                    "sources": [
                        {"title": "官网文档", "url": "https://help.aliyun.com/doc", "snippet": "文档正文"}
                    ],
                },
            },
            {
                "type": "message",
                "role": "assistant",
                "content": "根据搜索结果...",
            },
        ]
    }
    valid_sources, summary, raw_sources = extract_responses_sources_and_summary(payload)
    items_summary = summary.get("output_items_summary", [])
    assert len(items_summary) == 2
    assert items_summary[0]["type"] == "web_search_call"
    assert items_summary[0]["has_action"] is True
    assert items_summary[0]["action_type"] == "web_search"
    assert items_summary[0]["source_count"] == 1
    assert items_summary[1]["type"] == "message"
    assert items_summary[1]["has_content"] is True


# 18. OpenAI Python 版本安全检测与 SDK 标识
def test_18_openai_package_version_detection():
    from src.search.qwen_provider import _detect_openai_package_version
    ver = _detect_openai_package_version()
    assert isinstance(ver, str)
    assert ver in ("未安装", "已安装(未知版本)") or ver.replace(".", "").isdigit()


# 19. call_debug_info 包含规范一全部脱敏审计字段
def test_19_call_debug_info_complete_audit_fields():
    provider = QwenSearchProvider(
        api_key="sk-qwen-test-success-key",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    res = provider.test_connection(ui_selected_mode="responses")
    dbg = res.call_debug_info
    assert dbg is not None
    assert dbg.get("http_method") == "POST"
    assert dbg.get("request_endpoint", "").endswith("/responses")
    assert dbg.get("request_model") == "qwen3.8-flash"
    assert isinstance(dbg.get("tools_array"), list)
    assert any(t.get("type") == "web_search" for t in dbg.get("tools_array", []))
    assert dbg.get("tool_choice") == "未设置"
    assert dbg.get("has_enable_search") is False
    assert dbg.get("has_search_options") is False
    assert "sdk_version" in dbg
    assert "openai_package_version" in dbg
    assert "2026年10月" in dbg.get("input_query", "")


# 20. 真实探针请求体输入使用近期互联网内容强制检索
def test_20_probe_web_search_payload_forces_internet_search():
    provider = QwenSearchProvider(
        api_key="sk-test-real-shape",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        api_mode="responses",
        model_name="qwen3.8-flash",
    )
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {"sources": [{"url": "https://help.aliyun.com/item"}]},
                }
            ]
        }
        mock_post.return_value = mock_resp
        provider._probe_web_search(timeout_sec=10)

        # 检查发往请求端点与 payload
        called_args, called_kwargs = mock_post.call_args
        assert called_args[0] == "https://maas.qianwenaiapi.com/compatible-mode/v1/responses"
        sent_json = called_kwargs.get("json", {})
        assert "2026年10月" in sent_json.get("input", "")
        assert sent_json.get("tools") == [{"type": "web_search"}]

