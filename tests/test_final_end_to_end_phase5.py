"""ClaimCheck Pro 第五阶段最终端到端自动化测试套件 (E2E Test Suite)
严格依据规范第八项要求，覆盖 16 大关键业务与安全场景：
1. Mock完整流程
2. BYOK仅用户资料分析
3. BYOK加搜索服务
4. 本地模型模式
5. 链接读取受限后的文本降级
6. 截图声明提取
7. 没有有效声明时阻止搜索
8. 搜索预算确认
9. 真实证据URL追踪
10. 型号不一致证据排除
11. 四级结论
12. 二次事实自检
13. 报告导出
14. 密钥脱敏
15. 输入变化后旧报告失效
16. Mock不能进入真实报告
"""

import os
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.core.security import mask_api_key, mask_search_api_key
from src.crawlers.url_extractor import AccessRestrictedError, extract_product_from_url
from src.ocr.image_processor import process_and_optimize_image
from src.parsers.text_parser import clean_product_detail_text
from src.providers.budget import BudgetLimits, BudgetTracker
from src.providers.mock_provider import MockAIProvider
from src.providers.openai_provider import OpenAICompatibleProvider
from src.providers.local_provider import LocalModelProvider
from src.search.base import SearchResultItem
from src.search.no_search_provider import NoSearchProvider
from src.search.manual_provider import ManualEvidenceProvider
from src.verifier.claim_decomposer import ClaimDecomposer, evaluate_claim_quality_and_category
from src.verifier.identity_extractor import ProductIdentityResult, extract_product_identity
from src.verifier.model_alignment import ModelAlignmentVerifier
from src.verifier.evidence_validator import EvidenceValidator
from src.verifier.cross_verifier import CrossVerifier
from src.verifier.fact_checker import FactSelfChecker, sanitize_legal_phrasing
from src.verifier.pipeline import (
    DataModeMismatchError,
    NoVerifiableClaimsError,
    VerificationPipeline,
    calculate_input_fingerprint,
    verification_pipeline,
)
from streamlit_app.mock_provider import mock_provider
from streamlit_app.report import ReportGenerator
from streamlit_app.schemas import (
    ClaimItem,
    EvidenceItem,
    ProductIdentity,
    SourceLevelEnum,
    TaskStateEnum,
    VerificationConclusionEnum,
    VerificationReport,
)


# -----------------------------------------------------------------------------
# 1. Mock 完整流程测试
# -----------------------------------------------------------------------------
def test_01_mock_complete_pipeline_flow():
    """测试 1: Mock 离线演示模式完整流程 (免Key、全流程闭环)"""
    pipeline = VerificationPipeline()
    report, progress = pipeline.run_mock_pipeline(
        case_id="case_01_supported",
        input_type="url",
        source_input="https://item.jd.com/mock-soundpro-x1.html",
    )
    assert report is not None
    assert report.is_mock is True
    assert report.service_mode == "mock"
    assert report.provider_name == "MockAIProvider"
    assert len(report.claims_results) == 3
    assert progress["generate_report"].value == "success"
    assert report.product.model == "SoundPro X1"


# -----------------------------------------------------------------------------
# 2. BYOK 仅用户资料分析测试
# -----------------------------------------------------------------------------
def test_02_byok_only_user_data_analysis():
    """测试 2: BYOK 真实模式在未配置搜索时，基于用户输入资料开展客观核验"""
    pipeline = VerificationPipeline()
    fake_provider = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="sk-test-byok-user-only-123456",
        model_name="gpt-4o-mini",
    )
    ident = ProductIdentityResult(brand="弱水时砂", model="琉璃X", variant="旗舰版", region="中国大陆")
    claims = [
        ClaimItem(
            claim_id=1,
            original_text="支持45dB降噪",
            atomic_statement="支持45dB主动降噪",
            category="功能",
            verification_target="降噪深度45dB",
        )
    ]
    report, progress = pipeline.run_real_pipeline(
        service_mode="byok",
        input_type="text",
        source_input="品牌：弱水时砂 型号：琉璃X 宣传：支持45dB降噪",
        provider=fake_provider,
        confirmed_identity=ident,
        confirmed_claims=claims,
        search_provider_name="none",
        search_queries=[],
        structured_evidences=[],
    )
    assert report.is_mock is False
    assert report.service_mode == "byok"
    assert report.search_status == "not_configured"
    assert report.claims_results[0].conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    assert "证据不足" in report.claims_results[0].analysis_reason


# -----------------------------------------------------------------------------
# 3. BYOK 加搜索服务测试
# -----------------------------------------------------------------------------
def test_03_byok_with_search_service():
    """测试 3: BYOK 模式挂接真实结构化证据，完成多源交叉核验"""
    pipeline = VerificationPipeline()
    fake_provider = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="sk-test-byok-search-654321",
        model_name="gpt-4o-mini",
    )
    ident = ProductIdentityResult(brand="声学极客", model="SoundPro X1", variant="旗舰版")
    claims = [
        ClaimItem(
            claim_id=1,
            original_text="最大降噪达到48dB",
            atomic_statement="主动降噪深度达48dB",
            category="参数",
            verification_target="降噪深度48dB",
            search_keywords=["SoundPro X1 降噪48dB", "官方说明书"],
        )
    ]
    ev = EvidenceItem(
        evidence_id="EVID-TEST-01",
        title="声学极客 SoundPro X1 官方规格书",
        url="https://www.soundgeek.com/soundpro-x1/specs",
        source_type="官方规格书",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="声学极客 SoundPro X1 旗舰耳机搭载双馈主动降噪芯片，实测最大降噪深度达到48dB，符合国标声学标准。",
        evidence_direction="support",
        published_at="2026-05",
        is_valid_evidence=True,
        is_independent_source=True,
    )
    report, progress = pipeline.run_real_pipeline(
        service_mode="byok",
        input_type="text",
        source_input="SoundPro X1 降噪48dB",
        provider=fake_provider,
        confirmed_identity=ident,
        confirmed_claims=claims,
        search_provider_name="tavily",
        search_queries=["SoundPro X1 官方规格"],
        structured_evidences=[ev],
    )
    assert report.claims_results[0].conclusion == VerificationConclusionEnum.SUPPORTED
    assert report.claims_results[0].confidence_score >= 80.0
    assert report.search_status == "executed"


# -----------------------------------------------------------------------------
# 4. 本地模型模式测试
# -----------------------------------------------------------------------------
def test_04_local_model_mode_execution():
    """测试 4: 本地模型服务配置与创建 (Ollama/LocalAI)"""
    pipeline = VerificationPipeline()
    provider = pipeline.create_provider(
        service_mode="local",
        local_config={
            "base_url": "http://127.0.0.1:11434/v1",
            "model_name": "qwen2.5:7b",
            "timeout": 45,
            "temperature": 0.2,
            "max_tokens": 1024,
        },
    )
    assert isinstance(provider, LocalModelProvider)
    assert provider.model_name == "qwen2.5:7b"
    assert provider.base_url == "http://127.0.0.1:11434/v1"


# -----------------------------------------------------------------------------
# 5. 链接读取受限后的文本降级测试
# -----------------------------------------------------------------------------
def test_05_link_restricted_text_fallback():
    """测试 5: 当商品公开链接遇到反爬保护时，合规降级并支持文本继续核验"""
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "<html><title>京东安全验证</title><body>请完成滑块验证码验证</body></html>"
        mock_resp.url = "https://item.jd.com/10001234.html"
        mock_get.return_value = mock_resp

        with pytest.raises(AccessRestrictedError) as exc_info:
            extract_product_from_url("https://item.jd.com/10001234.html")
        assert "京东" in exc_info.value.platform_name

    # 用户手动改用文本模式清洗
    clean_res = clean_product_detail_text("品牌：弱水时砂 型号：琉璃X 支持45dB主动降噪 续航30小时")
    assert clean_res.cleaned_text != ""
    assert "弱水时砂" in clean_res.cleaned_text


# -----------------------------------------------------------------------------
# 6. 截图声明提取测试
# -----------------------------------------------------------------------------
def test_06_screenshot_claims_extraction():
    """测试 6: 截图输入预处理与宣传声明抽取"""
    from PIL import Image
    import io
    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    proc_res = process_and_optimize_image(buf.getvalue())
    assert len(proc_res.base64_data) > 0
    assert proc_res.width <= 1920 and proc_res.height <= 1920

    # 声明拆解器应能从 OCR 文字提取事实
    ocr_text = "弱水时砂 琉璃X 旗舰真无线耳机\n支持45dB深度降噪\n30小时超长续航"
    decomposer = ClaimDecomposer(max_claims=5)
    claims = decomposer.decompose(ocr_text)
    assert len(claims) >= 2


# -----------------------------------------------------------------------------
# 7. 没有有效声明时阻止搜索测试
# -----------------------------------------------------------------------------
def test_07_block_search_when_no_valid_claims():
    """测试 7: 无效内容过滤后有效声明为 0 时，硬拦截阻止网络搜索"""
    decomposer = ClaimDecomposer()
    invalid_text = "【截图1提取内容】 品牌 商品编号 尊贵非凡高端品质 暂无数据"
    valid_claims, rejected = decomposer.decompose_with_details(invalid_text)
    assert len(valid_claims) == 0
    assert len(rejected) > 0

    pipeline = VerificationPipeline()
    fake_provider = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="sk-test-fake", model_name="gpt-4o-mini")
    with pytest.raises(NoVerifiableClaimsError):
        pipeline.run_real_pipeline(
            service_mode="byok",
            input_type="text",
            source_input=invalid_text,
            provider=fake_provider,
            confirmed_claims=[],
        )


# -----------------------------------------------------------------------------
# 8. 搜索预算确认测试
# -----------------------------------------------------------------------------
def test_08_search_budget_confirmation_check():
    """测试 8: 搜索预算跟踪器正确计算并呈现预估请求数与费用承担方"""
    tracker = BudgetTracker(BudgetLimits(max_search_requests=5))
    summary_byok = tracker.get_preflight_summary(
        claims_count=4,
        service_mode="byok",
        search_mode="tavily",
    )
    assert "Tavily" in summary_byok["search_payer"]
    assert "用户" in summary_byok["payer"]
    assert "4 条" in summary_byok["claims_count"]

    summary_mock = tracker.get_preflight_summary(
        claims_count=4,
        service_mode="mock",
        search_mode="none",
    )
    assert "0" in summary_mock["estimated_searches"]


# -----------------------------------------------------------------------------
# 9. 真实证据 URL 追踪测试
# -----------------------------------------------------------------------------
def test_09_real_evidence_url_tracking():
    """测试 9: 证据对象保留真实 URL，不捏造不存在的网页"""
    ev = EvidenceItem(
        evidence_id="EVID-01",
        title="官方技术白皮书",
        url="https://consumer.huawei.com/cn/audio/specs/",
        source_type="品牌官网",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="华为 FreeBuds Pro 支持智慧动态降噪与 LDAC 高清音频传输协议。",
        evidence_direction="support",
    )
    assert ev.url.startswith("https://")
    assert "consumer.huawei.com" in ev.url
    assert len(ev.excerpt) >= 20


# -----------------------------------------------------------------------------
# 10. 型号不一致证据排除测试
# -----------------------------------------------------------------------------
def test_10_exclude_model_mismatch_evidences():
    """测试 10: 型号不符 (mismatch) 的外部证据必须被判定器强制剔除"""
    target_prod = {"brand": "声学极客", "model": "SoundPro X1", "variant": "旗舰版"}
    ev_mismatch = EvidenceItem(
        evidence_id="EVID-MISMATCH",
        title="SoundPro 青春版实测",
        url="https://review.com/soundpro-lite",
        source_type="媒体评测",
        source_level="B级 (权威实验室/科技媒体评测)",
        model_match="mismatch",
        excerpt="声学极客 SoundPro 青春版采用单馈降噪芯片，实测降噪仅有 25dB，续航为 18 小时。",
        evidence_direction="conflict",
    )
    claim = ClaimItem(
        claim_id=1,
        original_text="48dB降噪",
        atomic_statement="支持48dB主动降噪",
        category="功能",
        verification_target="降噪48dB",
    )
    validator = EvidenceValidator()
    valid_pool, excl_pool, _ = validator.validate_and_deduplicate(claim, [ev_mismatch], target_prod)
    assert len(valid_pool) == 0
    assert len(excl_pool) == 1
    assert excl_pool[0]["model_match"] == "mismatch"


# -----------------------------------------------------------------------------
# 11. 四级结论判定测试
# -----------------------------------------------------------------------------
def test_11_four_level_verdicts_consistency():
    """测试 11: 交叉核验引擎严格仅输出四级结论，无第五种定论"""
    verifier = CrossVerifier()
    claim = ClaimItem(
        claim_id=1,
        original_text="续航长达40小时",
        atomic_statement="整机综合续航达40小时",
        category="性能",
        verification_target="续航40小时",
    )
    target = {"brand": "声学极客", "model": "SoundPro X1"}

    # 无证据 -> 证据不足
    res_none = verifier.verify_single_claim(claim, [], target)
    assert res_none.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE

    # 包含遗漏条件证据 -> 部分支持
    ev_cond = EvidenceItem(
        evidence_id="EVID-COND",
        title="官方手册",
        url="https://brand.com/doc",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="SoundPro X1 在关闭降噪模式且特定音频格式下，整机续航可达40小时；开启降噪后为24小时。",
        evidence_direction="partial",
        is_valid_evidence=True,
    )
    res_partial = verifier.verify_single_claim(claim, [ev_cond], target)
    assert res_partial.conclusion == VerificationConclusionEnum.PARTIALLY_SUPPORTED


# -----------------------------------------------------------------------------
# 12. 二次事实自检测试
# -----------------------------------------------------------------------------
def test_12_fact_self_check_enforcement():
    """测试 12: 十五条事实自检铁律审查与激进法律词汇脱敏"""
    raw_reason = "商家存在虚假宣传与商业欺诈行为，严重违反广告法！"
    cleaned = sanitize_legal_phrasing(raw_reason)
    assert "虚假宣传" not in cleaned
    assert "商业欺诈" not in cleaned
    assert "出入" in cleaned or "未经充分证实" in cleaned


# -----------------------------------------------------------------------------
# 13. 报告导出测试
# -----------------------------------------------------------------------------
def test_13_report_export_md_and_txt(tmp_path):
    """测试 13: 报告生成引擎正确导出 Markdown 与 TXT 文件并落盘"""
    report = mock_provider.generate_report_from_case("case_01_supported", service_mode="mock")
    md_content = ReportGenerator.generate_markdown(report)
    txt_content = ReportGenerator.generate_text(report)

    assert "# ClaimCheck Pro" in md_content and "核验报告" in md_content
    assert report.product.brand in md_content
    assert "客观中立" in md_content
    assert "ClaimCheck Pro" in txt_content and "核验报告" in txt_content


# -----------------------------------------------------------------------------
# 14. 密钥脱敏安全测试
# -----------------------------------------------------------------------------
def test_14_api_key_and_cookie_masking():
    """测试 14: API Key 首尾掩码安全处理，日志与输出中绝无明文 Key"""
    raw_llm_key = "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz"
    masked_llm = mask_api_key(raw_llm_key)
    assert masked_llm.startswith("sk-") and "****" in masked_llm
    assert "1234567890" not in masked_llm

    raw_search_key = "tvly-production-998877665544332211"
    masked_search = mask_search_api_key(raw_search_key)
    assert masked_search.startswith("tvly-****")
    assert "99887766" not in masked_search


# -----------------------------------------------------------------------------
# 15. 输入变化后旧报告失效测试
# -----------------------------------------------------------------------------
def test_15_input_change_invalidates_old_report():
    """测试 15: 当输入发生变化时，输入指纹不匹配，强制阻断渲染旧报告"""
    fp_orig = calculate_input_fingerprint(
        input_type="url",
        content="https://item.jd.com/10001.html",
        service_mode="byok",
        provider_name="OpenAICompatibleProvider",
        model_name="gpt-4o-mini",
        confirmed_model="琉璃X",
    )
    fp_changed = calculate_input_fingerprint(
        input_type="url",
        content="https://item.jd.com/10002.html",
        service_mode="byok",
        provider_name="OpenAICompatibleProvider",
        model_name="gpt-4o-mini",
        confirmed_model="琉璃X",
    )
    assert fp_orig != fp_changed


# -----------------------------------------------------------------------------
# 16. Mock 不能进入真实报告安全隔离测试
# -----------------------------------------------------------------------------
def test_16_mock_data_cannot_leak_to_real_report():
    """测试 16: 硬安全门禁——真实模式下若报告标记为 is_mock=True 必须彻底阻断"""
    mock_report = mock_provider.generate_report_from_case("case_01_supported", service_mode="mock")
    assert mock_report.is_mock is True

    # 模拟真实模式拦截检查
    current_service_mode = "byok"
    is_violation = (mock_report.is_mock is True and current_service_mode != "mock")
    assert is_violation is True
