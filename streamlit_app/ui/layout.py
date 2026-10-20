from datetime import datetime
import streamlit as st

from src.core.security import mask_api_key, mask_search_api_key, validate_local_url
from src.providers import (
    BudgetLimits,
    BudgetTracker,
    ConnectionTestResult,
    LocalModelProvider,
    MockAIProvider,
    OpenAICompatibleProvider,
)
from src.search import (
    KimiSearchProvider,
    ManualEvidenceItem,
    ManualEvidenceProvider,
    NoSearchProvider,
    QwenSearchProvider,
    SearchCapabilities,
    SearchConnectionResult,
    TavilySearchProvider,
    validate_web_url,
)
from src.core.environment import is_streamlit_cloud, get_current_limits
from src.search.qwen_provider import check_timeout_recommendation
from src.search.qwen_provider_models import (
    QWEN_PLATFORM_CONFIGS,
    get_qwen_models_for_platform,
    validate_custom_model_id,
    is_vision_supported,
)


def clear_search_test_state():
    """当用户修改搜索服务关键配置（服务来源、Base URL、Key、模式、模型、提取器）时，立即重置旧的测试状态与检测结果"""
    try:
        st.session_state["search_test_result"] = None
        st.session_state["search_connection_status"] = "not_tested"
        st.session_state["search_connection_latency"] = 0
    except Exception:
        pass
    try:
        st.session_state.search_test_result = None
        st.session_state.search_connection_status = "not_tested"
        st.session_state.search_connection_latency = 0
    except Exception:
        pass


def render_settings_drawer():
    """轻量级设置区域：服务模式切换、Key配置与网络搜索服务配置 (二者彻底解耦)"""
    is_cloud = is_streamlit_cloud()
    with st.expander("⚙️ 服务模式与端点设置 (Service Settings)", expanded=False):
        if is_cloud:
            st.info("☁️ **公网云端部署模式 (Streamlit Community Cloud)**：您的 API Key 仅保存在当前浏览器临时会话中，绝不写入任何文件或磁盘，关闭页面即刻销毁。本地模型仅本地桌面版支持。")

        st.markdown("### 🧠 一、AI 模型服务 (AI Model Service)")
        c_mode_select, c_mode_desc = st.columns([1, 2])
        
        with c_mode_select:
            service_mode = st.radio(
                "运行服务模式：",
                options=["mock", "byok", "local"],
                format_func=lambda x: {
                    "mock": "🟢 Mock 离线演示 (免Key/稳定)",
                    "byok": "☁️ 用户自带 API (BYOK - OpenAI)",
                    "local": "💻 用户本地模型 (仅桌面版支持)" if is_cloud else "💻 用户本地模型 (Local - Ollama)",
                }[x],
                index=["mock", "byok", "local"].index(st.session_state.get("service_mode", "mock")),
                key="radio_service_mode_ui",
            )
            if service_mode != st.session_state.get("service_mode"):
                st.session_state.service_mode = service_mode
                st.session_state.current_report = None
                st.session_state.extracted_identity = None
                st.session_state.fallback_alert = None
                st.session_state.analysis_error = None
                st.session_state.progress_state = None
                st.session_state.analysis_completed = False

        with c_mode_desc:
            if service_mode == "mock":
                st.info("💡 **Mock 演示模式**：内置完整离线案例，无 API Key，无需联网，保证演示与测试绝对稳定。")
                if st.button("🔌 测试连接 (Mock 端点)", use_container_width=True):
                    provider = MockAIProvider()
                    st.session_state.conn_test_result = provider.test_connection()

            elif service_mode == "byok":
                st.info("☁️ **用户自带 API 模式**：兼容 OpenAI 协议。公网 Base URL 强制仅允许 HTTPS。")
                c_url, c_key = st.columns([1, 1])
                with c_url:
                    st.session_state.byok_base_url = st.text_input(
                        "Base URL (仅限 HTTPS)",
                        value=st.session_state.byok_base_url,
                        placeholder="https://api.openai.com/v1",
                    )
                with c_key:
                    u_key = st.text_input(
                        "API Key (临时会话凭据)",
                        value=st.session_state.byok_api_key,
                        type="password",
                        placeholder="sk-...",
                    )
                    st.session_state.byok_api_key = u_key
                    if u_key:
                        st.caption(f"🔒 已脱敏：`{mask_api_key(u_key)}`")

                b_mod = st.text_input("模型名称", value=st.session_state.byok_model)
                if b_mod != st.session_state.byok_model:
                    st.session_state.byok_model = b_mod
                    st.session_state.current_report = None
                    st.session_state.analysis_completed = False
                
                with st.expander("高级模型超参", expanded=False):
                    c_p1, c_p2, c_p3 = st.columns(3)
                    c_p1.slider("超时 (秒)", 5, 120, int(st.session_state.byok_timeout), key="byok_t")
                    c_p2.slider("温度 Temperature", 0.0, 1.0, float(st.session_state.byok_temperature), 0.05, key="byok_temp")
                    c_p3.number_input("Max Tokens", 256, 8192, int(st.session_state.byok_max_tokens), 256, key="byok_tok")

                if st.button("🔌 测试连接 (BYOK 端点)", use_container_width=True):
                    with st.spinner("正在探测端点连通性..."):
                        provider = OpenAICompatibleProvider(
                            base_url=st.session_state.byok_base_url,
                            api_key=st.session_state.byok_api_key,
                            model_name=st.session_state.byok_model,
                            timeout=st.session_state.byok_timeout,
                            temperature=st.session_state.byok_temperature,
                            max_tokens=st.session_state.byok_max_tokens,
                        )
                        st.session_state.conn_test_result = provider.test_connection()

            elif service_mode == "local":
                if is_cloud:
                    st.warning("⚠️ **本地模型仅本地桌面版支持。** 公网云端运行在隔离容器内，无法连接您个人电脑上的本地端口（如 127.0.0.1 / localhost）。请切换至 Mock 演示或用户自带 API (BYOK) 模式。")
                else:
                    st.info("💻 **用户本地模型模式**：支持 Ollama/vLLM 本地端口，仅限 127.0.0.1、localhost 或局域网。")
                    c_lurl, c_lmod = st.columns([1, 1])
                    with c_lurl:
                        st.session_state.local_base_url = st.text_input("本地端点 URL", value=st.session_state.local_base_url)
                    with c_lmod:
                        l_mod = st.text_input("本地模型名", value=st.session_state.local_model)
                        if l_mod != st.session_state.local_model:
                            st.session_state.local_model = l_mod
                            st.session_state.current_report = None
                            st.session_state.analysis_completed = False

                    if st.button("🔌 测试连接 (本地端点)", use_container_width=True):
                        with st.spinner("正在探测本地模型服务响应..."):
                            provider = LocalModelProvider(
                                base_url=st.session_state.local_base_url,
                                model_name=st.session_state.local_model,
                                timeout=st.session_state.local_timeout,
                                temperature=st.session_state.local_temperature,
                                max_tokens=st.session_state.local_max_tokens,
                            )
                            st.session_state.conn_test_result = provider.test_connection()

        # 模型连接测试结果展示
        test_res: ConnectionTestResult = st.session_state.get("conn_test_result")
        if test_res:
            if test_res.success:
                st.success(
                    f"✅ **AI模型连接成功！** 耗时: `{test_res.response_time_ms} ms` ｜ "
                    f"文本: `{'支持' if test_res.supports_text else '未知'}` ｜ "
                    f"JSON模式: `{'支持' if test_res.supports_json_mode else '降级'}` ｜ "
                    f"多模态: `{'支持' if test_res.supports_vision else '本地OCR'}`"
                )
            else:
                st.error(f"❌ **AI模型连接失败**（耗时 {test_res.response_time_ms} ms）：{test_res.error_message}")

        # ---------------------------------------------------------------------
        # 2. 网络搜索服务设置 (Search Provider) 与 LLM 彻底解耦
        # ---------------------------------------------------------------------
        st.markdown("---")
        st.markdown("### 🌐 二、网络搜索服务设置 (Search Provider)")
        st.caption("⚠️ 核心安全与计费边界：模型连接成功不得显示为网络搜索已配置。搜索服务必须与模型 API 100% 独立配置与计费。")

        c_search_mode_sel, c_search_mode_desc = st.columns([1, 2])
        with c_search_mode_sel:
            search_mode_options = ["none", "tavily", "kimi", "qwen", "manual"]
            current_sm = st.session_state.get("search_mode", "none")
            if current_sm not in search_mode_options:
                current_sm = "none"

            selected_sm = st.radio(
                "网络搜索服务：",
                options=search_mode_options,
                format_func=lambda x: {
                    "none": "⚪ 未配置 (None · 不发起网络检索 · 零检索费用)",
                    "tavily": "🔍 Tavily 搜索 (用户自带 API Key)",
                    "kimi": "🌙 Kimi 搜索 (Moonshot 官方独立搜索工具)",
                    "qwen": "⚡ Qwen 通义千问搜索 (阿里百炼 DashScope 官方搜索)",
                    "manual": "📎 Manual 手动证据链接 (用户自主提供参考资料)",
                }[x],
                index=search_mode_options.index(current_sm),
                key="radio_search_mode_ui",
            )
            if selected_sm != st.session_state.get("search_mode"):
                st.session_state.search_mode = selected_sm
                name_map = {
                    "none": "none",
                    "tavily": "Tavily",
                    "kimi": "Kimi",
                    "qwen": "Qwen",
                    "manual": "Manual",
                }
                st.session_state.search_provider_name = name_map.get(selected_sm, "none")
                st.session_state.current_report = None
                st.session_state.verification_report = None
                st.session_state.report_markdown = None
                st.session_state.analysis_completed = False
                st.session_state.search_results = None
                st.session_state.search_test_result = None
                if selected_sm == "none":
                    st.session_state.search_connection_status = "not_configured"
                elif selected_sm in ["tavily", "kimi", "qwen"]:
                    st.session_state.search_connection_status = "not_tested"
                elif selected_sm == "manual":
                    st.session_state.search_connection_status = "connected" if st.session_state.get("manual_evidence_items") else "not_configured"

        with c_search_mode_desc:
            if selected_sm == "none":
                st.warning("⚪ **当前未配置网络搜索服务**：**当前不会执行实时网络搜索。** 系统严格保证零外部检索费用，请求数严格为 0，绝不伪造检索数据。")
                if st.button("🔌 检查搜索状态", use_container_width=True, key="btn_test_none_search"):
                    provider = NoSearchProvider()
                    st.session_state.search_test_result = provider.test_connection()
                    st.session_state.search_mode = "none"
                    st.session_state.search_provider_name = "none"
                    st.session_state.search_connection_status = "not_configured"
                    st.rerun()

            elif selected_sm == "tavily":
                st.info("🔍 **Tavily 搜索服务 (用户自带 API)**：仅支持官方固定 HTTPS 端点，所有网络检索费用由用户个人账户完全承担。")
                st.text_input("固定搜索端点 (仅限 HTTPS · 防篡改)", value="https://api.tavily.com/search", disabled=True)

                # 1. Tavily API Key
                tv_key = st.text_input(
                    "Tavily API Key (临时会话凭据)",
                    value=st.session_state.get("search_api_key", ""),
                    type="password",
                    placeholder="tvly-...",
                    key="input_tavily_api_key",
                )
                if tv_key != st.session_state.get("search_api_key"):
                    st.session_state.search_api_key = tv_key
                    st.session_state.current_report = None
                    st.session_state.verification_report = None
                    st.session_state.report_markdown = None
                    st.session_state.analysis_completed = False
                if tv_key:
                    st.caption(f"🔒 已脱敏安全存储（仅保存在会话中）：`{mask_search_api_key(tv_key)}`")

                # 2. 每条声明最大搜索结果数 & 3. 搜索超时 & 4. 搜索语言
                c_s1, c_s2, c_s3 = st.columns(3)
                with c_s1:
                    st.session_state.search_max_results = st.slider(
                        "每条声明最大搜索结果数",
                        min_value=1,
                        max_value=10,
                        value=int(st.session_state.get("search_max_results", 5)),
                        key="sl_search_max_results",
                    )
                with c_s2:
                    st.session_state.search_timeout = st.slider(
                        "搜索超时 (秒)",
                        min_value=5,
                        max_value=30,
                        value=int(st.session_state.get("search_timeout", 15)),
                        key="sl_search_timeout",
                    )
                with c_s3:
                    lang_opts = ["zh", "en", "auto"]
                    cur_lang = st.session_state.get("search_language", "zh")
                    if cur_lang not in lang_opts:
                        cur_lang = "zh"
                    st.session_state.search_language = st.selectbox(
                        "搜索语言",
                        options=lang_opts,
                        index=lang_opts.index(cur_lang),
                        format_func=lambda x: {"zh": "中文 (zh)", "en": "英文 (en)", "auto": "自动检测 (auto)"}[x],
                        key="sb_search_language",
                    )

                # 5. 优先官方来源 & 6. 是否包含用户评价
                c_chk1, c_chk2 = st.columns(2)
                with c_chk1:
                    st.session_state.prefer_official_sources = st.checkbox(
                        "优先官方来源 (优先匹配品牌官网、官方说明书与参数页)",
                        value=st.session_state.get("prefer_official_sources", True),
                        key="chk_prefer_official",
                    )
                with c_chk2:
                    st.session_state.include_user_reviews = st.checkbox(
                        "是否包含用户评价 (允许检索第三方媒体与用户评测)",
                        value=st.session_state.get("include_user_reviews", False),
                        key="chk_include_reviews",
                    )

                # 7. 测试搜索连接按钮
                if st.button("🔌 测试 Tavily 搜索连接", use_container_width=True, key="btn_test_tavily_search"):
                    if not st.session_state.get("search_api_key", "").strip():
                        st.error("❌ 请先输入 Tavily API Key 后再测试连接。")
                        st.session_state.search_mode = "tavily"
                        st.session_state.search_provider_name = "Tavily"
                        st.session_state.search_connection_status = "failed"
                    else:
                        with st.spinner("正在向 Tavily 官方接口发送轻量探测请求 (ping)..."):
                            provider = TavilySearchProvider(
                                api_key=st.session_state.search_api_key,
                                max_results=st.session_state.search_max_results,
                                timeout=st.session_state.search_timeout,
                                prefer_official_sources=st.session_state.prefer_official_sources,
                                search_language=st.session_state.search_language,
                                include_user_reviews=st.session_state.include_user_reviews,
                            )
                            t_res = provider.test_connection()
                            st.session_state.search_test_result = t_res
                            st.session_state.search_mode = "tavily"
                            st.session_state.search_provider_name = "Tavily"
                            if t_res.success:
                                st.session_state.search_connection_status = "connected"
                                st.session_state.search_connection_latency = t_res.response_time_ms
                            else:
                                st.session_state.search_connection_status = "failed"
                                st.session_state.search_connection_latency = t_res.response_time_ms
                            st.rerun()

            elif selected_sm == "kimi":
                st.info("🌙 **Kimi 独立搜索工具 (Moonshot AI)**：使用 Kimi 官方独立搜索接口 (`/v1/tools/search` 与 `/v1/tools/fetch`)，绝不使用旧版即将下线的 `$web_search`。")
                kimi_url = st.text_input(
                    "Kimi Base URL (支持国内官方与专有网关)",
                    value=st.session_state.get("kimi_search_base_url", "https://api.moonshot.cn/v1"),
                    placeholder="https://api.moonshot.cn/v1",
                    key="input_kimi_search_base_url",
                )
                if kimi_url != st.session_state.get("kimi_search_base_url"):
                    st.session_state.kimi_search_base_url = kimi_url

                kimi_key = st.text_input(
                    "Kimi API Key (临时会话凭据)",
                    value=st.session_state.get("kimi_search_api_key", ""),
                    type="password",
                    placeholder="sk-...",
                    key="input_kimi_search_api_key",
                )
                if kimi_key != st.session_state.get("kimi_search_api_key"):
                    st.session_state.kimi_search_api_key = kimi_key
                    st.session_state.current_report = None
                    st.session_state.verification_report = None
                    st.session_state.report_markdown = None
                    st.session_state.analysis_completed = False
                if kimi_key:
                    st.caption(f"🔒 已脱敏安全存储（仅保存在会话中）：`{mask_search_api_key(kimi_key)}`")

                c_k1, c_k2, c_k3, c_k4 = st.columns(4)
                with c_k1:
                    km_modes = ["basic", "pro"]
                    cur_km = st.session_state.get("kimi_search_mode", "basic")
                    if cur_km not in km_modes:
                        cur_km = "basic"
                    st.session_state.kimi_search_mode = st.selectbox(
                        "搜索工具模式",
                        options=km_modes,
                        index=km_modes.index(cur_km),
                        format_func=lambda x: {"basic": "标准搜索 (search)", "pro": "深度搜索 (search_pro)"}[x],
                        key="sb_kimi_search_mode",
                    )
                with c_k2:
                    st.session_state.kimi_search_max_results = st.slider(
                        "最大搜索结果数",
                        min_value=1,
                        max_value=10,
                        value=int(st.session_state.get("kimi_search_max_results", 5)),
                        key="sl_kimi_max_results",
                    )
                with c_k3:
                    st.session_state.kimi_search_max_fetches = st.slider(
                        "最大正文抓取数",
                        min_value=1,
                        max_value=5,
                        value=int(st.session_state.get("kimi_search_max_fetches", 3)),
                        key="sl_kimi_max_fetches",
                    )
                with c_k4:
                    st.session_state.kimi_search_timeout = st.slider(
                        "超时时间 (秒)",
                        min_value=5,
                        max_value=30,
                        value=int(st.session_state.get("kimi_search_timeout", 15)),
                        key="sl_kimi_timeout",
                    )

                if st.button("🔌 测试 Kimi 搜索工具连接", use_container_width=True, key="btn_test_kimi_search"):
                    if not st.session_state.get("kimi_search_api_key", "").strip():
                        st.error("❌ 请先输入 Kimi API Key 后再测试连接。")
                        st.session_state.search_mode = "kimi"
                        st.session_state.search_provider_name = "Kimi"
                        st.session_state.search_connection_status = "failed"
                    else:
                        with st.spinner("正在向 Kimi /v1/tools/search 独立端点发送探测请求..."):
                            provider = KimiSearchProvider(
                                api_key=st.session_state.kimi_search_api_key,
                                base_url=st.session_state.get("kimi_search_base_url", "https://api.moonshot.cn/v1"),
                                search_mode=st.session_state.get("kimi_search_mode", "basic"),
                                max_results=st.session_state.get("kimi_search_max_results", 5),
                                max_fetches=st.session_state.get("kimi_search_max_fetches", 3),
                                timeout=st.session_state.get("kimi_search_timeout", 15),
                            )
                            k_res = provider.test_connection()
                            st.session_state.search_test_result = k_res
                            st.session_state.search_mode = "kimi"
                            st.session_state.search_provider_name = "Kimi"
                            if k_res.success:
                                st.session_state.search_connection_status = "connected"
                                st.session_state.search_connection_latency = k_res.response_time_ms
                            else:
                                st.session_state.search_connection_status = "failed"
                                st.session_state.search_connection_latency = k_res.response_time_ms
                            st.rerun()

            elif selected_sm == "qwen":
                st.info("⚡ **通义千问联网搜索**：支持“千问AI平台 (MaaS)”与“阿里云百炼DashScope”两大来源。推荐使用 Responses API 模式（挂载 `web_search` 与 `web_extractor` 工具，返回真实可追溯来源 URL 与正文）。")

                # 1. 千问服务来源选择
                q_platform_opts = ["qianwen_ai", "dashscope"]
                cur_q_platform = st.session_state.get("qwen_provider_platform", "qianwen_ai")
                if cur_q_platform not in q_platform_opts:
                    cur_q_platform = "qianwen_ai"

                c_q_plat, c_q_plat_tip = st.columns([1, 2])
                with c_q_plat:
                    selected_q_platform = st.radio(
                        "千问服务来源：",
                        options=q_platform_opts,
                        index=q_platform_opts.index(cur_q_platform),
                        format_func=lambda x: {
                            "qianwen_ai": "千问AI平台 (MaaS · 默认推荐)",
                            "dashscope": "阿里云百炼DashScope",
                        }[x],
                        key="radio_qwen_platform_ui",
                    )
                with c_q_plat_tip:
                    plat_cfg = QWEN_PLATFORM_CONFIGS.get(selected_q_platform, {})
                    st.caption(plat_cfg.get("tip", ""))
                    st.caption(f"💡 {plat_cfg.get('recommended_mode_tip', '')}")

                # 切换服务平台时自动刷新 Base URL 与推荐调用模式
                if selected_q_platform != st.session_state.get("qwen_provider_platform"):
                    st.session_state.qwen_provider_platform = selected_q_platform
                    if selected_q_platform == "qianwen_ai":
                        st.session_state.qwen_search_base_url = "https://maas.qianwenaiapi.com/compatible-mode/v1"
                        st.session_state.qwen_search_api_mode = "responses"
                        st.session_state.qwen_search_model = "qwen3.8-flash"
                    else:
                        st.session_state.qwen_search_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
                        st.session_state.qwen_search_api_mode = "chat_completions"
                        st.session_state.qwen_search_model = "qwen-plus"
                    clear_search_test_state()
                    st.rerun()

                # 2. Base URL 与 API Key
                default_base_url = plat_cfg.get("base_url", "")
                widget_base_key = f"input_qwen_search_base_url_{selected_q_platform}"
                if widget_base_key not in st.session_state:
                    st.session_state[widget_base_key] = default_base_url

                qwen_url = st.text_input(
                    f"{'千问AI平台' if selected_q_platform == 'qianwen_ai' else '百炼DashScope'} Base URL",
                    value=st.session_state.get(widget_base_key, default_base_url),
                    placeholder=default_base_url,
                    key=widget_base_key,
                )
                if qwen_url != st.session_state.get("qwen_search_base_url"):
                    st.session_state.qwen_search_base_url = qwen_url
                    clear_search_test_state()

                qwen_key = st.text_input(
                    f"{'千问AI平台' if selected_q_platform == 'qianwen_ai' else 'DashScope'} API Key (临时会话凭据)",
                    value=st.session_state.get("qwen_search_api_key", ""),
                    type="password",
                    placeholder="sk-...",
                    key="input_qwen_search_api_key",
                )
                if qwen_key != st.session_state.get("qwen_search_api_key"):
                    st.session_state.qwen_search_api_key = qwen_key
                    st.session_state.current_report = None
                    st.session_state.verification_report = None
                    st.session_state.report_markdown = None
                    st.session_state.analysis_completed = False
                    clear_search_test_state()
                if qwen_key:
                    st.caption(f"🔒 已脱敏安全存储（仅保存在会话中）：`{mask_search_api_key(qwen_key)}`")

                # 3. 参数列：调用模式、搜索模型、最大检索条数、超时时间
                c_q1, c_q2, c_q3, c_q4 = st.columns(4)
                with c_q1:
                    qm_modes = ["responses", "chat_completions"]
                    cur_qm = st.session_state.get("qwen_search_api_mode", plat_cfg.get("default_mode", "responses"))
                    if cur_qm not in qm_modes:
                        cur_qm = "responses"
                    chosen_api_mode = st.selectbox(
                        "调用模式",
                        options=qm_modes,
                        index=qm_modes.index(cur_qm),
                        format_func=lambda x: {
                            "responses": "Responses API (首选推荐 · 来源全)",
                            "chat_completions": "Chat Completions (enable_search)",
                        }[x],
                        key=f"sb_qwen_search_api_mode_{selected_q_platform}",
                    )
                    if chosen_api_mode != st.session_state.get("qwen_search_api_mode"):
                        st.session_state.qwen_search_api_mode = chosen_api_mode
                        clear_search_test_state()
                with c_q2:
                    # 动态读取该平台和模式下的模型列表
                    avail_models = get_qwen_models_for_platform(selected_q_platform, st.session_state.qwen_search_api_mode)
                    model_id_list = [m.model_id for m in avail_models]
                    model_options = model_id_list + ["custom_input"]

                    cur_qmod = st.session_state.get("qwen_search_model", plat_cfg.get("default_model", "qwen3.8-flash"))
                    if cur_qmod not in model_options and cur_qmod not in model_id_list:
                        st.session_state.qwen_custom_model_id = cur_qmod
                        cur_qmod = "custom_input"

                    sel_model_idx = model_options.index(cur_qmod) if cur_qmod in model_options else 0
                    chosen_model_opt = st.selectbox(
                        "搜索模型",
                        options=model_options,
                        index=sel_model_idx,
                        format_func=lambda x: "✍️ 手动输入模型ID..." if x == "custom_input" else x,
                        key=f"sb_qwen_search_model_opt_{selected_q_platform}",
                    )
                    if chosen_model_opt != "custom_input" and chosen_model_opt != st.session_state.get("qwen_search_model"):
                        st.session_state.qwen_search_model = chosen_model_opt
                        clear_search_test_state()

                with c_q3:
                    st.session_state.qwen_search_max_count = st.slider(
                        "最大检索条数",
                        min_value=1,
                        max_value=10,
                        value=int(st.session_state.get("qwen_search_max_count", 5)),
                        key="sl_qwen_max_count",
                    )
                with c_q4:
                    st.session_state.qwen_search_timeout = st.slider(
                        "超时时间 (秒)",
                        min_value=10,
                        max_value=120,
                        value=int(st.session_state.get("qwen_search_timeout", 60)),
                        key="sl_qwen_timeout",
                    )

                # 超时过短检测与建议 (<= 20 秒提示)
                q_to_val = int(st.session_state.get("qwen_search_timeout", 60))
                q_to_advice = check_timeout_recommendation(q_to_val)
                if q_to_advice:
                    st.warning(f"⚠️ {q_to_advice}")

                # 手动输入模型ID扩展项
                if chosen_model_opt == "custom_input":
                    c_cmod1, c_cmod2 = st.columns([2, 1])
                    with c_cmod1:
                        c_mod_id = st.text_input(
                            "输入官方模型 ID (如 qwen2.5-vl-72b-instruct)",
                            value=st.session_state.get("qwen_custom_model_id", ""),
                            placeholder="例如: qwen2.5-vl-72b-instruct",
                            key="input_qwen_custom_model_id",
                        )
                        st.session_state.qwen_custom_model_id = c_mod_id
                        if c_mod_id.strip() and c_mod_id.strip() != st.session_state.get("qwen_search_model"):
                            st.session_state.qwen_search_model = c_mod_id.strip()
                            clear_search_test_state()
                    with c_cmod2:
                        val_ok, val_msg = validate_custom_model_id(c_mod_id)
                        if c_mod_id:
                            if val_ok:
                                has_v = is_vision_supported(c_mod_id)
                                st.caption(f"✅ 格式合法 {'(支持视觉理解)' if has_v else '(纯文本)'}")
                            else:
                                st.caption(f"⚠️ {val_msg}")

                chosen_extractor = st.checkbox(
                    "挂载网页正文提取器 (web_extractor · 推荐开启，用于提取权威网页 Markdown 段落)",
                    value=st.session_state.get("qwen_enable_web_extractor", True),
                    key="chk_qwen_web_extractor",
                )
                if chosen_extractor != st.session_state.get("qwen_enable_web_extractor"):
                    st.session_state.qwen_enable_web_extractor = chosen_extractor
                    clear_search_test_state()

                # 本次预计调用与费用透明说明（连接测试默认禁止自动重试）
                st.info(
                    "ℹ️ **本次预计调用**：\n"
                    "- 模型：最多 1 次\n"
                    "- 搜索：最多 1 次\n"
                    "- 网页提取：最多 1 次\n\n"
                    "*费用由用户自己的千问 API 账户承担，连接测试默认禁止自动重试。*"
                )

                if st.button("🔌 测试 Qwen 千问搜索连接", use_container_width=True, key="btn_test_qwen_search"):
                    if not st.session_state.get("qwen_search_api_key", "").strip():
                        st.error("❌ 请先输入 API Key 后再测试连接。")
                        st.session_state.search_mode = "qwen"
                        st.session_state.search_provider_name = "Qwen"
                        st.session_state.search_connection_status = "failed"
                    else:
                        with st.spinner("正在向千问搜索端点发送四步独立能力探活请求..."):
                            provider = QwenSearchProvider(
                                api_key=st.session_state.qwen_search_api_key,
                                base_url=st.session_state.get("qwen_search_base_url", ""),
                                model_name=st.session_state.get("qwen_search_model", ""),
                                api_mode=st.session_state.get("qwen_search_api_mode", "responses"),
                                max_search_count=st.session_state.get("qwen_search_max_count", 5),
                                enable_web_extractor=st.session_state.get("qwen_enable_web_extractor", True),
                                timeout=st.session_state.get("qwen_search_timeout", 60),
                                provider_platform=st.session_state.get("qwen_provider_platform", "qianwen_ai"),
                            )
                            q_res = provider.test_connection(ui_selected_mode=st.session_state.get("qwen_search_api_mode", "responses"))
                            st.session_state.search_test_result = q_res
                            st.session_state.search_mode = "qwen"
                            st.session_state.search_provider_name = "Qwen"
                            if q_res.success:
                                st.session_state.search_connection_status = "connected"
                                st.session_state.search_connection_latency = q_res.response_time_ms
                            else:
                                st.session_state.search_connection_status = "failed"
                                st.session_state.search_connection_latency = q_res.response_time_ms
                            st.rerun()

            elif selected_sm == "manual":
                st.info("📎 **手动证据模式**：由用户自行提供权威官方资料或评测链接。系统直接从这些链接提取证据，0 API 检索费用。")
                st.session_state.search_mode = "manual"
                st.session_state.search_provider_name = "Manual"
                st.session_state.search_connection_status = "connected" if st.session_state.get("manual_evidence_items") else "not_configured"
                st.markdown("##### ➕ 添加参考证据链接")
                c_u1, c_u2 = st.columns([3, 2])
                m_url = c_u1.text_input("证据页面 URL (仅限 HTTP/HTTPS)", placeholder="https://www.brand.com/specs", key="m_url_input")
                m_type = c_u2.selectbox(
                    "来源类型",
                    options=["official", "manual", "spec", "review", "other"],
                    format_func=lambda x: {
                        "official": "品牌官网",
                        "manual": "官方说明书",
                        "spec": "官方规格页",
                        "review": "专业评测",
                        "other": "其他公开资料",
                    }[x],
                    key="m_type_select",
                )
                c_u3, c_u4 = st.columns([2, 2])
                m_title = c_u3.text_input("材料名称/标题 (选填)", placeholder="例如：SoundPro X1 官方规格说明", key="m_title_input")
                m_note = c_u4.text_input("用户批注/关注点 (选填)", placeholder="例如：第4章明确标明降噪48dB", key="m_note_input")

                if st.button("➕ 添加到手动证据列表", use_container_width=True, key="btn_add_manual_item"):
                    is_valid, err_msg = validate_web_url(m_url)
                    if not is_valid:
                        st.error(f"❌ 链接格式无效：{err_msg}")
                    else:
                        existing = [item.get("url") for item in st.session_state.get("manual_evidence_items", [])]
                        if m_url.strip() in existing:
                            st.warning("⚠️ 该证据链接已存在，无需重复添加。")
                        else:
                            st.session_state.manual_evidence_items.append({
                                "url": m_url.strip(),
                                "title": m_title.strip() or m_url.strip(),
                                "source_type": m_type,
                                "user_note": m_note.strip(),
                                "added_at": datetime.now().isoformat(),
                            })
                            st.success(f"✅ 成功添加证据链接：{m_title or m_url}")
                            provider = ManualEvidenceProvider(initial_items=[
                                ManualEvidenceItem(
                                    url=it["url"],
                                    title=it.get("title", ""),
                                    source_type=it.get("source_type", "official"),
                                    user_note=it.get("user_note", ""),
                                    added_at=it.get("added_at", ""),
                                )
                                for it in st.session_state.manual_evidence_items
                            ])
                            st.session_state.search_test_result = provider.test_connection()
                            st.rerun()

                m_items = st.session_state.get("manual_evidence_items", [])
                if m_items:
                    st.markdown(f"**已录入 {len(m_items)} 条手动证据链接：**")
                    for m_idx, m_item in enumerate(m_items):
                        c_col1, c_col2, c_col3, c_col4 = st.columns([3, 1.5, 3, 0.8])
                        c_col1.markdown(f"**{m_idx+1}. [{m_item.get('title')}]({m_item.get('url')})**", unsafe_allow_html=True)
                        c_col2.caption(f"类别: {m_item.get('source_type')}")
                        c_col3.caption(f"备注: {m_item.get('user_note') or '无'}")
                        if c_col4.button("🗑️", key=f"btn_del_manual_ev_{m_idx}"):
                            del st.session_state.manual_evidence_items[m_idx]
                            st.rerun()
                    if st.button("🧹 清空所有手动证据", key="btn_clear_all_m_items"):
                        st.session_state.manual_evidence_items = []
                        st.rerun()
                else:
                    st.caption("ℹ️ 暂未录入任何手动证据链接。")

        # 搜索连接测试结果与 5 维能力检测矩阵展示
        s_test_res: SearchConnectionResult = st.session_state.get("search_test_result")
        if s_test_res:
            st.markdown("---")
            # 状态区分与横幅展示
            if s_test_res.status_tag == "model_ok_search_timeout":
                st.warning(
                    f"⚠️ **模型可用，搜索超时** ｜ 耗时: `{s_test_res.response_time_ms} ms` ｜ "
                    "普通模型与 Responses API 运行正常，但网络搜索探针在配置时间内未响应。建议适当调大超时时间（推荐 60 至 90 秒）或稍后重试。"
                )
            elif s_test_res.status_tag == "search_ok_extractor_timeout":
                st.warning(
                    f"⚠️ **搜索可用，网页提取超时** ｜ 耗时: `{s_test_res.response_time_ms} ms` ｜ "
                    "千问联网搜索功能已成功连接并返回真实来源 URL；网页提取器 (web_extractor) 发生超时已自动降级。系统将使用内置安全网页读取器完成正文提取。"
                )
            elif s_test_res.status_tag == "search_ok_extractor_failed":
                st.warning(
                    f"⚠️ **搜索可用，网页提取降级** ｜ 耗时: `{s_test_res.response_time_ms} ms` ｜ "
                    "千问联网搜索功能正常；网页提取器已自动降级为内置读取器。"
                )
            elif s_test_res.success:
                st.success(
                    f"✅ **搜索服务连接正常！** Provider: `{s_test_res.provider_name}` ｜ "
                    f"耗时: `{s_test_res.response_time_ms} ms` ｜ "
                    f"结果: `{s_test_res.error_message}`"
                )
            else:
                st.error(
                    f"❌ **搜索服务检测未通过**（状态标签: `{s_test_res.status_tag}` ｜ 耗时: `{s_test_res.response_time_ms} ms`）："
                    f"{s_test_res.error_message}"
                )

            # 展示 6 维能力检测矩阵
            caps = getattr(s_test_res, "capabilities", None)
            steps = getattr(s_test_res, "steps", {}) or {}
            if caps:
                st.markdown("##### 🧭 搜索服务 6 维独立能力检测矩阵")
                cap_c1, cap_c2, cap_c3, cap_c4, cap_c5, cap_c6 = st.columns(6)

                # 1. 普通模型调用
                s1 = steps.get("auth_chat")
                if s1:
                    t_badge = "🟢 成功" if s1.status == "success" else ("⏳ 超时" if s1.status == "timeout" else "🔴 失败")
                else:
                    t_badge = "🟢 正常" if caps.supports_text_model is True else ("🔴 异常" if caps.supports_text_model is False else "⚪ 不适用")
                cap_c1.metric("普通模型调用", t_badge)

                # 2. Responses API
                s2 = steps.get("responses_api")
                if s2:
                    r_badge = "🟢 成功" if s2.status == "success" else ("⏳ 超时" if s2.status == "timeout" else ("🔴 失败" if s2.status == "failed" else "⚪ 兼容模式"))
                else:
                    r_badge = "🟢 支持" if caps.supports_responses_api else "⚪ 兼容模式"
                cap_c2.metric("Responses API", r_badge)

                # 3. 联网搜索
                s3 = steps.get("web_search")
                if s3:
                    s_badge = "🟢 成功" if s3.status == "success" else ("⏳ 超时" if s3.status == "timeout" else "🔴 失败")
                else:
                    s_badge = "🟢 具备" if caps.supports_web_search else "🔴 不支持"
                cap_c3.metric("联网搜索", s_badge)

                # 4. 来源 URL
                u_badge = "🟢 支持" if caps.supports_source_urls else "🔴 不支持"
                cap_c4.metric("来源 URL", u_badge)

                # 5. 网页提取
                s4 = steps.get("web_extractor")
                if s4:
                    e_badge = "🟢 成功" if s4.status == "success" else ("⏳ 降级(超时)" if s4.status == "timeout" else ("🔴 失败" if s4.status == "failed" else "⚪ 未开启"))
                elif s_test_res.extractor_status == "degraded":
                    e_badge = "🟡 降级"
                else:
                    e_badge = "🟢 支持" if caps.supports_web_extractor else "⚪ 未挂载"
                cap_c5.metric("网页提取", e_badge)

                # 6. 图片理解
                v_badge = "🟢 支持" if caps.supports_vision else "⚪ 纯文本"
                cap_c6.metric("图片理解", v_badge)

                # 细分状态标签特别提示
                if s_test_res.status_tag == "platform_mismatch":
                    st.error("⚠️ **服务平台与API Key不匹配**：当前API Key可能不属于所选服务平台，请确认Base URL与API Key来自同一控制台。")
                elif s_test_res.status_tag == "responses_mode_not_applied":
                    st.error("⚠️ **调用模式未生效 (responses_mode_not_applied)**：界面已选择 Responses API 模式，但实际底层请求未正确路由至 /responses 端点。")
                elif s_test_res.status_tag == "web_search_tool_not_attached":
                    st.error("⚠️ **未挂载搜索工具 (web_search_tool_not_attached)**：请求中未包含 web_search 工具配置，请检查请求参数。")
                elif s_test_res.status_tag == "web_search_tool_not_called":
                    st.warning("⚠️ **未调用搜索工具 (web_search_tool_not_called)**：已正确挂载web_search，但模型决策未调用搜索工具。请确认模型是否支持或尝试更换提示词。")
                elif s_test_res.status_tag == "web_search_called_no_sources":
                    st.warning("⚠️ **搜索调用但来源为空 (web_search_called_no_sources)**：已检测到 web_search_call，但返回的 sources 列表为空，未获取到网页来源。")
                elif s_test_res.status_tag == "source_parse_failed":
                    st.warning("⚠️ **来源解析失败 (source_parse_failed)**：模型执行了搜索并产生了来源数据，但未能解析出合法的 HTTP/HTTPS 链接。")
                elif s_test_res.status_tag == "chat_ok_search_fail":
                    st.warning("⚠️ **未开通联网搜索 (chat_ok_search_fail)**：模型普通对话通信正常，但独立联网搜索工具权限未开通或调用被拒绝。请在服务商控制台开通搜索权限。")
                elif s_test_res.status_tag == "search_ok_no_url":
                    is_responses_ui = (
                        (s_test_res.call_debug_info and s_test_res.call_debug_info.get("provider_call_mode") == "responses")
                        or st.session_state.get("qwen_search_api_mode") == "responses"
                    )
                    if is_responses_ui:
                        st.warning("⚠️ **可联网但无来源URL (search_ok_no_url)**：千问已执行联网搜索，但未返回可追溯的来源链接。为防止虚假证据，系统已禁止此类内容成为 A 级官方证据。请尝试更换检索关键词或调整模型。")
                    else:
                        st.warning("⚠️ **可联网但无来源URL (search_ok_no_url)**：当前使用的 Chat Completions 兼容模式未返回真实来源超链接。为防止虚假证据，系统已禁止此类内容成为 A 级官方证据。强烈建议切换为 **Responses API** 模式以获取可追溯证据。")

            # 搜索来源结构与模式诊断展开项 (安全脱敏)
            if getattr(s_test_res, "call_debug_info", None) or getattr(s_test_res, "source_diagnostics", None):
                with st.expander("🛠️ 搜索来源结构与模式诊断 (安全脱敏)", expanded=True):
                    if s_test_res.call_debug_info:
                        dbg = s_test_res.call_debug_info
                        st.markdown("##### 📡 实际调用模式与端点追踪")
                        cd1, cd2, cd3 = st.columns(3)
                        cd1.markdown(f"**UI选择模式**：`{dbg.get('ui_selected_mode', '')}`")
                        cd2.markdown(f"**Provider执行模式**：`{dbg.get('provider_call_mode', '')}`")
                        cd3.markdown(f"**请求端点**：`{dbg.get('request_endpoint', '')}`")
                        cd4, cd5, cd6 = st.columns(3)
                        cd4.markdown(f"**请求模型**：`{dbg.get('request_model', '')}`")
                        tools_str = ", ".join(dbg.get('tools_enabled', [])) or "无"
                        cd5.markdown(f"**挂载工具**：`{tools_str}`")
                        cd6.markdown(f"**响应对象类型**：`{dbg.get('response_object_type', '')}`")
                        # 增强请求诊断 (规范一)
                        st.markdown("##### 🔎 增强请求诊断")
                        ed1, ed2, ed3 = st.columns(3)
                        ed1.markdown(f"**HTTP方法**：`{dbg.get('http_method', 'POST')}`")
                        ed2.markdown(f"**SDK版本**：`{dbg.get('sdk_version', '未知')}`")
                        ed3.markdown(f"**OpenAI Python版本**：`{dbg.get('openai_package_version', '未安装')}`")
                        ed4, ed5, ed6 = st.columns(3)
                        ed4.markdown(f"**tool_choice**：`{dbg.get('tool_choice', '未设置')}`")
                        ed5.markdown(f"**enable_search**：`{'是' if dbg.get('has_enable_search') else '否'}`")
                        ed6.markdown(f"**search_options**：`{'是' if dbg.get('has_search_options') else '否'}`")
                        ed7, ed8 = st.columns(2)
                        input_q = dbg.get('input_query', '')
                        ed7.markdown(f"**测试查询**：`{input_q[:50]}{'...' if len(input_q) > 50 else ''}`")
                        import json as _json_dbg
                        t_arr = dbg.get('tools_array', [])
                        ed8.markdown(f"**Tools 结构**：`{_json_dbg.dumps(t_arr, ensure_ascii=False)}`")
                        # 响应统计 (规范四)
                        if dbg.get("web_search_call_count") is not None or dbg.get("source_count") is not None:
                            st.markdown("##### 📊 响应结构统计")
                            rs1, rs2, rs3, rs4 = st.columns(4)
                            rs1.markdown(f"**web_search_call次数**：`{dbg.get('web_search_call_count', 0)}`")
                            rs2.markdown(f"**message次数**：`{dbg.get('message_count', 0)}`")
                            rs3.markdown(f"**reasoning次数**：`{dbg.get('reasoning_count', 0)}`")
                            usage_ws = dbg.get('usage_web_search_count')
                            rs4.markdown(f"**usage.web_search.count**：`{usage_ws if usage_ws is not None else '无'}`")
                            rs5, rs6 = st.columns(2)
                            rs5.markdown(f"**原始来源数**：`{dbg.get('source_count', 0)}`")
                            rs6.markdown(f"**有效HTTP URL数**：`{dbg.get('valid_http_url_count', 0)}`")
                    if s_test_res.source_diagnostics:
                        sdiag = s_test_res.source_diagnostics
                        st.markdown("##### 🔬 Responses API 输出结构解析")
                        sd1, sd2, sd3, sd4 = st.columns(4)
                        sd1.markdown(f"**Output 项数**：`{sdiag.get('output_item_count', 0)}`")
                        types_str = ", ".join(sdiag.get('output_types', [])) or "无"
                        sd2.markdown(f"**Output 类型**：`{types_str}`")
                        sd3.markdown(f"**包含 web_search_call**：`{'是' if sdiag.get('has_web_search_call') else '否'}`")
                        sd4.markdown(f"**包含 action 结构**：`{'是' if sdiag.get('has_action') else '否'}`")
                        sd5, sd6, sd7, sd8 = st.columns(4)
                        sd5.markdown(f"**原始 Sources 数量**：`{sdiag.get('sources_count', 0)}`")
                        sd6.markdown(f"**有效可追溯 URL 数量**：`{sdiag.get('valid_url_count', 0)}`")
                        sd7.markdown(f"**具备有效 URL**：`{'是' if sdiag.get('sources_have_url') else '否'}`")
                        sd8.markdown(f"**提取器调用数**：`{sdiag.get('web_extractor_tool_count', 0)}`")
                        if sdiag.get("output_items_summary"):
                            st.markdown("###### 📦 Output 项脱敏结构摘要 (规范四)")
                            st.json(sdiag["output_items_summary"])

            # 超时与网络诊断报告
            if s_test_res.diagnostics:
                with st.expander("🔍 网络与超时诊断报告 (安全脱敏)", expanded=True):
                    diag = s_test_res.diagnostics
                    d_c1, d_c2, d_c3 = st.columns(3)
                    d_c1.markdown(f"**DNS解析耗时**：`{diag.get('dns_latency_ms', 0)} ms`")
                    d_c2.markdown(f"**TCP/TLS连接结果**：`{diag.get('tcp_tls_status', 'unknown')}`")
                    d_c3.markdown(f"**超时发生阶段**：`{'连接阶段 (Connect)' if diag.get('timeout_phase') == 'connect' else ('读取阶段 (Read)' if diag.get('timeout_phase') == 'read' else '未知')}`")
                    d_c4, d_c5, d_c6 = st.columns(3)
                    d_c4.markdown(f"**请求路径**：`{diag.get('request_url', '')}`")
                    d_c5.markdown(f"**目标模型**：`{diag.get('actual_model', '')}`")
                    d_c6.markdown(f"**收到HTTP响应头**：`{'是' if diag.get('received_headers') else '否'}`")


        # ---------------------------------------------------------------------
        # 核心架构能力分离：模型 API vs 网页读取器 vs 搜索服务 (严禁等同混淆)
        # ---------------------------------------------------------------------
        st.markdown("---")
        st.markdown("#### 🛡️ 服务能力与边界隔离 (模型 API · 网页读取器 · 搜索服务)")

        c_llm_box, c_reader_box, c_search_box = st.columns(3)

        with c_llm_box:
            # 确定当前模型状态
            if service_mode == "mock":
                llm_status_badge = '<span style="color:#16865C; background:#F0FDF4; border:1px solid #86EFAC; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🟢 内置Mock引擎</span>'
            elif test_res and test_res.success:
                llm_status_badge = f'<span style="color:#356AE6; background:#EFF6FF; border:1px solid #BFDBFE; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🟢 已连接 ({st.session_state.byok_model if service_mode=="byok" else st.session_state.local_model})</span>'
            else:
                llm_status_badge = '<span style="color:#667085; background:#F6F8FB; border:1px solid #DDE3EA; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">⚪ 待测试 / 离线</span>'

            st.markdown(
                f"""
                <div style="background:#FFFFFF; border:1px solid #DDE3EA; border-top:3px solid #356AE6; border-radius:10px; padding:14px; min-height:280px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span style="font-weight:700; color:#152033; font-size:0.92rem;">🧠 模型 API (LLM)</span>
                        {llm_status_badge}
                    </div>
                    <div style="font-size:0.82rem; color:#152033; font-weight:650; margin-bottom:6px;">核心职责：<strong>负责理解和核验</strong></div>
                    <div style="font-size:0.8rem; color:#16865C; font-weight:600;">✅ 执行范围：</div>
                    <ul style="font-size:0.78rem; color:#526176; margin:3px 0 8px 0; padding-left:16px; line-height:1.45;">
                        <li>拆解宣传文案为最多 5 项原子事实</li>
                        <li>提取品牌与型号并执行多候选对齐</li>
                        <li>结合多源材料进行客观逻辑比对</li>
                        <li>执行二次事实自检铁律，防止臆测</li>
                    </ul>
                    <div style="font-size:0.8rem; color:#B42318; font-weight:600;">❌ 边界限制：</div>
                    <div style="font-size:0.78rem; color:#526176; margin-top:2px; line-height:1.4;">
                        模型本身不具备全网自动实时检索与抓取能力。
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c_reader_box:
            reader_status_badge = '<span style="color:#16865C; background:#F0FDF4; border:1px solid #86EFAC; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🟢 内置合规就绪</span>'
            st.markdown(
                f"""
                <div style="background:#FFFFFF; border:1px solid #DDE3EA; border-top:3px solid #16865C; border-radius:10px; padding:14px; min-height:280px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span style="font-weight:700; color:#152033; font-size:0.92rem;">🕷️ 网页读取器 (Web Reader)</span>
                        {reader_status_badge}
                    </div>
                    <div style="font-size:0.82rem; color:#152033; font-weight:650; margin-bottom:6px;">核心职责：<strong>负责提取链接内容</strong></div>
                    <div style="font-size:0.8rem; color:#16865C; font-weight:600;">✅ 执行范围：</div>
                    <ul style="font-size:0.78rem; color:#526176; margin:3px 0 8px 0; padding-left:16px; line-height:1.45;">
                        <li>提取公开电商与品牌官网静态页</li>
                        <li>解析 JSON-LD、Meta 与结构化参数</li>
                        <li>自动拦截内网与非标 SSRF 风险</li>
                        <li>读取受限时自动激活合规降级引导</li>
                    </ul>
                    <div style="font-size:0.8rem; color:#B42318; font-weight:600;">❌ 边界限制：</div>
                    <div style="font-size:0.78rem; color:#526176; margin-top:2px; line-height:1.4;">
                        绝不破解验证码、登录墙、滑块或盗用 Cookie。
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c_search_box:
            # 动态计算搜索服务徽标
            cur_sm = st.session_state.get("search_mode", "none")
            s_res = st.session_state.get("search_test_result")
            if cur_sm == "tavily":
                if s_res and s_res.success:
                    search_status_badge = f'<span style="color:#16865C; background:#F0FDF4; border:1px solid #86EFAC; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🟢 Tavily已连接 ({mask_search_api_key(st.session_state.get("search_api_key", ""))})</span>'
                elif s_res and not s_res.success:
                    search_status_badge = '<span style="color:#B42318; background:#FEF3F2; border:1px solid #FECDCA; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🔴 Tavily连接失败</span>'
                else:
                    search_status_badge = '<span style="color:#B54708; background:#FFFAEB; border:1px solid #FEDF89; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🟡 Tavily待测试</span>'
            elif cur_sm == "kimi":
                if s_res and s_res.success:
                    search_status_badge = f'<span style="color:#16865C; background:#F0FDF4; border:1px solid #86EFAC; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🟢 Kimi搜索已连接 ({mask_search_api_key(st.session_state.get("kimi_search_api_key", ""))})</span>'
                elif s_res and not s_res.success:
                    search_status_badge = '<span style="color:#B42318; background:#FEF3F2; border:1px solid #FECDCA; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🔴 Kimi搜索连接失败</span>'
                else:
                    search_status_badge = '<span style="color:#B54708; background:#FFFAEB; border:1px solid #FEDF89; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🟡 Kimi待测试</span>'
            elif cur_sm == "qwen":
                if s_res and s_res.success:
                    search_status_badge = f'<span style="color:#16865C; background:#F0FDF4; border:1px solid #86EFAC; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🟢 千问搜索已连接 ({mask_search_api_key(st.session_state.get("qwen_search_api_key", ""))})</span>'
                elif s_res and not s_res.success:
                    search_status_badge = '<span style="color:#B42318; background:#FEF3F2; border:1px solid #FECDCA; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🔴 千问搜索连接失败</span>'
                else:
                    search_status_badge = '<span style="color:#B54708; background:#FFFAEB; border:1px solid #FEDF89; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🟡 千问待测试</span>'
            elif cur_sm == "manual":
                manual_count = len(st.session_state.get("manual_evidence_items", []))
                search_status_badge = f'<span style="color:#1D4ED8; background:#EFF6FF; border:1px solid #BFDBFE; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🔵 手动证据 ({manual_count}条)</span>'
            else:
                search_status_badge = '<span style="color:#667085; background:#F6F8FB; border:1px solid #DDE3EA; padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">⚪ 未配置 (不发起搜索)</span>'

            st.markdown(
                f"""
                <div style="background:#FFFFFF; border:1px solid #DDE3EA; border-top:3px solid #356AE6; border-radius:10px; padding:14px; min-height:280px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span style="font-weight:700; color:#152033; font-size:0.92rem;">🌐 搜索服务 (Search API)</span>
                        {search_status_badge}
                    </div>
                    <div style="font-size:0.82rem; color:#152033; font-weight:650; margin-bottom:6px;">核心职责：<strong>检索公开权威资料与评测</strong></div>
                    <div style="font-size:0.8rem; color:#16865C; font-weight:600;">✅ 运行规范：</div>
                    <ul style="font-size:0.78rem; color:#526176; margin:3px 0 8px 0; padding-left:16px; line-height:1.45;">
                        <li>依据商品型号生成高精准事实查询词</li>
                        <li>仅检索公开 Web 权威页面与行业标准</li>
                        <li>固定 HTTPS 官方端点，防 SSRF 篡改</li>
                        <li>支持用户手动录入可信证据链接</li>
                    </ul>
                    <div style="font-size:0.8rem; color:#B42318; font-weight:600;">❌ 费用与安全铁律：</div>
                    <div style="font-size:0.78rem; color:#526176; margin-top:2px; line-height:1.4;">
                        未配置搜索时请求数为 0；绝不伪造检索结果；绝不产生开发者代付费用。
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 显式提示：当配置或连接模型 API 时，明确展示两者解耦状态
        if cur_sm == "none":
            st.info("💡 **架构解耦提示**：模型 API 连接成功仅代表语言理解能力就绪；网络搜索服务独立计费与配置。模型连接成功不得显示为网络搜索已配置。当前未配置搜索服务时，**当前不会执行实时网络搜索**。系统严格保证零外部检索费用，绝不伪造搜索结果。")
        elif cur_sm == "tavily":
            st.info("💡 **Tavily 搜索就绪**：核验时将根据宣传声明生成精准查询词检索公开权威网页，检索费用由用户自有 Tavily 账户承担。")
        elif cur_sm == "kimi":
            st.info("💡 **Kimi 独立搜索就绪**：核验时将调用 Moonshot 官方 `/v1/tools/search` 独立检索工具与 `/v1/tools/fetch` 抓取工具，检索费用由用户自有 Moonshot 账户承担。")
        elif cur_sm == "qwen":
            st.info("💡 **通义千问搜索就绪**：核验时将调用阿里百炼 DashScope 官方搜索服务，挂载来源超链接与网页正文提取，检索费用由用户自有百炼账户承担。")
        elif cur_sm == "manual":
            st.info("💡 **手动证据就绪**：核验时将优先参考用户录入的证据材料链接，不调用外部商业搜索 API，0 检索费用。")

        st.markdown("---")
        c_rst1, c_rst2 = st.columns([1.5, 2.5])
        with c_rst1:
            if st.button("🧹 清空所有临时密钥与会话 (安全退出)", use_container_width=True, key="btn_clear_session_cloud"):
                st.session_state.byok_api_key = ""
                st.session_state.search_api_key = ""
                st.session_state.kimi_api_key = ""
                st.session_state.qwen_api_key = ""
                st.session_state.current_report = None
                st.session_state.clear()
                st.rerun()
        with c_rst2:
            st.caption("🔒 **安全保障**：所有 API Key 仅暂存于当前浏览器 Session 内存中，不写入任何持久化文件或数据库，点击上方按钮或关闭浏览器标签即可彻底销毁。")

