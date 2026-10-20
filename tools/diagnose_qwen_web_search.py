#!/usr/bin/env python3
"""
Qwen Web Search Diagnostic Tool
================================
Standalone script to diagnose web_search tool integration with the Qwen Responses API.

Strictly follows ClaimCheck Pro Security & Zero-Cost Principles:
1. Zero fake URLs / Zero fabricated data
2. NEVER print or log API Key, Authorization header, or Cookie
3. Exactly ONE request (NO automatic retries, NO quota waste)
4. Sanitized request & response structure diagnostics (Section 1 to 5)

Usage:
    set QWEN_API_KEY=sk-...
    python tools/diagnose_qwen_web_search.py

Optional env vars:
    QWEN_BASE_URL  - API base URL (default: https://maas.qianwenaiapi.com/compatible-mode/v1)
    QWEN_MODEL     - Model name (default: qwen3.8-flash)
"""

import json
import os
import re
import sys
import time

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library is required. Install with: pip install requests")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration (Section 2: Exact Query & Tools)
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://maas.qianwenaiapi.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.8-flash"

# 用户明确指定的问题 (规范二)
TEST_QUERY = (
    "请实际调用web_search，搜索千问AI平台在2026年10月发布或更新的联网搜索官方文档。"
    "必须返回至少一个来自官方域名的HTTP或HTTPS来源URL。禁止仅依赖模型内部知识回答。"
)

TOOLS = [{"type": "web_search"}]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_openai_version() -> str:
    try:
        import openai  # type: ignore
        return getattr(openai, "__version__", "已安装(未知版本)")
    except ImportError:
        return "未安装"


def _sanitize(value: str, *, visible_chars: int = 4) -> str:
    """Mask a secret string, showing only the last few characters."""
    if not value:
        return "(empty)"
    if len(value) <= visible_chars:
        return "***"
    return f"***{value[-visible_chars:]}"


def _extract_urls(text: str) -> list[str]:
    """Extract http/https URLs from text."""
    if not text:
        return []
    return re.findall(r"https?://[^\s\)\]\">]+", text)


def _print_section(title: str) -> None:
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


# ---------------------------------------------------------------------------
# Main diagnostic
# ---------------------------------------------------------------------------

def main() -> None:
    print("Qwen Web Search Standalone Diagnostic")
    print("-" * 50)

    # ---- Resolve API key ----
    api_key = os.environ.get("QWEN_API_KEY", "").strip()
    if not api_key:
        try:
            api_key = input("Enter QWEN_API_KEY (will not be logged): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(1)

    if not api_key:
        print("ERROR: No API key provided. Set QWEN_API_KEY or enter at prompt.")
        sys.exit(1)

    # ---- Resolve optional config ----
    base_url = os.environ.get("QWEN_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("QWEN_MODEL", DEFAULT_MODEL)
    endpoint = f"{base_url}/responses"

    # ---- Build request (Section 1 & Section 3: Equivalent to client.responses.create) ----
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload = {
        "model": model,
        "input": TEST_QUERY,
        "tools": TOOLS,
    }

    openai_ver = _detect_openai_version()

    # ---- Print sanitized request summary (Section 1) ----
    _print_section("一、脱敏请求摘要 (REQUEST SUMMARY)")
    print(f"  HTTP 方法          : POST")
    print(f"  实际请求端点        : {endpoint}")
    print(f"  请求模型 (model)   : {model}")
    print(f"  测试输入问题        : {TEST_QUERY}")
    print(f"  Tools 完整数组结构  : {json.dumps(TOOLS, ensure_ascii=False)}")
    print(f"  tool_choice        : 未设置")
    print(f"  是否存在 enable_search: False")
    print(f"  是否存在 search_options: False")
    print(f"  SDK 版本           : raw_requests (openai {openai_ver})")
    print(f"  OpenAI Python 包版本: {openai_ver}")
    print(f"  API Key (已脱敏)    : {_sanitize(api_key)}")
    print("  [安全审计确认] 未打印完整 API Key，未打印 Authorization Header，未打印 Cookie")

    # ---- Send request (single attempt, no retry) ----
    _print_section("二、执行单次请求 (NO RETRY)")
    print("  正在向 Responses API 发送单次诊断探针...")

    t0 = time.perf_counter()
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=90)
    except requests.RequestException as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(f"\n  连接异常 (耗时 {elapsed_ms:.0f} ms): {type(exc).__name__}: {exc}")
        _print_summary(False, "网络连接异常或超时", status_tag="connection_error")
        sys.exit(1)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # ---- Analyse response (Section 4) ----
    _print_section("三、真实响应结构解析 (RESPONSE ANALYSIS)")
    print(f"  HTTP 状态码        : {resp.status_code}")
    print(f"  响应耗时           : {elapsed_ms:.0f} ms")

    if resp.status_code != 200:
        print(f"\n  错误响应内容 (前500字符):")
        print(f"  {resp.text[:500]}")
        _print_summary(False, f"HTTP {resp.status_code}", status_tag=f"http_{resp.status_code}")
        sys.exit(1)

    try:
        data = resp.json()
    except ValueError:
        print("  错误: 响应不是合法的 JSON")
        print(f"  原始响应前200字符: {resp.text[:200]}")
        _print_summary(False, "JSON 解析失败", status_tag="json_parse_error")
        sys.exit(1)

    # ---- Output items analysis (Section 4 structure summary) ----
    output_items = data.get("output", [])
    if isinstance(output_items, dict):
        output_items = output_items.get("items", [output_items])
    if not isinstance(output_items, list):
        output_items = []

    output_count = len(output_items)
    output_types = [str(item.get("type", "") or "") for item in output_items if isinstance(item, dict)]

    # 规范四: 提取 output 项脱敏结构摘要
    output_items_summary = []
    has_web_search_call = False
    web_search_call_count = 0
    web_extractor_call_count = 0
    reasoning_count = 0
    message_count = 0
    extracted_sources = []

    for item in output_items:
        if not isinstance(item, dict):
            continue
        itype = str(item.get("type", "") or "")
        action = item.get("action")
        action_type = str(action.get("type", "") or "") if isinstance(action, dict) else ""
        
        # Sources in action or item
        sources_list = []
        if isinstance(action, dict) and isinstance(action.get("sources"), list):
            sources_list = action["sources"]
        elif isinstance(item.get("sources"), list):
            sources_list = item["sources"]

        item_src_count = len(sources_list)
        has_content = bool(item.get("content") or item.get("text"))

        output_items_summary.append({
            "type": itype,
            "has_action": action is not None,
            "action_type": action_type,
            "source_count": item_src_count,
            "has_content": has_content,
        })

        if itype == "web_search_call":
            has_web_search_call = True
            web_search_call_count += 1
            for s in sources_list:
                if isinstance(s, dict):
                    extracted_sources.append(s)
        elif itype in ("web_extractor_call", "web_extractor"):
            web_extractor_call_count += 1
        elif itype in ("reasoning", "thinking"):
            reasoning_count += 1
        elif itype == "message":
            message_count += 1

    # Extract URLs from sources and text
    raw_source_count = len(extracted_sources)
    valid_http_urls = []
    for s in extracted_sources:
        u = str(s.get("url", "") or "").strip()
        if u and (u.startswith("http://") or u.startswith("https://")):
            if u not in valid_http_urls:
                valid_http_urls.append(u)

    # Usage stats
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    x_tools = usage.get("x_tools", {}) if isinstance(usage, dict) else {}
    ws_usage = x_tools.get("web_search", {}) if isinstance(x_tools, dict) else {}
    usage_ws_count = ws_usage.get("count") if isinstance(ws_usage, dict) else None

    # Print Section 4 required fields
    print(f"  output_count                 : {output_count}")
    print(f"  output_types                 : {output_types}")
    print(f"  reasoning_count              : {reasoning_count}")
    print(f"  web_search_call_count        : {web_search_call_count}")
    print(f"  web_extractor_call_count     : {web_extractor_call_count}")
    print(f"  message_count                : {message_count}")
    print(f"  source_count                 : {raw_source_count}")
    print(f"  valid_http_url_count         : {len(valid_http_urls)}")
    print(f"  usage.x_tools.web_search.count: {usage_ws_count if usage_ws_count is not None else '(无)'}")

    _print_section("四、output 结构条目摘要 (规范四)")
    print(json.dumps(output_items_summary, ensure_ascii=False, indent=2))

    if valid_http_urls:
        _print_section("五、来源 URL 抽样 (最多展示 3 条)")
        for idx, u in enumerate(valid_http_urls[:3], 1):
            print(f"  [{idx}] {u}")

    # ---- Status Tag & Reason Diagnosis (Section 5) ----
    _print_section("六、细分未调用/成功原因判定 (规范五)")
    status_tag = ""
    diagnosis_detail = ""

    if not endpoint.endswith("/responses"):
        status_tag = "responses_mode_not_applied"
        diagnosis_detail = "端点未以 /responses 结尾"
    elif not any(t.get("type") == "web_search" for t in TOOLS):
        status_tag = "web_search_tool_not_attached"
        diagnosis_detail = "tools 数组中未挂载 web_search"
    elif usage_ws_count and usage_ws_count > 0 and not has_web_search_call:
        status_tag = "source_parse_failed"
        diagnosis_detail = "usage 显示已调用搜索工具，但在 output 中未能解析出搜索结果"
    elif not has_web_search_call:
        status_tag = "web_search_tool_not_called"
        diagnosis_detail = "已正确挂载web_search，但模型决策未调用搜索工具。"
    elif has_web_search_call and raw_source_count == 0:
        status_tag = "web_search_called_no_sources"
        diagnosis_detail = "已检测到 web_search_call，但其 sources 列表为空"
    elif raw_source_count > 0 and len(valid_http_urls) == 0:
        status_tag = "source_parse_failed"
        diagnosis_detail = "web_search_call 中包含来源数据，但未解析出合法有效的 HTTP/HTTPS 链接"
    elif valid_http_urls:
        status_tag = "connected_searchable"
        diagnosis_detail = "成功调用 web_search 并返回合法可追溯的 HTTP/HTTPS 来源链接"
    else:
        status_tag = "search_ok_no_url"
        diagnosis_detail = "已触发联网搜索，但未返回可追溯的来源链接"

    print(f"  判定状态标签 : {status_tag}")
    print(f"  判定详细说明 : {diagnosis_detail}")

    # ---- Final Summary (Section 9) ----
    is_success = (status_tag == "connected_searchable")
    _print_summary(is_success, diagnosis_detail, status_tag=status_tag)


def _print_summary(passed: bool, reason: str = "", *, status_tag: str = "") -> None:
    _print_section("七、最终验收结论 (DIAGNOSTIC RESULT)")
    print(f"  状态标签 (status_tag): {status_tag}")
    print(f"  诊断结果             : {reason}")
    print()

    if passed:
        print("  =======================================================")
        print("  [PASS] 千问联网搜索工具调用成功，已返回真实来源链接！")
        print("  =======================================================")
    else:
        print("  =======================================================")
        print("  [STOP] 未能成功调用搜索工具或未获取真实 URL。")
        print("  已保留单次诊断数据，请勿自动重试以免消耗用户配额。")
        print("  =======================================================")


if __name__ == "__main__":
    main()
