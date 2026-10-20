"""ClaimCheck Pro 现代白亮专业 UI 组件库 (White/Light SaaS Components)
完全遵循 Clean / Minimal / Trustworthy / Calm / Modern SaaS 视觉风格与 WCAG AA 标准
"""

import textwrap
from typing import List, Optional
import streamlit as st

from streamlit_app.schemas import (
    ALLOWED_CLAIM_CATEGORIES,
    ClaimItem,
    FilteredCandidate,
    VerificationReport,
)
from src.core.security import mask_search_api_key
from src.search.query_generator import LayeredQueryGenerator
from src.verifier.identity_extractor import ProductIdentityResult


def render_top_navbar(service_mode: str, on_new_check):
    """顶部轻量级白底导航栏 (高度约 64px)"""
    mode_configs = {
        "mock": ("🟢 Mock 演示模式", "#15803D", "#F0FDF4", "#86EFAC"),
        "byok": ("☁️ BYOK 模式", "#1D4ED8", "#EFF6FF", "#BFDBFE"),
        "local": ("💻 本地模型", "#6D28D9", "#F5F3FF", "#DDD6FE"),
    }
    mode_text, text_color, bg_color, border_color = mode_configs.get(
        service_mode, ("Mock 模式", "#15803D", "#F0FDF4", "#86EFAC")
    )

    c_left, c_right = st.columns([7, 3])
    with c_left:
        st.markdown(
            """
            <div class="top-navbar">
                <div class="nav-brand">
                    <span style="font-size:1.35rem;">🔍</span>
                    <span class="nav-title">ClaimCheck Pro</span>
                    <span class="nav-badge">商品宣传真实性与参数证据核验系统</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c_right:
        c_mode, c_btn = st.columns([1.1, 1])
        with c_mode:
            st.markdown(
                f"""
                <div style="text-align:right; margin-top:8px;">
                    <span style="font-size:0.83rem; color:{text_color}; font-weight:600; background:{bg_color}; padding:6px 12px; border-radius:8px; border:1px solid {border_color};">
                        {mode_text}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c_btn:
            if st.button("🔄 新建核验", use_container_width=True):
                on_new_check()


def render_hero_banner():
    """简洁清晰的 Hero 标语区"""
    st.markdown(
        """
        <div class="hero-container">
            <h1 class="hero-title">核验商品宣传，查看真实依据</h1>
            <p class="hero-subtitle">
                输入商品链接、粘贴详情文本或上传商品截图，对比官方资料与权威评测，透视夸大宣传。
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_badge(service_mode: str, byok_url: str = "", byok_model: str = "", local_url: str = "", local_model: str = ""):
    """紧凑状态提示小胶囊 (柔和浅色背景与高对比度文字)"""
    if service_mode == "mock":
        st.markdown(
            """
            <div class="status-pill-mock">
                <span>🟢</span>
                <span><strong>Mock 演示模式</strong> · 内置离线标准资料库与毫秒级比对 · 不产生网络与云端 API 费用</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif service_mode == "byok":
        masked_url = byok_url or "https://api.openai.com/v1"
        st.markdown(
            f"""
            <div class="status-pill-byok">
                <span>☁️</span>
                <span><strong>用户自带 API (BYOK)</strong> · 端点: <code>{masked_url}</code> · 模型: <code>{byok_model or 'gpt-4o-mini'}</code> · 费用由用户自有账户承担</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif service_mode == "local":
        masked_local = local_url or "http://127.0.0.1:11434/v1"
        st.markdown(
            f"""
            <div class="status-pill-local">
                <span>💻</span>
                <span><strong>用户本地模型</strong> · 端点: <code>{masked_local}</code> · 模型: <code>{local_model or 'qwen2.5:7b'}</code> · 0 外部费用 · 数据完全保留在本地</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_example_drawer(cases: list, active_case_id: str, on_load_case):
    """次级案例抽屉 (白底浅框弱化辅助功能)"""
    with st.expander("💡 没有商品？试用预置演示案例 (Sample Cases)", expanded=False):
        st.caption("快捷载入典型核验场景（含充分印证、部分支持、标称冲突与证据不足）：")
        cols = st.columns(4)
        for idx, c in enumerate(cases[:4]):
            with cols[idx]:
                c_name = c.get("case_name", c.get("case_id", f"案例 {idx+1}"))
                st.markdown(
                    f"""
                    <div style="background:#F8FAFC; padding:10px 12px; border-radius:8px; border:1px solid #E2E8F0; min-height:86px; margin-bottom:6px;">
                        <div style="font-weight:650; font-size:0.86rem; color:#0F172A; margin-bottom:4px;">{c_name[:16]}</div>
                        <div style="font-size:0.75rem; color:#64748B;">输入类型: {c.get('input_type', '公开链接/文本')}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.button(
                    f"加载案例 {idx+1} (Case {idx+1})",
                    key=f"btn_case_{c['case_id']}",
                    on_click=on_load_case,
                    args=(c["case_id"],),
                    use_container_width=True,
                )


def render_budget_pill(budget_info: dict, service_mode: str, search_mode: str = "none"):
    """紧凑调用预算摘要与详情展开 (清晰分离模型与搜索费用)"""
    payer_text = budget_info.get("payer", "用户自行承担")
    search_payer = budget_info.get("search_payer", "零费用 (不发起网络检索)")
    search_req = budget_info.get("search_requests_count", "0 次 (未配置搜索)")

    if service_mode == "mock":
        st.markdown(
            """
            <div class="budget-pill-line">
                ⏱️ 预计：最多 5 条宣传声明 · 预置数据比对 · 搜索: <strong>0次请求</strong> · <strong>零 API 费用</strong> (Mock演示)
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="budget-pill-line">
                ⏱️ 预计：最多 {budget_info.get('claims_count', '5 条')} · {budget_info.get('estimated_model_calls', '约 3 次')} · 搜索: <strong>{search_req}</strong> · 承担方：<strong>{payer_text} ｜ 搜索: {search_payer}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("🔍 查看调用预算与防超额规则详情", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("单次最大声明", f"{budget_info.get('claims_count', '5 条')}")
        c2.metric("模型调用上限", f"{budget_info.get('estimated_model_calls', '3 次')}")
        c3.metric("搜索请求上限", f"{search_req}")
        c4.metric("超时限制", f"{budget_info.get('timeout_limit', '60 秒')}")

        st.markdown(
            f"""
            <div style="font-size:0.8rem; color:#475467; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:6px; padding:8px 12px; margin-top:8px;">
                <div>• <strong>检索模式</strong>：<code>{search_mode.upper()}</code> ｜ 每条声明最大抓取：<code>{budget_info.get('max_search_results_per_claim', '5 条')}</code> ｜ 最大重试：<code>{budget_info.get('max_retries', '1 次')}</code></div>
                <div>• <strong>费用防线</strong>：系统 100% 杜绝开发者代付模式。未配置搜索服务时，搜索请求数严格为 0，不捏造任何检索结果。</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_report_metadata_header(report: VerificationReport):
    """板块 1: 分析模式与来源标识卡片 (根据第十三阶段规范设计)"""
    # 1. 数据模式文字
    if report.is_mock:
        mode_badge = '<span class="badge-supported" style="background:#F0FDF4; color:#16865C; border:1px solid #86EFAC;">🟢 Mock 演示数据 (is_mock=True)</span>'
    elif report.search_status == "not_configured":
        mode_badge = '<span class="badge-partial" style="background:#FFF8E6; color:#9A6700; border:1px solid #FDE68A;">💻 实时模型分析 (未配置独立搜索 · is_mock=False)</span>'
    else:
        mode_badge = '<span class="badge-byok" style="background:#EFF6FF; color:#356AE6; border:1px solid #BFDBFE; padding:3px 8px; border-radius:6px; font-weight:600; font-size:0.8rem;">🌐 实时网络核验 (is_mock=False)</span>'

    # 2. 网页读取状态
    fetch_map = {
        "success": "✅ 抓取成功",
        "failed": "❌ 读取受限/失败",
        "restricted": "🛡️ 访问受限",
        "restricted_user_supplemented": "🛡️ 受限，已由用户补充资料",
        "insufficient_data": "⚠️ 信息不足",
        "not_executed": "➖ 未执行 (文本/截图模式)",
    }
    fetch_text = fetch_map.get(report.page_fetch_status, report.page_fetch_status)

    # 3. 搜索服务状态
    search_map = {
        "executed": "🟢 已执行全网实时检索",
        "not_configured": "⚪ 未配置网络搜索服务",
        "failed": "🔴 检索失败",
        "manual_only": "🟡 仅使用手动补充证据",
        "mock_preset": "🟢 离线预置标准凭证",
    }
    search_text = search_map.get(report.search_status, report.search_status)
    sp_name = getattr(report, "search_provider_name", "") or ("无" if report.search_status == "not_configured" else "内置")

    img_method_tag = ""
    if getattr(report, "input_type", "") == "image" or "截图" in (report.evidence_scope or ""):
        img_method_tag = '<span>📷 检索机制：<strong style="color:#0284C7;">基于图片文字与商品特征的联网检索 (非传统反向图片搜索)</strong></span>'

    card_html = f"""<div class="saas-card" style="margin-bottom:1rem; padding:16px 20px; background:#FFFFFF; border:1px solid #DDE3EA; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
<div style="font-size:0.95rem; font-weight:700; color:#0F172A; margin-bottom:10px; display:flex; align-items:center; gap:8px;">
    <span>🔍</span> <span>板块 1：分析模式与来源标识</span>
</div>
<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:12px; font-size:0.85rem;">
<div><span style="color:#667085; font-weight:500;">数据分析模式：</span><div style="margin-top:2px;">{mode_badge}</div></div>
<div><span style="color:#667085; font-weight:500;">语言模型 Provider：</span><div style="font-weight:650; color:#152033; margin-top:2px;"><code>{getattr(report, 'ai_provider_name', '') or report.provider_name}</code> · <strong>{getattr(report, 'ai_model_name', '') or report.model_name}</strong></div></div>
<div><span style="color:#667085; font-weight:500;">网络搜索 Provider：</span><div style="font-weight:600; color:#152033; margin-top:2px;"><code>{sp_name}</code> ({search_text})</div></div>
<div><span style="color:#667085; font-weight:500;">商品主页读取：</span><div style="font-weight:600; color:#152033; margin-top:2px;">{fetch_text}</div></div>
<div style="grid-column: 1 / -1; margin-top:4px; padding-top:10px; border-top:1px dashed #DDE3EA; display:flex; flex-wrap:wrap; gap:16px; font-size:0.82rem; color:#475569;">
    <span>📊 真实搜索查询：<strong style="color:#2563EB;">{getattr(report, 'search_query_count', 0)} 次</strong></span>
    <span>🌐 候选公开网页：<strong style="color:#0F172A;">{getattr(report, 'candidate_webpage_count', 0)} 个</strong></span>
    <span>📑 成功提取正文：<strong style="color:#15803D;">{getattr(report, 'extracted_webpage_count', 0)} 项</strong></span>
    <span>🔒 证据采纳范围：<strong style="color:#0F172A;">{report.evidence_scope or '用户输入与全网公开证据'}</strong></span>
    {img_method_tag}
</div>
</div>
</div>"""
    st.markdown(card_html, unsafe_allow_html=True)

    if report.search_status == "not_configured" and not report.is_mock:
        st.info(
            "💡 **未配置网络搜索服务提示**：AI模型已完成宣传声明拆解与逻辑比对，但因未配置独立搜索API，"
            "系统未向公网发起实时检索，结论严格基于当前输入资料判定。若需全网交叉比对，请在设置中配置搜索API。"
        )


def render_stepper(progress_state: Optional[dict] = None, current_step: int = 6):
    """六步渐进式状态指示器：两行展示 (第一行步骤名，第二行完整状态)，桌面横向，移动端纵向"""
    step_defs = [
        ("fetch_info", "1.提交商品资料"),
        ("confirm_identity", "2.确认商品身份"),
        ("decompose_claims", "3.确认宣传声明"),
        ("search_evidence", "4.搜索公开证据"),
        ("cross_verify", "5.多源核验证据"),
        ("generate_report", "6.查看导出报告"),
    ]

    status_styles = {
        "success": ("✓ 已完成", "#16865C", "#F0FDF4", "#86EFAC"),
        "running": ("● 执行中", "#356AE6", "#EFF6FF", "#BFDBFE"),
        "failed": ("✗ 访问受限", "#D64545", "#FFF1F0", "#FCA5A5"),
        "not_configured": ("⚪ 未配置", "#667085", "#F6F8FB", "#DDE3EA"),
        "skipped": ("— 已跳过", "#98A2B3", "#F6F8FB", "#DDE3EA"),
        "needs_confirmation": ("⚠️ 待确认", "#B7791F", "#FFF8E6", "#FDE68A"),
        "insufficient_data": ("⚠️ 信息不足", "#B7791F", "#FFF8E6", "#FDE68A"),
        "pending": ("待执行", "#667085", "#F6F8FB", "#DDE3EA"),
    }

    boxes_html = []
    if progress_state:
        for key, name in step_defs:
            status = progress_state.get(key, "pending")
            status_val = status.value if hasattr(status, "value") else str(status)
            text, fg, bg, border = status_styles.get(status_val, (status_val, "#667085", "#F6F8FB", "#DDE3EA"))
            boxes_html.append(
                f'<div class="step-box-v2"><div class="step-title-v2">{name}</div><div class="step-status-v2" style="color:{fg}; background:{bg}; border:1px solid {border};">{text}</div></div>'
            )
    else:
        for idx, (key, name) in enumerate(step_defs, 1):
            if idx < current_step:
                status_val = "success"
            elif idx == current_step:
                status_val = "running"
            else:
                status_val = "pending"
            text, fg, bg, border = status_styles.get(status_val, (status_val, "#667085", "#F6F8FB", "#DDE3EA"))
            boxes_html.append(
                f'<div class="step-box-v2"><div class="step-title-v2">{name}</div><div class="step-status-v2" style="color:{fg}; background:{bg}; border:1px solid {border};">{text}</div></div>'
            )

    full_stepper = "".join(boxes_html)
    st.markdown(
        f'<div class="stepper-container-v2">{full_stepper}</div>',
        unsafe_allow_html=True,
    )


def render_degradation_action_card(
    error_info: dict,
    on_paste_text,
    on_upload_image,
    on_retry_normalized,
    retry_count: int = 0,
):
    """渲染白色受限页面合规降级操作卡片"""
    platform_name = error_info.get("platform_name", "未知平台")
    product_id = error_info.get("product_id", "未知")
    original_url = error_info.get("original_url", "")
    normalized_url = error_info.get("normalized_url", "")
    http_status = error_info.get("http_status", 200)
    page_title = error_info.get("page_title", "")
    error_code = error_info.get("error_code", "PAGE_ACCESS_RESTRICTED")

    card_html = f"""<div class="saas-card" style="border: 1px solid #DDE3EA; border-top: 4px solid #D64545; padding: 18px 22px; margin-top: 0.8rem; margin-bottom: 0.8rem;">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
<div style="display:flex; align-items:center; gap:8px;">
<span style="font-size:1.35rem;">🛡️</span>
<span style="font-size:1.15rem; font-weight:750; color:#152033;">无法自动读取该商品页面</span>
</div>
<span style="background:#FFF1F0; color:#B42318; border:1px solid #FCA5A5; padding:3px 10px; border-radius:6px; font-weight:700; font-size:0.8rem;">访问受限 · 合规降级保护</span>
</div>
<p style="font-size:0.88rem; color:#526176; line-height:1.55; margin-bottom:12px;">该页面可能依赖登录、验证码、JavaScript动态加载或平台访问保护。<strong>ClaimCheck Pro 不会绕过平台限制，也不会使用 Mock 商品替代真实结果。</strong></p>
<div style="background:#FFF1F0; border-left:3px solid #B42318; padding:7px 12px; border-radius:0 6px 6px 0; margin-bottom:14px; font-size:0.85rem; color:#B42318; font-weight:600;">🔒 核心结论：直接读取被平台安全策略拦截，但您可以通过补充文字或截图无缝继续本次核验。</div>
<div style="background:#F6F8FB; border:1px solid #DDE3EA; border-radius:8px; padding:10px 14px; margin-bottom:14px;">
<div style="font-size:0.84rem; font-weight:700; color:#152033; margin-bottom:8px;">📋 识别到的请求与页面元数据：</div>
<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:8px; font-size:0.82rem;">
<div><span style="color:#667085;">电商平台：</span> <strong style="color:#152033;">{platform_name}</strong></div>
<div><span style="color:#667085;">商品识别ID：</span> <strong style="color:#152033;">{product_id}</strong></div>
<div><span style="color:#667085;">HTTP 状态码：</span> <strong style="color:#152033;">{http_status}</strong></div>
<div><span style="color:#667085;">错误类型编码：</span> <code style="color:#B42318; font-weight:600;">{error_code}</code></div>
<div style="grid-column: 1 / -1;"><span style="color:#667085;">页面抓取标题：</span> <span style="color:#152033;">{page_title or '（未抓取到有效标题）'}</span></div>
<div style="grid-column: 1 / -1; word-break:break-all;"><span style="color:#667085;">原始输入链接：</span> <span style="color:#526176;">{original_url}</span></div>
<div style="grid-column: 1 / -1; word-break:break-all;"><span style="color:#667085;">标准化链接：</span> <span style="color:#356AE6;">{normalized_url}</span></div>
</div>
</div>
<div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-bottom:12px;">
<div style="background:#FFFFFF; border:1px solid #DDE3EA; border-radius:8px; padding:10px 12px;">
<div style="font-weight:700; font-size:0.85rem; color:#152033; margin-bottom:4px;">❓ 为什么读取失败？</div>
<ul style="margin:0; padding-left:16px; font-size:0.8rem; color:#526176; line-height:1.5;">
<li>平台触发非浏览器反自动化检测，强制跳转验证码。</li>
<li>商品核心规格由前端异步 JS 动态渲染，静态无法提取。</li>
<li>为保障用户隐私与合规，系统绝不暴力破解或盗用 Cookie。</li>
</ul>
</div>
<div style="background:#EFF6FF; border:1px solid #BFDBFE; border-radius:8px; padding:10px 12px;">
<div style="font-weight:700; font-size:0.85rem; color:#1D4ED8; margin-bottom:4px;">💡 接下来怎么做？</div>
<ul style="margin:0; padding-left:16px; font-size:0.8rem; color:#1E40AF; line-height:1.5;">
<li>点击下方【粘贴商品详情文本】蓝色主按钮，直接复制粘贴文案。</li>
<li>点击下方【上传宣传截图】次级按钮，通过本地离线 OCR 提取参数。</li>
<li>若含有多余营销参数，可尝试【使用标准化链接重新尝试】（最多重试1次）。</li>
</ul>
</div>
</div>
<div style="font-size:0.85rem; font-weight:700; color:#152033; margin-bottom:4px;">👇 请在下方直接选择处理方式继续核验（无需刷新）：</div>
</div>"""
    st.markdown(card_html, unsafe_allow_html=True)

    # 3个操作按钮紧随其后
    c1, c2, c3 = st.columns([1.25, 1.25, 1.5])
    with c1:
        st.button(
            "📋 粘贴商品详情文本",
            type="primary",
            use_container_width=True,
            on_click=on_paste_text,
            key="btn_deg_paste",
        )
    with c2:
        st.button(
            "🖼️ 上传商品宣传截图",
            type="secondary",
            use_container_width=True,
            on_click=on_upload_image,
            key="btn_deg_image",
        )
    with c3:
        can_retry = retry_count < 1
        retry_label = "🔄 使用标准化链接重新尝试 (最多重试1次)" if can_retry else "🔒 已达重试上限 (最多重试1次，请改用文本/截图)"
        st.button(
            retry_label,
            use_container_width=True,
            disabled=not can_retry,
            on_click=on_retry_normalized,
            key="btn_deg_retry",
        )



def render_overall_summary_card(report: VerificationReport):
    """板块 3: 综合研判与核心结论卡片"""
    summary_text = report.overall_summary or "本次核验已完成各项声明与公开凭证的多源交叉比对。"
    verified_count = len(report.claims_results)
    human_count = getattr(report, "manual_review_count", len(report.human_verification_items or []))

    st.markdown(
        f"""
        <div class="saas-card" style="border-left: 4px solid #2563EB; margin-top:1rem; margin-bottom:1rem;">
            <div style="font-size:0.95rem; font-weight:700; color:#2563EB; margin-bottom:6px; display:flex; align-items:center; gap:8px;">
                <span>📋</span> <span>板块 3：综合研判与核心结论</span>
            </div>
            <div style="font-size:1.02rem; font-weight:600; color:#0F172A; line-height:1.65; margin-bottom:10px;">
                {summary_text}
            </div>
        """,
        unsafe_allow_html=True,
    )

    if getattr(report, "highest_risk_claim", None):
        st.markdown(
            f"""
            <div style="background:#FEF2F2; border:1px solid #FECACA; border-radius:6px; padding:10px 14px; margin-bottom:10px; font-size:0.86rem; color:#991B1B;">
                🚨 <strong>重点关注冲突声明</strong>：{report.highest_risk_claim}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
            <div style="font-size:0.82rem; color:#475569; display:flex; flex-wrap:wrap; gap:16px;">
                <span>• 已核验核心声明：<strong style="color:#0F172A;">{verified_count} 条</strong></span>
                <span>• 需人工复核重点：<strong style="color:{'#B91C1C' if human_count > 0 else '#15803D'};">{human_count} 项</strong></span>
                <span>• 核验引擎：<strong style="color:#0F172A;">ClaimCheck Pro V0.1.7 (Phase 4 强化版)</strong></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_cards(report_or_summary):
    """板块 2: 总体统计卡片 (4级结论分布 + 阶段4度量细项，兼容报告对象或字典)"""
    if isinstance(report_or_summary, dict):
        summary = report_or_summary
        valid_cnt = 0
        indep_cnt = 0
        manual_cnt = 0
        total_claims = sum(summary.values())
    else:
        summary = report_or_summary.conclusion_summary or {}
        valid_cnt = getattr(report_or_summary, "valid_evidence_count", 0)
        indep_cnt = getattr(report_or_summary, "independent_source_count", 0)
        manual_cnt = getattr(report_or_summary, "manual_review_count", 0)
        total_claims = len(report_or_summary.claims_results) if report_or_summary.claims_results else sum(summary.values())

    st.markdown(
        """
        <div style="font-size:0.95rem; font-weight:700; color:#0F172A; margin-top:1rem; margin-bottom:8px; display:flex; align-items:center; gap:8px;">
            <span>📈</span> <span>板块 2：四级核验结论分布统计</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div style="background:#ECFDF5; border:1px solid #A7F3D0; border-top:4px solid #10B981; border-radius:8px; padding:12px 14px; text-align:center;">
                <span style="font-size:0.86rem; font-weight:700; color:#047857;">🟢 有证据支持</span>
                <div style="font-size:1.85rem; font-weight:800; color:#10B981; margin:4px 0;">{summary.get('有证据支持', 0)}</div>
                <div style="font-size:0.75rem; color:#065F46;">同型号权威资料充分印证</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div style="background:#FFFBEB; border:1px solid #FDE68A; border-top:4px solid #F59E0B; border-radius:8px; padding:12px 14px; text-align:center;">
                <span style="font-size:0.86rem; font-weight:700; color:#B45309;">🟡 部分支持</span>
                <div style="font-size:1.85rem; font-weight:800; color:#F59E0B; margin:4px 0;">{summary.get('部分支持', 0)}</div>
                <div style="font-size:0.75rem; color:#78350F;">核心属实但省略限定条件</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div style="background:#FEF2F2; border:1px solid #FECACA; border-top:4px solid #EF4444; border-radius:8px; padding:12px 14px; text-align:center;">
                <span style="font-size:0.86rem; font-weight:700; color:#B91C1C;">🔴 存在冲突</span>
                <div style="font-size:1.85rem; font-weight:800; color:#EF4444; margin:4px 0;">{summary.get('存在冲突', 0)}</div>
                <div style="font-size:0.75rem; color:#7F1D1D;">参数与官方资料直接矛盾</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
            <div style="background:#F9FAFB; border:1px solid #E5E7EB; border-top:4px solid #6B7280; border-radius:8px; padding:12px 14px; text-align:center;">
                <span style="font-size:0.86rem; font-weight:700; color:#374151;">⚪ 证据不足</span>
                <div style="font-size:1.85rem; font-weight:800; color:#6B7280; margin:4px 0;">{summary.get('证据不足', 0)}</div>
                <div style="font-size:0.75rem; color:#4B5563;">未查到同型号客观凭证</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 阶段 4 强化附加指标行
    st.markdown(
        f"""
        <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; margin-top:10px; margin-bottom:14px; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:10px 14px;">
            <div style="text-align:center;">
                <span style="font-size:0.75rem; color:#64748B;">核心声明总数</span>
                <div style="font-weight:700; color:#0F172A; font-size:1rem;">{total_claims} 项</div>
            </div>
            <div style="text-align:center;">
                <span style="font-size:0.75rem; color:#64748B;">筛选有效证据</span>
                <div style="font-weight:700; color:#15803D; font-size:1rem;">{valid_cnt} 项</div>
            </div>
            <div style="text-align:center;">
                <span style="font-size:0.75rem; color:#64748B;">独立证据源</span>
                <div style="font-weight:700; color:#2563EB; font-size:1rem;">{indep_cnt} 个</div>
            </div>
            <div style="text-align:center;">
                <span style="font-size:0.75rem; color:#64748B;">需人工复核</span>
                <div style="font-weight:700; color:{'#EF4444' if manual_cnt > 0 else '#64748B'}; font-size:1rem;">{manual_cnt} 项</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_identity_card(prod):
    """板块 4: 商品身份档案 (Product Identity 双列网格与铭牌核对)"""
    st.markdown(
        f"""
        <div class="saas-card" style="margin-top:1rem; margin-bottom:1rem;">
            <div class="saas-card-header">
                <span class="saas-card-title">🏷️ 板块 4：商品身份档案 (Product Identity)</span>
                <span style="font-size:0.8rem; color:#15803D; background:#DCFCE7; border:1px solid #86EFAC; padding:3px 10px; border-radius:6px; font-weight:600;">
                    识别置信度 {int(getattr(prod, 'confidence', 0.9) * 100)}%
                </span>
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:14px; margin-bottom:12px;">
                <div><span style="color:#64748B; font-size:0.82rem;">品牌 (Brand)</span><div style="font-weight:650; color:#0F172A; font-size:1rem;">{prod.brand or '未知品牌'}</div></div>
                <div><span style="color:#64748B; font-size:0.82rem;">标准型号 (Model)</span><div style="font-weight:650; color:#0F172A; font-size:1rem;">{prod.model or '未知型号'}</div></div>
                <div><span style="color:#64748B; font-size:0.82rem;">版本 / 规格</span><div style="font-weight:650; color:#0F172A; font-size:1rem;">{prod.version or '标准规格'}</div></div>
                <div><span style="color:#64748B; font-size:0.82rem;">销售地区</span><div style="font-weight:650; color:#0F172A; font-size:1rem;">{prod.sales_region or '中国大陆'}</div></div>
            </div>
            <div style="font-size:0.82rem; color:#475569; border-top:1px solid #F1F5F9; padding-top:8px;">
                🔍 <strong>识别依据</strong>：{getattr(prod, 'specs', '') or '经公开页面结构化参数与正文严格对齐'}
            </div>
            <div style="background:#FFFBEB; border:1px solid #FDE68A; border-radius:6px; padding:8px 12px; margin-top:8px; font-size:0.82rem; color:#92400E;">
                💡 <strong>铭牌核对提醒</strong>：购买前后请重点核对机身铭牌与系统信息中显示的型号是否为【{prod.model}】，谨防同系列低配衍生版或海外版混淆。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_claim_item(idx: int, item):
    """板块 5: 单条声明拆解与多源证据折叠卡片 (完全符合第十三阶段要求)"""
    claim = item.claim
    conc = getattr(item, "verdict", None) or (item.conclusion.value if hasattr(item.conclusion, 'value') else str(item.conclusion))
    badge_colors = {
        "有证据支持": ("#10B981", "#ECFDF5", "#A7F3D0"),
        "部分支持": ("#F59E0B", "#FFFBEB", "#FDE68A"),
        "存在冲突": ("#EF4444", "#FEF2F2", "#FECACA"),
        "证据不足": ("#6B7280", "#F9FAFB", "#E5E7EB"),
    }
    b_fg, b_bg, b_border = badge_colors.get(conc, ("#6B7280", "#F9FAFB", "#E5E7EB"))

    statement = claim.atomic_statement
    conf_score = getattr(item, "confidence_score", round(item.confidence * 100.0, 1))
    conf_level = getattr(item, "confidence_level", "中")
    needs_review = getattr(item, "needs_manual_review", False)
    valid_ev_count = len([e for e in item.evidences if getattr(e, "is_valid_evidence", True)])

    # 1行简明核心理由摘要
    brief_reason = (item.analysis_reason or "").split("\n")[0].strip()
    if len(brief_reason) > 65:
        brief_reason = brief_reason[:65] + "..."

    review_badge_title = " ⚠️ [需复核]" if needs_review else ""
    # 折叠状态下包含：声明、结论、置信度、有效证据数、一句话具体理由 (符合阶段五规范)
    expander_title = f"声明 {idx}：{statement} ｜ 【{conc}】 ｜ 置信度: {conf_level}({conf_score:.0f}分) ｜ 有效证据: {valid_ev_count}项 ｜ 简述: {brief_reason}{review_badge_title}"

    with st.expander(expander_title, expanded=False):
        # 折叠卡片顶部概要行
        st.markdown(
            f"""
            <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:10px 14px; margin-bottom:12px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <span style="font-size:0.92rem; font-weight:700; color:#0F172A;">
                        #{idx} 【{claim.category}】{claim.single_verifiable_fact or claim.atomic_statement}
                    </span>
                    <div style="display:flex; gap:8px;">
                        <span style="font-size:0.78rem; font-weight:700; color:{b_fg}; background:{b_bg}; border:1px solid {b_border}; padding:3px 8px; border-radius:6px;">
                            ● {conc}
                        </span>
                        <span style="font-size:0.78rem; font-weight:600; color:#2563EB; background:#EFF6FF; border:1px solid #BFDBFE; padding:3px 8px; border-radius:6px;">
                            置信度: {conf_level} ({conf_score:.1f}分)
                        </span>
                    </div>
                </div>
                <div style="font-size:0.84rem; color:#475569; line-height:1.5;">
                    💡 <strong>核心理由速览</strong>：{brief_reason}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 详细参数区
        c_meta, c_side = st.columns([7, 3])
        with c_meta:
            kw_tags = " ".join([f"<code style='background:#F1F5F9; color:#0F172A; padding:2px 6px; border-radius:4px;'>{k}</code>" for k in getattr(claim, 'search_keywords', [])])
            st.markdown(
                f"""
                <div style="font-size:0.88rem; line-height:1.7; color:#334155;">
                    <div>• <strong>宣传原文摘录</strong>：<span style="color:#2563EB; font-weight:500;">“{claim.original_text}”</span></div>
                    <div>• <strong>单一可验证事实</strong>：<strong style="color:#0F172A;">{claim.single_verifiable_fact or claim.atomic_statement}</strong></div>
                    <div>• <strong>核验指标目标</strong>：<code style="background:#F1F5F9; color:#0F172A; padding:2px 6px; border-radius:4px; border:1px solid #E2E8F0;">{claim.verification_target}</code></div>
                    <div>• <strong>检索关键词线索</strong>：{kw_tags or '同型号核心技术参数'}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c_side:
            if needs_review:
                st.markdown(
                    f"""
                    <div style="background:#FEF2F2; border:1px solid #FECACA; border-radius:6px; padding:8px 10px; font-size:0.78rem; color:#991B1B;">
                        ⚠️ <strong>触发人工复核</strong>：<br/>{getattr(item, 'review_reason', '存在版本或测试条件争议')}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """
                    <div style="background:#F0FDF4; border:1px solid #BBF7D0; border-radius:6px; padding:8px 10px; font-size:0.78rem; color:#166534;">
                        ✅ <strong>证据链自洽</strong>：<br/>逻辑清晰，无需人工二次介入
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # 详细分析理由 (回答6大核心问题)
        st.markdown(
            f"""
            <div style="margin-top:10px; margin-bottom:12px; background:#FFFFFF; border:1px solid #E2E8F0; border-radius:8px; padding:12px 14px;">
                <div style="font-size:0.86rem; font-weight:700; color:#0F172A; margin-bottom:6px;">📑 详细分析理由 (多源事实研判)：</div>
                <div style="font-size:0.85rem; color:#334155; line-height:1.65; white-space:pre-wrap;">{item.analysis_reason}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 证据溯源明细 (支撑、冲突、部分支持、排除)
        supp_ids = getattr(item, "supporting_evidence_ids", [])
        conf_ids = getattr(item, "contradicting_evidence_ids", [])
        part_ids = getattr(item, "partial_evidence_ids", [])
        excl_evs = getattr(item, "excluded_evidences", [])

        st.markdown(
            f"""
            <div style="font-size:0.84rem; color:#475569; display:flex; flex-wrap:wrap; gap:12px; margin-bottom:10px; padding:6px 10px; background:#F8FAFC; border-radius:6px;">
                <span>🟢 支撑证据: <strong style="color:#10B981;">{len(supp_ids)} 项</strong> ({", ".join(supp_ids) or "无"})</span>
                <span>🔴 冲突证据: <strong style="color:#EF4444;">{len(conf_ids)} 项</strong> ({", ".join(conf_ids) or "无"})</span>
                <span>🟡 部分支持: <strong style="color:#F59E0B;">{len(part_ids)} 项</strong> ({", ".join(part_ids) or "无"})</span>
                <span>⚪ 排除证据: <strong style="color:#6B7280;">{len(excl_evs)} 项</strong></span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 真实支撑与冲突证据卡片
        if not item.evidences:
            st.caption("⚠️ 检索库与公开网页中未发现直接同型号凭证，依自检铁律判定为‘证据不足’（绝不推定造假）。")
        else:
            for e_idx, e in enumerate(item.evidences, 1):
                e_title = e.title or e.source_title or "公开参考资料"
                e_url = e.url or e.source_url or ""
                e_level = e.source_level.value if hasattr(e.source_level, 'value') else str(e.source_level)
                e_match = getattr(e, "model_match", "exact")
                e_excerpt = e.excerpt or e.snippet or ""
                e_dir = e.evidence_direction or "support"
                e_indep = getattr(e, "is_independent_source", True)

                dir_badge = {
                    "support": ("🟢 倾向支持", "#10B981", "#ECFDF5", "#A7F3D0"),
                    "contradict": ("🔴 倾向冲突", "#EF4444", "#FEF2F2", "#FECACA"),
                    "partial": ("🟡 部分支持", "#F59E0B", "#FFFBEB", "#FDE68A"),
                }.get(e_dir, ("⚪ 体验参考", "#6B7280", "#F9FAFB", "#E5E7EB"))

                match_text = {
                    "exact": "✅ 同型号对齐 (exact)",
                    "probable": "⚠️ 高度疑似 (probable)",
                    "series_only": "⚠️ 仅同系列 (series_only)",
                    "mismatch": "❌ 型号不符 (mismatch)",
                }.get(e_match, f"型号: {e_match}")

                indep_tag = " · 独立证据源" if e_indep else " · 转载/重复源"
                link_txt = f" <a href='{e_url}' target='_blank' style='color:#2563EB; font-weight:600; text-decoration:none;'>[🔗 真实公开来源]</a>" if e_url else ""

                st.markdown(
                    f"""
                    <div class="evidence-item-card" style="margin-bottom:8px;">
                        <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                            <span style="font-weight:650; color:#0F172A; font-size:0.86rem;">
                                {e_idx}. [{e_level}] {e_title}{link_txt}
                            </span>
                            <span style="font-size:0.75rem; color:{dir_badge[1]}; background:{dir_badge[2]}; border:1px solid {dir_badge[3]}; padding:2px 6px; border-radius:4px; font-weight:600;">
                                {dir_badge[0]} ｜ {match_text}{indep_tag}
                            </span>
                        </div>
                        <div class="evidence-quote-box" style="font-size:0.82rem; line-height:1.6; color:#334155;">
                            “{e_excerpt}”
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # 排除证据折叠查看
        if excl_evs:
            with st.expander(f"查看被排除的证据线索 (共 {len(excl_evs)} 项)", expanded=False):
                for ex_item in excl_evs:
                    st.markdown(
                        f"""
                        <div style="font-size:0.8rem; color:#64748B; padding:4px 0; border-bottom:1px dashed #E2E8F0;">
                            • <strong>{ex_item.get('title', '未知线索')}</strong>：<span style="color:#B91C1C;">{ex_item.get('exclusion_reason', '未通过有效性门限')}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        # 自检状态与局限性建议
        st.markdown(
            f"""
            <div style="display:flex; justify-content:space-between; font-size:0.8rem; color:#64748B; margin-top:8px; border-top:1px solid #F1F5F9; padding-top:6px;">
                <span>🛡️ 事实自检：<strong style="color:#15803D;">{getattr(item, 'self_check_status', 'passed')}</strong> ({item.self_check_notes or '通过铁律自检'})</span>
                <span>💡 建议：{getattr(item, 'user_advice', '购买前核对同型号出厂铭牌')}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_advice_and_disclaimer(report: VerificationReport):
    """结果看板第 5 层：人工确认清单与购买建议 (双列白卡)"""
    c_check, c_adv = st.columns(2)
    with c_check:
        st.markdown(
            """
            <div class="saas-card" style="height:100%;">
                <div class="saas-card-title" style="margin-bottom:8px;">📋 人工确认清单 (Human Checklist)</div>
            """,
            unsafe_allow_html=True,
        )
        items = report.human_verification_items or []
        if items:
            for item in items:
                st.warning(f"⚠️ {item}")
        else:
            st.caption("暂无需要特别人工确认的异常事项。")
        st.markdown("</div>", unsafe_allow_html=True)

    with c_adv:
        st.markdown(
            """
            <div class="saas-card" style="height:100%;">
                <div class="saas-card-title" style="margin-bottom:8px;">🛒 购买前防坑建议 (Pre-Purchase Advice)</div>
            """,
            unsafe_allow_html=True,
        )
        advices = report.pre_purchase_advice or []
        if advices:
            for adv in advices:
                st.success(f"💡 {adv}")
        else:
            st.caption("建议优先选择品牌官方授权专卖店，索取正规发票以保障售后权益。")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div style="margin-top:1.25rem; font-size:0.78rem; color:#64748B; text-align:center; line-height:1.6;">
            ⚖️ <strong>客观中立与非鉴定声明</strong>：{report.disclaimer}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_report_actions(report: VerificationReport, md_content: str, txt_content: str, on_reset):
    """板块 6: 报告导出操作 (Markdown/TXT下载、一键复制、重新开始)"""
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    with c1:
        st.download_button(
            label="📥 下载 Markdown 报告 (.md)",
            data=md_content,
            file_name=f"{report.report_id}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with c2:
        st.download_button(
            label="📄 下载纯文本报告 (.txt)",
            data=txt_content,
            file_name=f"{report.report_id}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with c3:
        if st.button("📋 一键复制核心摘要", use_container_width=True):
            st.toast("✅ 已生成核心摘要，可直接复制上方总体结论与逐项卡片！", icon="📋")
    with c4:
        if st.button("🔄 开始新的一项核验", use_container_width=True):
            on_reset()

    st.markdown(
        """
        <div style="margin-top:14px; font-size:0.78rem; color:#64748B; text-align:center; line-height:1.6;">
            🔒 <strong>隐私安全合规承诺</strong>：报告内容已严格执行隐私过滤，全篇不包含任何 API Key (<code>sk-****</code> / <code>tvly-****</code>)、Cookie、Session 凭证或 Authorization 请求头。
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_claim_confirmation_card(
    identity: ProductIdentityResult,
    claims: List[ClaimItem],
    rejected_candidates: List[FilteredCandidate],
    on_confirm,
    on_delete_claim,
    on_add_claim,
    on_edit_claim=None,
):
    """阶段 1：宣传声明提取确认卡片 (展示识别商品信息、有效声明列表、未采用内容及增删改)"""
    st.markdown(
        """
        <div class="saas-card" style="margin-top:1.25rem; margin-bottom:1.25rem; border:1px solid #CBD5E1; box-shadow:0 4px 12px rgba(15, 23, 42, 0.05);">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #F1F5F9; padding-bottom:10px; margin-bottom:14px;">
                <div style="font-size:1.15rem; font-weight:700; color:#0F172A; display:flex; align-items:center; gap:8px;">
                    <span>📋</span> <span>第一阶段：宣传声明提取确认</span>
                </div>
                <div style="font-size:0.82rem; color:#475569; background:#F8FAFC; border:1px solid #E2E8F0; padding:4px 10px; border-radius:6px;">
                    已提取有效声明 <strong>{} 条</strong> / 过滤噪点 <strong>{} 项</strong>
                </div>
            </div>
        """.format(len(claims), len(rejected_candidates)),
        unsafe_allow_html=True,
    )

    # 1. 识别到的商品信息
    p_id_str = identity.product_id if identity.product_id else "未提取到（可选）"
    st.markdown(
        f"""
        <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:12px 16px; margin-bottom:16px;">
            <div style="font-size:0.85rem; font-weight:700; color:#334155; margin-bottom:6px;">🏷️ 识别到的商品基础信息 (已与声明相互隔离)：</div>
            <div style="display:flex; flex-wrap:wrap; gap:16px; font-size:0.9rem; color:#0F172A;">
                <span><strong>品牌：</strong><span style="color:#2563EB;">{identity.brand or '未知品牌'}</span></span>
                <span><strong>型号：</strong><span style="color:#0F172A;">{identity.model or '标准型号'}</span></span>
                <span><strong>商品编号：</strong><code style="color:#0F172A; background:#E2E8F0; padding:2px 6px; border-radius:4px;">{p_id_str}</code></span>
                <span><strong>版本/规格：</strong><span style="color:#475569;">{identity.variant or '标准版'}</span></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2. 提取到的有效声明列表
    if not claims:
        st.warning(
            "⚠️ **暂未从当前资料中提取到可验证的宣传声明。**\n\n"
            "请上传或粘贴包含具体参数、功能或卖点的资料，例如续航时间、降噪等级、防水等级、功率、材料或兼容性说明。\n\n"
            "您也可以在下方手动补充一条具体声明继续核验。"
        )
    else:
        st.markdown(
            """
            <div style="font-size:0.9rem; font-weight:700; color:#1E293B; margin-bottom:8px;">
                🎯 提取到的可验证宣传声明 (门禁标准：质量评分 ≥ 0.65 且属于客观事实)：
            </div>
            """,
            unsafe_allow_html=True,
        )

        cat_colors = {
            "参数": ("#1D4ED8", "#EFF6FF", "#BFDBFE"),
            "功能": ("#047857", "#ECFDF5", "#A7F3D0"),
            "性能": ("#B45309", "#FFFBEB", "#FDE68A"),
            "材料": ("#6D28D9", "#F5F3FF", "#DDD6FE"),
            "兼容性": ("#0369A1", "#F0F9FF", "#BAE6FD"),
            "使用条件": ("#C2410C", "#FFF7ED", "#FFEDD5"),
            "明确体验承诺": ("#4338CA", "#EEF2FF", "#C7D2FE"),
        }

        for idx, claim in enumerate(claims):
            c_text_col, c_bg_col, c_bd_col = cat_colors.get(
                claim.category, ("#1D4ED8", "#EFF6FF", "#BFDBFE")
            )
            col_info, col_del = st.columns([8.5, 1.5])
            with col_info:
                st.markdown(
                    f"""
                    <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:8px; padding:10px 14px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <span style="font-size:0.85rem; font-weight:700; color:#64748B;">#{claim.claim_id}</span>
                            <span style="font-size:0.95rem; font-weight:600; color:#0F172A;">{claim.atomic_statement}</span>
                        </div>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span style="font-size:0.75rem; color:{c_text_col}; background:{c_bg_col}; border:1px solid {c_bd_col}; padding:3px 8px; border-radius:6px; font-weight:600;">
                                {claim.category}
                            </span>
                            <span style="font-size:0.75rem; color:#15803D; background:#F0FDF4; border:1px solid #BBF7D0; padding:3px 8px; border-radius:6px; font-weight:600;">
                                ⭐ 质量得分 {claim.claim_quality_score:.2f}
                            </span>
                            <span style="font-size:0.75rem; color:#475569; background:#F8FAFC; border:1px solid #E2E8F0; padding:3px 8px; border-radius:6px;">
                                ✅ 可独立核验
                            </span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col_del:
                if st.button("🗑️ 删除", key=f"btn_del_claim_{idx}", use_container_width=True):
                    on_delete_claim(idx)

    # 3. 手动补充声明
    with st.expander("➕ 手动补充一条可验证声明", expanded=False):
        c_add_txt, c_add_cat, c_add_btn = st.columns([5, 3, 2])
        with c_add_txt:
            new_text = st.text_input("声明陈述：", placeholder="例如：单耳重量仅4.2g", key="input_manual_claim_text")
        with c_add_cat:
            new_cat = st.selectbox("类别：", options=ALLOWED_CLAIM_CATEGORIES, key="select_manual_claim_cat")
        with c_add_btn:
            st.write("")
            st.write("")
            if st.button("添加声明", key="btn_add_manual_claim", type="secondary", use_container_width=True):
                if new_text and new_text.strip():
                    on_add_claim(new_text.strip(), new_cat)
                else:
                    st.toast("请输入声明内容", icon="⚠️")

    # 4. 折叠区域：查看未采用内容
    if rejected_candidates:
        with st.expander(f"📁 查看未采用内容 ({len(rejected_candidates)} 项已被安全过滤)", expanded=False):
            st.caption("以下内容属于截图占位符、品牌/型号标识、空字段标题或未达评分门槛的文本，已自动过滤：")
            rej_data = []
            for r in rejected_candidates:
                rej_data.append({
                    "候选内容原文": r.original_text,
                    "未采用具体原因": r.rejection_reason,
                    "质量得分": f"{r.score:.2f}",
                    "推断类型": r.category or "未知",
                })
            st.dataframe(rej_data, use_container_width=True, hide_index=True)

    # 5. 底部确认按钮
    st.write("")
    if st.button(
        "✅ 确认以上声明，开始证据核验",
        type="primary",
        use_container_width=True,
        disabled=(len(claims) == 0),
        key="btn_confirm_claims_to_verify",
    ):
        on_confirm()

    st.markdown("</div>", unsafe_allow_html=True)


def render_search_execution_panel(
    identity: ProductIdentityResult,
    claims: List[ClaimItem],
    search_mode: str,
    search_provider_name: str,
    search_api_key: str,
    search_max_results: int,
    search_executed: bool,
    phase3_queries: List[Any],
    phase3_evidence: dict,
    on_confirm_search,
    on_reset_search,
    on_back_to_claims,
    on_proceed_to_phase4=None,
):
    """第三阶段：网络搜索与正文提取执行面板 (包含前置确认卡片与结果审计看板)"""
    st.markdown(
        """
        <div class="saas-card" style="margin-top:1.25rem; margin-bottom:1.25rem; border:1px solid #CBD5E1; box-shadow:0 4px 12px rgba(15, 23, 42, 0.05);">
        """,
        unsafe_allow_html=True,
    )

    if not search_executed:
        # -------------------------------------------------------------
        # 状态 1：前置搜索确认卡片 (未执行搜索时必须显式获得用户确认)
        # -------------------------------------------------------------
        search_timeout = st.session_state.get("search_timeout", 15)
        prefer_official = st.session_state.get("prefer_official_sources", True)
        include_reviews = st.session_state.get("include_user_reviews", False)
        manual_items = st.session_state.get("manual_evidence_items", [])
        conn_status = st.session_state.get("search_connection_status", "not_tested")

        # 头部模式徽标与状态展示
        status_text = "🟢 已连接" if conn_status == "connected" else ("🔴 连接失败" if conn_status == "failed" else "🟡 待测试")
        if search_mode == "tavily":
            mode_badge = f'<span style="color:#1D4ED8; background:#EFF6FF; border:1px solid #BFDBFE; padding:4px 10px; border-radius:6px; font-weight:600;">🔍 搜索模式：<strong>TAVILY</strong> ｜ 状态: <strong>{status_text}</strong> ｜ 用户自带Key</span>'
        elif search_mode == "kimi":
            mode_badge = f'<span style="color:#0284C7; background:#F0F9FF; border:1px solid #BAE6FD; padding:4px 10px; border-radius:6px; font-weight:600;">🌙 搜索模式：<strong>KIMI</strong> ｜ 状态: <strong>{status_text}</strong> ｜ Moonshot独立工具</span>'
        elif search_mode == "qwen":
            mode_badge = f'<span style="color:#7C3AED; background:#F5F3FF; border:1px solid #DDD6FE; padding:4px 10px; border-radius:6px; font-weight:600;">⚡ 搜索模式：<strong>QWEN</strong> ｜ 状态: <strong>{status_text}</strong> ｜ 阿里百炼官方搜索</span>'
        elif search_mode == "manual":
            mode_badge = f'<span style="color:#15803D; background:#F0FDF4; border:1px solid #BBF7D0; padding:4px 10px; border-radius:6px; font-weight:600;">📎 搜索模式：<strong>MANUAL</strong> ｜ 已录入 <strong>{len(manual_items)} 条</strong>手动证据</span>'
        else:
            mode_badge = '<span style="color:#64748B; background:#F8FAFC; border:1px solid #E2E8F0; padding:4px 10px; border-radius:6px; font-weight:600;">⚪ 搜索模式：<strong>NONE</strong> ｜ 未配置独立搜索服务</span>'

        st.markdown(
            f"""
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #F1F5F9; padding-bottom:10px; margin-bottom:14px;">
                <div style="font-size:1.15rem; font-weight:700; color:#0F172A; display:flex; align-items:center; gap:8px;">
                    <span>🌐</span> <span>第三阶段：网络搜索与候选正文提取前置确认</span>
                </div>
                <div>
                    {mode_badge}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if "商品宣传截图" in st.session_state.get("input_mode", "") or st.session_state.get("ocr_text"):
            st.markdown(
                """
                <div style="background:#F0F9FF; border:1px solid #BAE6FD; border-left:4px solid #0284C7; border-radius:8px; padding:10px 14px; margin-bottom:12px; font-size:0.84rem; color:#0369A1; line-height:1.6;">
                    🔍 <strong>检索机制说明</strong>：<strong>基于图片文字与商品特征的联网检索</strong><br/>
                    本系统绝不把文本搜索描述为传统反向图片搜索。当前依托纯本地离线 OCR 提取的真实文字与型号特征，在独立网络搜索引擎中执行定向交叉核验。
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 费用承担方声明 (绝不提供共享付费Key)
        if search_mode == "tavily":
            masked_k = f"{search_api_key[:4]}****{search_api_key[-4:]}" if len(search_api_key) >= 8 else "未填写"
            cost_html = f"""
            <div style="background:#FFFBEB; border:1px solid #FDE68A; border-left:4px solid #D97706; border-radius:8px; padding:12px 16px; margin-bottom:16px;">
                <div style="font-size:0.88rem; font-weight:700; color:#92400E; margin-bottom:4px;">
                    ⚠️ 检索费用承担方明确声明 (用户自带 API 模式)
                </div>
                <div style="font-size:0.84rem; color:#78350F; line-height:1.6;">
                    • <strong>当前配置：</strong>Tavily Search API (密钥: <code>{masked_k}</code>)。<br/>
                    • <strong>费用责任：</strong>网络检索将直接调用您个人配置的 Tavily 账户，<strong>产生的所有 API 费用由您的个人账户完全承担</strong>。<br/>
                    • <strong>安全保障：</strong>系统绝不提供或承担共享付费 Key，且绝不会在后台自动无限制静默消耗额度。
                </div>
            </div>
            """
        elif search_mode == "kimi":
            kimi_k = st.session_state.get("kimi_search_api_key", "")
            masked_km = f"{kimi_k[:4]}****{kimi_k[-4:]}" if len(kimi_k) >= 8 else "未填写"
            cost_html = f"""
            <div style="background:#F0F9FF; border:1px solid #BAE6FD; border-left:4px solid #0284C7; border-radius:8px; padding:12px 16px; margin-bottom:16px;">
                <div style="font-size:0.88rem; font-weight:700; color:#0369A1; margin-bottom:4px;">
                    🌙 Moonshot AI (Kimi) 独立搜索工具费用声明
                </div>
                <div style="font-size:0.84rem; color:#075985; line-height:1.6;">
                    • <strong>当前配置：</strong>Kimi 独立工具接口 (密钥: <code>{masked_km}</code> ｜ 模式: <code>{st.session_state.get('kimi_search_mode', 'basic')}</code>)。<br/>
                    • <strong>费用责任：</strong>将直接调用 Moonshot 官方 <code>/v1/tools/search</code> 与 <code>/v1/tools/fetch</code> 接口，费用完全由您的 Moonshot 账户承担。<br/>
                    • <strong>架构解耦：</strong>模型对话连接不代表独立搜索开通，系统以真实检索探活作为凭据。
                </div>
            </div>
            """
        elif search_mode == "qwen":
            qwen_k = st.session_state.get("qwen_search_api_key", "")
            masked_qw = f"{qwen_k[:4]}****{qwen_k[-4:]}" if len(qwen_k) >= 8 else "未填写"
            cost_html = f"""
            <div style="background:#F5F3FF; border:1px solid #DDD6FE; border-left:4px solid #7C3AED; border-radius:8px; padding:12px 16px; margin-bottom:16px;">
                <div style="font-size:0.88rem; font-weight:700; color:#6D28D9; margin-bottom:4px;">
                    ⚡ 阿里百炼 DashScope (通义千问) 搜索费用声明
                </div>
                <div style="font-size:0.84rem; color:#5B21B6; line-height:1.6;">
                    • <strong>当前配置：</strong>通义千问搜索 (密钥: <code>{masked_qw}</code> ｜ 模式: <code>{st.session_state.get('qwen_search_api_mode', 'responses')}</code> ｜ 模型: <code>{st.session_state.get('qwen_search_model', 'qwen-plus')}</code>)。<br/>
                    • <strong>费用责任：</strong>调用将直接从您的阿里云百炼账户扣除 Token 与工具调用费用，0 开发者代付。<br/>
                    • <strong>来源溯源铁律：</strong>若未返回真实来源 URL，系统将标明不可追溯并禁止评定为 A 级官方证据。
                </div>
            </div>
            """
        elif search_mode == "manual":
            cost_html = f"""
            <div style="background:#F0FDF4; border:1px solid #BBF7D0; border-left:4px solid #16A34A; border-radius:8px; padding:12px 16px; margin-bottom:16px;">
                <div style="font-size:0.88rem; font-weight:700; color:#166534; margin-bottom:4px;">
                    📝 手动补充证据模式 (零检索费用)
                </div>
                <div style="font-size:0.84rem; color:#14532D; line-height:1.6;">
                    • 当前无需外部搜索 API，零网络检索账单费用。<br/>
                    • 系统将仅从您手动录入的 <strong>{len(manual_items)} 条</strong>权威公开资料（品牌官网、官方说明书、官方规格页、专业评测）中提取真实正文，并执行来源分级与型号比对。
                </div>
            </div>
            """
        else:
            cost_html = """
            <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-left:4px solid #64748B; border-radius:8px; padding:12px 16px; margin-bottom:16px;">
                <div style="font-size:0.88rem; font-weight:700; color:#334155; margin-bottom:4px;">
                    🚫 未配置独立搜索服务 (NoSearchProvider)
                </div>
                <div style="font-size:0.84rem; color:#475569; line-height:1.6;">
                    • 当前未连接任何搜索服务，<strong>不会向公网发起检索，亦不会产生任何费用</strong>。<br/>
                    • 执行后将生成分层检索词规划，但不会抓取到候选公开网页正文，所有声明将客观判定为“证据不足”。<br/>
                    • 如需真实网络证据，请在上方【设置抽屉】中配置 Tavily、Kimi、通义千问 API Key 或录入手动证据链接。
                </div>
            </div>
            """
        st.markdown(cost_html, unsafe_allow_html=True)

        # 预先生成分层检索词预览 (纯内存规划，0 外部请求)
        target_prod = {
            "brand": identity.brand or "",
            "model": identity.model or "",
            "product_name": getattr(identity, "name", "") or "",
            "variant": identity.variant or "",
            "region": identity.region or "",
        }
        generator = LayeredQueryGenerator()
        planned_queries_by_claim = {}
        total_planned_queries = 0
        for c in claims:
            q_list = generator.generate_queries_for_claim(
                identity=target_prod,
                claim=c,
                include_user_reviews=include_reviews,
                max_queries=5,
            )
            planned_queries_by_claim[c.claim_id] = q_list
            total_planned_queries += len(q_list)

        # 计算调用上限
        if search_mode in ["tavily", "kimi", "qwen"]:
            estimated_requests = f"≤ {min(total_planned_queries, len(claims) * 2)} 次 API 请求"
        elif search_mode == "manual":
            estimated_requests = f"{len(manual_items)} 次网页抓取 (0 次搜索 API)"
        else:
            estimated_requests = "0 次 (未配置搜索服务)"

        # 参数与调用预算展示 (4维清晰预算)
        c_m1, c_m2, c_m3, c_m4 = st.columns(4)
        c_m1.metric("单次待核声明数", f"{len(claims)} 项声明")
        c_m2.metric("搜索调用上限", estimated_requests)
        c_m3.metric("候选网页提取上限", f"≤ {len(claims) * 3} 页")
        c_m4.metric("模型调用估算", "1 次深度分析")

        # 即将执行的检索词列表 (供用户在执行前审计)
        with st.expander(f"📋 即将执行的检索词规划列表 (共 {total_planned_queries} 条检索词 · 点击展开/收起)", expanded=True):
            for c in claims:
                st.markdown(f"**声明 #{c.claim_id}**（类别: `{c.category}`）：**{c.atomic_statement}**")
                c_queries = planned_queries_by_claim.get(c.claim_id, [])
                for q in c_queries:
                    type_icon = "🏛️ Layer 1 官方资料" if q.query_type == "official" else ("🔬 Layer 2 专业实测" if q.query_type == "review" else "💬 Layer 3 用户反馈")
                    st.markdown(f"- `{type_icon} (P{q.priority})`: **`{q.query_text}`**")
                st.markdown("")

        # 若未配置搜索服务，提供快速切换入口
        if search_mode == "none":
            st.info("💡 **快捷切换搜索模式**：如需配置真实网络证据，可在此快速切换：")
            col_q1, col_q2, col_q3, col_q4 = st.columns(4)
            with col_q1:
                if st.button("🔍 Tavily 搜索", key="btn_quick_switch_tavily", use_container_width=True):
                    st.session_state.search_mode = "tavily"
                    st.session_state.search_provider_name = "Tavily"
                    st.session_state.search_connection_status = "not_tested"
                    st.rerun()
            with col_q2:
                if st.button("🌙 Kimi 搜索", key="btn_quick_switch_kimi", use_container_width=True):
                    st.session_state.search_mode = "kimi"
                    st.session_state.search_provider_name = "Kimi"
                    st.session_state.search_connection_status = "not_tested"
                    st.rerun()
            with col_q3:
                if st.button("⚡ 通义千问", key="btn_quick_switch_qwen", use_container_width=True):
                    st.session_state.search_mode = "qwen"
                    st.session_state.search_provider_name = "Qwen"
                    st.session_state.search_connection_status = "not_tested"
                    st.rerun()
            with col_q4:
                if st.button("📎 手动证据模式", key="btn_quick_switch_manual", use_container_width=True):
                    st.session_state.search_mode = "manual"
                    st.session_state.search_provider_name = "Manual"
                    st.session_state.search_connection_status = "connected" if len(manual_items) > 0 else "not_configured"
                    st.rerun()

        # 执行与返回按钮
        c_exec_btn, c_back_btn = st.columns([7, 3])
        with c_exec_btn:
            if search_mode in ["tavily", "kimi", "qwen"]:
                btn_label = f"🚀 确认并开始网络搜索 (费用由用户自有 {search_mode.upper()} 账户承担)"
            elif search_mode == "manual":
                btn_label = f"🚀 确认并开始抓取手动证据链接 (共 {len(manual_items)} 条 · 0 API 费用)"
            else:
                btn_label = "🚀 执行离线检索规划 (不发起网络请求 · 0 费用)"

            if st.button(
                btn_label,
                type="primary",
                use_container_width=True,
                key="btn_trigger_phase3_search",
            ):
                on_confirm_search()
        with c_back_btn:
            if st.button(
                "↩️ 返回修改宣传声明",
                type="secondary",
                use_container_width=True,
                key="btn_back_to_claims_edit",
            ):
                on_back_to_claims()

    else:
        # -------------------------------------------------------------
        # 状态 2：第三阶段结果审计看板 (展示真实查询、网页、正文与来源分级)
        # -------------------------------------------------------------
        total_q = len(phase3_queries)
        exec_q = len([q for q in phase3_queries if getattr(q, 'execution_status', '') == 'executed'])
        total_ev = sum(len(ev_list) for ev_list in phase3_evidence.values())

        st.markdown(
            f"""
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #F1F5F9; padding-bottom:10px; margin-bottom:14px;">
                <div style="font-size:1.15rem; font-weight:700; color:#0F172A; display:flex; align-items:center; gap:8px;">
                    <span>🔎</span> <span>第三阶段：网络搜索与正文提取执行成果看板</span>
                </div>
                <div style="font-size:0.82rem; color:#15803D; background:#F0FDF4; border:1px solid #BBF7D0; padding:4px 10px; border-radius:6px; font-weight:600;">
                    ✅ 检索词审计完成 ｜ 提取证据 {total_ev} 项
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 统计看板
        st.markdown(
            f"""
            <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; margin-bottom:16px;">
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:10px; text-align:center;">
                    <div style="font-size:0.75rem; color:#64748B;">生成分层检索词</div>
                    <div style="font-size:1.25rem; font-weight:700; color:#0F172A;">{total_q} 个</div>
                </div>
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:10px; text-align:center;">
                    <div style="font-size:0.75rem; color:#64748B;">执行搜索次数</div>
                    <div style="font-size:1.25rem; font-weight:700; color:#2563EB;">{exec_q} 次</div>
                </div>
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:10px; text-align:center;">
                    <div style="font-size:0.75rem; color:#64748B;">提取网页证据项</div>
                    <div style="font-size:1.25rem; font-weight:700; color:#15803D;">{total_ev} 项</div>
                </div>
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:10px; text-align:center;">
                    <div style="font-size:0.75rem; color:#64748B;">搜索服务模式</div>
                    <div style="font-size:1.0rem; font-weight:700; color:#475569; padding-top:4px;">{search_mode.upper()}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 1. 分层检索词执行审计表
        with st.expander("🔍 查看分层检索词规划与执行审计明细", expanded=True):
            if phase3_queries:
                q_rows = []
                for q in phase3_queries:
                    type_zh = {
                        "official": "Layer 1 (官方规格)",
                        "review": "Layer 2 (专业评测)",
                        "experience": "Layer 3 (用户反馈)",
                    }.get(getattr(q, 'query_type', ''), getattr(q, 'query_type', ''))
                    q_rows.append({
                        "查询 ID": getattr(q, 'query_id', ''),
                        "声明序号": f"#{getattr(q, 'claim_id', '')}",
                        "分层类型": type_zh,
                        "优先级": f"P{getattr(q, 'priority', 1)}",
                        "完整检索词文本": getattr(q, 'query_text', ''),
                        "执行状态": getattr(q, 'execution_status', ''),
                    })
                st.dataframe(q_rows, use_container_width=True, hide_index=True)
            else:
                st.caption("暂无生成的检索词记录。")

        # 2. 真实网页正文与候选证据明细
        st.markdown(
            """
            <div style="font-size:0.92rem; font-weight:700; color:#1E293B; margin-top:16px; margin-bottom:10px;">
                📑 提取到的真实网页正文与结构化证据 (逐声明展示)：
            </div>
            """,
            unsafe_allow_html=True,
        )

        for claim in claims:
            cid = claim.claim_id
            ev_list = phase3_evidence.get(cid, [])

            st.markdown(
                f"""
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:10px 14px; margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:0.88rem; font-weight:700; color:#0F172A;">
                            #{cid} 【{claim.category}】{claim.atomic_statement}
                        </span>
                        <span style="font-size:0.75rem; color:#475569; background:#FFFFFF; border:1px solid #E2E8F0; padding:2px 8px; border-radius:4px;">
                            匹配到 {len(ev_list)} 项证据
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if not ev_list:
                st.markdown(
                    """
                    <div style="font-size:0.82rem; color:#64748B; padding:8px 16px; margin-bottom:12px;">
                        ⚠️ 未从已配置的检索源中获取到同型号相关网页证据（严格遵循客观中立与反造假原则，绝不伪造检索内容）。
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                for idx, ev in enumerate(ev_list, 1):
                    ev_title = ev.title or "公开网页资料"
                    ev_url = ev.url or ""
                    ev_lvl = ev.source_level.value if hasattr(ev.source_level, 'value') else str(ev.source_level)
                    ev_type = ev.source_type or "公开资料"
                    ev_match = ev.model_match or "unknown"
                    ev_excerpt = ev.excerpt or ""

                    lvl_badge_color = {
                        "A级": ("#15803D", "#F0FDF4", "#BBF7D0"),
                        "B级": ("#1D4ED8", "#EFF6FF", "#BFDBFE"),
                        "C级": ("#B45309", "#FFFBEB", "#FDE68A"),
                        "D级": ("#64748B", "#F8FAFC", "#E2E8F0"),
                    }.get(ev_lvl, ("#64748B", "#F8FAFC", "#E2E8F0"))

                    match_badge_color = {
                        "exact": ("#15803D", "#F0FDF4", "#BBF7D0", "✅ 同型号对齐"),
                        "compatible": ("#B45309", "#FFFBEB", "#FDE68A", "⚠️ 衍生兼容型号"),
                        "mismatch": ("#B91C1C", "#FEF2F2", "#FECACA", "❌ 型号不匹配"),
                        "unknown": ("#475569", "#F8FAFC", "#E2E8F0", "❓ 未知型号"),
                    }.get(ev_match, ("#475569", "#F8FAFC", "#E2E8F0", f"型号: {ev_match}"))

                    link_tag = f"<a href='{ev_url}' target='_blank' style='color:#2563EB; font-weight:500; text-decoration:none;'>[🔗 真实网页来源]</a>" if ev_url else ""

                    st.markdown(
                        f"""
                        <div class="evidence-item-card" style="margin-bottom:10px;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                                <span style="font-weight:650; color:#0F172A; font-size:0.86rem;">
                                    {idx}. {ev_title} {link_tag}
                                </span>
                                <div style="display:flex; gap:6px;">
                                    <span style="font-size:0.75rem; color:{lvl_badge_color[0]}; background:{lvl_badge_color[1]}; border:1px solid {lvl_badge_color[2]}; padding:2px 6px; border-radius:4px; font-weight:600;">
                                        {ev_lvl}
                                    </span>
                                    <span style="font-size:0.75rem; color:{match_badge_color[0]}; background:{match_badge_color[1]}; border:1px solid {match_badge_color[2]}; padding:2px 6px; border-radius:4px; font-weight:600;">
                                        {match_badge_color[3]}
                                    </span>
                                </div>
                            </div>
                            <div style="font-size:0.78rem; color:#64748B; margin-bottom:6px;">
                                来源类别: {ev_type} ｜ 提取字符数: {len(ev_excerpt)} 字
                            </div>
                            <div class="evidence-quote-box" style="font-size:0.82rem; color:#334155; line-height:1.6;">
                                {ev_excerpt}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        # 3. 第四阶段操作引导 (交叉核验与报告生成)
        st.markdown(
            """
            <div style="background:#F0FDF4; border:1px solid #BBF7D0; border-left:4px solid #16A34A; border-radius:8px; padding:14px 16px; margin-top:20px; margin-bottom:16px;">
                <div style="font-weight:700; color:#166534; font-size:0.95rem; display:flex; align-items:center; gap:8px;">
                    <span>🎯</span> <span>第四阶段就绪：已提取真实网页证据，可执行多源交叉核验</span>
                </div>
                <div style="font-size:0.84rem; color:#14532D; margin-top:6px; line-height:1.6;">
                    • <strong>同型号严格对齐：</strong>对上述提取证据执行 exact / probable / series_only / mismatch 五态对齐过滤；<br/>
                    • <strong>证据有效性与去重：</strong>排除 D 级软文、计算内容指纹与相似度聚类去重，确保独立证据统计真实；<br/>
                    • <strong>四级研判与置信度：</strong>输出“有证据支持 / 部分支持 / 存在冲突 / 证据不足”，计算 6 维度 0~100 量化置信度；<br/>
                    • <strong>二次事实自检与差异化理由：</strong>落实 15 项事实自检铁律，生成回答 6 大核心问题的具体专业分析。
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        c_p4_btn, c_re_btn, c_ret_btn = st.columns([5, 2.5, 2.5])
        with c_p4_btn:
            if st.button("🚀 开始第四阶段：执行多源交叉核验并生成报告", type="primary", use_container_width=True, key="btn_proceed_to_phase4"):
                if on_proceed_to_phase4:
                    on_proceed_to_phase4()
        with c_re_btn:
            if st.button("🔄 重新搜索提取", use_container_width=True, key="btn_reset_phase3_search"):
                on_reset_search()
        with c_ret_btn:
            if st.button("↩️ 返回修改声明", use_container_width=True, key="btn_back_claims_from_p3"):
                on_back_to_claims()

    st.markdown("</div>", unsafe_allow_html=True)


