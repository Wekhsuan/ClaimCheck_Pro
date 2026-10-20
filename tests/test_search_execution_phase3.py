"""ClaimCheck Pro 第三阶段单元与集成测试套件 (Phase 3 Search Execution Tests)

覆盖：
1. 分层检索词生成器 (LayeredQueryGenerator)：
   - 官方优先 (Layer 1, Priority 1)
   - 专业评测 (Layer 2, Priority 2)
   - 用户体验查询默认关闭，显式开启才生成 (Layer 3, Priority 3)
   - 每条声明限制 4~6 个查询并去重
   - 缺少品牌型号强保护、严禁使用占位符与噪点
   - 核心关键词提取 (48dB, 40小时, 65W, LHDC 5.0)
2. 候选网页安全抓取与正文提取 (EvidenceFetcher)：
   - SSRF 拦截防御 (回环 127.0.0.1、内网私有 IP 拦截)
   - 单页最大 2MB 流式截断
   - Content-Type 白名单校验
   - 反爬滑块与登录墙受限状态检测 (restricted)
   - DOM 噪声清理 (nav, footer, script, style, ads)
   - 高密度段落定位与 200~450 字上下文摘录
3. Tavily Extract 抓取端点
4. 证据来源 A/B/C/D 分级与型号对齐结构化 (EvidenceStructurer)
"""

from unittest.mock import MagicMock, patch
import pytest

from src.crawlers.evidence_fetcher import EvidenceFetcher, WebPageExcerptResult
from src.search.base import SearchResultItem
from src.search.evidence_structurer import EvidenceStructurer
from src.search.query_generator import LayeredQueryGenerator, SearchQueryItem
from src.search.tavily_provider import TavilySearchProvider
from streamlit_app.schemas import ClaimItem, EvidenceItem


# =============================================================================
# 1. 分层检索词生成器测试 (LayeredQueryGenerator)
# =============================================================================

def test_query_generator_official_priority():
    """测试第一层官方资料优先生成 (Priority 1)"""
    generator = LayeredQueryGenerator()
    identity = {"brand": "声学极客", "model": "SoundPro X1", "product_name": "SoundPro X1 降噪耳机"}
    claim = ClaimItem(
        claim_id=1,
        original_text="双馈主动降噪高达48dB",
        atomic_statement="双馈主动降噪高达48dB",
        category="参数",
        verification_target="48dB降噪深度",
        claim_quality_score=0.92,
        is_verifiable=True,
    )
    queries = generator.generate_queries_for_claim(identity, claim, include_user_reviews=False)
    assert len(queries) >= 3
    # 官方词优先级必须是 1
    p1_queries = [q for q in queries if q.priority == 1]
    assert len(p1_queries) >= 2
    # 包含官方规格或说明书
    texts = [q.query_text for q in queries]
    assert any("官方规格" in t for t in texts)
    assert any("48db" in t.lower() for t in texts)


def test_query_generator_review_priority():
    """测试第二层专业评测生成 (Priority 2)"""
    generator = LayeredQueryGenerator()
    identity = {"brand": "华为", "model": "FreeBuds Pro 3"}
    claim = {"claim_id": 2, "atomic_statement": "支持LHDC 5.0高清音频传输", "category": "功能"}
    queries = generator.generate_queries_for_claim(identity, claim, include_user_reviews=False)
    p2_queries = [q for q in queries if q.priority == 2]
    assert len(p2_queries) >= 1
    assert any("评测" in q.query_text or "实测" in q.query_text for q in p2_queries)


def test_query_generator_user_reviews_toggle():
    """测试第三层用户体验反馈查询开关控制"""
    generator = LayeredQueryGenerator()
    identity = {"brand": "索尼", "model": "WH-1000XM5"}
    claim = {"claim_id": 3, "atomic_statement": "续航达到30小时", "category": "参数"}

    # 默认关闭：不应包含 Layer 3 (experience)
    queries_off = generator.generate_queries_for_claim(identity, claim, include_user_reviews=False)
    assert not any(q.query_type == "experience" for q in queries_off)

    # 显式开启：包含 Layer 3 (experience, priority 3)
    queries_on = generator.generate_queries_for_claim(identity, claim, include_user_reviews=True)
    exp_queries = [q for q in queries_on if q.query_type == "experience"]
    assert len(exp_queries) >= 1
    assert exp_queries[0].priority == 3
    assert "用户反馈" in exp_queries[0].query_text or "常见问题" in exp_queries[0].query_text


def test_query_generator_caps_and_deduplication():
    """测试查询词数量上限控制在 4~6 条且无重复"""
    generator = LayeredQueryGenerator()
    identity = {"brand": "苹果", "model": "AirPods Pro 2"}
    claim = {"claim_id": 1, "atomic_statement": "单次充电续航6小时，搭配充电盒达30小时", "category": "参数"}
    queries = generator.generate_queries_for_claim(identity, claim, include_user_reviews=True, max_queries=5)
    assert len(queries) <= 6
    texts = [q.query_text for q in queries]
    assert len(texts) == len(set(texts)), "查询词不得存在重复项"


def test_query_generator_rejects_missing_brand_model():
    """测试品牌与型号缺失时拒绝生成过度宽泛的无意义查询"""
    generator = LayeredQueryGenerator()
    identity = {"brand": "通用品牌", "model": "未知型号"}
    claim = {"claim_id": 1, "atomic_statement": "支持快充功能", "category": "功能"}
    queries = generator.generate_queries_for_claim(identity, claim)
    assert queries == []


def test_query_generator_rejects_placeholders():
    """测试严禁使用占位符、字段标题生成检索词"""
    generator = LayeredQueryGenerator()
    identity = {"brand": "小米", "model": "Buds 4 Pro"}
    for ph in ["【截图1提取内容】", "商品编号", "OCR识别内容", "未知内容"]:
        claim = {"claim_id": 1, "atomic_statement": ph, "category": "参数"}
        queries = generator.generate_queries_for_claim(identity, claim)
        assert queries == [], f"占位符 {ph} 应直接返回空列表"


def test_query_generator_keyword_extraction():
    """测试核心参数硬核词提取 (数值+单位, 协议标准)"""
    generator = LayeredQueryGenerator()
    kw_anc = generator.extract_claim_core_keywords("双馈深度主动降噪高达48dB", "参数")
    assert "48db" in kw_anc.lower()
    kw_charge = generator.extract_claim_core_keywords("支持GaN 65W超快闪充", "参数")
    assert "65w" in kw_charge.lower()
    kw_proto = generator.extract_claim_core_keywords("支持LHDC 5.0超清传输协议", "功能")
    assert "lhdc" in kw_proto.lower()
    kw_water = generator.extract_claim_core_keywords("整机具备IPX5级防水保护", "功能")
    assert "5" in kw_water or "防水" in kw_water or "ipx" in kw_water.lower()


# =============================================================================
# 2. 候选网页安全抓取与正文提取测试 (EvidenceFetcher)
# =============================================================================

def test_evidence_fetcher_ssrf_blocking():
    """测试 SSRF 防护：严格拦截本地回环与私有网络 IP"""
    fetcher = EvidenceFetcher()
    for bad_url in [
        "http://127.0.0.1:8080/admin",
        "http://localhost/secret",
        "http://192.168.1.1/router",
        "http://10.0.0.5/api",
        "http://169.254.169.254/latest/meta-data/",
    ]:
        res = fetcher.fetch_and_extract_excerpt(bad_url, "降噪")
        assert res.fetch_status == "ssrf_blocked"
        assert res.http_status == 403


def test_evidence_fetcher_content_type_whitelist():
    """测试 Content-Type 白名单校验：非 HTML/XHTML 直接拒绝"""
    fetcher = EvidenceFetcher()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "application/pdf"}
    mock_resp.iter_content = MagicMock(return_value=[b"%PDF-1.4 binary data"])

    with patch("src.crawlers.evidence_fetcher.validate_public_url", return_value=(True, "https://example.com/manual.pdf")):
        with patch("requests.Session.get", return_value=mock_resp):
            res = fetcher.fetch_and_extract_excerpt("https://example.com/manual.pdf", "48dB")
            assert res.fetch_status == "invalid_content_type"
            assert res.http_status == 415


def test_evidence_fetcher_size_limit():
    """测试单页 2MB 最大内容截断限制"""
    fetcher = EvidenceFetcher()
    # 模拟超过 2MB 的流式响应
    chunk = b"A" * (1024 * 512)  # 512 KB
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    mock_resp.encoding = "utf-8"
    mock_resp.iter_content = MagicMock(return_value=[chunk, chunk, chunk, chunk, chunk])  # 2.5 MB

    with patch("src.crawlers.evidence_fetcher.validate_public_url", return_value=(True, "https://example.com/huge-page.html")):
        with patch("requests.Session.get", return_value=mock_resp):
            res = fetcher.fetch_and_extract_excerpt("https://example.com/huge-page.html", "降噪")
            assert res.fetch_status in ["success", "restricted"]
            # 截断后内容不得超出 2MB
            assert res.content_bytes_len <= 2 * 1024 * 1024


def test_evidence_fetcher_anti_bot_detection():
    """测试反爬滑块与登录墙受限状态检测 (restricted)"""
    fetcher = EvidenceFetcher()
    html_blocked = """
    <html>
        <head><title>安全验证 - 访问受限</title></head>
        <body>
            <div id="captcha-box">请完成下方滑块验证码后继续访问页面</div>
        </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    mock_resp.encoding = "utf-8"
    mock_resp.iter_content = MagicMock(return_value=[html_blocked.encode("utf-8")])

    with patch("src.crawlers.evidence_fetcher.validate_public_url", return_value=(True, "https://item.example.com/item/123")):
        with patch("requests.Session.get", return_value=mock_resp):
            res = fetcher.fetch_and_extract_excerpt("https://item.example.com/item/123", "降噪")
            assert res.fetch_status == "restricted"
            assert "验证码" in res.error_message or "滑块" in res.error_message


def test_evidence_fetcher_clean_dom_noise():
    """测试 DOM 噪声过滤：清理 nav, header, footer, script, style, ads"""
    dirty_html = """
    <!DOCTYPE html>
    <html>
    <head><title>声学极客 SoundPro X1 官方规格</title><style>.ad{color:red;}</style></head>
    <body>
        <nav><a href="/">首页导航</a><a href="/login">登录注册</a></nav>
        <header><h1>顶部横幅促销广告</h1></header>
        <main>
            <p>声学极客 SoundPro X1 降噪旗舰真无线耳机采用前后双馈麦克风架构。</p>
            <p>根据声学国家重点实验室测试，在典型低频噪音环境下，双馈主动降噪深度高达48dB，有效隔绝飞机轰鸣与地铁喧嚣。</p>
            <p>综合续航时间长达40小时，支持急速闪充功能。</p>
        </main>
        <footer><p>版权所有 京ICP备123456号 客服电话 400-888-8888</p></footer>
        <script>console.log("analytics tracking code");</script>
    </body>
    </html>
    """
    cleaned = EvidenceFetcher.clean_html_content(dirty_html)
    assert "首页导航" not in cleaned
    assert "顶部横幅促销广告" not in cleaned
    assert "版权所有" not in cleaned
    assert "analytics tracking" not in cleaned
    assert "双馈主动降噪深度高达48dB" in cleaned


def test_evidence_fetcher_keyword_density_excerpt():
    """测试高密度关键词段落定位与 200~450 字上下文摘录"""
    fetcher = EvidenceFetcher()
    html_page = """
    <html>
    <head><title>SoundPro X1 专业实测报告</title></head>
    <body>
        <article>
            <p>第一节：外观设计与佩戴舒适度。SoundPro X1 采用了轻量化人体工学腔体，单耳仅重4.2克。</p>
            <p>第二节：降噪性能实测。我们使用专业消音室与人工耳测试平台，在80dB粉红噪声背景下，实测测得 SoundPro X1 的最大降噪深度达到了48.2dB，降噪频宽覆盖至3000Hz，表现极为优异，在同价位产品中处于领先水平。</p>
            <p>第三节：音质与续航表现。耳机在关闭降噪时单次可播放10小时，配合充电盒总续航可达40小时，支持快充功能。</p>
        </article>
    </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    mock_resp.encoding = "utf-8"
    mock_resp.iter_content = MagicMock(return_value=[html_page.encode("utf-8")])

    with patch("src.crawlers.evidence_fetcher.validate_public_url", return_value=(True, "https://tech.example.com/soundpro-review")):
        with patch("requests.Session.get", return_value=mock_resp):
            res = fetcher.fetch_and_extract_excerpt("https://tech.example.com/soundpro-review", "48dB")
            assert res.fetch_status == "success"
            assert "48.2dB" in res.excerpt or "48" in res.excerpt
            assert 100 <= len(res.excerpt) <= 600, f"摘录字数应在合理事实区间内，当前为 {len(res.excerpt)} 字"


# =============================================================================
# 3. Tavily Extract 端点测试
# =============================================================================

def test_tavily_extract_endpoint():
    """测试 TavilySearchProvider.extract 端点调用与优雅降级"""
    provider = TavilySearchProvider(api_key="tvly-test-mock-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json = MagicMock(return_value={
        "results": [
            {"url": "https://example.com/spec", "raw_content": "Official spec content with 48dB ANC."},
        ],
        "failed_results": [],
    })

    with patch("requests.post", return_value=mock_resp):
        res = provider.extract(["https://example.com/spec"])
        assert len(res) == 1
        assert "48dB" in res[0]["raw_content"]


# =============================================================================
# 4. 证据结构化与来源分级测试 (EvidenceStructurer)
# =============================================================================

def test_evidence_structurer_grades_and_alignment():
    """测试 A/B/C/D 来源分类与四维型号对齐结构化装配"""
    search_item = SearchResultItem(
        title="华为官方商城 - FreeBuds Pro 3 规格参数",
        url="https://consumer.huawei.com/cn/headphones/freebuds-pro-3/specs/",
        snippet="华为 FreeBuds Pro 3 支持星闪连接与双高清音频解码，配合充电盒综合续航长达30小时。",
        domain="consumer.huawei.com",
        provider="tavily",
        published_at="2024-03-01",
    )
    fetch_res = WebPageExcerptResult(
        url=search_item.url,
        domain=search_item.domain,
        title=search_item.title,
        fetch_status="success",
        http_status=200,
        content_type="text/html",
        excerpt="官方规格表：华为 FreeBuds Pro 3 支持星闪连接核心技术，续航时间关闭降噪模式下单耳续航为7小时，配合充电盒综合续航可达30小时。",
    )
    target_product = {
        "brand": "华为",
        "model": "FreeBuds Pro 3",
        "product_name": "华为 FreeBuds Pro 3",
        "variant": "标准版",
    }

    ev = EvidenceStructurer.structure_evidence(
        claim_id=1,
        search_item=search_item,
        fetch_res=fetch_res,
        target_product=target_product,
        index=1,
    )

    assert isinstance(ev, EvidenceItem)
    assert ev.evidence_id == "ev_1_1"
    assert "A级" in ev.source_level
    assert ev.model_match == "exact"
    assert "华为 FreeBuds Pro 3" in ev.excerpt
    assert "30小时" in ev.excerpt


def test_evidence_structurer_restricted_fallback():
    """测试抓取受限时回退并明确标注【页面受限】"""
    search_item = SearchResultItem(
        title="京东商品详情页",
        url="https://item.jd.com/10001.html",
        snippet="声学极客 SoundPro X1 双馈降噪48dB，快速发货。",
        domain="item.jd.com",
        provider="tavily",
    )
    fetch_res = WebPageExcerptResult(
        url=search_item.url,
        domain=search_item.domain,
        title=search_item.title,
        fetch_status="restricted",
        http_status=200,
        excerpt="",
    )
    target_product = {"brand": "声学极客", "model": "SoundPro X1"}

    ev = EvidenceStructurer.structure_evidence(
        claim_id=2,
        search_item=search_item,
        fetch_res=fetch_res,
        target_product=target_product,
        index=1,
    )

    assert "【页面受限】" in ev.excerpt
    assert ev.url == "https://item.jd.com/10001.html"
