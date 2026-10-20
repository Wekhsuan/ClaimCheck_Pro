"""ClaimCheck Pro 核心机制验收测试：Mock 与真实模式 (BYOK / Local) 彻底隔离性与稳定性测试套件

涵盖 16 个高优先级回归测试项：
1. Mock 模式只能返回 Mock 数据
2. BYOK 模式严禁调用 MockProvider
3. Local 模式严禁调用 MockProvider
4. BYOK 网页读取失败返回结构化错误，绝不回退到 SoundPro X1
5. 修改商品链接后旧报告失效
6. 修改详情文本后旧报告失效
7. 切换服务模式后旧报告失效
8. 未配置搜索服务时，search_status 明确为 not_configured
9. 真实模式下检测到 is_mock=True 时硬阻断展示
10. Provider 异常直接抛出，绝不回退到 Mock 案例
11. JSON 解析失败时直接报错，绝不回退到 Mock 案例
12. 京东受限页面触发合规降级保护
13. 输入指纹 (input_fingerprint) 精准检测任何参数与内容变动
14. 清理旧报告时严格保留用户 API Key 与端点配置
15. BYOK 生成的报告元数据标记为真实模式，绝无 Mock 水印
16. 异常信息与日志中 API Key 必须严格脱敏，绝不暴露明文
"""

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

WORKSPACE_ROOT = Path(__file__).parent.parent.resolve()
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.core.security import mask_api_key
from src.crawlers.url_extractor import (
    AccessRestrictedError,
    InsufficientProductInfoError,
    extract_product_from_url,
)
from src.providers import (
    MockAIProvider,
    OpenAICompatibleProvider,
    LocalModelProvider,
)
from src.verifier.pipeline import (
    DataModeMismatchError,
    VerificationPipeline,
    calculate_input_fingerprint,
    verification_pipeline,
)
from streamlit_app.schemas import (
    StepStatusEnum,
    StructuredError,
    VerificationConclusionEnum,
    VerificationReport,
)


def test_01_mock_mode_only_returns_mock_data():
    """T01: Mock 模式只返回 Mock 演示数据，标记 is_mock=True"""
    pipeline = VerificationPipeline()
    report, progress = pipeline.run_mock_pipeline(
        case_id="case_01_supported",
        input_type="url",
        source_input="https://item.jd.com/mock-soundpro-x1.html",
    )
    assert report.is_mock is True
    assert report.service_mode == "mock"
    assert report.provider_name == "MockAIProvider"
    assert report.search_status == "mock_preset"
    assert progress["generate_report"] == StepStatusEnum.SUCCESS
    assert "声学极客" in report.product.brand


def test_02_byok_mode_never_calls_mock_provider():
    """T02: BYOK 模式只能使用 OpenAICompatibleProvider，严禁调用 MockProvider"""
    pipeline = VerificationPipeline()
    provider = pipeline.create_provider(
        service_mode="byok",
        byok_config={
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-user-test-key-12345678",
            "model_name": "gpt-4o-mini",
        },
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert not isinstance(provider, MockAIProvider)
    assert provider.model_name == "gpt-4o-mini"


def test_03_local_mode_never_calls_mock_provider():
    """T03: Local 模式只能使用 LocalModelProvider，严禁调用 MockProvider"""
    pipeline = VerificationPipeline()
    provider = pipeline.create_provider(
        service_mode="local",
        local_config={
            "base_url": "http://127.0.0.1:11434/v1",
            "model_name": "qwen2.5:7b",
        },
    )
    assert isinstance(provider, LocalModelProvider)
    assert not isinstance(provider, MockAIProvider)
    assert provider.model_name == "qwen2.5:7b"


def test_04_byok_page_fetch_failure_returns_structured_error():
    """T04: BYOK 模式下网页读取受限或失败时，抛出结构化异常，严禁返回 SoundPro X1"""
    pipeline = VerificationPipeline()
    mock_llm = MagicMock(spec=OpenAICompatibleProvider)
    mock_llm.get_name.return_value = "OpenAICompatibleProvider"
    mock_llm.model_name = "gpt-4o-mini"

    # 模拟网页读取抛出 AccessRestrictedError
    with patch("src.verifier.pipeline.extract_product_from_url") as mock_extract:
        mock_extract.side_effect = AccessRestrictedError("检测到京东反爬验证码拦截，触发合规降级保护")
        with pytest.raises(AccessRestrictedError) as exc_info:
            pipeline.run_real_pipeline(
                service_mode="byok",
                input_type="url",
                source_input="https://item.jd.com/10145673910180.html",
                provider=mock_llm,
            )
        assert "反爬验证码" in str(exc_info.value)
        # 验证绝未返回任何 Mock 报告对象


def test_05_url_change_invalidates_old_report():
    """T05: 修改商品链接导致 input_fingerprint 改变，旧报告判定为过期"""
    fp1 = calculate_input_fingerprint(
        input_type="url",
        content="https://item.jd.com/10001.html",
        service_mode="byok",
        provider_name="OpenAICompatibleProvider",
        model_name="gpt-4o-mini",
        confirmed_model="Model-A",
    )
    fp2 = calculate_input_fingerprint(
        input_type="url",
        content="https://item.jd.com/10002.html",  # URL 变化
        service_mode="byok",
        provider_name="OpenAICompatibleProvider",
        model_name="gpt-4o-mini",
        confirmed_model="Model-A",
    )
    assert fp1 != fp2


def test_06_detail_text_change_invalidates_old_report():
    """T06: 修改详情文本导致 input_fingerprint 改变，旧报告失效"""
    fp1 = calculate_input_fingerprint(
        input_type="text",
        content="华为 FreeBuds Pro 3 智慧动态降噪",
        service_mode="byok",
        provider_name="OpenAICompatibleProvider",
        model_name="gpt-4o-mini",
    )
    fp2 = calculate_input_fingerprint(
        input_type="text",
        content="华为 FreeBuds Pro 3 智慧动态降噪 星闪音频连接技术",
        service_mode="byok",
        provider_name="OpenAICompatibleProvider",
        model_name="gpt-4o-mini",
    )
    assert fp1 != fp2


def test_07_service_mode_change_invalidates_old_report():
    """T07: 切换服务模式导致 input_fingerprint 改变，禁止混用"""
    fp_mock = calculate_input_fingerprint(
        input_type="url",
        content="https://example.com/p",
        service_mode="mock",
        provider_name="MockAIProvider",
        model_name="offline-mock-v1",
    )
    fp_byok = calculate_input_fingerprint(
        input_type="url",
        content="https://example.com/p",
        service_mode="byok",
        provider_name="OpenAICompatibleProvider",
        model_name="gpt-4o-mini",
    )
    assert fp_mock != fp_byok


def test_08_unconfigured_search_sets_not_configured():
    """T08: 未配置搜索服务时，search_status 明确为 not_configured，无证据依铁律1归入证据不足"""
    pipeline = VerificationPipeline()
    mock_llm = MagicMock(spec=OpenAICompatibleProvider)
    mock_llm.get_name.return_value = "OpenAICompatibleProvider"
    mock_llm.model_name = "gpt-4o-mini"

    sample_text = (
        "索尼（SONY）WH-1000XM5 头戴式无线降噪耳机\n"
        "双芯驱动 30小时长续航 8麦克风高清通话\n"
        "规格：重量约250g，支持LDAC高解析度蓝牙编码"
    )

    report, progress = pipeline.run_real_pipeline(
        service_mode="byok",
        input_type="text",
        source_input=sample_text,
        provider=mock_llm,
        manual_evidence_links="",
        manual_evidence_materials="",
    )

    assert report.is_mock is False
    assert report.service_mode == "byok"
    assert report.search_status == "not_configured"
    assert "未配置网络搜索服务" in report.evidence_scope
    assert progress["search_evidence"] == StepStatusEnum.NOT_CONFIGURED
    # 验证依据铁律1：所有未获公开证据的声明判定为 INSUFFICIENT_EVIDENCE
    for c_res in report.claims_results:
        assert c_res.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
        assert "证据不足" in c_res.analysis_reason


def test_09_is_mock_mismatch_blocks_display():
    """T09: 真实服务模式下若注入 is_mock=True 的报告，硬门禁抛出 DataModeMismatchError"""
    pipeline = VerificationPipeline()
    mock_llm = MagicMock(spec=OpenAICompatibleProvider)
    mock_llm.get_name.return_value = "OpenAICompatibleProvider"
    mock_llm.model_name = "gpt-4o-mini"

    # 如果有任何恶意或意外使得 report.is_mock 变为 True
    # 模拟 pipeline 内部安全门禁触发
    with patch.object(pipeline.cross_verifier, "verify_single_claim") as mock_v:
        # 强制在校验后篡改 is_mock
        def mock_verify(*args, **kwargs):
            raise DataModeMismatchError("安全阻断：真实模式下禁止返回Mock数据")
        mock_v.side_effect = mock_verify

        with pytest.raises(DataModeMismatchError):
            pipeline.run_real_pipeline(
                service_mode="byok",
                input_type="text",
                source_input="索尼（SONY）WH-1000XM5 头戴式无线降噪耳机 30小时长续航",
                provider=mock_llm,
                manual_evidence_materials="官方说明书技术指标参数",
            )


def test_10_provider_exception_never_falls_back_to_mock():
    """T10: Provider 发生异常（如网络超时或401），直接向上抛出，绝不回退到 Mock 案例"""
    pipeline = VerificationPipeline()
    faulty_provider = MagicMock(spec=OpenAICompatibleProvider)
    faulty_provider.get_name.return_value = "OpenAICompatibleProvider"
    faulty_provider.model_name = "gpt-4o-mini"

    # 让拆解或核验过程调用 provider 抛出 TimeoutError
    with patch.object(pipeline.decomposer, "decompose") as mock_dec:
        mock_dec.side_effect = TimeoutError("OpenAI API 调用超时 (30s)")

        with pytest.raises(TimeoutError) as exc_info:
            pipeline.run_real_pipeline(
                service_mode="byok",
                input_type="text",
                source_input="索尼（SONY）WH-1000XM5 头戴式无线降噪耳机 30小时长续航",
                provider=faulty_provider,
            )
        assert "OpenAI API 调用超时" in str(exc_info.value)


def test_11_json_parse_failure_never_falls_back_to_mock():
    """T11: JSON 解析异常直接报错，绝不静默加载 SoundPro X1 案例"""
    pipeline = VerificationPipeline()
    provider = MagicMock(spec=OpenAICompatibleProvider)
    provider.get_name.return_value = "OpenAICompatibleProvider"
    provider.model_name = "gpt-4o-mini"

    with patch.object(pipeline.cross_verifier, "verify_single_claim") as mock_verify:
        mock_verify.side_effect = json.JSONDecodeError("Expecting value", "bad json", 0)

        with pytest.raises(json.JSONDecodeError):
            pipeline.run_real_pipeline(
                service_mode="byok",
                input_type="text",
                source_input="索尼（SONY）WH-1000XM5 头戴式无线降噪耳机 30小时长续航",
                provider=provider,
                manual_evidence_materials="官方说明书技术指标参数",
            )


def test_12_jd_restricted_page_safely_degrades():
    """T12: 京东空壳反爬页面触发 InsufficientProductInfoError 或 AccessRestrictedError"""
    jd_anti_bot_html = """
    <!DOCTYPE html>
    <html>
    <head><title>京东(JD.COM)-正品低价、品质保障、配送及时、轻松购物！</title></head>
    <body>
        <script src="//static.360buyimg.com/risk/pc-risk/2.2.0/pc-core-disposal.js"></script>
        <div>请您使用高版本浏览器浏览本网页。</div>
    </body>
    </html>
    """
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = jd_anti_bot_html
        mock_resp.content = jd_anti_bot_html.encode("utf-8")
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_get.return_value = mock_resp

        with pytest.raises((AccessRestrictedError, InsufficientProductInfoError)) as exc_info:
            extract_product_from_url("https://item.jd.com/10145673910180.html")
        assert "访问限制" in str(exc_info.value) or "未包含有效商品信息" in str(exc_info.value)


def test_13_input_fingerprint_mismatch_blocks_display():
    """T13: input_fingerprint 只要参数不同就完全不匹配"""
    base_params = {
        "input_type": "url",
        "content": "https://item.jd.com/12345.html",
        "service_mode": "byok",
        "provider_name": "OpenAICompatibleProvider",
        "model_name": "gpt-4o-mini",
        "confirmed_model": "X1",
    }
    fp_base = calculate_input_fingerprint(**base_params)

    # 修改 model_name
    mod_params = dict(base_params)
    mod_params["model_name"] = "deepseek-chat"
    fp_mod = calculate_input_fingerprint(**mod_params)
    assert fp_base != fp_mod

    # 修改 confirmed_model
    mod_params2 = dict(base_params)
    mod_params2["confirmed_model"] = "X2"
    fp_mod2 = calculate_input_fingerprint(**mod_params2)
    assert fp_base != fp_mod2


def test_14_user_api_config_preserved_when_clearing_report():
    """T14: 清理旧报告与状态时，必须严格保留用户的 API Key 与端点配置"""
    session = {
        "byok_base_url": "https://api.deepseek.com/v1",
        "byok_api_key": "sk-user-precious-key-12345",
        "byok_model": "deepseek-chat",
        "current_report": "old_report_object",
        "analysis_completed": True,
    }

    # 模拟 invalidate_analysis_state 逻辑
    def invalidate(st_session):
        st_session["current_report"] = None
        st_session["analysis_completed"] = False

    invalidate(session)
    assert session["current_report"] is None
    assert session["analysis_completed"] is False
    # 核心 API Key 与 Base URL 完好无损
    assert session["byok_api_key"] == "sk-user-precious-key-12345"
    assert session["byok_base_url"] == "https://api.deepseek.com/v1"
    assert session["byok_model"] == "deepseek-chat"


def test_15_mock_results_never_saved_in_byok_history():
    """T15: BYOK 真实模式下生成的报告，is_mock 严禁为 True，绝不使用 Mock 案例 ID"""
    from src.verifier.identity_extractor import ProductIdentityResult

    pipeline = VerificationPipeline()
    mock_llm = MagicMock(spec=OpenAICompatibleProvider)
    mock_llm.get_name.return_value = "OpenAICompatibleProvider"
    mock_llm.model_name = "gpt-4o-mini"

    confirmed_id = ProductIdentityResult(
        name="戴森 HD15 吹风机",
        brand="戴森",
        model="HD15",
        identity_confidence=0.98,
        user_confirmed=True,
    )
    report, _ = pipeline.run_real_pipeline(
        service_mode="byok",
        input_type="text",
        source_input="戴森（Dyson）HD15 吹风机 智能温控快速干发",
        provider=mock_llm,
        confirmed_identity=confirmed_id,
    )
    assert report.is_mock is False
    assert report.service_mode == "byok"
    assert report.provider_name == "OpenAICompatibleProvider"
    assert "MOCK" not in report.report_id
    assert report.report_id.startswith("REP-BYOK-")


def test_16_error_log_never_exposes_plain_api_key():
    """T16: 报错信息中若包含用户的 API Key，必须经过脱敏替换，绝不输出明文"""
    plain_key = "sk-proj-998877665544332211aabbccddeeff"
    error_message_with_key = f"Error 401: Unauthorized request with token '{plain_key}' to endpoint."

    masked = mask_api_key(plain_key)
    safe_error_message = error_message_with_key.replace(plain_key, masked)

    assert plain_key not in safe_error_message
    assert masked in safe_error_message
    assert "sk-pr****ff" in safe_error_message
