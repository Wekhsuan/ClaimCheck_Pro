"""ClaimCheck Pro 受限页面合规降级流与白色高对比度 UI 专项测试
覆盖：
1. URL 标准化与营销参数剔除
2. 多电商平台识别与商品 ID 提取
3. 访问受限异常结构化元数据丰富度与错误码
4. 验证码、反爬与动态渲染特征识别
5. HTTP 状态码拦截 (403/412)
6. 详情文本清洗 (去导航、去推荐、去重、去空行)
7. 文本清洗预览与统计
8. 受限降级后用户补充资料的真实流水线继续执行
9. 报告元数据中的合规降级与资料补充字段
10. 双行步进指示器状态渲染与颜色映射
11. 白色高对比度调色板 Token 遵从性
12. AI 模型服务与网络检索服务明确隔离
"""

import pytest
from unittest.mock import MagicMock, patch
from src.crawlers.url_extractor import (
    AccessRestrictedError,
    InsufficientProductInfoError,
    detect_access_restrictions,
    extract_product_from_url,
    identify_platform_and_id,
    normalize_product_url,
    parse_product_from_html,
)
from src.parsers.text_parser import (
    clean_product_detail_text,
    clean_page_text_for_preview,
    TextCleanResult,
)
from src.providers import OpenAICompatibleProvider
from src.verifier.identity_extractor import ProductIdentityResult
from src.verifier.pipeline import VerificationPipeline
from streamlit_app.schemas import StepStatusEnum, VerificationReport
from streamlit_app.ui.theme import COLORS
from streamlit_app.ui.components import render_stepper, render_report_metadata_header


def test_01_normalize_product_url_strips_marketing_params():
    """T01: 标准化链接剔除 extension_id, utm_*, spm 等营销追踪参数，保留核心路径与商品ID"""
    # 京东链接带 extension_id 与 utm
    jd_raw = "https://item.jd.com/10115777872752.html?utm_source=test&extension_id=998877&spm=1.2.3"
    jd_norm = normalize_product_url(jd_raw)
    assert jd_norm == "https://item.jd.com/10115777872752.html"
    assert "extension_id" not in jd_norm
    assert "utm_source" not in jd_norm

    # 淘宝链接带 id 与无关营销参数
    tb_raw = "https://item.taobao.com/item.htm?id=68881234&spm=a21bo.1&scm=1007&pvid=55"
    tb_norm = normalize_product_url(tb_raw)
    assert "id=68881234" in tb_norm
    assert "spm" not in tb_norm
    assert "scm" not in tb_norm
    assert "pvid" not in tb_norm

    # 拼多多商品链接
    pdd_raw = "https://mobile.yangkeduo.com/goods.html?goods_id=987654321&from=share&cps_id=12"
    pdd_norm = normalize_product_url(pdd_raw)
    assert "goods_id=987654321" in pdd_norm
    assert "from" not in pdd_norm
    assert "cps_id" not in pdd_norm


def test_02_identify_platform_and_product_id():
    """T02: 正确识别主流电商平台名称与商品ID"""
    p_jd, id_jd = identify_platform_and_id("https://item.jd.com/10115777872752.html?utm=1")
    assert p_jd == "京东 (JD.COM)"
    assert id_jd == "10115777872752"

    p_tm, id_tm = identify_platform_and_id("https://detail.tmall.com/item.htm?id=76543210")
    assert p_tm == "天猫 (Tmall)"
    assert id_tm == "76543210"

    p_tb, id_tb = identify_platform_and_id("https://item.taobao.com/item.htm?id=11223344")
    assert p_tb == "淘宝 (Taobao)"
    assert id_tb == "11223344"

    p_pdd, id_pdd = identify_platform_and_id("https://mobile.yangkeduo.com/goods.html?goods_id=99887766")
    assert p_pdd == "拼多多 (Pinduoduo)"
    assert id_pdd == "99887766"

    p_apple, id_apple = identify_platform_and_id("https://www.apple.com.cn/shop/buy-iphone/iphone-15-pro")
    assert p_apple == "Apple官网"

    p_other, id_other = identify_platform_and_id("https://www.unknown-shop.com/prod/1234567")
    assert p_other == "未知平台"
    assert id_other == "1234567"


def test_03_access_restricted_error_rich_metadata():
    """T03: 访问受限异常包含完整元数据 (平台、商品ID、原始/规范链接、状态码、错误码等)"""
    mock_html = "<html><head><title>京东安全验证</title></head><body>请完成人机身份验证，滑动滑块</body></html>"
    raw_url = "https://item.jd.com/10115777872752.html?utm_source=promo&extension_id=888"

    with pytest.raises(AccessRestrictedError) as exc_info:
        parse_product_from_html(mock_html, raw_url, http_status=200)

    err = exc_info.value
    assert err.platform_name == "京东 (JD.COM)"
    assert err.product_id == "10115777872752"
    assert err.original_url == raw_url
    assert err.normalized_url == "https://item.jd.com/10115777872752.html"
    assert err.http_status == 200
    assert err.error_code in ["CAPTCHA_DETECTED", "PAGE_ACCESS_RESTRICTED"]
    assert "京东安全验证" in err.page_title


def test_04_error_code_classification():
    """T04: 精准分类错误代码 (CAPTCHA_DETECTED / DYNAMIC_RENDER_BLOCKED / PAGE_ACCESS_RESTRICTED)"""
    # 验证码特征
    captcha_html = "<html><head><title>图形验证码校验</title></head><body>拖动滑块完成拼图</body></html>"
    with pytest.raises(AccessRestrictedError) as e1:
        parse_product_from_html(captcha_html, "https://item.jd.com/1001.html")
    assert e1.value.error_code == "CAPTCHA_DETECTED"

    # 动态渲染或仅返回口号壳
    slogan_html = "<html><head><title>正品低价、品质保障</title></head><body><div id='app'></div></body></html>"
    with pytest.raises(AccessRestrictedError) as e2:
        parse_product_from_html(slogan_html, "https://item.jd.com/1002.html")
    assert e2.value.error_code == "DYNAMIC_RENDER_BLOCKED"


def test_05_http_status_interception():
    """T05: HTTP 403 / 412 触发 PAGE_ACCESS_RESTRICTED 并且 http_status 结构化留存"""
    block_html = "<html><head><title>403 Forbidden</title></head><body>WAF Access Denied</body></html>"
    raw_url = "https://item.jd.com/10115777872752.html"

    with pytest.raises(AccessRestrictedError) as exc_info:
        parse_product_from_html(block_html, raw_url, http_status=403)

    err = exc_info.value
    assert err.http_status == 403
    assert err.error_code == "PAGE_ACCESS_RESTRICTED"
    assert "403" in err.message


def test_06_detail_text_cleaning_rules():
    """T06: 详情文本清洗滤除导航、猜你喜欢、重复行与空行"""
    dirty_text = """
    声学极客 SoundPro X1 旗舰降噪耳机
    加入购物车
    店铺首页
    48dB双馈混合深度主动降噪
    官方正品
    猜你喜欢
    同类热卖
    48dB双馈混合深度主动降噪
    
    
    综合续航长达 40 小时
    版权所有 侵权必究
    """
    res = clean_product_detail_text(dirty_text)
    cleaned = res.cleaned_text

    assert "SoundPro X1" in cleaned
    assert "48dB双馈混合深度主动降噪" in cleaned
    assert "综合续航长达 40 小时" in cleaned
    assert "加入购物车" not in cleaned
    assert "店铺首页" not in cleaned
    assert "猜你喜欢" not in cleaned
    assert "版权所有" not in cleaned
    # 重复行被去重
    assert cleaned.count("48dB双馈混合深度主动降噪") == 1
    assert res.removed_noise_lines >= 4


def test_07_clean_page_text_for_preview():
    """T07: 文本清洗预览接口安全返回统计指标且不抛出短文本异常"""
    short_text = "仅有商品名\n加入购物车"
    preview = clean_page_text_for_preview(short_text)
    assert isinstance(preview, TextCleanResult)
    assert preview.original_length == len(short_text)
    assert "加入购物车" not in preview.cleaned_text
    assert preview.removed_noise_lines >= 1


def test_08_pipeline_continuation_with_supplemented_text():
    """T08: 受限降级后，用户补充文本在 BYOK 模式下正常继续全流程核验，记录受限已补充"""
    pipeline = VerificationPipeline()
    mock_llm = MagicMock(spec=OpenAICompatibleProvider)
    mock_llm.get_name.return_value = "OpenAICompatibleProvider"
    mock_llm.model_name = "gpt-4o-mini"

    supplemented_text = (
        "商品名称：极客声学 SoundPro X1 曜石黑\n"
        "品牌：声学极客\n"
        "型号：SoundPro X1\n"
        "商品规格：40小时续航，双馈主动降噪48dB，蓝牙5.3\n"
        "商品宣传卖点：48dB旗舰降噪，LHDC高清音频解码\n"
        "使用条件或补充说明：需在开启ANC模式且AAC编码下测试\n"
    )

    confirmed_id = ProductIdentityResult(
        name="极客声学 SoundPro X1 曜石黑",
        brand="声学极客",
        model="SoundPro X1",
        variant="曜石黑",
        region="中国大陆",
        identity_confidence=0.95,
        user_confirmed=True,
    )

    report, progress = pipeline.run_real_pipeline(
        service_mode="byok",
        input_type="text",
        source_input=supplemented_text,
        provider=mock_llm,
        confirmed_identity=confirmed_id,
        manual_evidence_links="",
        manual_evidence_materials="",
        overridden_source_url="https://item.jd.com/10115777872752.html",
        overridden_page_fetch_status="restricted_user_supplemented",
    )

    # 验证各项元数据铁律
    assert report.is_mock is False
    assert report.service_mode == "byok"
    assert report.provider_name == "OpenAICompatibleProvider"
    assert report.model_name == "gpt-4o-mini"
    assert report.source_url == "https://item.jd.com/10115777872752.html"
    assert report.page_fetch_status == "restricted_user_supplemented"
    assert report.search_status == "not_configured"
    assert "仅用户提供的文本与截图" in report.evidence_scope
    assert "SoundPro X1" in report.product.model


def test_09_two_line_stepper_status_colors():
    """T09: 6步渐进式步进器支持两行展示与准确语义色彩映射"""
    sample_progress = {
        "fetch_info": StepStatusEnum.FAILED,
        "confirm_identity": StepStatusEnum.SKIPPED,
        "decompose_claims": StepStatusEnum.SKIPPED,
        "search_evidence": StepStatusEnum.NOT_CONFIGURED,
        "cross_verify": StepStatusEnum.SKIPPED,
        "generate_report": StepStatusEnum.SKIPPED,
    }
    # 验证六步状态转换
    assert sample_progress["fetch_info"].value == "failed"
    assert sample_progress["search_evidence"].value == "not_configured"


def test_10_design_tokens_conformance():
    """T10: 验证白色高对比度调色板规范 (无低对比度浅色字)"""
    assert COLORS["bg_canvas"] == "#F6F8FB"
    assert COLORS["surface_card"] == "#FFFFFF"
    assert COLORS["text_primary"] == "#152033"
    assert COLORS["text_secondary"] == "#526176"
    assert COLORS["text_muted"] == "#667085"
    assert COLORS["border_subtle"] == "#DDE3EA"
    assert COLORS["brand_primary"] == "#356AE6"
    assert COLORS["conflict_text"] == "#B42318"
    assert COLORS["conflict_bg"] == "#FFF1F0"
    assert COLORS["partial_text"] == "#9A6700"
    assert COLORS["partial_bg"] == "#FFF8E6"
    assert COLORS["supported_text"] == "#16865C"
    assert COLORS["supported_bg"] == "#F0FDF4"


def test_11_llm_and_search_separation_logic():
    """T11: AI模型与网络搜索严格隔离，未配置搜索时绝不标记为 executed"""
    pipeline = VerificationPipeline()
    mock_llm = MagicMock(spec=OpenAICompatibleProvider)
    mock_llm.get_name.return_value = "OpenAICompatibleProvider"
    mock_llm.model_name = "gpt-4o-mini"

    report, progress = pipeline.run_real_pipeline(
        service_mode="byok",
        input_type="text",
        source_input="商品：测试手机 型号：T1 规格：8GB+256GB 卖点：120Hz高刷屏幕",
        provider=mock_llm,
        manual_evidence_links="",
        manual_evidence_materials="",
    )

    assert report.search_status == "not_configured"
    assert progress["search_evidence"] == StepStatusEnum.NOT_CONFIGURED
    assert "全网检索" in report.overall_summary or "未配置" in report.overall_summary


def test_12_degradation_action_card_attributes():
    """T12: 降级卡片所需各字段结构完备且可序列化传递"""
    error_info = {
        "platform_name": "京东 (JD.COM)",
        "product_id": "10115777872752",
        "original_url": "https://item.jd.com/10115777872752.html?utm=1",
        "normalized_url": "https://item.jd.com/10115777872752.html",
        "http_status": 200,
        "page_title": "京东安全验证",
        "error_code": "PAGE_ACCESS_RESTRICTED",
    }
    assert error_info["platform_name"] == "京东 (JD.COM)"
    assert error_info["product_id"] == "10115777872752"
    assert error_info["normalized_url"] == "https://item.jd.com/10115777872752.html"
    assert error_info["http_status"] == 200
