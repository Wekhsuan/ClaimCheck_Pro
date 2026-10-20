"""ClaimCheck Pro 现代白亮专业主题与设计系统规范 (White/Light SaaS Design Tokens & CSS)
视觉关键词: Clean, Minimal, Trustworthy, Modern SaaS, Accessible (WCAG AA)
"""

import streamlit as st

# -----------------------------------------------------------------------------
# 设计 Token 体系 (White/Light Professional SaaS)
# -----------------------------------------------------------------------------
COLORS = {
    # 品牌与主操作
    "brand_primary": "#356AE6",       # 品牌蓝 (强对比，Accessible)
    "brand_hover": "#2452C7",         # 品牌蓝 Hover 态
    "brand_light_bg": "#EFF6FF",      # 品牌微浅蓝底色
    "brand_border": "#BFDBFE",        # 品牌浅蓝边框

    # 基础画板与容器
    "bg_canvas": "#F6F8FB",           # 全局页面画布底色
    "surface_card": "#FFFFFF",        # 实体卡片主背景
    "surface_muted": "#F0F4F8",       # 次级灰底 (步进器、输入栏轨道)
    "surface_subtle": "#F6F8FB",      # 嵌套卡片浅底 (证据明细卡片)

    # 文字层级规范 (WCAG AA 强对比)
    "text_primary": "#152033",        # 主标题、卡片大字、核心结论 (深暗蓝黑，对比度>14:1)
    "text_secondary": "#526176",      # 正文、副标题、标签文字 (对比度>7:1)
    "text_muted": "#667085",          # 辅助小字、时间戳、说明 (对比度>4.5:1)
    "text_light": "#8A94A6",          # 禁用态、微弱提示

    # 四级核验结论语义色彩体系 (浅色微底 + 深色文字 + 微边框)
    "supported_text": "#16865C",      # 🟢 有证据支持深绿
    "supported_bg": "#F0FDF4",        # 浅绿背景
    "supported_border": "#86EFAC",    # 浅绿边框

    "partial_text": "#9A6700",        # 🟡 部分支持琥珀棕
    "partial_bg": "#FFF8E6",          # 浅黄背景
    "partial_border": "#FDE68A",      # 浅黄边框

    "conflict_text": "#B42318",       # 🔴 存在冲突深红 (红色仅用于此处与报错)
    "conflict_bg": "#FFF1F0",         # 浅红背景
    "conflict_border": "#FCA5A5",     # 浅红边框

    "insufficient_text": "#526176",   # ⚪ 证据不足石板灰
    "insufficient_bg": "#F6F8FB",     # 浅灰背景
    "insufficient_border": "#DDE3EA", # 浅灰边框

    # 边框与分割线
    "border_subtle": "#DDE3EA",       # 常用卡片边框
    "border_strong": "#CBD5E1",       # 输入框与分割线
}


def inject_custom_theme():
    """向页面注入高质量纯白/浅色现代专业 SaaS 视觉样式表"""
    css = """
    <style>
    /* =========================================================================
       1. 全局页面画布与文字对比度加固 (消除浅色文字)
       ========================================================================= */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #F6F8FB !important;
        color: #152033 !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
    }

    /* 限制主视图宽度，居中呈现高保真卡片视口 (1060px) */
    .block-container {
        max-width: 1060px !important;
        padding-top: 1.25rem !important;
        padding-bottom: 4rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        margin: 0 auto !important;
    }

    /* 顶部装饰条与侧边栏彻底浅色化 */
    [data-testid="stHeader"] {
        background-color: transparent !important;
    }
    [data-testid="stSidebar"] {
        background-color: #FFFFFF !important;
        border-right: 1px solid #DDE3EA !important;
    }

    /* 全局标题与文字层级强化：强制高对比度深色 */
    h1, h2, h3, h4, h5, h6 {
        color: #152033 !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
    }
    p, span, label, div {
        color: #152033;
    }
    .stMarkdown p, .stMarkdown span {
        color: #152033 !important;
    }
    [data-testid="stCaptionContainer"] p, .stCaption {
        color: #526176 !important;
        font-weight: 500 !important;
    }

    /* =========================================================================
       2. 顶部导航栏 (Top Navbar) - 紧凑、专业、清爽
       ========================================================================= */
    .top-navbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: #FFFFFF;
        border: 1px solid #DDE3EA;
        border-radius: 12px;
        padding: 0.65rem 1.25rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04);
    }
    .nav-brand {
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .nav-title {
        font-size: 1.2rem;
        font-weight: 750;
        color: #152033;
        letter-spacing: -0.3px;
    }
    .nav-badge {
        font-size: 0.8rem;
        color: #526176;
        background: #F6F8FB;
        padding: 3px 10px;
        border-radius: 6px;
        border: 1px solid #DDE3EA;
        font-weight: 600;
    }

    /* =========================================================================
       3. 主操作区标语 (Hero Banner)
       ========================================================================= */
    .hero-container {
        text-align: center;
        padding: 0.75rem 0 1.5rem 0;
    }
    .hero-title {
        font-size: 2.1rem;
        font-weight: 750;
        color: #152033 !important;
        letter-spacing: -0.5px;
        margin-bottom: 0.45rem;
    }
    .hero-subtitle {
        font-size: 1.02rem;
        color: #526176 !important;
        line-height: 1.55;
        max-width: 680px;
        margin: 0 auto;
    }

    /* =========================================================================
       4. 状态提示小胶囊 (Status Pill)
       ========================================================================= */
    .status-pill-mock {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        background: #F0FDF4;
        border: 1px solid #86EFAC;
        color: #16865C;
        font-size: 0.85rem;
        padding: 0.45rem 1rem;
        border-radius: 8px;
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.02);
    }
    .status-pill-byok {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        background: #EFF6FF;
        border: 1px solid #BFDBFE;
        color: #356AE6;
        font-size: 0.85rem;
        padding: 0.45rem 1rem;
        border-radius: 8px;
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.02);
    }
    .status-pill-local {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        background: #F5F3FF;
        border: 1px solid #DDD6FE;
        color: #6D28D9;
        font-size: 0.85rem;
        padding: 0.45rem 1rem;
        border-radius: 8px;
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.02);
    }

    /* =========================================================================
       5. 按钮样式体系 (Primary Brand Blue / Secondary Outline)
       ========================================================================= */
    /* 主按钮：品牌纯正蓝 (#356AE6) */
    button[kind="primary"], .stButton > button[kind="primary"] {
        background-color: #356AE6 !important;
        border: 1px solid #356AE6 !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        border-radius: 10px !important;
        height: 48px !important;
        box-shadow: 0 1px 3px 0 rgba(53, 106, 230, 0.3) !important;
        transition: all 0.15s ease-in-out !important;
    }
    button[kind="primary"]:hover, .stButton > button[kind="primary"]:hover {
        background-color: #2452C7 !important;
        border-color: #2452C7 !important;
        box-shadow: 0 3px 8px 0 rgba(53, 106, 230, 0.4) !important;
        transform: translateY(-1px);
    }

    /* 次级按钮：白底灰框，悬停微灰 */
    button[kind="secondary"], .stButton > button[kind="secondary"] {
        background-color: #FFFFFF !important;
        border: 1px solid #DDE3EA !important;
        color: #152033 !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        height: 42px !important;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03) !important;
        transition: all 0.15s ease-in-out !important;
    }
    button[kind="secondary"]:hover, .stButton > button[kind="secondary"]:hover {
        background-color: #F6F8FB !important;
        border-color: #CBD5E1 !important;
        color: #152033 !important;
    }

    /* 文字按钮 (Text / Ghost Button) - 降级卡片标准化重试按钮 */
    .st-key-btn_deg_retry button {
        background-color: transparent !important;
        border: 1px dashed #CBD5E1 !important;
        color: #356AE6 !important;
        box-shadow: none !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        height: 44px !important;
        border-radius: 10px !important;
        transition: all 0.15s ease-in-out !important;
    }
    .st-key-btn_deg_retry button:hover:not(:disabled) {
        background-color: #EFF6FF !important;
        border-color: #BFDBFE !important;
        color: #1D4ED8 !important;
        text-decoration: underline !important;
    }
    .st-key-btn_deg_retry button:disabled {
        background-color: #F8FAFC !important;
        border-color: #E2E8F0 !important;
        color: #94A3B8 !important;
        cursor: not-allowed !important;
    }

    /* =========================================================================
       6. 输入框与文本域 (Text Input & Text Area)
       ========================================================================= */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        background-color: #FFFFFF !important;
        color: #1D2939 !important;
        border: 1px solid #DDE3EA !important;
        border-radius: 9px !important;
        padding: 0.65rem 0.9rem !important;
        font-size: 0.95rem !important;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04) !important;
        transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #356AE6 !important;
        box-shadow: 0 0 0 3px rgba(53, 106, 230, 0.15) !important;
    }

    /* =========================================================================
       7. Tabs 切换卡片体系 (高对比度深色文字)
       ========================================================================= */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: #F0F4F8;
        padding: 5px;
        border-radius: 10px;
        border: 1px solid #DDE3EA;
    }
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        border-radius: 8px;
        color: #526176 !important;
        font-size: 0.95rem;
        font-weight: 600;
        padding: 0 18px;
        border: none !important;
        background: transparent !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #152033 !important;
        font-weight: 700 !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.08) !important;
    }

    /* =========================================================================
       8. 纯白通用卡片系统 (SaaS Card)
       ========================================================================= */
    .saas-card {
        background: #FFFFFF;
        border: 1px solid #DDE3EA;
        border-radius: 14px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.03);
    }
    .saas-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.85rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #F0F4F8;
    }
    .saas-card-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: #152033;
    }

    /* =========================================================================
       9. 状态步进指示器 (两行展示，桌面水平，移动端垂直)
       ========================================================================= */
    .stepper-container-v2 {
        display: flex;
        flex-direction: row;
        justify-content: space-between;
        align-items: stretch;
        gap: 8px;
        background: #FFFFFF;
        border: 1px solid #DDE3EA;
        border-radius: 12px;
        padding: 10px;
        margin: 1.2rem 0;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03);
    }
    @media (max-width: 768px) {
        .stepper-container-v2 {
            flex-direction: column;
            gap: 8px;
        }
    }
    .step-box-v2 {
        flex: 1;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center;
        padding: 8px 6px;
        border-radius: 8px;
        background: #F6F8FB;
        border: 1px solid #DDE3EA;
        min-height: 58px;
    }
    .step-title-v2 {
        font-size: 0.82rem;
        font-weight: 600;
        color: #152033;
        margin-bottom: 4px;
    }
    .step-status-v2 {
        font-size: 0.76rem;
        font-weight: 600;
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
    }

    /* =========================================================================
       10. 四级结论统计卡片 (微边框 + 顶边色条 + 浅底)
       ========================================================================= */
    .metric-card-supported {
        background: #F0FDF4;
        border: 1px solid #86EFAC;
        border-top: 3px solid #16865C;
        border-radius: 12px;
        padding: 1.1rem 0.8rem;
        text-align: center;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.02);
    }
    .metric-card-partial {
        background: #FFF8E6;
        border: 1px solid #FDE68A;
        border-top: 3px solid #9A6700;
        border-radius: 12px;
        padding: 1.1rem 0.8rem;
        text-align: center;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.02);
    }
    .metric-card-conflict {
        background: #FFF1F0;
        border: 1px solid #FCA5A5;
        border-top: 3px solid #B42318;
        border-radius: 12px;
        padding: 1.1rem 0.8rem;
        text-align: center;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.02);
    }
    .metric-card-insufficient {
        background: #F6F8FB;
        border: 1px solid #DDE3EA;
        border-top: 3px solid #667085;
        border-radius: 12px;
        padding: 1.1rem 0.8rem;
        text-align: center;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.02);
    }
    .metric-num {
        font-size: 1.9rem;
        font-weight: 750;
        margin: 0.25rem 0;
        line-height: 1.2;
    }
    .metric-sub {
        font-size: 0.78rem;
        color: #526176;
        font-weight: 500;
    }

    /* =========================================================================
       11. 结论徽章 (Badges)
       ========================================================================= */
    .badge-supported {
        background: #F0FDF4;
        color: #16865C;
        border: 1px solid #86EFAC;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-partial {
        background: #FFF8E6;
        color: #9A6700;
        border: 1px solid #FDE68A;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-conflict {
        background: #FFF1F0;
        color: #B42318;
        border: 1px solid #FCA5A5;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-insufficient {
        background: #F6F8FB;
        color: #526176;
        border: 1px solid #DDE3EA;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }

    /* =========================================================================
       12. Expander 折叠器与证据明细卡片
       ========================================================================= */
    [data-testid="stExpander"] {
        background-color: #FFFFFF !important;
        border: 1px solid #DDE3EA !important;
        border-radius: 12px !important;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03) !important;
        margin-bottom: 0.85rem !important;
    }
    .streamlit-expanderHeader {
        background-color: #FFFFFF !important;
        color: #152033 !important;
        font-weight: 650 !important;
        border-radius: 12px !important;
    }
    .streamlit-expanderContent {
        background-color: #FFFFFF !important;
        border-top: 1px solid #F0F4F8 !important;
        padding-top: 1rem !important;
    }

    /* 嵌套证据卡片样式 */
    .evidence-item-card {
        background: #F6F8FB;
        padding: 12px 16px;
        border-radius: 10px;
        margin-bottom: 10px;
        border: 1px solid #DDE3EA;
    }
    .evidence-quote-box {
        font-size: 0.88rem;
        color: #152033;
        line-height: 1.55;
        background: #FFFFFF;
        border-left: 3px solid #356AE6;
        padding: 8px 12px;
        border-radius: 0 6px 6px 0;
        margin-top: 6px;
        border-top: 1px solid #F0F4F8;
        border-right: 1px solid #F0F4F8;
        border-bottom: 1px solid #F0F4F8;
    }

    /* 单行调用预算小提示 */
    .budget-pill-line {
        font-size: 0.85rem;
        color: #526176;
        text-align: center;
        margin-top: 0.6rem;
        font-weight: 500;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

