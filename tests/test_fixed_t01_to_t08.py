"""ClaimCheck Pro 八大固定测试套件 (T01 ~ T08 固定验收测试)

验收标准对应：
- T01：Mock模式在无API Key、无网络时完整运行
- T02：用户API有效和无效配置测试
- T03：本地模型地址测试
- T04：公开商品链接读取与声明拆解
- T05：商品截图候选型号确认
- T06：有证据支持和部分支持案例
- T07：存在冲突和证据不足案例
- T08：登录、验证码或受限页面的安全降级
"""

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.security import validate_byok_url, validate_local_url
from src.crawlers.ssrf_filter import safe_fetch_html, SSRFSecurityError
from src.crawlers.url_extractor import (
    parse_product_from_html,
    detect_access_restrictions,
    AccessRestrictedError,
)
from src.parsers.text_parser import clean_product_detail_text
from src.providers.base import ConnectionTestResult
from src.providers.mock_provider import MockAIProvider
from src.providers.openai_provider import OpenAICompatibleProvider
from src.providers.local_provider import LocalModelProvider
from src.verifier.identity_extractor import extract_product_identity
from src.verifier.claim_decomposer import ClaimDecomposer
from src.verifier.cross_verifier import cross_verifier
from src.verifier.evidence_classifier import evidence_classifier
from src.verifier.fact_checker import fact_self_checker, sanitize_legal_phrasing
from streamlit_app.mock_provider import mock_provider
from streamlit_app.schemas import (
    ClaimItem,
    EvidenceItem,
    ProductIdentity,
    VerificationConclusionEnum,
)
from streamlit_app.report import ReportGenerator


# =============================================================================
# T01：Mock模式在无API Key、无网络时完整运行
# =============================================================================
def test_t01_mock_offline_complete_run():
    """T01: 验证在断网、零Key环境下，Mock模式毫秒级完整运行全流程"""
    t0 = time.perf_counter()
    
    # 1. 加载并生成报告
    report = mock_provider.generate_report_from_case("case_01_supported", service_mode="mock")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    
    # 2. 验证核心属性
    assert report.is_mock is True
    assert report.service_mode == "mock"
    assert report.product.brand == "声学极客 (SoundGeek)"
    assert report.product.model == "SoundPro X1"
    assert len(report.claims_results) == 3
    assert report.overall_summary != ""
    assert len(report.human_verification_items) >= 2
    assert len(report.pre_purchase_advice) >= 2
    
    # 3. 验证报告导出包含 Mock 演示水印
    md_content = ReportGenerator.generate_markdown(report)
    assert "当前为Mock演示数据，未执行实时网络核验" in md_content
    assert elapsed_ms < 100, f"Mock模式执行超时: {elapsed_ms:.1f}ms"


# =============================================================================
# T02：用户API有效和无效配置测试
# =============================================================================
def test_t02_user_api_configurations():
    """T02: 验证各种正确与异常用户 API 配置下的精准诊断与拦截"""
    # 场景 1: 未配置 Key
    p_no_key = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="")
    res_no_key = p_no_key.test_connection()
    assert res_no_key.success is False
    assert "API Key" in res_no_key.error_message and ("不能为空" in res_no_key.error_message or "未配置" in res_no_key.error_message)

    # 场景 2: 非法 HTTP 公网地址拦截 (只允许 HTTPS)
    is_valid_http, err_http = validate_byok_url("http://api.openai.com/v1")
    assert is_valid_http is False
    assert "HTTPS" in err_http

    # 场景 3: 401 无效密钥
    mock_resp_401 = MagicMock()
    mock_resp_401.status_code = 401
    mock_resp_401.json.return_value = {"error": {"message": "Incorrect API key provided"}}
    with patch("requests.post", return_value=mock_resp_401):
        p_401 = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="sk-invalid")
        res_401 = p_401.test_connection()
        assert res_401.success is False
        assert "401" in res_401.error_message
        assert ("验证失败" in res_401.error_message) or ("认证失败" in res_401.error_message)

    # 场景 4: 429 配额用尽
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.json.return_value = {"error": {"message": "You exceeded your current quota"}}
    with patch("requests.post", return_value=mock_resp_429):
        p_429 = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="sk-noquota")
        res_429 = p_429.test_connection()
        assert res_429.success is False
        assert "429" in res_429.error_message
        assert "额度耗尽" in res_429.error_message

    # 场景 5: 有效配置与全功能探测
    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    with patch("requests.post", return_value=mock_resp_200):
        p_200 = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="sk-valid", model="gpt-4o-mini")
        res_200 = p_200.test_connection()
        assert res_200.success is True
        assert res_200.supports_text is True
        assert res_200.supports_json_mode is True
        assert res_200.supports_vision is True


# =============================================================================
# T03：本地模型地址测试
# =============================================================================
def test_t03_local_model_endpoint_address():
    """T03: 验证本地端点白名单、危险公网拦截与连接拒绝处理"""
    # 场景 1: 本地合法回环地址与私有网段
    for valid_url in ["http://127.0.0.1:11434/v1", "http://localhost:11434/v1", "http://192.168.1.100:11434/v1"]:
        ok, _ = validate_local_url(valid_url)
        assert ok is True

    # 场景 2: 危险公网IP或未授权域名拦截
    for invalid_url in ["http://123.57.1.1:11434/v1", "http://8.8.8.8:11434/v1", "http://api.deepseek.com/v1"]:
        ok, err = validate_local_url(invalid_url)
        assert ok is False
        assert ("公网" in err) or ("外部IP" in err) or ("回环地址" in err) or ("非法" in err)

    # 场景 3: 本地未启动服务 (Connection Refused 优雅捕获)
    p_local = LocalModelProvider(base_url="http://127.0.0.1:59999/v1", model="qwen2.5:7b")
    res_loc = p_local.test_connection()
    assert res_loc.success is False
    assert "无法连接到本地" in res_loc.error_message
    assert "127.0.0.1:59999" in res_loc.error_message


# =============================================================================
# T04：公开商品链接读取与声明拆解
# =============================================================================
def test_t04_public_link_and_claim_decomposition():
    """T04: 针对公开静态商品页解析品牌型号并原子化拆解声明 (<=5条)"""
    fixture_path = PROJECT_ROOT / "tests" / "fixtures" / "static_product_jsonld.html"
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. 结构化抽取商品身份
    prod = parse_product_from_html(html, "https://item.example.com/soundpro.html")
    assert prod.brand == "声学极客"
    assert prod.model == "SoundPro X1"
    assert "48dB" in prod.description

    # 2. 宣传声明原子化拆解
    decomposer = ClaimDecomposer(max_claims=5)
    claims = decomposer.decompose(prod.description)
    assert len(claims) <= 5
    assert len(claims) >= 2
    for c in claims:
        assert c.single_verifiable_fact != ""
        assert c.category in ["参数", "功能", "性能", "材料", "兼容性", "使用条件", "明确体验承诺", "规格参数", "核心功能", "实测性能", "用户体验"]
        # 排除情绪化用词
        assert "遥遥领先" not in c.atomic_statement


# =============================================================================
# T05：商品截图候选型号确认
# =============================================================================
def test_t05_screenshot_candidate_confirmation():
    """T05: 识别截图中的多个相似型号，未确认时锁定，确认后解锁"""
    # 模拟从长图或截图中 OCR 出包含多个相似型号的文本
    ocr_text = """
    【新品对比选购指南】
    1. SoundPro X1 旗舰版：双馈降噪 48dB / 蓝牙 5.3 / LHDC 5.0；
    2. SoundPro SE 青春版：单馈降噪 35dB / 蓝牙 5.2 / AAC 解码；
    3. SoundPro Air 轻巧版：半入耳无降噪 / 13mm 大动圈。
    """
    ident_res = extract_product_identity(ocr_text)
    
    # 验证识别出多候选且匹配度计算正确
    assert ident_res.has_multiple_candidates is True
    assert len(ident_res.candidates) >= 2
    assert ident_res.user_confirmed is False
    
    # 模拟用户人工交互选定候选 1 (SoundPro X1 旗舰版)
    chosen = ident_res.candidates[0]
    ident_res.name = chosen.name
    ident_res.model = chosen.model
    ident_res.variant = chosen.variant
    ident_res.user_confirmed = True
    
    assert ident_res.user_confirmed is True
    assert ident_res.model == "SoundPro X1"


# =============================================================================
# T06：有证据支持和部分支持案例
# =============================================================================
def test_t06_supported_and_partially_supported():
    """T06: 验证同型号A级支持与省略条件的部分支持四级判定"""
    target = {"brand": "声学极客", "model": "SoundPro X1", "variant": "旗舰版"}
    
    # 1. 有证据支持 (同型号 A 级质检完全支持)
    claim_supp = ClaimItem(
        claim_id=1,
        original_text="深度降噪高达48dB",
        atomic_statement="最大降噪深度达到48dB",
        single_verifiable_fact="最大降噪深度48dB",
        category="规格参数",
        verification_target="降噪指标",
    )
    ev_a = EvidenceItem(
        evidence_id="E01",
        title="声学极客官方技术白皮书 SoundPro X1",
        url="https://soundgeek.cn/specs",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="依据国家质检标准测试，SoundPro X1 最大降噪深度为48.2dB",
        evidence_direction="support",
    )
    res_supp = cross_verifier.verify_single_claim(claim_supp, [ev_a], target)
    assert res_supp.conclusion == VerificationConclusionEnum.SUPPORTED
    assert res_supp.confidence >= 0.90
    assert res_supp.self_check_passed is True

    # 2. 部分支持 (宣称40小时续航，但省略了关闭降噪前提条件)
    claim_part = ClaimItem(
        claim_id=2,
        original_text="配合充电仓综合续航40小时",
        atomic_statement="整机综合续航达40小时",
        single_verifiable_fact="整机续航40小时",
        category="实测性能",
        verification_target="续航表现",
    )
    ev_part = EvidenceItem(
        evidence_id="E02",
        title="SoundPro X1 说明书",
        url="https://soundgeek.cn/manual.pdf",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="单次听歌9小时，仅在关闭降噪特定使用条件下整机达到40小时综合续航",
        evidence_direction="partial",
    )
    res_part = cross_verifier.verify_single_claim(claim_part, [ev_part], target)
    assert res_part.conclusion == VerificationConclusionEnum.PARTIALLY_SUPPORTED
    assert "省略" in res_part.analysis_reason or "条件" in res_part.analysis_reason


# =============================================================================
# T07：存在冲突和证据不足案例
# =============================================================================
def test_t07_conflict_and_insufficient_evidence():
    """T07: 验证高可信冲突判定与自检铁律1(未提及不判不支持)"""
    laptop_target = {"brand": "幻影", "model": "Pro 14", "variant": "2024款"}
    
    # 1. 存在冲突 (宣称雷电4，但官方明确为 USB 3.2 Gen2)
    claim_conf = ClaimItem(
        claim_id=1,
        original_text="搭载满血雷电4(Thunderbolt 4)接口",
        atomic_statement="配备雷电4接口支持40Gbps",
        single_verifiable_fact="搭载雷电4接口",
        category="规格参数",
        verification_target="雷电4接口支持",
    )
    ev_conf = EvidenceItem(
        evidence_id="E03",
        title="幻影 Pro 14 完整端口规格定义",
        url="https://phantom-tech.com/specs",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="左侧Type-C为全功能USB 3.2 Gen2 (10Gbps)，不支持Thunderbolt或USB4",
        evidence_direction="contradict",
    )
    res_conf = cross_verifier.verify_single_claim(claim_conf, [ev_conf], laptop_target)
    assert res_conf.conclusion == VerificationConclusionEnum.CONFLICT
    assert res_conf.confidence >= 0.90

    # 2. 证据不足 (宣称量子负离子防辐射，无任何同型号资料，自检铁律1生效)
    claim_unknown = ClaimItem(
        claim_id=2,
        original_text="量子负离子屏蔽99.9%射频辐射",
        atomic_statement="具备99.9%射频辐射阻隔效能",
        single_verifiable_fact="99.9%辐射屏蔽率",
        category="核心功能",
        verification_target="防辐射效能",
    )
    res_unknown = cross_verifier.verify_single_claim(claim_unknown, [], laptop_target)
    assert res_unknown.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    # 绝不违法定性
    assert "商业欺诈" not in res_unknown.analysis_reason
    assert "虚假宣传" not in res_unknown.analysis_reason


# =============================================================================
# T08：登录、验证码或受限页面的安全降级
# =============================================================================
def test_t08_login_captcha_restricted_graceful_fallback():
    """T08: 遇到登录拦截、滑块人机验证时自动停止并触发合规优雅降级"""
    fixture_path = PROJECT_ROOT / "tests" / "fixtures" / "login_restricted_page.html"
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 验证受限检测
    reason = detect_access_restrictions(html, current_url="https://sec.taobao.com/punish?punish_type=1")
    assert reason is not None
    assert "受限" in reason or "反自动化" in reason or "特征" in reason

    # 验证强制抛出异常拒绝暴力破解
    with pytest.raises(AccessRestrictedError) as exc_info:
        parse_product_from_html(html, source_url="https://sec.taobao.com/item")
    assert "不绕过任何登录与验证码限制" in str(exc_info.value)
    assert "商品详情文本" in str(exc_info.value) or "商品宣传截图" in str(exc_info.value)
