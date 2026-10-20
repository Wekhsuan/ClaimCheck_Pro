"""ClaimCheck Pro 第一阶段专项测试套件：有效宣传声明提取、无效内容过滤与质量评分

包含用户要求的 15 项关键测试用例：
1. 【截图1提取内容】不得被提取为声明
2. 【截图2提取内容】不得被提取为声明
3. OCR识别内容、截图提取结果不得被提取为声明
4. 弱水时砂作为品牌被提取到 product_identity.brand，不得进入 claims
5. 商品编号、商品编号：1008695271 不得进入 claims
6. 品牌、型号、规格、参数等纯字段名不得进入 claims
7. 未知内容、暂无、空字符串不得进入 claims
8. 未替换的模板变量（如 {brand}、{model}）不得进入 claims
9. 只有字段名称没有字段值的内容不得进入 claims
10. 支持45dB主动降噪 正确识别为性能或参数，评分 >= 0.65，is_verifiable=True
11. 总续航达到30小时 正确识别为性能或参数，评分 >= 0.65，is_verifiable=True
12. 支持IPX5防水 正确识别为性能或明确体验承诺，评分 >= 0.65，is_verifiable=True
13. 仅有2条有效声明时，最终声明数量必须为2，不得强行凑满5条
14. 没有任何有效声明时，必须抛出明确异常并停止后续核验流程
15. 提取到的所有声明的 category 必须严格属于 7 个允许类别之一
"""

import pytest
from unittest.mock import MagicMock

from src.verifier.claim_decomposer import (
    ClaimDecomposer,
    ClaimQualityFilter,
    evaluate_claim_quality_and_category,
)
from src.verifier.identity_extractor import extract_product_identity
from src.verifier.pipeline import (
    NoVerifiableClaimsError,
    VerificationPipeline,
)
from src.providers import OpenAICompatibleProvider
from streamlit_app.schemas import (
    ALLOWED_CLAIM_CATEGORIES,
    ClaimItem,
    ProductIdentity,
)


@pytest.fixture
def decomposer():
    return ClaimDecomposer(max_claims=5, quality_threshold=0.65)


@pytest.fixture
def pipeline():
    return VerificationPipeline()


# =============================================================================
# 1. 占位符过滤测试 (用例 1, 2, 3)
# =============================================================================
def test_01_screenshot_1_placeholder_rejected(decomposer):
    """用例 1: 【截图1提取内容】不得被提取为声明"""
    text = "【截图1提取内容】\n支持45dB主动降噪"
    claims, rejected = decomposer.decompose_with_details(text)
    
    assert len(claims) == 1
    assert claims[0].atomic_statement == "支持45dB主动降噪"
    
    # 确认占位符在拒绝列表中
    rejected_texts = [r.original_text for r in rejected]
    assert "【截图1提取内容】" in rejected_texts
    ph_reasons = [r.rejection_reason for r in rejected if "截图1" in r.original_text]
    assert "截图占位符" in ph_reasons[0]


def test_02_screenshot_2_placeholder_rejected(decomposer):
    """用例 2: 【截图2提取内容】不得被提取为声明"""
    text = "【截图2提取内容】\n总续航达到30小时"
    claims, rejected = decomposer.decompose_with_details(text)
    
    assert len(claims) == 1
    assert claims[0].atomic_statement == "总续航达到30小时"
    
    rejected_texts = [r.original_text for r in rejected]
    assert "【截图2提取内容】" in rejected_texts
    ph_reasons = [r.rejection_reason for r in rejected if "截图2" in r.original_text]
    assert "截图占位符" in ph_reasons[0]


def test_03_ocr_and_screenshot_extraction_placeholders_rejected(decomposer):
    """用例 3: OCR识别内容、截图提取结果不得被提取为声明"""
    text = "OCR识别内容\n截图提取结果\n支持IPX5防水\n本地OCR提取"
    claims, rejected = decomposer.decompose_with_details(text)
    
    assert len(claims) == 1
    assert claims[0].atomic_statement == "支持IPX5防水"
    
    rejected_texts = [r.original_text for r in rejected]
    assert "OCR识别内容" in rejected_texts
    assert "截图提取结果" in rejected_texts
    for r in rejected:
        if r.original_text in ["OCR识别内容", "截图提取结果"]:
            assert "系统占位符" in r.rejection_reason


# =============================================================================
# 2. 品牌与商品编号路由测试 (用例 4, 5)
# =============================================================================
def test_04_brand_ruoshuishisha_routed_to_identity_not_claims(decomposer):
    """用例 4: 弱水时砂作为品牌被提取到 product_identity.brand，不得进入 claims"""
    input_text = "弱水时砂\n琉璃X\n支持45dB主动降噪\n总续航达到30小时"
    
    # 1. 验证 identity_extractor 将弱水时砂提取为品牌
    ident_res = extract_product_identity(input_text)
    assert ident_res.brand == "弱水时砂"
    
    # 2. 验证 claim_decomposer 拦截弱水时砂，绝不进入声明列表
    product = ProductIdentity(
        brand=ident_res.brand,
        model=ident_res.model,
        version="标准版",
    )
    claims, rejected = decomposer.decompose_with_details(input_text, target_product=product)
    
    claim_texts = [c.atomic_statement for c in claims]
    assert "弱水时砂" not in claim_texts
    
    # 确认弱水时砂被归为商品身份元数据并记录拒绝原因
    ruoshui_rejected = [r for r in rejected if "弱水时砂" in r.original_text]
    assert len(ruoshui_rejected) > 0
    assert "属于商品品牌标识" in ruoshui_rejected[0].rejection_reason
    assert "已收录于商品身份" in ruoshui_rejected[0].rejection_reason


def test_05_product_id_never_in_claims(decomposer):
    """用例 5: 商品编号、商品编号：1008695271 不得进入 claims"""
    input_text = "商品编号\n商品编号：1008695271\n支持65W快充"
    
    # 验证 identity_extractor 提取到 product_id
    ident_res = extract_product_identity(input_text)
    assert ident_res.product_id == "1008695271"
    
    # 验证 claim_decomposer 过滤商品编号
    claims, rejected = decomposer.decompose_with_details(input_text)
    claim_texts = [c.atomic_statement for c in claims]
    assert "商品编号" not in claim_texts
    assert "商品编号：1008695271" not in claim_texts
    assert "1008695271" not in claim_texts
    
    # 检查拒绝原因
    rejected_reasons = {r.original_text: r.rejection_reason for r in rejected}
    assert "商品编号" in rejected_reasons
    assert "商品编号：1008695271" in rejected_reasons
    assert "商品编号/货号元数据" in rejected_reasons["商品编号：1008695271"]


# =============================================================================
# 3. 字段标题、空值与模板变量拦截测试 (用例 6, 7, 8, 9)
# =============================================================================
def test_06_pure_field_titles_rejected(decomposer):
    """用例 6: 品牌、型号、规格、参数等纯字段名不得进入 claims"""
    input_text = "品牌\n型号\n规格\n参数\n详情页\n包装清单\n好评率\n支持双设备连接"
    claims, rejected = decomposer.decompose_with_details(input_text)
    
    assert len(claims) == 1
    assert claims[0].atomic_statement == "支持双设备连接"
    
    rejected_texts = [r.original_text for r in rejected]
    for field in ["品牌", "型号", "规格", "参数", "详情页", "包装清单", "好评率"]:
        assert field in rejected_texts
        reason = [r.rejection_reason for r in rejected if r.original_text == field][0]
        assert "字段" in reason or "标题" in reason or "品牌" in reason or "型号" in reason


def test_07_unknown_empty_placeholders_rejected(decomposer):
    """用例 7: 未知内容、暂无、空字符串不得进入 claims"""
    input_text = "未知内容\n暂无\n   \n未提供\nN/A\n支持入耳检测"
    claims, rejected = decomposer.decompose_with_details(input_text)
    
    assert len(claims) == 1
    assert claims[0].atomic_statement == "支持入耳检测"
    
    rejected_texts = [r.original_text for r in rejected]
    assert "未知内容" in rejected_texts
    assert "暂无" in rejected_texts
    assert "未提供" in rejected_texts


def test_08_unreplaced_template_variables_rejected(decomposer):
    """用例 8: 未替换的模板变量（如 {brand}、{model}）不得进入 claims"""
    input_text = "{brand} 旗舰新款\n{model} 超强降噪\n<param> 规格说明\n支持无线充电"
    claims, rejected = decomposer.decompose_with_details(input_text)
    
    assert len(claims) == 1
    assert claims[0].atomic_statement == "支持无线充电"
    
    rejected_texts = [r.original_text for r in rejected]
    assert "{brand} 旗舰新款" in rejected_texts
    assert "{model} 超强降噪" in rejected_texts
    assert "<param> 规格说明" in rejected_texts
    
    reason = [r.rejection_reason for r in rejected if "{brand}" in r.original_text][0]
    assert "未替换的模板变量" in reason


def test_09_field_name_without_value_rejected(decomposer):
    """用例 9: 只有字段名称没有字段值的内容不得进入 claims"""
    input_text = "续航：\n充电功率:\n防水等级：\n支持45dB主动降噪"
    claims, rejected = decomposer.decompose_with_details(input_text)
    
    assert len(claims) == 1
    assert claims[0].atomic_statement == "支持45dB主动降噪"
    
    rejected_texts = [r.original_text for r in rejected]
    assert "续航：" in rejected_texts
    assert "充电功率:" in rejected_texts
    assert "防水等级：" in rejected_texts
    
    for r in rejected:
        if r.original_text in ["续航：", "充电功率:", "防水等级："]:
            assert "缺少具体参数" in r.rejection_reason or "字段名称" in r.rejection_reason


# =============================================================================
# 4. 有效声明与评分算法验证 (用例 10, 11, 12)
# =============================================================================
def test_10_anc_45db_valid_performance_or_param(decomposer):
    """用例 10: 支持45dB主动降噪 正确识别为性能或参数，评分 >= 0.65，is_verifiable=True"""
    phrase = "支持45dB主动降噪"
    score, is_verifiable, category, target = evaluate_claim_quality_and_category(phrase)
    
    assert score >= 0.65
    assert is_verifiable is True
    assert category in ["性能", "参数"]
    
    # 通过 decomposer 端到端检验
    claims = decomposer.decompose(phrase)
    assert len(claims) == 1
    assert claims[0].atomic_statement == phrase
    assert claims[0].claim_quality_score >= 0.65
    assert claims[0].is_verifiable is True
    assert claims[0].category in ["性能", "参数"]


def test_11_battery_30h_valid_performance_or_param(decomposer):
    """用例 11: 总续航达到30小时 正确识别为性能或参数，评分 >= 0.65，is_verifiable=True"""
    phrase = "总续航达到30小时"
    score, is_verifiable, category, target = evaluate_claim_quality_and_category(phrase)
    
    assert score >= 0.65
    assert is_verifiable is True
    assert category in ["性能", "参数"]
    
    claims = decomposer.decompose(phrase)
    assert len(claims) == 1
    assert claims[0].atomic_statement == phrase
    assert claims[0].claim_quality_score >= 0.65
    assert claims[0].is_verifiable is True
    assert claims[0].category in ["性能", "参数"]


def test_12_ipx5_waterproof_valid_commitment(decomposer):
    """用例 12: 支持IPX5防水 正确识别为明确体验承诺或性能，评分 >= 0.65，is_verifiable=True"""
    phrase = "支持IPX5防水"
    score, is_verifiable, category, target = evaluate_claim_quality_and_category(phrase)
    
    assert score >= 0.65
    assert is_verifiable is True
    assert category in ["明确体验承诺", "性能", "材料"]
    
    claims = decomposer.decompose(phrase)
    assert len(claims) == 1
    assert claims[0].atomic_statement == phrase
    assert claims[0].claim_quality_score >= 0.65
    assert claims[0].is_verifiable is True
    assert claims[0].category in ["明确体验承诺", "性能", "材料"]


# =============================================================================
# 5. 动态数量控制与 0 声明中断安全拦截 (用例 13, 14, 15)
# =============================================================================
def test_13_dynamic_claim_count_exactly_two(decomposer):
    """用例 13: 仅有2条有效声明时，最终声明数量必须为2，不得强行凑满5条"""
    input_text = """
    弱水时砂
    琉璃X
    商品编号：1008695271
    规格：标准版
    【截图1提取内容】
    支持45dB主动降噪
    总续航达到30小时
    官方正品
    假一赔十
    """
    claims, rejected = decomposer.decompose_with_details(input_text)
    
    # 严格检验数量动态自适应：只有2条有效，输出精确为2条，绝不凑满5条
    assert len(claims) == 2
    claim_texts = [c.atomic_statement for c in claims]
    assert "支持45dB主动降噪" in claim_texts
    assert "总续航达到30小时" in claim_texts
    
    # 确认其余项均被正确归入 rejected
    assert len(rejected) >= 5


def test_14_no_valid_claims_stops_and_raises_error(decomposer, pipeline):
    """用例 14: 没有任何有效声明时，必须返回空并抛出明确异常，停止后续核验流程"""
    # 纯垃圾/占位符文案
    useless_input = """
    【截图1提取内容】
    弱水时砂
    商品编号：1008695271
    规格
    参数
    详情页
    未知内容
    官方正品
    """
    claims, rejected = decomposer.decompose_with_details(useless_input)
    assert len(claims) == 0
    assert len(rejected) > 0
    
    # 模拟在流水线中执行真实核验，必须抛出 NoVerifiableClaimsError，严禁生成 Mock 报告
    mock_llm = MagicMock(spec=OpenAICompatibleProvider)
    mock_llm.get_name.return_value = "OpenAICompatibleProvider"
    mock_llm.model_name = "gpt-4o-mini"
    
    with pytest.raises(NoVerifiableClaimsError) as exc_info:
        pipeline.run_real_pipeline(
            service_mode="byok",
            input_type="text",
            source_input=useless_input,
            provider=mock_llm,
        )
    
    # 检验友好的用户提示文案
    expected_msg_fragment = "暂未从当前资料中提取到可验证的宣传声明"
    assert expected_msg_fragment in str(exc_info.value)
    assert exc_info.value.filtered_candidates is not None


def test_15_all_categories_strictly_within_seven_allowed(decomposer):
    """用例 15: 提取到的所有声明的 category 必须严格属于 7 个允许类别之一"""
    comprehensive_input = """
    单耳净重仅4.5g
    支持双设备快速切换
    主动降噪深度达48dB
    采用航空级铝合金腔体
    支持LHDC 5.0超清音频传输协议
    需搭配专用App开启高解析度模式
    支持IPX5级生活防水防汗
    """
    claims, _ = decomposer.decompose_with_details(comprehensive_input)
    
    assert len(claims) >= 5
    for c in claims:
        assert c.category in ALLOWED_CLAIM_CATEGORIES, f"声明 '{c.atomic_statement}' 的类别 '{c.category}' 不在 7 个严格允许类别中"
