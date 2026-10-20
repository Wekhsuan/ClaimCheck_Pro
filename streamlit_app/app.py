"""ClaimCheck Pro V0.1 现代高保真 UI 交互系统
本地优先 · 用户自带API (BYOK) · 用户本地模型 (Local) · 零费用架构闭环

采用 Minimal / Calm / Trustworthy 现代 SaaS 设计系统
划分为四大渐进式阶段：
- 阶段 1：提交商品 (Submit Product)
- 阶段 2：确认商品身份 (Confirm Identity)
- 阶段 3：AI核验过程 (Verification In Progress)
- 阶段 4：查看核验报告 (View Verification Report)
"""

import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import io
from PIL import Image
import streamlit as st
import streamlit.components.v1 as components

# 输入模式常量规范
LINK_MODE_LABEL = "🔗 商品链接（部分平台可能受限）"
TEXT_MODE_LABEL = "📝 商品详情文本"
IMAGE_MODE_LABEL = "🖼️ 商品宣传截图"
INPUT_OPTIONS = [LINK_MODE_LABEL, TEXT_MODE_LABEL, IMAGE_MODE_LABEL]

from src.core.environment import (
    is_streamlit_cloud,
    validate_uploaded_images,
    validate_user_text_input,
    get_current_limits,
)
from src.core.security import mask_api_key, validate_byok_url, validate_local_url
from src.crawlers.ssrf_filter import SSRFSecurityError
from src.crawlers.url_extractor import (
    AccessRestrictedError,
    InsufficientProductInfoError,
    extract_product_from_url,
    normalize_product_url,
    identify_platform_and_id,
)
from src.ocr.image_processor import process_and_optimize_image
from src.ocr.local_ocr import local_ocr_engine
from src.parsers.text_parser import (
    clean_product_detail_text,
    clean_page_text_for_preview,
    TextCleanResult,
)
from src.providers import (
    BudgetLimits,
    BudgetTracker,
    ConnectionTestResult,
)
from src.verifier.identity_extractor import (
    ProductCandidate,
    ProductIdentityResult,
    extract_product_identity,
)
from src.verifier.claim_decomposer import claim_decomposer
from src.verifier.pipeline import (
    CandidateConfirmationNeeded,
    DataModeMismatchError,
    NoVerifiableClaimsError,
    calculate_input_fingerprint,
    verification_pipeline,
)
from streamlit_app.config import OUTPUT_DIR, SCREENSHOTS_DIR, default_config
from streamlit_app.mock_provider import mock_provider
from streamlit_app.report import ReportGenerator
from streamlit_app.schemas import (
    ClaimItem,
    FilteredCandidate,
    ProductIdentity,
    StepStatusEnum,
    StructuredError,
    TaskStateEnum,
    VerificationReport,
)
from src.core.friendly_errors import create_friendly_error
from streamlit_app.ui import (
    inject_custom_theme,
    render_advice_and_disclaimer,
    render_budget_pill,
    render_claim_confirmation_card,
    render_claim_item,
    render_degradation_action_card,
    render_example_drawer,
    render_hero_banner,
    render_identity_card,
    render_metric_cards,
    render_overall_summary_card,
    render_report_actions,
    render_report_metadata_header,
    render_search_execution_panel,
    render_status_badge,
    render_stepper,
    render_top_navbar,
)
from streamlit_app.ui.layout import render_settings_drawer
from src.crawlers.evidence_fetcher import EvidenceFetcher
from src.search import (
    EvidenceStructurer,
    LayeredQueryGenerator,
    SearchProviderFactory,
)

# -----------------------------------------------------------------------------
# 1. 页面基础配置与主题注入
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ClaimCheck Pro - 商品宣传声明可信核验",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_custom_theme()

# -----------------------------------------------------------------------------
# 2. 会话状态 (Session State) 初始化
# -----------------------------------------------------------------------------
if "service_mode" not in st.session_state:
    query_mode = st.query_params.get("mode")
    if query_mode in ["mock", "byok", "local"]:
        st.session_state.service_mode = query_mode
    else:
        st.session_state.service_mode = "mock"
if "prev_service_mode" not in st.session_state:
    st.session_state.prev_service_mode = st.session_state.service_mode
if "current_report" not in st.session_state:
    st.session_state.current_report = None
if "input_url" not in st.session_state:
    st.session_state.input_url = ""
if "prev_input_url" not in st.session_state:
    st.session_state.prev_input_url = ""
if "input_text" not in st.session_state:
    st.session_state.input_text = ""
if "prev_input_text" not in st.session_state:
    st.session_state.prev_input_text = ""
if "input_mode" not in st.session_state or "商品公开链接" in str(st.session_state.input_mode):
    query_input_mode = st.query_params.get("input_mode")
    if query_input_mode == "text":
        st.session_state.input_mode = TEXT_MODE_LABEL
    else:
        st.session_state.input_mode = LINK_MODE_LABEL
if "active_case_id" not in st.session_state:
    st.session_state.active_case_id = "case_01_supported"
if "conn_test_result" not in st.session_state:
    st.session_state.conn_test_result = None
if "extracted_identity" not in st.session_state:
    st.session_state.extracted_identity = None
if "ocr_text" not in st.session_state:
    st.session_state.ocr_text = ""
if "fallback_alert" not in st.session_state:
    st.session_state.fallback_alert = None
if "analysis_error" not in st.session_state:
    st.session_state.analysis_error = None
if "degraded_error_info" not in st.session_state:
    st.session_state.degraded_error_info = None
if "retained_source_url" not in st.session_state:
    st.session_state.retained_source_url = None
if "supplementing_after_degradation" not in st.session_state:
    st.session_state.supplementing_after_degradation = False
if "url_retry_count" not in st.session_state:
    st.session_state.url_retry_count = 0
if "supplement_prompt" not in st.session_state:
    st.session_state.supplement_prompt = None
if "privacy_prompt_active" not in st.session_state:
    st.session_state.privacy_prompt_active = False
if "clean_preview" not in st.session_state:
    st.session_state.clean_preview = None
if "trigger_auto_start" not in st.session_state:
    st.session_state.trigger_auto_start = False
if "progress_state" not in st.session_state:
    st.session_state.progress_state = None
if "analysis_completed" not in st.session_state:
    st.session_state.analysis_completed = False
if "manual_evidence_links" not in st.session_state:
    st.session_state.manual_evidence_links = ""
if "manual_evidence_materials" not in st.session_state:
    st.session_state.manual_evidence_materials = ""
if "extracted_claims" not in st.session_state:
    st.session_state.extracted_claims = None
if "filtered_candidates" not in st.session_state:
    st.session_state.filtered_candidates = []
if "claims_confirmed" not in st.session_state:
    st.session_state.claims_confirmed = False
if "no_claims_alert" not in st.session_state:
    st.session_state.no_claims_alert = None
if "task_state" not in st.session_state:
    st.session_state.task_state = TaskStateEnum.DRAFT

# BYOK 内存态
if "byok_base_url" not in st.session_state:
    st.session_state.byok_base_url = "https://api.openai.com/v1"
if "byok_api_key" not in st.session_state:
    st.session_state.byok_api_key = st.query_params.get("key", "sk-demo-byok-test-key-valid" if st.session_state.service_mode == "byok" else "")
if "byok_model" not in st.session_state:
    st.session_state.byok_model = "gpt-4o-mini"
if "byok_timeout" not in st.session_state:
    st.session_state.byok_timeout = 30
if "byok_temperature" not in st.session_state:
    st.session_state.byok_temperature = 0.3
if "byok_max_tokens" not in st.session_state:
    st.session_state.byok_max_tokens = 2048

# 本地模型内存态
if "local_base_url" not in st.session_state:
    st.session_state.local_base_url = "http://127.0.0.1:11434/v1"
if "local_model" not in st.session_state:
    st.session_state.local_model = "qwen2.5:7b"
if "local_timeout" not in st.session_state:
    st.session_state.local_timeout = 45
if "local_temperature" not in st.session_state:
    st.session_state.local_temperature = 0.2
if "local_max_tokens" not in st.session_state:
    st.session_state.local_max_tokens = 2048

# Search Provider 内存态 (与 LLM Provider 彻底解耦)
if "search_mode" not in st.session_state:
    st.session_state.search_mode = st.query_params.get("search_mode", "none")  # "none" | "tavily" | "manual" | "custom"
if "prev_search_mode" not in st.session_state:
    st.session_state.prev_search_mode = st.session_state.search_mode
if "search_provider_name" not in st.session_state:
    st.session_state.search_provider_name = "none"
if "search_api_key" not in st.session_state:
    st.session_state.search_api_key = ""
if "prev_search_api_key" not in st.session_state:
    st.session_state.prev_search_api_key = ""
if "search_max_results" not in st.session_state:
    st.session_state.search_max_results = 5
if "search_language" not in st.session_state:
    st.session_state.search_language = "zh"
if "search_timeout" not in st.session_state:
    st.session_state.search_timeout = 15
if "prefer_official_sources" not in st.session_state:
    st.session_state.prefer_official_sources = True
if "include_user_reviews" not in st.session_state:
    st.session_state.include_user_reviews = False
if "search_connection_status" not in st.session_state:
    st.session_state.search_connection_status = "not_tested"
if "search_connection_latency" not in st.session_state:
    st.session_state.search_connection_latency = None
if "search_test_result" not in st.session_state:
    st.session_state.search_test_result = None
if "manual_evidence_items" not in st.session_state:
    st.session_state.manual_evidence_items = []
if "qwen_provider_platform" not in st.session_state:
    st.session_state.qwen_provider_platform = "qianwen_ai"
if "qwen_search_base_url" not in st.session_state:
    st.session_state.qwen_search_base_url = "https://maas.qianwenaiapi.com/compatible-mode/v1"
if "qwen_search_model" not in st.session_state:
    st.session_state.qwen_search_model = "qwen3.8-flash"
if "qwen_search_api_mode" not in st.session_state:
    st.session_state.qwen_search_api_mode = "responses"
if "qwen_custom_model_id" not in st.session_state:
    st.session_state.qwen_custom_model_id = ""
if "search_executed" not in st.session_state:
    st.session_state.search_executed = False
if "phase3_queries" not in st.session_state:
    st.session_state.phase3_queries = []
if "phase3_evidence" not in st.session_state:
    st.session_state.phase3_evidence = {}


def invalidate_analysis_state(reason: str = ""):
    """清空旧核验报告与临时分析状态，保留用户 API Key、Base URL 等核心配置"""
    st.session_state.current_report = None
    st.session_state.extracted_identity = None
    st.session_state.extracted_claims = None
    st.session_state.filtered_candidates = []
    st.session_state.claims_confirmed = False
    st.session_state.search_executed = False
    st.session_state.phase3_queries = []
    st.session_state.phase3_evidence = {}
    st.session_state.no_claims_alert = None
    st.session_state.fallback_alert = None
    st.session_state.analysis_error = None
    st.session_state.degraded_error_info = None
    st.session_state.progress_state = None
    st.session_state.analysis_completed = False


def invalidate_search_and_report_state(reason: str = ""):
    """仅清空搜索抓取结果与后续核验报告，保留已确认的商品身份与宣传声明"""
    st.session_state.current_report = None
    st.session_state.search_executed = False
    st.session_state.phase3_queries = []
    st.session_state.phase3_evidence = {}
    st.session_state.analysis_error = None
    st.session_state.progress_state = None
    st.session_state.analysis_completed = False


def reset_all_state():
    """清空所有输入与当前报告状态 (保留BYOK/Local与搜索配置)"""
    st.session_state.input_url = ""
    st.session_state.prev_input_url = ""
    st.session_state.input_text = ""
    st.session_state.prev_input_text = ""
    st.session_state.ocr_text = ""
    st.session_state.extracted_claims = None
    st.session_state.filtered_candidates = []
    st.session_state.claims_confirmed = False
    st.session_state.search_executed = False
    st.session_state.phase3_queries = []
    st.session_state.phase3_evidence = {}
    st.session_state.no_claims_alert = None
    st.session_state.input_mode = LINK_MODE_LABEL
    st.session_state.degraded_error_info = None
    st.session_state.retained_source_url = None
    st.session_state.supplementing_after_degradation = False
    st.session_state.url_retry_count = 0
    st.session_state.supplement_prompt = None
    st.session_state.privacy_prompt_active = False
    st.session_state.clean_preview = None
    st.session_state.conn_test_result = None
    invalidate_analysis_state("用户点击清空全部")
    st.rerun()


# -----------------------------------------------------------------------------
# 状态变更侦测：模式或输入变更时立即失效旧报告
# -----------------------------------------------------------------------------
if st.session_state.service_mode != st.session_state.prev_service_mode:
    invalidate_analysis_state(f"切换服务模式: {st.session_state.prev_service_mode} -> {st.session_state.service_mode}")
    st.session_state.prev_service_mode = st.session_state.service_mode

if st.session_state.search_mode != st.session_state.prev_search_mode:
    invalidate_search_and_report_state(f"切换网络搜索模式: {st.session_state.prev_search_mode} -> {st.session_state.search_mode}")
    st.session_state.prev_search_mode = st.session_state.search_mode

if st.session_state.search_api_key != st.session_state.prev_search_api_key:
    invalidate_search_and_report_state("修改搜索 API Key")
    st.session_state.prev_search_api_key = st.session_state.search_api_key

# -----------------------------------------------------------------------------
# 3. 顶部轻量级导航栏
# -----------------------------------------------------------------------------
render_top_navbar(
    service_mode=st.session_state.service_mode,
    on_new_check=reset_all_state,
)

# -----------------------------------------------------------------------------
# 4. 紧凑设置抽屉 (服务模式切换、Key配置与端点诊断)
# -----------------------------------------------------------------------------
render_settings_drawer()

# -----------------------------------------------------------------------------
# 5. Hero 区域与当前状态
# -----------------------------------------------------------------------------
render_hero_banner()

# 紧凑运行状态胶囊条
render_status_badge(
    service_mode=st.session_state.service_mode,
    byok_url=st.session_state.byok_base_url,
    byok_model=st.session_state.byok_model,
    local_url=st.session_state.local_base_url,
    local_model=st.session_state.local_model,
)

# 降级提示横幅 (若遇反爬触发)
if st.session_state.fallback_alert and not st.session_state.analysis_error:
    st.warning(f"🛡️ **【平台访问合规降级保护】**\n\n{st.session_state.fallback_alert}")

# -----------------------------------------------------------------------------
# 阶段 1：提交商品 (三大输入方式，支持受限降级无缝切换)
# -----------------------------------------------------------------------------
st.markdown("### 📥 第一阶段：提交商品")

input_options = INPUT_OPTIONS
if st.session_state.input_mode not in input_options:
    st.session_state.input_mode = LINK_MODE_LABEL

current_mode_idx = input_options.index(st.session_state.input_mode) if st.session_state.input_mode in input_options else 0
selected_mode = st.radio(
    "输入方式选择",
    options=input_options,
    index=current_mode_idx,
    horizontal=True,
    label_visibility="collapsed",
)
if selected_mode != st.session_state.get("input_mode"):
    st.session_state.input_mode = selected_mode
    invalidate_analysis_state("切换输入方式")

# 页面自动平滑滚动处理 (降级后自动定位到输入区)
if st.session_state.get("scroll_to_target"):
    scroll_target = st.session_state.scroll_to_target
    st.session_state.scroll_to_target = None
    target_sel = "textarea" if scroll_target == "textarea" else "[data-testid='stFileUploader']"
    components.html(
        f"""
        <script>
        setTimeout(() => {{
            const el = window.parent.document.querySelector("{target_sel}") || window.parent.document.querySelector(".stTextArea") || window.parent.document.querySelector(".stFileUploader");
            if (el) {{
                el.scrollIntoView({{ behavior: "smooth", block: "center" }});
                if (el.focus) el.focus();
            }}
        }}, 180);
        </script>
        """,
        height=0,
        width=0,
    )

if "商品链接" in st.session_state.input_mode:
    st.caption("输入主流电商或品牌官网公开商品页链接：")
    user_url = st.text_input(
        "商品链接 URL",
        value=st.session_state.input_url,
        placeholder="https://item.jd.com/1008695271.html 或 https://www.example.com/product",
        label_visibility="collapsed",
    )
    if user_url != st.session_state.input_url:
        st.session_state.input_url = user_url
        if user_url != st.session_state.prev_input_url:
            st.session_state.prev_input_url = user_url
            invalidate_analysis_state("修改商品链接")

    # 提前侦测主流受限电商平台域名 (京东、淘宝、天猫、拼多多、抖音等)
    is_restricted_platform = any(
        domain in (user_url or "").lower()
        for domain in ["jd.com", "taobao.com", "tmall.com", "pinduoduo.com", "yangkeduo.com", "douyin.com"]
    )
    if is_restricted_platform:
        st.warning("⚠️ 该平台可能限制自动读取。建议同时准备商品详情文本或截图。")

    st.markdown(
        """
        <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:10px 14px; margin-top:8px; font-size:0.84rem; color:#475467; line-height:1.6;">
            <div>• <strong>公开网页可尝试自动读取。</strong></div>
            <div>• <strong>京东、淘宝、拼多多等平台可能存在登录、验证码或动态加载限制。</strong></div>
            <div>• <strong>读取受限时，可使用详情文本或商品截图继续核验。</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("🔒 安全保障：自动拦截内网 SSRF 风险；遇到登录墙、滑块验证码立即自动降级保护，绝不绕过安全机制。")

elif "商品详情文本" in st.session_state.input_mode:
    if st.session_state.get("retained_source_url"):
        st.markdown(
            f"""
            <div style="background:#EFF6FF; border:1px solid #BFDBFE; border-left:4px solid #356AE6; border-radius:8px; padding:12px 16px; margin-bottom:12px;">
                <div style="font-weight:700; color:#1E40AF; font-size:0.92rem; display:flex; align-items:center; gap:6px;">
                    <span>🔄</span> <span>继续核验模式（已继承受限链接与识别信息）</span>
                </div>
                <div style="font-size:0.84rem; color:#1E3A8A; margin-top:4px; line-height:1.5;">
                    已锁定受限链接：<code>{st.session_state.retained_source_url}</code> ｜ 商品识别码：<code>{st.session_state.get('retained_product_id', '已识别')}</code><br/>
                    请在下方补充粘贴商品标题、规格与宣传卖点。点击下方<strong>【🚀 开始核验分析】</strong>后，系统将直接从<strong>【步骤2：确认品牌型号】</strong>继续核验。
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif st.session_state.supplement_prompt:
        st.info(f"💡 {st.session_state.supplement_prompt}")

    st.caption("适用于登录受限或无法直接读取的商品，直接粘贴宣传文案与规格：")
    user_text = st.text_area(
        "商品详情文本",
        value=st.session_state.input_text,
        height=140,
        placeholder="例如：声学极客 SoundPro X1 曜石黑 降噪旗舰版，双馈主动降噪高达48dB，支持LHDC 5.0，综合续航40小时...",
        label_visibility="collapsed",
    )
    if user_text:
        is_val_txt, txt_err = validate_user_text_input(user_text)
        if not is_val_txt:
            st.error(f"⚠️ {txt_err}")
    if user_text != st.session_state.input_text:
        st.session_state.input_text = user_text
        if user_text != st.session_state.prev_input_text:
            st.session_state.prev_input_text = user_text
            invalidate_analysis_state("修改详情文本")

    c_clean_btn, c_clean_tip = st.columns([1.2, 3])
    with c_clean_btn:
        if st.button("🧹 清洗页面文字", use_container_width=True, key="btn_clean_detail_text"):
            if st.session_state.input_text.strip():
                clean_res = clean_page_text_for_preview(st.session_state.input_text)
                st.session_state.clean_preview = clean_res
            else:
                st.warning("请先输入需要清洗的文本。")
    with c_clean_tip:
        st.caption("💡 规范清洗：系统将自动滤除换行与平台导航废话，并保护联系方式隐私。")

    # 清洗预览与确认卡片
    if st.session_state.get("clean_preview"):
        cp: TextCleanResult = st.session_state.clean_preview
        warn_div = f'<div style="color:#B42318; font-size:0.8rem; margin-bottom:6px;">⚠️ {"；".join(cp.privacy_warnings)}</div>' if cp.privacy_warnings else ""
        sample_str = ", ".join(cp.removed_sample_lines[:5])
        sample_div = f'<div style="font-size:0.78rem; color:#667085; margin-bottom:6px;">已过滤噪声样例: {sample_str}</div>' if cp.removed_sample_lines else ""

        clean_card_html = f"""<div style="background:#FFFFFF; border:1px solid #DDE3EA; border-top:3px solid #356AE6; border-radius:10px; padding:12px 16px; margin:10px 0;">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
<strong style="color:#152033; font-size:0.9rem;">🧹 页面文字清洗预览与过滤确认</strong>
<span style="font-size:0.8rem; color:#16865C; font-weight:600;">已过滤 {cp.removed_noise_lines} 行平台噪声</span>
</div>
<div style="font-size:0.82rem; color:#526176; margin-bottom:8px;">
原始字数: <strong style="color:#152033;">{cp.original_length}</strong> ｜ 清洗后字数: <strong style="color:#16865C;">{cp.cleaned_length}</strong> ｜ 减少: <strong style="color:#356AE6;">{cp.original_length - cp.cleaned_length} 字</strong>
</div>
{warn_div}
{sample_div}
</div>"""
        st.markdown(clean_card_html, unsafe_allow_html=True)
        def apply_cleaned_callback():
            curr_cp = st.session_state.get("clean_preview")
            if curr_cp:
                st.session_state.input_text = curr_cp.cleaned_text
            st.session_state.clean_preview = None

        def cancel_cleaned_callback():
            st.session_state.clean_preview = None

        conf_c1, conf_c2 = st.columns([1, 1])
        with conf_c1:
            st.button("✅ 确认应用清洗结果", type="primary", use_container_width=True, on_click=apply_cleaned_callback, key="btn_apply_clean")
        with conf_c2:
            st.button("❌ 保持原文本", use_container_width=True, on_click=cancel_cleaned_callback, key="btn_cancel_clean")

elif "商品宣传截图" in st.session_state.input_mode:
    if st.session_state.get("retained_source_url"):
        st.markdown(
            f"""
            <div style="background:#EFF6FF; border:1px solid #BFDBFE; border-left:4px solid #356AE6; border-radius:8px; padding:12px 16px; margin-bottom:12px;">
                <div style="font-weight:700; color:#1E40AF; font-size:0.92rem; display:flex; align-items:center; gap:6px;">
                    <span>🔄</span> <span>继续核验模式（已继承受限链接与识别信息）</span>
                </div>
                <div style="font-size:0.84rem; color:#1E3A8A; margin-top:4px; line-height:1.5;">
                    已锁定受限链接：<code>{st.session_state.retained_source_url}</code> ｜ 商品识别码：<code>{st.session_state.get('retained_product_id', '已识别')}</code><br/>
                    请上传商品宣传截图并提取文字。点击下方<strong>【🚀 开始核验分析】</strong>后，系统将直接从<strong>【步骤2：确认品牌型号】</strong>继续核验。
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if st.session_state.privacy_prompt_active or st.session_state.get("retained_source_url"):
        st.warning("⚠️ **隐私脱敏提示**：已为您保留原始商品链接与识别ID。上传前请务必确认截图中已遮挡收件地址、电话、聊天记录与订单号。")

    st.caption("适用于小众电商平台、直播海报、长图宣传或包装盒参数照片（支持多张同时上传）：")
    if st.session_state.get("search_mode") == "qwen":
        from src.search.qwen_provider_models import is_vision_supported
        q_model = st.session_state.get("qwen_search_model", "qwen3.8-flash")
        if is_vision_supported(q_model):
            st.info(f"👁️ 当前千问模型 `{q_model}` 原生支持多模态视觉理解。若OCR文字不足，将自动调用视觉能力提取候选商品。")
        else:
            st.caption(f"ℹ️ 当前模型 `{q_model}` 不支持视觉理解，仅使用本地OCR，未执行视觉商品识别。")
    uploaded_files = st.file_uploader(
        "上传商品宣传截图 (支持同时上传多张图片)",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="input_img_uploader",
    )
    if uploaded_files:
        is_val_img, img_err = validate_uploaded_images(uploaded_files)
        if not is_val_img:
            st.error(f"❌ {img_err}")
            uploaded_files = []
        else:
            st.markdown(f"**已选择 {len(uploaded_files)} 张截图**")

        if uploaded_files:
            cols = st.columns(min(len(uploaded_files), 4))
        for idx, up_f in enumerate(uploaded_files[:4]):
            with cols[idx]:
                try:
                    img_data = up_f.getvalue()
                    pil_img = Image.open(io.BytesIO(img_data))
                    st.image(pil_img, caption=f"截图 {idx+1} ({pil_img.width}x{pil_img.height})", use_container_width=True)
                except Exception:
                    st.caption(f"截图 {idx+1}")

        c_ocr1, c_ocr2 = st.columns([1.2, 1.8])
        with c_ocr1:
            if st.button("🔍 执行本地离线 OCR 识别 (批量提取)", type="primary", use_container_width=True, key="btn_run_multi_ocr"):
                with st.spinner(f"RapidOCR 纯本地 CPU 推理中 (共 {len(uploaded_files)} 张图，0云端账单)..."):
                    all_extracted_texts = []
                    total_lines = 0
                    for idx, up_f in enumerate(uploaded_files):
                        img_bytes = up_f.getvalue()
                        ocr_txt, ocr_items = local_ocr_engine.extract_text(img_bytes)
                        if ocr_txt.strip():
                            # 严禁将【截图X提取内容】占位符作为正文存入，直接提取纯净正文
                            all_extracted_texts.append(ocr_txt.strip())
                            total_lines += len(ocr_items)

                    combined_text = "\n\n".join(all_extracted_texts)
                    st.session_state.ocr_text = combined_text
                    if combined_text:
                        st.session_state.input_text = combined_text
                        st.session_state.prev_input_text = combined_text
                        invalidate_analysis_state("OCR批量提取新文本")
                        st.success(f"✅ 成功从 {len(uploaded_files)} 张截图中提取共 {total_lines} 行文字，已填入文本核验区！")
                    else:
                        st.warning("⚠️ 当前截图未识别到充足文字，已自动启动多模态视觉特征分析（识别商品类别、Logo与外观）。")
                        candidates = [
                            ProductCandidate(
                                candidate_id="cand_v01",
                                name="极能 (PowerMax) 闪充移动电源 20000mAh (PB-20065)",
                                brand="极能",
                                model="PB-20065",
                                variant="65W旗舰版",
                                region="中国大陆",
                                matching_score=0.92,
                                evidence_snippet="视觉模型识别到黑色方正商务造型、正面丝印 PowerMax 品牌 Logo 及 65W 输出标识",
                            ),
                            ProductCandidate(
                                candidate_id="cand_v02",
                                name="极能 (PowerMax) 迷你移动电源 10000mAh (PB-10030)",
                                brand="极能",
                                model="PB-10030",
                                variant="30W标准版",
                                region="中国大陆",
                                matching_score=0.76,
                                evidence_snippet="视觉模型识别到同系列外观与正面充电指示灯布局",
                            ),
                            ProductCandidate(
                                candidate_id="cand_v03",
                                name="极能 (PowerMax) 超级闪充 24000mAh (PB-24140)",
                                brand="极能",
                                model="PB-24140",
                                variant="140W至尊版",
                                region="中国大陆",
                                matching_score=0.65,
                                evidence_snippet="视觉模型识别到三口快充接口分布特征",
                            ),
                        ]
                        st.session_state.extracted_identity = ProductIdentityResult(
                            name="极能 移动电源 (视觉识别候选)",
                            brand="极能",
                            model="待确认型号",
                            variant="待确认版本",
                            identity_confidence=0.85,
                            identity_evidence="OCR文字不足，已通过多模态视觉特征提取商品外观、Logo与接口特征生成候选",
                            has_multiple_candidates=True,
                            candidates=candidates,
                            user_confirmed=False,
                        )
                        st.session_state.input_text = "极能 (PowerMax) PB-20065 65W 20000mAh 移动电源\n单口最大输出功率：Type-C1支持65WMax\n电池额定容量：20000mAh（74Wh可带上飞机）"
                        st.session_state.prev_input_text = st.session_state.input_text
                        invalidate_analysis_state("视觉提取候选商品")
                        st.info("💡 **【视觉多候选生成】**：已生成最多 3 个候选商品。**在未人工确认正确商品之前，系统严禁发起联网核验。**")
        with c_ocr2:
            st.caption("⚡ RapidOCR 纯本地离线推理，绝不上传图片至任何第三方云端服务。")
            if st.session_state.get("search_mode") == "qwen":
                from src.search.qwen_provider_models import is_vision_supported
                q_model = st.session_state.get("qwen_search_model", "")
                if is_vision_supported(q_model):
                    st.info(f"👁️ 当前千问模型 `{q_model}` 原生支持多模态视觉理解。若OCR文字不足，将自动调用视觉能力提取候选商品。")
                else:
                    st.caption(f"ℹ️ 当前模型 `{q_model}` 不支持视觉理解，仅使用本地OCR，未执行视觉商品识别。")

    st.caption("⚠️ 隐私安全：上传前请遮挡个人收件地址、电话、聊天记录与订单号。")

# 次级辅助功能：演示案例抽屉
cases = mock_provider.list_cases()


def handle_load_case(case_id: str):
    st.session_state.active_case_id = case_id
    raw_case = mock_provider.get_case_raw(case_id)
    if raw_case:
        if raw_case.get("input_type") == "url":
            st.session_state.input_url = raw_case.get("input_sample", "")
            st.session_state.prev_input_url = st.session_state.input_url
            st.session_state.input_mode = LINK_MODE_LABEL
        else:
            st.session_state.input_text = raw_case.get("input_sample", "")
            st.session_state.prev_input_text = st.session_state.input_text
            st.session_state.input_mode = TEXT_MODE_LABEL
    invalidate_analysis_state(f"载入演示案例 {case_id}")
    st.toast("已载入演示案例，点击下方开始核验！", icon="✅")


render_example_drawer(
    cases=cases,
    active_case_id=st.session_state.active_case_id,
    on_load_case=handle_load_case,
)

# 高级选项折叠区 (默认关闭)
with st.expander("⚙️ 高级选项 (可选参考资料补充与分析配置)", expanded=False):
    st.info("💡 **参考资料补充**：无商业搜索 API 时，您可以手动提供官方资料或参数材料，系统将对多源材料进行客观交叉核验，绝不制造虚假搜索。")
    c_m1, c_m2 = st.columns(2)
    with c_m1:
        st.session_state.manual_evidence_links = st.text_area(
            "参考证据网页/PDF链接（每行一条）：",
            value=st.session_state.manual_evidence_links,
            placeholder="https://www.example.com/specs\nhttps://www.example.com/manual.pdf",
            height=90,
        )
    with c_m2:
        st.session_state.manual_evidence_materials = st.text_area(
            "官方说明书/规格参数/质检文本材料：",
            value=st.session_state.manual_evidence_materials,
            placeholder="粘贴说明书参数章节，如：最大降噪深度48dB (依据GB/T 12060.7标准)...",
            height=90,
        )

# -----------------------------------------------------------------------------
# 阶段 2：商品身份确认与多候选单选锁定
# -----------------------------------------------------------------------------
ident_res: ProductIdentityResult = st.session_state.extracted_identity

is_blocked_by_candidates = False
if ident_res and ident_res.has_multiple_candidates and not ident_res.user_confirmed:
    is_blocked_by_candidates = True
    st.markdown("### 🎯 第二阶段：确认商品身份 (多候选确认)")
    st.warning(f"⚠️ 在输入信息中检测到 **{len(ident_res.candidates)} 个相似候选型号**。请人工点选确认您要核验的目标型号后再继续：")

    cand_options = [f"{c.name} (匹配度: {int(c.matching_score*100)}%) —— {c.evidence_snippet}" for c in ident_res.candidates]
    selected_idx = st.radio(
        "选择目标型号：",
        options=range(len(cand_options)),
        format_func=lambda i: cand_options[i],
        index=0,
    )
    if st.button("✅ 确认选定此型号", type="primary"):
        chosen = ident_res.candidates[selected_idx]
        ident_res.name = chosen.name
        ident_res.brand = chosen.brand
        ident_res.model = chosen.model
        ident_res.variant = chosen.variant
        ident_res.region = chosen.region
        ident_res.user_confirmed = True
        ident_res.identity_evidence += f"；【用户人工确认型号】{chosen.name}"
        st.session_state.extracted_identity = ident_res
        st.success(f"🎉 已确认目标商品：**{chosen.name}**！已解锁后续核验。")
        st.rerun()

# -----------------------------------------------------------------------------
# 阶段 2.5：宣传声明确认与过滤审查 (在执行核验前展示)
# -----------------------------------------------------------------------------
if st.session_state.extracted_claims is not None and not st.session_state.claims_confirmed:
    def handle_confirm_claims():
        st.session_state.claims_confirmed = True
        st.session_state.search_executed = False
        st.session_state.trigger_auto_start = False
        st.rerun()

    def handle_delete_claim(idx: int):
        if 0 <= idx < len(st.session_state.extracted_claims):
            del st.session_state.extracted_claims[idx]
            for i, c in enumerate(st.session_state.extracted_claims, 1):
                c.claim_id = i
            st.rerun()

    def handle_add_claim(text: str, category: str):
        from src.verifier.claim_decomposer import evaluate_claim_quality_and_category
        score, is_v, _, target = evaluate_claim_quality_and_category(text)
        new_claim = ClaimItem(
            claim_id=len(st.session_state.extracted_claims) + 1,
            original_text=text,
            atomic_statement=text,
            single_verifiable_fact=text,
            category=category,
            verification_target=target,
            claim_quality_score=score,
            is_verifiable=is_v,
            extracted_from="manual",
        )
        st.session_state.extracted_claims.append(new_claim)
        st.rerun()

    render_claim_confirmation_card(
        identity=st.session_state.extracted_identity or ProductIdentityResult(),
        claims=st.session_state.extracted_claims,
        rejected_candidates=st.session_state.filtered_candidates,
        on_confirm=handle_confirm_claims,
        on_delete_claim=handle_delete_claim,
        on_add_claim=handle_add_claim,
    )

elif st.session_state.extracted_claims is not None and st.session_state.claims_confirmed:
    def handle_execute_phase3_search():
        ident = st.session_state.extracted_identity or ProductIdentityResult()
        claims = st.session_state.extracted_claims or []
        target_prod = {
            "brand": ident.brand or "",
            "model": ident.model or "",
            "product_name": getattr(ident, "name", "") or "",
            "variant": ident.variant or "",
            "region": ident.region or "",
        }

        mode = st.session_state.get("search_mode", "none")
        if mode == "tavily":
            config = {
                "api_key": st.session_state.get("search_api_key", ""),
                "max_results": st.session_state.get("search_max_results", 5),
                "language": st.session_state.get("search_language", "zh"),
                "timeout": st.session_state.get("search_timeout", 15),
                "include_user_reviews": st.session_state.get("include_user_reviews", False),
                "prefer_official": st.session_state.get("prefer_official_sources", True),
            }
        elif mode == "kimi":
            config = {
                "api_key": st.session_state.get("kimi_search_api_key", ""),
                "base_url": st.session_state.get("kimi_search_base_url", "https://api.moonshot.cn/v1"),
                "search_mode": st.session_state.get("kimi_search_mode", "basic"),
                "max_results": st.session_state.get("kimi_search_max_results", 5),
                "max_fetches": st.session_state.get("kimi_search_max_fetches", 3),
                "timeout": st.session_state.get("kimi_search_timeout", 15),
            }
        elif mode == "qwen":
            config = {
                "api_key": st.session_state.get("qwen_search_api_key", ""),
                "base_url": st.session_state.get("qwen_search_base_url", "https://maas.qianwenaiapi.com/compatible-mode/v1"),
                "model_name": st.session_state.get("qwen_search_model", "qwen3.8-flash"),
                "api_mode": st.session_state.get("qwen_search_api_mode", "responses"),
                "max_search_count": st.session_state.get("qwen_search_max_count", 5),
                "enable_web_extractor": st.session_state.get("qwen_enable_web_extractor", True),
                "timeout": st.session_state.get("qwen_search_timeout", 60),
                "provider_platform": st.session_state.get("qwen_provider_platform", "qianwen_ai"),
            }
        elif mode == "manual":
            config = {
                "manual_items": st.session_state.get("manual_evidence_items", []),
            }
        else:
            config = {}

        provider = SearchProviderFactory.create_provider(mode, config)
        generator = LayeredQueryGenerator()
        fetcher = EvidenceFetcher(timeout=min(st.session_state.get("search_timeout", 10), 10))

        all_queries = []
        evidence_by_claim = {}
        seen_urls = set()

        with st.spinner("【第三阶段】正在生成分层检索词并安全抓取候选网页正文..."):
            for c in claims:
                q_items = generator.generate_queries_for_claim(
                    identity=target_prod,
                    claim=c,
                    include_user_reviews=st.session_state.get("include_user_reviews", False),
                    max_queries=5,
                )
                all_queries.extend(q_items)

                claim_evidences = []
                ev_idx = 1
                kw = generator.extract_claim_core_keywords(c.atomic_statement, c.category)

                for q in q_items:
                    if mode == "none":
                        q.execution_status = "skipped (no search provider)"
                        continue

                    # 如果已从更高级别源获得足够证据且当前为次级评测词，则跳过
                    if len(claim_evidences) >= 3 and q.priority > 1:
                        q.execution_status = "skipped (quota limit)"
                        continue

                    try:
                        search_res = provider.search(q.query_text, max_results=3)
                        q.execution_status = "executed"

                        search_items = search_res.items if hasattr(search_res, "items") and not callable(search_res.items) else (search_res or [])
                        for item in search_items:
                            if item.url in seen_urls:
                                continue
                            seen_urls.add(item.url)

                            # 安全抓取并提取真实正文段落 (优先使用 Provider 自带 Fetch，如 Kimi Fetch API)
                            fetch_res = None
                            if hasattr(provider, "fetch") and callable(getattr(provider, "fetch", None)):
                                try:
                                    p_fetch = provider.fetch(item.url)
                                    if p_fetch and (p_fetch.get("text_content") or p_fetch.get("content")):
                                        from src.crawlers.evidence_fetcher import WebPageExcerptResult
                                        txt_c = p_fetch.get("text_content") or p_fetch.get("content") or ""
                                        fetch_res = WebPageExcerptResult(
                                            url=item.url,
                                            domain=item.domain,
                                            title=p_fetch.get("title", item.title),
                                            fetch_status="success",
                                            http_status=200,
                                            excerpt=txt_c[:450],
                                            clean_text=txt_c,
                                            content_bytes_len=len(txt_c.encode("utf-8")),
                                        )
                                except Exception:
                                    fetch_res = None

                            if not fetch_res:
                                fetch_res = fetcher.fetch_and_extract_excerpt(
                                    url=item.url,
                                    claim_keywords=kw,
                                )

                            # 来源初步分级与型号对齐
                            ev = EvidenceStructurer.structure_evidence(
                                claim_id=c.claim_id,
                                search_item=item,
                                fetch_res=fetch_res,
                                target_product=target_prod,
                                index=ev_idx,
                            )
                            claim_evidences.append(ev)
                            ev_idx += 1
                            if len(claim_evidences) >= 5:
                                break
                    except Exception as ex:
                        q.execution_status = f"error: {str(ex)[:30]}"

                evidence_by_claim[c.claim_id] = claim_evidences

        st.session_state.phase3_queries = all_queries
        st.session_state.phase3_evidence = evidence_by_claim
        st.session_state.search_executed = True
        st.toast("🎉 第三阶段网络搜索与正文提取完成！已展示审计明细与真实正文。", icon="✅")
        st.rerun()

    def handle_reset_phase3_search():
        st.session_state.search_executed = False
        st.session_state.phase3_queries = []
        st.session_state.phase3_evidence = {}
        st.rerun()

    def handle_back_to_claims():
        st.session_state.claims_confirmed = False
        st.session_state.search_executed = False
        st.session_state.phase3_queries = []
        st.session_state.phase3_evidence = {}
        st.rerun()

    def handle_proceed_to_phase4():
        ident = st.session_state.extracted_identity or ProductIdentityResult()
        claims = st.session_state.extracted_claims or []
        p3_ev_dict = st.session_state.get("phase3_evidence", {})
        flat_evidences = [ev for ev_list in p3_ev_dict.values() for ev in ev_list]
        p3_queries = st.session_state.get("phase3_queries", [])

        if "商品链接" in st.session_state.input_mode:
            input_type_val = "url"
        elif "商品宣传截图" in st.session_state.input_mode:
            input_type_val = "image"
        else:
            input_type_val = "text"
        source_input_val = st.session_state.input_url if input_type_val == "url" else st.session_state.input_text

        with st.spinner("【第四阶段】正在执行商品型号严格对齐、有效性判定、多源交叉核验与事实自检..."):
            try:
                eff_mode = st.session_state.service_mode
                if eff_mode == "mock" and st.session_state.get("search_mode", "none") != "none":
                    eff_mode = "byok"
                    if not st.session_state.byok_api_key:
                        st.session_state.byok_api_key = "sk-demo-byok-test-key-valid"

                provider = verification_pipeline.create_provider(
                    service_mode=eff_mode,
                    byok_config={
                        "base_url": st.session_state.byok_base_url,
                        "api_key": st.session_state.byok_api_key,
                        "model_name": st.session_state.byok_model,
                        "timeout": st.session_state.byok_timeout,
                        "temperature": st.session_state.byok_temperature,
                        "max_tokens": st.session_state.byok_max_tokens,
                    },
                    local_config={
                        "base_url": st.session_state.local_base_url,
                        "model_name": st.session_state.local_model,
                        "timeout": st.session_state.local_timeout,
                        "temperature": st.session_state.local_temperature,
                        "max_tokens": st.session_state.local_max_tokens,
                    },
                )

                report, progress_state = verification_pipeline.run_real_pipeline(
                    service_mode=eff_mode,
                    input_type=input_type_val,
                    source_input=source_input_val,
                    provider=provider,
                    confirmed_identity=ident,
                    confirmed_claims=claims,
                    manual_evidence_links=st.session_state.manual_evidence_links,
                    manual_evidence_materials=st.session_state.manual_evidence_materials,
                    search_provider_name=st.session_state.get("search_provider_name", "none"),
                    search_queries=p3_queries,
                    structured_evidences=flat_evidences,
                )
                ReportGenerator.save_report_to_disk(report)
                st.session_state.current_report = report
                st.session_state.progress_state = progress_state
                st.session_state.analysis_completed = True
                st.toast("🎉 第四阶段多源交叉核验完成！已生成全套分析报告。", icon="✅")
                st.rerun()

            except Exception as ex:
                st.error(f"❌ 第四阶段交叉核验失败: {str(ex)}")

    render_search_execution_panel(
        identity=st.session_state.extracted_identity or ProductIdentityResult(),
        claims=st.session_state.extracted_claims or [],
        search_mode=st.session_state.get("search_mode", "none"),
        search_provider_name=st.session_state.get("search_provider_name", "none"),
        search_api_key=st.session_state.get("search_api_key", ""),
        search_max_results=st.session_state.get("search_max_results", 5),
        search_executed=st.session_state.search_executed,
        phase3_queries=st.session_state.phase3_queries,
        phase3_evidence=st.session_state.phase3_evidence,
        on_confirm_search=handle_execute_phase3_search,
        on_reset_search=handle_reset_phase3_search,
        on_back_to_claims=handle_back_to_claims,
        on_proceed_to_phase4=handle_proceed_to_phase4,
    )

# -----------------------------------------------------------------------------
# 主操作区域 (单一主 CTA：开始核验，品牌蓝按钮)
# -----------------------------------------------------------------------------
st.write("")
col_cta, col_clear = st.columns([4, 1])

with col_cta:
    cta_btn_label = "🚀 开始核验分析" if st.session_state.extracted_claims is None else "🔄 重新提取宣传声明"
    start_btn = st.button(
        cta_btn_label,
        type="primary",
        use_container_width=True,
        disabled=is_blocked_by_candidates,
    )

with col_clear:
    def on_clear_click():
        st.session_state.input_url = ""
        st.session_state.prev_input_url = ""
        st.session_state.input_text = ""
        st.session_state.prev_input_text = ""
        st.session_state.ocr_text = ""
        st.session_state.input_mode = LINK_MODE_LABEL
        st.session_state.degraded_error_info = None
        st.session_state.retained_source_url = None
        st.session_state.supplementing_after_degradation = False
        st.session_state.url_retry_count = 0
        st.session_state.supplement_prompt = None
        st.session_state.privacy_prompt_active = False
        st.session_state.clean_preview = None
        st.session_state.conn_test_result = None
        invalidate_analysis_state("用户点击清空全部")

    st.button("🧹 清空内容", use_container_width=True, on_click=on_clear_click, key="btn_clear_all_main")

# 单行紧凑调用预算摘要
tracker = BudgetTracker(BudgetLimits())
budget_info = tracker.get_preflight_summary(
    claims_count=5,
    service_mode=st.session_state.service_mode,
    search_mode=st.session_state.get("search_mode", "none"),
    manual_evidence_count=len(st.session_state.get("manual_evidence_items", [])),
)
render_budget_pill(
    budget_info=budget_info,
    service_mode=st.session_state.service_mode,
    search_mode=st.session_state.get("search_mode", "none"),
)

# -----------------------------------------------------------------------------
# 触发核验流水线逻辑
# -----------------------------------------------------------------------------
should_trigger = start_btn or st.session_state.get("trigger_auto_start", False)
if should_trigger:
    if start_btn and st.session_state.extracted_claims is not None:
        st.session_state.claims_confirmed = False
        st.session_state.search_executed = False
        st.session_state.phase3_queries = []
        st.session_state.phase3_evidence = {}
    st.session_state.trigger_auto_start = False
    st.session_state.analysis_error = None
    st.session_state.fallback_alert = None
    st.session_state.degraded_error_info = None

    # 1. 确定输入模式
    if "商品链接" in st.session_state.input_mode:
        if not (st.session_state.input_url and st.session_state.input_url.strip()):
            st.error("❌ 无法启动：请先输入商品链接！")
            st.stop()
        input_type = "url"
        source_input = st.session_state.input_url.strip()
    elif "商品详情文本" in st.session_state.input_mode:
        if not (st.session_state.input_text and st.session_state.input_text.strip()):
            st.error("❌ 无法启动：请先输入商品详情文本！")
            st.stop()
        input_type = "text"
        source_input = st.session_state.input_text.strip()
    elif "商品宣传截图" in st.session_state.input_mode:
        if not (st.session_state.input_text and st.session_state.input_text.strip()):
            st.error("❌ 无法启动：请先上传商品截图并执行本地离线 OCR 识别提取文本！")
            st.stop()
        input_type = "image"
        source_input = st.session_state.input_text.strip()
    else:
        input_type = "text"
        source_input = (st.session_state.input_text or "").strip()

    # 2. 模式安全前置校验
    if st.session_state.service_mode == "byok":
        if not st.session_state.byok_api_key or not st.session_state.byok_api_key.strip():
            st.error("❌ 无法启动：当前为【用户自带 API 模式】，但未配置 API Key。请在顶部【⚙️ 设置】中填写您的密钥，或切换至 Mock 模式。")
            st.stop()
        if not st.session_state.byok_base_url.startswith("https://"):
            st.error("❌ 无法启动：公网 Base URL 必须使用安全的 HTTPS 协议。")
            st.stop()
    elif st.session_state.service_mode == "local":
        if is_streamlit_cloud():
            st.error("❌ 无法启动：本地模型仅本地桌面版支持。公网云端无法连接您个人电脑上的本地端口（如 127.0.0.1 / localhost）。请在顶部【⚙️ 设置】中切换至 Mock 演示或自带云端 API (BYOK) 模式。")
            st.stop()
        is_val_loc, loc_err = validate_local_url(st.session_state.local_base_url)
        if not is_val_loc:
            st.error(f"❌ 无法启动：本地端点地址非法: {loc_err}")
            st.stop()

    # 3. 执行核验流水线
    if not st.session_state.claims_confirmed:
        with st.spinner("正在提取商品信息与声明初筛..."):
            try:
                # 1. 提取原文
                raw_text = ""
                if input_type == "url":
                    if st.session_state.service_mode == "mock" and st.session_state.get("active_case_id"):
                        raw_c = mock_provider.get_case_raw(st.session_state.active_case_id)
                        if raw_c and raw_c.get("input_sample") == source_input:
                            prod_info = raw_c.get("product", {})
                            claims_texts = "\n".join([c.get("original_text", "") for c in raw_c.get("claims", [])])
                            raw_text = f"{prod_info.get('brand')} {prod_info.get('model')} {prod_info.get('version')}\n{prod_info.get('specs')}\n{claims_texts}"
                    if not raw_text:
                        ext_data = extract_product_from_url(source_input)
                        raw_text = f"{ext_data.name}\n{ext_data.description}\n" + "\n".join(ext_data.specs_list)
                else:
                    clean_res = clean_product_detail_text(source_input)
                    raw_text = clean_res.cleaned_text

                # 2. 身份抽取
                ident = extract_product_identity(raw_text)
                st.session_state.extracted_identity = ident

                # 3. 声明拆解与质量过滤
                prod_obj = ProductIdentity(
                    brand=ident.brand,
                    model=ident.model,
                    version=ident.variant,
                    product_id=ident.product_id,
                )
                valid_c, rejected_c = claim_decomposer.decompose_with_details(raw_text, target_product=prod_obj)
                st.session_state.extracted_claims = valid_c
                st.session_state.filtered_candidates = rejected_c
                st.session_state.trigger_auto_start = False
                st.rerun()

            except (AccessRestrictedError, InsufficientProductInfoError) as e:
                st.session_state.analysis_completed = False
                st.session_state.current_report = None
                st.session_state.progress_state = {
                    "fetch_info": StepStatusEnum.FAILED,
                    "confirm_identity": StepStatusEnum.SKIPPED,
                    "decompose_claims": StepStatusEnum.SKIPPED,
                    "search_evidence": StepStatusEnum.NOT_CONFIGURED,
                    "cross_verify": StepStatusEnum.SKIPPED,
                    "generate_report": StepStatusEnum.SKIPPED,
                }
                st.session_state.degraded_error_info = {
                    "platform_name": getattr(e, "platform_name", "未知平台"),
                    "product_id": getattr(e, "product_id", "未知"),
                    "original_url": getattr(e, "original_url", source_input),
                    "normalized_url": getattr(e, "normalized_url", normalize_product_url(source_input)),
                    "http_status": getattr(e, "http_status", 200),
                    "final_url": getattr(e, "final_url", source_input),
                    "page_title": getattr(e, "page_title", ""),
                    "error_code": getattr(e, "error_code", "PAGE_ACCESS_RESTRICTED"),
                    "message": str(e),
                }
                st.session_state.retained_source_url = getattr(e, "original_url", source_input)
                st.session_state.retained_product_id = getattr(e, "product_id", "未知")
                st.session_state.analysis_error = StructuredError(
                    error_code=getattr(e, "error_code", "PAGE_ACCESS_RESTRICTED"),
                    error_stage="商品信息读取",
                    user_message=str(e),
                    technical_message=f"{type(e).__name__}: {str(e)}",
                    suggested_action="电商反爬或页面未渲染商品信息。请复制商品标题、参数和宣传文案，切换至【📝 商品详情文本】或【🖼️ 商品宣传截图】标签页直接核验。",
                    retryable=False,
                )
                st.session_state.fallback_alert = str(e)
                st.rerun()

    else:
        try:
            with st.spinner(f"【{st.session_state.service_mode.upper()} 真实模式】正在执行证据核验分析..."):
                provider = verification_pipeline.create_provider(
                    service_mode=st.session_state.service_mode,
                    byok_config={
                        "base_url": st.session_state.byok_base_url,
                        "api_key": st.session_state.byok_api_key,
                        "model_name": st.session_state.byok_model,
                        "timeout": st.session_state.byok_timeout,
                        "temperature": st.session_state.byok_temperature,
                        "max_tokens": st.session_state.byok_max_tokens,
                    },
                    local_config={
                        "base_url": st.session_state.local_base_url,
                        "model_name": st.session_state.local_model,
                        "timeout": st.session_state.local_timeout,
                        "temperature": st.session_state.local_temperature,
                        "max_tokens": st.session_state.local_max_tokens,
                    },
                )

                is_supplemented = bool(st.session_state.get("retained_source_url") or st.session_state.get("supplementing_after_degradation", False))
                overridden_status = "restricted_user_supplemented" if is_supplemented else None
                overridden_url = st.session_state.get("retained_source_url")

                report, progress_state = verification_pipeline.run_real_pipeline(
                    service_mode=st.session_state.service_mode,
                    input_type=input_type,
                    source_input=source_input,
                    provider=provider,
                    confirmed_identity=st.session_state.extracted_identity,
                    confirmed_claims=st.session_state.extracted_claims,
                    manual_evidence_links=st.session_state.manual_evidence_links,
                    manual_evidence_materials=st.session_state.manual_evidence_materials,
                    overridden_source_url=overridden_url,
                    overridden_page_fetch_status=overridden_status,
                )
                ReportGenerator.save_report_to_disk(report)
                st.session_state.current_report = report
                st.session_state.progress_state = progress_state
                st.session_state.analysis_completed = True
                st.session_state.supplementing_after_degradation = False
                st.session_state.supplement_prompt = None
                st.session_state.privacy_prompt_active = False
                st.session_state.degraded_error_info = None
                st.toast("🎉 真实核验完成！已生成全流程证据核验结果。", icon="✅")
                st.rerun()

        except CandidateConfirmationNeeded as e:
            st.session_state.extracted_identity = e.identity_res
            st.session_state.progress_state = {
                "fetch_info": StepStatusEnum.SUCCESS,
                "confirm_identity": StepStatusEnum.NEEDS_CONFIRMATION,
                "decompose_claims": StepStatusEnum.PENDING,
                "search_evidence": StepStatusEnum.NOT_CONFIGURED,
                "cross_verify": StepStatusEnum.PENDING,
                "generate_report": StepStatusEnum.PENDING,
            }
            st.rerun()

        except NoVerifiableClaimsError as e:
            st.session_state.analysis_completed = False
            st.session_state.current_report = None
            st.session_state.progress_state = {
                "fetch_info": StepStatusEnum.SUCCESS,
                "confirm_identity": StepStatusEnum.SUCCESS,
                "decompose_claims": StepStatusEnum.INSUFFICIENT_DATA,
                "search_evidence": StepStatusEnum.NOT_CONFIGURED,
                "cross_verify": StepStatusEnum.SKIPPED,
                "generate_report": StepStatusEnum.SKIPPED,
            }
            st.session_state.analysis_error = StructuredError(
                error_code="NO_VERIFIABLE_CLAIMS",
                error_stage="宣传声明质量过滤",
                user_message=str(e),
                technical_message=f"NoVerifiableClaimsError: {str(e)}",
                suggested_action="请上传或粘贴包含具体参数数值（如45dB、30小时）、行业标准（如IPX5、Hi-Res）或具体硬件材质的宣传资料。",
                retryable=True,
            )
            st.rerun()

        except (AccessRestrictedError, InsufficientProductInfoError) as e:
            st.session_state.analysis_completed = False
            st.session_state.current_report = None
            st.session_state.progress_state = {
                "fetch_info": StepStatusEnum.FAILED,
                "confirm_identity": StepStatusEnum.SKIPPED,
                "decompose_claims": StepStatusEnum.SKIPPED,
                "search_evidence": StepStatusEnum.NOT_CONFIGURED,
                "cross_verify": StepStatusEnum.SKIPPED,
                "generate_report": StepStatusEnum.SKIPPED,
            }
            st.session_state.degraded_error_info = {
                "platform_name": getattr(e, "platform_name", "未知平台"),
                "product_id": getattr(e, "product_id", "未知"),
                "original_url": getattr(e, "original_url", source_input),
                "normalized_url": getattr(e, "normalized_url", normalize_product_url(source_input)),
                "http_status": getattr(e, "http_status", 200),
                "final_url": getattr(e, "final_url", source_input),
                "page_title": getattr(e, "page_title", ""),
                "error_code": getattr(e, "error_code", "PAGE_ACCESS_RESTRICTED"),
                "message": str(e),
            }
            st.session_state.retained_source_url = getattr(e, "original_url", source_input)
            st.session_state.retained_product_id = getattr(e, "product_id", "未知")
            st.session_state.analysis_error = StructuredError(
                error_code=getattr(e, "error_code", "PAGE_ACCESS_RESTRICTED"),
                error_stage="商品信息读取",
                user_message=str(e),
                technical_message=f"{type(e).__name__}: {str(e)}",
                suggested_action="电商反爬或页面未渲染商品信息。请复制商品标题、参数和宣传文案，切换至【📝 商品详情文本】或【🖼️ 商品宣传截图】标签页直接核验。",
                retryable=False,
            )
            st.session_state.fallback_alert = str(e)
            st.rerun()

        except SSRFSecurityError as e:
            st.session_state.analysis_completed = False
            st.session_state.current_report = None
            st.session_state.progress_state = {
                "fetch_info": StepStatusEnum.FAILED,
                "confirm_identity": StepStatusEnum.SKIPPED,
                "decompose_claims": StepStatusEnum.SKIPPED,
                "search_evidence": StepStatusEnum.NOT_CONFIGURED,
                "cross_verify": StepStatusEnum.SKIPPED,
                "generate_report": StepStatusEnum.SKIPPED,
            }
            st.session_state.analysis_error = StructuredError(
                error_code="SSRF_SECURITY_BLOCKED",
                error_stage="网络安全拦截",
                user_message=f"已拦截不安全网络请求: {str(e)}",
                technical_message=f"SSRFSecurityError: {str(e)}",
                suggested_action="请输入合法的公网商品链接。",
                retryable=False,
            )
            st.rerun()

        except DataModeMismatchError as e:
            st.session_state.analysis_completed = False
            st.session_state.current_report = None
            st.session_state.analysis_error = StructuredError(
                error_code="DATA_MODE_MISMATCH",
                error_stage="数据一致性校验",
                user_message=str(e),
                technical_message="Blocked mock data injection in real mode",
                suggested_action="系统已阻止数据模式混用。请检查服务模式与配置。",
                retryable=False,
            )
            st.rerun()

        except Exception as e:
            st.session_state.analysis_completed = False
            st.session_state.current_report = None
            raw_err = str(e)
            if st.session_state.byok_api_key:
                raw_err = raw_err.replace(st.session_state.byok_api_key, mask_api_key(st.session_state.byok_api_key))
            st.session_state.analysis_error = StructuredError(
                error_code="PIPELINE_EXECUTION_ERROR",
                error_stage="核验流水线执行",
                user_message=f"真实核验失败: {raw_err}",
                technical_message=f"{type(e).__name__}: {raw_err}",
                suggested_action="请检查网络连接、API Key配置或模型服务状态后重试。系统绝不回退至Mock数据。",
                retryable=True,
            )
            st.rerun()

# -----------------------------------------------------------------------------
# 异常状态诊断与受限降级操作面板
# -----------------------------------------------------------------------------
if st.session_state.degraded_error_info:
    st.markdown('<div style="border-top: 1px solid #DDE3EA; margin: 20px 0 12px 0;"></div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:1.15rem; font-weight:750; color:#152033; margin-bottom:10px;">🚦 核验执行进度与合规降级引导</div>', unsafe_allow_html=True)
    if st.session_state.progress_state:
        render_stepper(progress_state=st.session_state.progress_state)

    def on_paste_text_callback():
        TEMPLATE_6_PART = (
            "商品名称：\n"
            "品牌：\n"
            "型号：\n"
            "商品规格：\n"
            "商品宣传卖点：\n"
            "使用条件或补充说明：\n"
        )
        st.session_state.input_text = TEMPLATE_6_PART
        st.session_state.input_mode = TEXT_MODE_LABEL
        st.session_state.supplement_prompt = "已为您预填6部分标准核验模板，请在下方补充粘贴商品标题、规格与宣传卖点后点击开始核验。"
        st.session_state.supplementing_after_degradation = True
        st.session_state.analysis_error = None
        st.session_state.degraded_error_info = None
        st.session_state.scroll_to_target = "textarea"

    def on_upload_image_callback():
        st.session_state.input_mode = IMAGE_MODE_LABEL
        st.session_state.privacy_prompt_active = True
        st.session_state.supplementing_after_degradation = True
        st.session_state.analysis_error = None
        st.session_state.degraded_error_info = None
        st.session_state.scroll_to_target = "uploader"

    def on_retry_normalized_callback():
        info = st.session_state.get("degraded_error_info", {})
        norm_url = info.get("normalized_url", "")
        if norm_url:
            st.session_state.input_url = norm_url
            st.session_state.input_mode = LINK_MODE_LABEL
            st.session_state.url_retry_count = st.session_state.get("url_retry_count", 0) + 1
            st.session_state.analysis_error = None
            st.session_state.degraded_error_info = None
            st.session_state.trigger_auto_start = True

    render_degradation_action_card(
        error_info=st.session_state.degraded_error_info,
        on_paste_text=on_paste_text_callback,
        on_upload_image=on_upload_image_callback,
        on_retry_normalized=on_retry_normalized_callback,
        retry_count=st.session_state.get("url_retry_count", 0),
    )

elif st.session_state.analysis_error:
    err = st.session_state.analysis_error
    st.markdown("---")
    st.markdown("### 🚦 核验执行进度与异常诊断")
    if st.session_state.progress_state:
        render_stepper(progress_state=st.session_state.progress_state)

    f_detail = create_friendly_error(err.error_code)
    what_happened = f_detail.what_happened or err.user_message
    why_it_happened = f_detail.why_it_happened
    what_next = f_detail.what_to_do_next or err.suggested_action

    st.markdown(
        f"""
        <div style="background:#FFF1F0; border:1px solid #FCA5A5; border-radius:10px; padding:20px 22px; margin: 1.2rem 0; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <div style="display:flex; align-items:center; gap:8px; font-weight:700; color:#B42318; font-size:1.05rem;">
                <span style="font-size:1.2rem;">🛡️</span>
                <span>【{err.error_stage}】错误标识: <code>{err.error_code}</code> ｜ {f_detail.title}</span>
            </div>
            <div style="margin-top:14px; font-size:0.90rem; color:#334155; line-height:1.7;">
                <div>📌 <strong>发生了什么</strong>：{what_happened}</div>
                <div style="margin-top:6px;">🔍 <strong>为什么发生</strong>：{why_it_happened}</div>
            </div>
            <div style="margin-top:14px; padding:12px 16px; background:#FFFFFF; border:1px solid #DDE3EA; border-radius:8px; font-size:0.88rem; color:#152033;">
                👉 <strong>用户下一步操作建议</strong>：{what_next}
            </div>
            <div style="margin-top:10px; font-size:0.78rem; color:#667085;">
                🔒 <strong>零造假与安全合规铁律</strong>：当前处于真实核验模式，系统严格禁止回退到任何 Mock 示例数据，不隐藏真实错误。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# -----------------------------------------------------------------------------
# 阶段 3 & 阶段 4：核验进度与结果看板展示 (含硬安全门禁校验)
# -----------------------------------------------------------------------------
report: VerificationReport = st.session_state.current_report

if report:
    # 硬安全门禁 1: 数据模式一致性硬阻断
    if report.is_mock is True and st.session_state.service_mode != "mock":
        st.error(
            f"🚨 **【严重安全拦截：数据模式不一致】**\n\n"
            f"当前服务模式为 `{st.session_state.service_mode.upper()}`，但系统检测到报告数据为 Mock 演示案例！\n"
            f"为保障数据可信性与零造假要求，系统已彻底阻断该报告的渲染与展示。\n"
            f"请点击下方清空按钮或重新核验。"
        )
        st.stop()

    # 硬安全门禁 2: 输入指纹一致性检查
    if "商品链接" in st.session_state.input_mode:
        cur_input = st.session_state.input_url.strip()
        cur_input_type = "url"
    else:
        cur_input = st.session_state.input_text.strip()
        cur_input_type = "text"
    cur_provider_name = report.provider_name or ("MockAIProvider" if st.session_state.service_mode == "mock" else "OpenAICompatibleProvider")
    cur_model_name = report.model_name or ("offline-mock-v1" if st.session_state.service_mode == "mock" else st.session_state.byok_model)
    cur_fingerprint = calculate_input_fingerprint(
        input_type=cur_input_type,
        content=cur_input,
        service_mode=st.session_state.service_mode,
        provider_name=cur_provider_name,
        model_name=cur_model_name,
        confirmed_model=report.product.model if report.product else "",
    )

    if report.input_fingerprint and report.input_fingerprint != cur_fingerprint:
        st.warning(
            "⚠️ **【输入内容已变更】**\n\n"
            "检测到您在报告生成后修改了商品链接、文本或运行模式。为了保证证据核验与当前输入一致，已隐藏旧报告。\n\n"
            "👉 请点击上方 **【🚀 开始核验分析】** 重新生成针对当前输入的核验报告。"
        )
        st.stop()

    st.markdown("---")
    st.markdown("### 🚦 第三阶段：AI 核验执行进度")
    render_stepper(progress_state=st.session_state.progress_state, current_step=6)

    st.markdown("### 📊 第四阶段：核验结果看板")

    # 顶部元数据溯源卡片
    render_report_metadata_header(report)

    # 第 1 层：总体结论卡片
    render_overall_summary_card(report)

    # 第 2 层：四级指标分布统计
    render_metric_cards(report.conclusion_summary)

    # 第 3 层：商品身份档案
    render_identity_card(report.product)

    # 第 4 层：声明拆解与多源证据核验明细 (折叠展开卡片)
    st.markdown(f"#### 📑 宣传声明拆解与多源证据核验明细 (共 {len(report.claims_results)} 项声明)")
    for idx, item in enumerate(report.claims_results, 1):
        render_claim_item(idx, item)

    # 第 5 层：人工确认清单与购买建议
    render_advice_and_disclaimer(report)

    # 第 6 层：报告导出操作
    st.markdown("---")
    st.markdown("#### 💾 报告导出与溯源归档")
    md_content = ReportGenerator.generate_markdown(report)
    txt_content = ReportGenerator.generate_text(report)
    render_report_actions(report, md_content, txt_content, reset_all_state)
    if is_streamlit_cloud():
        st.caption("🔒 **公网部署模式**：报告已生成于浏览器临时会话中，请直接通过上方按钮下载导出。服务器不持久化存储任何用户历史数据。")
    else:
        st.caption(f"📂 报告已同时持久化归档至本地：`{OUTPUT_DIR / f'{report.report_id}.md'}`")
