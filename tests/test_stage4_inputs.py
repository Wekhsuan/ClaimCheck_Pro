"""ClaimCheck Pro 阶段 4 自动化测试用例 (Three Inputs & Identity Extraction)

覆盖阶段 4 验收标准：
1. 测试公开静态页面 (优先解析 JSON-LD Product 结构)；
2. 测试动态或限制页面 (检测登录墙/反爬/滑块，合规阻断并触发优雅降级)；
3. 测试商品详情文本 (过滤电商导航噪声、多余重复行、检测敏感隐私如电话与订单号)；
4. 测试商品截图 (Pillow 压缩优化与 RapidOCR 纯本地离线文本提取)；
5. 测试多个相似型号候选识别与交互确认逻辑。
"""

import os
import sys
from pathlib import Path
import pytest

# 保证工作区根目录处于模块搜索路径首位
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.crawlers.ssrf_filter import safe_fetch_html, SSRFSecurityError
from src.crawlers.url_extractor import (
    parse_product_from_html,
    detect_access_restrictions,
    AccessRestrictedError,
    ExtractedProductData,
)
from src.parsers.text_parser import clean_product_detail_text, TextCleanResult
from src.ocr.image_processor import process_and_optimize_image, ProcessedImageResult
from src.ocr.local_ocr import local_ocr_engine
from src.verifier.identity_extractor import (
    extract_product_identity,
    ProductIdentityResult,
    ProductCandidate,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SCREENSHOTS_DIR = Path(__file__).parent.parent / "screenshots"


def test_public_static_page_json_ld():
    """测试 1: 公开静态页面解析，优先提取 schema.org/Product JSON-LD"""
    fixture_path = FIXTURES_DIR / "static_product_jsonld.html"
    assert fixture_path.exists(), f"未找到测试样本: {fixture_path}"

    with open(fixture_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 1. 验证 HTML 解析与 JSON-LD 结构化提取
    prod = parse_product_from_html(html_content, source_url="https://example.com/item/10001.html")
    assert prod.source_type == "json_ld"
    assert prod.brand == "声学极客"
    assert prod.model == "SoundPro X1"
    assert "48dB" in prod.description
    assert prod.price_info == "599.00"

    # 2. 验证基于结构化数据的身份确认
    identity = extract_product_identity(
        text_content=f"{prod.name}\n{prod.description}",
        pre_extracted={
            "brand": prod.brand,
            "model": prod.model,
            "name": prod.name,
        }
    )
    assert identity.brand == "声学极客"
    assert identity.model == "SoundPro X1"
    assert identity.identity_confidence >= 0.8
    assert "SoundPro X1" in identity.identity_evidence


def test_restricted_page_graceful_fallback():
    """测试 2: 动态或限制页面检测与合规降级，阻断爬取并不绕过验证码"""
    fixture_path = FIXTURES_DIR / "login_restricted_page.html"
    assert fixture_path.exists(), f"未找到测试样本: {fixture_path}"

    with open(fixture_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 1. 验证命中登录/滑块反爬特征
    reason = detect_access_restrictions(html_content, current_url="https://sec.taobao.com/punish?punish_type=1")
    assert reason is not None
    assert "受限" in reason or "反自动化" in reason or "特征" in reason

    # 2. 验证调用解析器时抛出 AccessRestrictedError 并提供降级提示
    with pytest.raises(AccessRestrictedError) as exc_info:
        parse_product_from_html(html_content, source_url="https://sec.taobao.com/item")

    err_msg = str(exc_info.value)
    assert "不绕过任何登录与验证码限制" in err_msg
    assert "商品详情文本" in err_msg or "商品宣传截图" in err_msg


def test_detail_text_cleaning_and_privacy_guard():
    """测试 3: 详情文本清洗、噪声过滤与个人隐私敏感信息扫描"""
    raw_text = (
        "【声学极客】SoundPro X1 旗舰降噪真无线耳机\n"
        "加入购物车\n"  # 噪声行
        "立即购买\n"  # 噪声行
        "48dB深度主动降噪，LHDC 5.0超高清传输，40小时综合续航\n"
        "官方正品\n"  # 噪声行
        "7天无理由退货\n"  # 噪声行
        "48dB深度主动降噪，LHDC 5.0超高清传输，40小时综合续航\n"  # 短期重复行
        "客户收件人电话：13812345678 请勿泄露\n"  # 隐私信息: 手机号
        "关联购买订单号：2026101688889999\n"  # 隐私信息: 订单号
    )

    clean_res = clean_product_detail_text(raw_text, min_len=10, max_len=10000)
    assert clean_res.removed_noise_lines >= 4
    assert "加入购物车" not in clean_res.cleaned_text
    assert "立即购买" not in clean_res.cleaned_text
    assert "7天无理由退货" not in clean_res.cleaned_text
    
    # 隐私警告断言
    assert len(clean_res.privacy_warnings) >= 2
    assert any("手机号码" in w for w in clean_res.privacy_warnings)
    assert any("订单号" in w for w in clean_res.privacy_warnings)

    # 身份识别断言
    identity = extract_product_identity(clean_res.cleaned_text)
    assert identity.brand == "声学极客"
    assert identity.model == "SoundPro X1"


def test_product_screenshot_local_ocr():
    """测试 4: 本地 Pillow 图片处理与 RapidOCR 离线文本抽取"""
    img_path = SCREENSHOTS_DIR / "test_ocr_input.png"
    assert img_path.exists(), f"未找到用于 OCR 测试的截图样本: {img_path}"

    # 1. Pillow 图像预处理与尺寸/质量检测
    processed = process_and_optimize_image(img_path, max_dimension=1920)
    assert processed.format == "JPEG"
    assert processed.width > 200
    assert processed.height > 200
    assert len(processed.base64_data) > 100
    assert "隐私安全提醒" in processed.privacy_notice

    # 2. RapidOCR 本地离线识别
    extracted_text, detailed_boxes = local_ocr_engine.extract_text(img_path)
    assert len(extracted_text) > 0
    # 验证是否成功提取出图中核心品牌与型号字符
    assert "极能" in extracted_text or "PowerMax" in extracted_text
    assert "PB-20065" in extracted_text or "65W" in extracted_text or "20000" in extracted_text

    # 3. 提取身份
    identity = extract_product_identity(extracted_text)
    assert identity.brand == "极能"
    assert identity.model == "PB-20065"


def test_multi_candidates_confirmation():
    """测试 5: 多个相似型号候选识别与必须由用户交互确认的逻辑"""
    multi_model_text = (
        "【声学极客】SoundPro X1 与 SoundPro X1-Pro 旗舰对比专场\n"
        "标准版 SoundPro X1 配备 42dB 降噪；\n"
        "旗舰版 SoundPro X1-Pro 配备 48dB 深度降噪与空间音频；\n"
        "另有入耳式 SoundPro Max 供发烧友选择。"
    )

    identity = extract_product_identity(multi_model_text)

    # 断言触发了多候选检测
    assert identity.has_multiple_candidates is True
    assert len(identity.candidates) >= 2
    assert len(identity.candidates) <= 3
    # 必须未确认，强制等待用户确认
    assert identity.user_confirmed is False

    # 验证候选结构
    cand_models = [c.model for c in identity.candidates]
    assert any("X1" in m for m in cand_models)

    # 模拟用户在前端单选卡片中选择了第 2 个候选 (例如 SoundPro X1-Pro)
    chosen_candidate = identity.candidates[1]
    identity.model = chosen_candidate.model
    identity.variant = chosen_candidate.variant
    identity.user_confirmed = True
    identity.identity_evidence += f"；用户在界面中手动确认目标型号为: {chosen_candidate.model}"

    assert identity.user_confirmed is True
    assert identity.model == chosen_candidate.model
    assert "用户在界面中手动确认" in identity.identity_evidence


def test_ssrf_security_filter():
    """补充测试: SSRF 安全过滤器防内网探测与非法协议阻断"""
    # 非法协议阻断
    with pytest.raises(SSRFSecurityError) as exc_proto:
        safe_fetch_html("ftp://example.com/file.txt")
    assert "协议" in str(exc_proto.value)

    # 回环地址阻断 (公开爬取模式下禁止探测内网)
    with pytest.raises(SSRFSecurityError) as exc_loop:
        safe_fetch_html("http://127.0.0.1:8501")
    assert "私有" in str(exc_loop.value) or "危险IP" in str(exc_loop.value) or "禁止访问" in str(exc_loop.value)
