"""ClaimCheck Pro 阶段 4 自动化测试套件 (Phase 4 Evidence Verification Tests)

覆盖 30 项专项核验测试场景：
1. exact型号A级证据能够形成有证据支持
2. 官方最高值省略条件形成部分支持
3. 同型号官方资料直接矛盾形成存在冲突
4. 只有C级来源形成证据不足
5. 只有D级来源形成证据不足
6. 搜索未配置不得生成实时网络核验结论
7. mismatch证据被排除并记录原因
8. series_only不能形成高置信强结论
9. 未提及不能判定为不支持
10. 重复转载只算一个独立来源
11. C级评论不能单独证明技术参数
12. A级与B级互相印证提高置信度
13. A级证据互相冲突触发人工复核
14. 地区版本不一致触发人工复核
15. 理由相似度超过0.85触发重写
16. 重写次数受控不会无限循环
17. 自检能够发现不存在的evidence_id
18. 自检能够发现引用片段不在正文中
19. 自检能够纠正过度绝对化断言
20. 证据不足不会被表述为虚假
21. 报告包含真实来源URL
22. 报告不包含API Key
23. 报告不包含Cookie
24. 报告不包含Authorization Header
25. Mock结果不能进入真实报告
26. 人工复核原因正确显示
27. 总体统计与逐项结论完全一致
28. confidence_score始终在0至100分
29. 四级结论之外的值被拒绝
30. 同一报告中每条声明理由具有证据差异性
"""

import copy
import re
from unittest.mock import MagicMock
import pytest

from streamlit_app.schemas import (
    ClaimItem,
    EvidenceItem,
    ProductIdentity,
    VerificationConclusionEnum,
    ClaimVerificationResult,
    VerificationReport,
)
from src.verifier.cross_verifier import cross_verifier
from src.verifier.evidence_validator import evidence_validator
from src.verifier.model_alignment import model_alignment_verifier
from src.verifier.fact_checker import fact_self_checker
from src.verifier.reason_generator import reason_generator
from src.verifier.human_review import human_review_engine
from src.verifier.pipeline import VerificationPipeline, DataModeMismatchError
from src.providers.base import AIProvider


@pytest.fixture
def target_earphones():
    return {
        "brand": "弱水时砂",
        "model": "琉璃X",
        "variant": "标准版",
        "region": "中国大陆",
    }


@pytest.fixture
def fake_provider():
    provider = MagicMock(spec=AIProvider)
    provider.get_name.return_value = "FakeTestProvider"
    provider.model_name = "fake-model-v1"
    provider.test_connection.return_value = (True, "测试连接成功", 15.0)
    provider.generate_text.return_value = "Fake generated text"
    return provider


# =============================================================================
# 测试 1: exact型号A级证据能够形成有证据支持
# =============================================================================
def test_01_exact_model_level_a_supported(target_earphones):
    claim = ClaimItem(
        claim_id=1,
        original_text="支持45dB主动降噪",
        atomic_statement="主动降噪深度达45dB",
        single_verifiable_fact="主动降噪深度45dB",
        category="参数",
        verification_target="降噪深度",
    )
    ev_a = EvidenceItem(
        evidence_id="EVID-001",
        title="弱水时砂 琉璃X 官方规格参数页",
        url="https://rosemusic.cn/specs/liulix",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="弱水时砂 琉璃X 具备双馈主动降噪技术，依据国家测试标准最大降噪深度可达45.2dB",
        evidence_direction="support",
    )
    result = cross_verifier.verify_single_claim(claim, [ev_a], target_earphones)
    assert result.conclusion == VerificationConclusionEnum.SUPPORTED
    assert result.verdict == "有证据支持"
    assert result.confidence_score >= 80.0
    assert result.confidence_level in ["高", "中高"]
    assert "EVID-001" in result.supporting_evidence_ids


# =============================================================================
# 测试 2: 官方最高值省略条件形成部分支持
# =============================================================================
def test_02_omitted_conditions_partially_supported(target_earphones):
    claim = ClaimItem(
        claim_id=2,
        original_text="整机续航高达35小时",
        atomic_statement="整机综合续航达到35小时",
        single_verifiable_fact="整机综合续航35小时",
        category="性能",
        verification_target="整机续航",
    )
    ev_cond = EvidenceItem(
        evidence_id="EVID-002",
        title="弱水时砂 琉璃X 用户手册",
        url="https://rosemusic.cn/manual/liulix.pdf",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="单次听歌7小时，仅在关闭降噪特定条件及AAC编码50%音量下整机续航可达35小时",
        evidence_direction="partial",
    )
    result = cross_verifier.verify_single_claim(claim, [ev_cond], target_earphones)
    assert result.conclusion == VerificationConclusionEnum.PARTIALLY_SUPPORTED
    assert result.verdict == "部分支持"
    assert "条件" in result.analysis_reason or "特定" in result.analysis_reason


# =============================================================================
# 测试 3: 同型号官方资料直接矛盾形成存在冲突
# =============================================================================
def test_03_same_model_official_direct_contradiction(target_earphones):
    claim = ClaimItem(
        claim_id=3,
        original_text="支持LHDC 5.0超高清无损音频传输协议",
        atomic_statement="支持LHDC 5.0协议",
        single_verifiable_fact="支持LHDC 5.0协议",
        category="兼容性",
        verification_target="音频传输协议",
    )
    ev_conflict = EvidenceItem(
        evidence_id="EVID-003",
        title="弱水时砂 琉璃X 官方技术白皮书",
        url="https://rosemusic.cn/specs/audio",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="弱水时砂 琉璃X 支持LDAC高清解码与AAC，不支持LHDC 5.0或aptX协议",
        evidence_direction="contradict",
    )
    result = cross_verifier.verify_single_claim(claim, [ev_conflict], target_earphones)
    assert result.conclusion == VerificationConclusionEnum.CONFLICT
    assert result.verdict == "存在冲突"
    assert "EVID-003" in result.contradicting_evidence_ids


# =============================================================================
# 测试 4: 只有C级来源形成证据不足
# =============================================================================
def test_04_only_level_c_insufficient_for_parameter(target_earphones):
    claim = ClaimItem(
        claim_id=4,
        original_text="内置12mm纳米平板复合振膜",
        atomic_statement="发声单元为12mm复合振膜",
        single_verifiable_fact="12mm复合振膜",
        category="参数",
        verification_target="振膜尺寸",
    )
    ev_c = EvidenceItem(
        evidence_id="EVID-004",
        title="知乎耳机论坛某网友拆机讨论",
        url="https://zhihu.com/question/123",
        source_level="C级 (垂直自媒体/论坛体验)",
        model_match="exact",
        excerpt="我拆开看感觉像是12mm振膜，挺大一个单元",
        evidence_direction="support",
    )
    result = cross_verifier.verify_single_claim(claim, [ev_c], target_earphones)
    assert result.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    assert result.verdict == "证据不足"


# =============================================================================
# 测试 5: 只有D级来源形成证据不足
# =============================================================================
def test_05_only_level_d_insufficient(target_earphones):
    claim = ClaimItem(
        claim_id=5,
        original_text="航空级钛合金机身材质",
        atomic_statement="机身采用钛合金材质",
        single_verifiable_fact="机身采用钛合金",
        category="材料",
        verification_target="机身材质",
    )
    ev_d = EvidenceItem(
        evidence_id="EVID-005",
        title="百家号营销推文：闭眼入爆款清单",
        url="https://baijiahao.baidu.com/article/999",
        source_level="D级 (电商买家评价/社交线索)",
        model_match="exact",
        excerpt="琉璃X 钛合金质感拉满太香了买它不后悔",
        evidence_direction="support",
    )
    result = cross_verifier.verify_single_claim(claim, [ev_d], target_earphones)
    assert result.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    assert result.verdict == "证据不足"
    assert len(result.excluded_evidences) >= 1
    assert "D级" in result.excluded_evidences[0]["exclusion_reason"]


# =============================================================================
# 测试 6: 搜索未配置不得生成实时网络核验结论
# =============================================================================
def test_06_search_not_configured_no_realtime_claim(target_earphones, fake_provider):
    pipeline = VerificationPipeline()
    report, progress = pipeline.run_real_pipeline(
        service_mode="byok",
        input_type="text",
        source_input="弱水时砂 琉璃X 蓝牙耳机 降噪45dB",
        provider=fake_provider,
        search_provider_name="none",
        structured_evidences=[],
        manual_evidence_links="",
        manual_evidence_materials="",
    )
    assert report.search_status == "not_configured"
    for cr in report.claims_results:
        assert cr.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    assert "未配置网络搜索服务" in report.overall_summary or "未执行全网检索" in report.overall_summary


# =============================================================================
# 测试 7: mismatch证据被排除并保留原因
# =============================================================================
def test_07_mismatch_evidence_excluded(target_earphones):
    claim = ClaimItem(
        claim_id=1,
        original_text="支持45dB主动降噪",
        atomic_statement="降噪深度45dB",
        single_verifiable_fact="降噪45dB",
        category="参数",
        verification_target="降噪指标",
    )
    ev_mismatch = EvidenceItem(
        evidence_id="EVID-MIS-01",
        title="弱水时砂 琉璃SE 青春版参数表",
        url="https://rosemusic.cn/specs/liuli_se",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="mismatch",
        excerpt="弱水时砂 琉璃SE 青春版入门耳机仅支持30dB单馈降噪",
        evidence_direction="contradict",
    )
    result = cross_verifier.verify_single_claim(claim, [ev_mismatch], target_earphones)
    assert result.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    assert len(result.excluded_evidences) == 1
    assert result.excluded_evidences[0]["evidence_id"] == "EVID-MIS-01"
    assert result.excluded_evidences[0]["model_match"] == "mismatch"


# =============================================================================
# 测试 8: series_only不能形成高置信强结论
# =============================================================================
def test_08_series_only_cannot_yield_strong_verdict(target_earphones):
    claim = ClaimItem(
        claim_id=1,
        original_text="支持45dB主动降噪",
        atomic_statement="降噪深度45dB",
        single_verifiable_fact="降噪45dB",
        category="参数",
        verification_target="降噪指标",
    )
    ev_series = EvidenceItem(
        evidence_id="EVID-SERIES-01",
        title="弱水时砂 琉璃系列 声学技术说明",
        url="https://rosemusic.cn/series/liuli",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="series_only",
        excerpt="弱水时砂 琉璃系列耳机全线搭载主动降噪技术",
        evidence_direction="support",
    )
    result = cross_verifier.verify_single_claim(claim, [ev_series], target_earphones)
    # 依据规则 8，series_only 无法单独支撑强结论
    assert result.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    assert result.confidence_score <= 65.0


# =============================================================================
# 测试 9: 未提及不能判定为不支持
# =============================================================================
def test_09_unreferenced_not_treated_as_contradict(target_earphones):
    claim = ClaimItem(
        claim_id=1,
        original_text="支持太空舱微循环抗辐射技术",
        atomic_statement="具备抗辐射微循环技术",
        single_verifiable_fact="抗辐射微循环技术",
        category="功能",
        verification_target="抗辐射功能",
    )
    # 传入空证据
    result = cross_verifier.verify_single_claim(claim, [], target_earphones)
    assert result.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    assert result.verdict == "证据不足"
    assert "虚假宣传" not in result.analysis_reason
    assert "商业欺诈" not in result.analysis_reason


# =============================================================================
# 测试 10: 重复转载只算一个独立来源
# =============================================================================
def test_10_duplicate_reposts_counted_as_one_independent_source(target_earphones):
    claim = ClaimItem(
        claim_id=1,
        original_text="支持45dB主动降噪",
        atomic_statement="主动降噪深度45dB",
        single_verifiable_fact="主动降噪45dB",
        category="参数",
        verification_target="降噪深度",
    )
    ev1 = EvidenceItem(
        evidence_id="EVID-ORIG-01",
        title="科技新声评测室：弱水时砂琉璃X深度实测报告",
        url="https://tech-audio.com/review/liulix",
        source_level="B级 (权威实验室/科技媒体评测)",
        model_match="exact",
        excerpt="经过人工耳专业实验室仪器测试，弱水时砂琉璃X在500Hz频段最大降噪深度达到45.1dB，综合消噪表现优异。",
        evidence_direction="support",
    )
    # 相同正文转载到其他站点
    ev2 = EvidenceItem(
        evidence_id="EVID-REPOST-02",
        title="数码快讯转载：弱水时砂琉璃X实测",
        url="https://repost-news.com/article/777",
        source_level="B级 (权威实验室/科技媒体评测)",
        model_match="exact",
        excerpt="经过人工耳专业实验室仪器测试，弱水时砂琉璃X在500Hz频段最大降噪深度达到45.1dB，综合消噪表现优异。",
        evidence_direction="support",
    )
    valid_evs, _, stats = evidence_validator.validate_and_deduplicate(claim, [ev1, ev2], target_earphones)
    assert len(valid_evs) == 2
    assert stats["valid_count"] == 2
    # 独立来源数必须为 1
    assert stats["independent_count"] == 1
    assert valid_evs[1].is_independent_source is False
    assert valid_evs[1].duplicate_of_evidence_id == "EVID-ORIG-01"


# =============================================================================
# 测试 11: C级评论不能单独证明技术参数
# =============================================================================
def test_11_level_c_cannot_prove_specs_alone(target_earphones):
    claim = ClaimItem(
        claim_id=1,
        original_text="支持65W极速闪充",
        atomic_statement="充电功率支持65W",
        single_verifiable_fact="支持65W快充",
        category="参数",
        verification_target="充电功率",
    )
    ev_c = EvidenceItem(
        evidence_id="EVID-C-01",
        title="贴吧吧友实测讨论",
        url="https://tieba.baidu.com/p/123",
        source_level="C级 (垂直自媒体/论坛体验)",
        model_match="exact",
        excerpt="我用原装线插上，看着屏幕提示像是65W快充",
        evidence_direction="support",
    )
    result = cross_verifier.verify_single_claim(claim, [ev_c], target_earphones)
    assert result.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE


# =============================================================================
# 测试 12: A级与B级互相印证提高置信度
# =============================================================================
def test_12_level_a_and_b_cross_corroboration(target_earphones):
    claim = ClaimItem(
        claim_id=1,
        original_text="支持45dB主动降噪",
        atomic_statement="降噪深度45dB",
        single_verifiable_fact="降噪深度45dB",
        category="参数",
        verification_target="降噪深度",
    )
    ev_a = EvidenceItem(
        evidence_id="EVID-A-01",
        title="弱水时砂 琉璃X 官方规格手册",
        url="https://rosemusic.cn/specs",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="弱水时砂 琉璃X 官方标称最大降噪深度为45dB，通过中国计量院认证",
        evidence_direction="support",
    )
    ev_b = EvidenceItem(
        evidence_id="EVID-B-01",
        title="RTINGS中国实验室独立横评：弱水时砂 琉璃X实测",
        url="https://rtings.com/headphones/liulix",
        source_level="B级 (权威实验室/科技媒体评测)",
        model_match="exact",
        excerpt="实验室仿真人工耳仪器测得弱水时砂琉璃X最大降噪深度为44.8dB，与官方标称高度吻合",
        evidence_direction="support",
    )
    result_single = cross_verifier.verify_single_claim(claim, [ev_a], target_earphones)
    result_both = cross_verifier.verify_single_claim(claim, [ev_a, ev_b], target_earphones)
    assert result_both.confidence_score >= result_single.confidence_score
    assert result_both.independent_source_count == 2
    assert result_both.verdict == "有证据支持"


# =============================================================================
# 测试 13: A级证据互相冲突触发人工复核
# =============================================================================
def test_13_conflicting_level_a_triggers_human_review(target_earphones):
    claim = ClaimItem(
        claim_id=1,
        original_text="支持45dB主动降噪",
        atomic_statement="降噪深度45dB",
        single_verifiable_fact="降噪深度45dB",
        category="参数",
        verification_target="降噪深度",
    )
    ev_a1 = EvidenceItem(
        evidence_id="EVID-A-01",
        title="弱水时砂 琉璃X 官方早期批次规格",
        url="https://rosemusic.cn/specs/v1",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="根据官方产品批次规格白皮书记载，弱水时砂 琉璃X 双馈主动降噪深度最高可达45dB。",
        evidence_direction="support",
    )
    ev_a2 = EvidenceItem(
        evidence_id="EVID-A-02",
        title="弱水时砂 琉璃X 官方最新说明书修订版",
        url="https://rosemusic.cn/manual/v2.pdf",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="因后续物料芯片供应调整，弱水时砂 琉璃X 最新批次硬件降噪上限调整为38dB，不支持45dB。",
        evidence_direction="contradict",
    )
    result = cross_verifier.verify_single_claim(claim, [ev_a1, ev_a2], target_earphones)
    assert result.needs_manual_review is True
    assert "A级" in result.review_reason or "冲突" in result.review_reason


# =============================================================================
# 测试 14: 地区版本不一致触发人工复核
# =============================================================================
def test_14_regional_version_discrepancy_triggers_human_review(target_earphones):
    claim = ClaimItem(
        claim_id=1,
        original_text="支持eSIM虚拟SIM卡功能",
        atomic_statement="具备eSIM功能",
        single_verifiable_fact="支持eSIM功能",
        category="功能",
        verification_target="eSIM网络",
    )
    ev_us = EvidenceItem(
        evidence_id="EVID-US-01",
        title="弱水时砂 琉璃X 美版产品说明书",
        url="https://rosemusic.com/us/specs",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="probable",
        excerpt="弱水时砂 琉璃X 美版支持北美运营商eSIM蜂窝数据通信协议与网络接入服务。",
        evidence_direction="support",
    )
    result = cross_verifier.verify_single_claim(claim, [ev_us], target_earphones)
    assert result.needs_manual_review is True
    assert "版本" in result.review_reason or "国行" in result.review_reason or "海外" in result.review_reason


# =============================================================================
# 测试 15: 理由相似度超过0.85触发重写
# =============================================================================
def test_15_reason_similarity_above_threshold_triggers_rewrite(target_earphones):
    c1 = ClaimItem(
        claim_id=1,
        original_text="支持45dB降噪",
        atomic_statement="降噪45dB",
        single_verifiable_fact="降噪45dB",
        category="参数",
        verification_target="降噪指标",
    )
    c2 = ClaimItem(
        claim_id=2,
        original_text="整机35小时续航",
        atomic_statement="续航35小时",
        single_verifiable_fact="续航35小时",
        category="性能",
        verification_target="续航时间",
    )
    # 模拟两份完全相同的模板理由
    identical_reason = "【核验目标】本项针对宣传声明开展多源核验。经核验未发现同型号有效证据，依据规则判定为证据不足。"
    r1 = ClaimVerificationResult(
        claim=c1,
        conclusion=VerificationConclusionEnum.INSUFFICIENT_EVIDENCE,
        analysis_reason=identical_reason,
        confidence=0.5,
    )
    r2 = ClaimVerificationResult(
        claim=c2,
        conclusion=VerificationConclusionEnum.INSUFFICIENT_EVIDENCE,
        analysis_reason=identical_reason,
        confidence=0.5,
    )
    results, has_warning = reason_generator.check_and_differentiate_reasons([r1, r2], target_earphones, similarity_threshold=0.85)
    assert has_warning is True
    # 经过差异化重写后，r2 与 r1 理由不再雷同
    assert r1.analysis_reason != results[1].analysis_reason
    assert "差异化核验明细" in results[1].analysis_reason or "#2" in results[1].analysis_reason


# =============================================================================
# 测试 16: 重写次数不会无限增加
# =============================================================================
def test_16_rewrite_loop_bounded(target_earphones):
    c1 = ClaimItem(claim_id=1, original_text="A", atomic_statement="A", single_verifiable_fact="A", category="参数", verification_target="A")
    c2 = ClaimItem(claim_id=2, original_text="B", atomic_statement="B", single_verifiable_fact="B", category="参数", verification_target="B")
    r1 = ClaimVerificationResult(claim=c1, conclusion=VerificationConclusionEnum.INSUFFICIENT_EVIDENCE, analysis_reason="模板文字", confidence=0.5)
    r2 = ClaimVerificationResult(claim=c2, conclusion=VerificationConclusionEnum.INSUFFICIENT_EVIDENCE, analysis_reason="模板文字", confidence=0.5)
    
    # 执行一次差异化
    results, _ = reason_generator.check_and_differentiate_reasons([r1, r2], target_earphones, similarity_threshold=0.85)
    # 再次调用，检查不会抛出 RecursionError 或引发死循环
    results2, _ = reason_generator.check_and_differentiate_reasons(results, target_earphones, similarity_threshold=0.85)
    assert len(results2) == 2


# =============================================================================
# 测试 17: 自检能够发现不存在的evidence_id
# =============================================================================
def test_17_self_check_detects_nonexistent_evidence_id():
    claim = ClaimItem(claim_id=1, original_text="测试", atomic_statement="测试", single_verifiable_fact="测试", category="参数", verification_target="测试")
    ev = EvidenceItem(evidence_id="EVID-101", title="真证据", source_level="A级", model_match="exact", excerpt="真证据内容")
    hallucinated_reason = "依据证据 EVID-999 记载，该功能完全成立。"
    report = fact_self_checker.audit_verification(
        claim=claim,
        conclusion=VerificationConclusionEnum.SUPPORTED,
        evidences=[ev],
        reason=hallucinated_reason,
        confidence=0.9,
    )
    assert any("EVID-999" in issue for issue in report.issues)
    assert "EVID-999" not in report.final_reason


# =============================================================================
# 测试 18: 自检能够发现引用片段不在正文中
# =============================================================================
def test_18_self_check_detects_unmatched_quote():
    claim = ClaimItem(claim_id=1, original_text="测试", atomic_statement="测试", single_verifiable_fact="测试", category="参数", verification_target="测试")
    ev = EvidenceItem(evidence_id="EVID-101", title="真证据", source_level="A级", model_match="exact", excerpt="正文中只有普通文字说明")
    hallucinated_quote_reason = "官方白皮书明确写道：“独家黑科技无损极速秒充”，因此完全支持。"
    report = fact_self_checker.audit_verification(
        claim=claim,
        conclusion=VerificationConclusionEnum.SUPPORTED,
        evidences=[ev],
        reason=hallucinated_quote_reason,
        confidence=0.9,
    )
    assert any("独家黑科技无损极速秒充" in issue for issue in report.issues)


# =============================================================================
# 测试 19: 自检能够纠正过度绝对化结论
# =============================================================================
def test_19_self_check_softens_absolute_assertions():
    claim = ClaimItem(claim_id=1, original_text="测试", atomic_statement="测试", single_verifiable_fact="测试", category="参数", verification_target="测试")
    ev = EvidenceItem(evidence_id="EVID-101", title="真证据", source_level="A级", model_match="exact", excerpt="实测数据不一致")
    harsh_reason = "该参数完全虚假，且商品绝对无用，商家存在欺诈。"
    report = fact_self_checker.audit_verification(
        claim=claim,
        conclusion=VerificationConclusionEnum.CONFLICT,
        evidences=[ev],
        reason=harsh_reason,
        confidence=0.95,
    )
    assert "完全虚假" not in report.final_reason
    assert "绝对无用" not in report.final_reason
    assert "欺诈" not in report.final_reason


# =============================================================================
# 测试 20: 证据不足不会被表述为虚假
# =============================================================================
def test_20_insufficient_evidence_never_labeled_fake(target_earphones):
    claim = ClaimItem(claim_id=1, original_text="宣称1", atomic_statement="宣称1", single_verifiable_fact="宣称1", category="参数", verification_target="目标")
    result = cross_verifier.verify_single_claim(claim, [], target_earphones)
    assert result.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    assert "假" not in result.analysis_reason or "绝不代表造假" in result.analysis_reason or "不足以形成" in result.analysis_reason
    assert "虚假宣传" not in result.analysis_reason


# =============================================================================
# 测试 21: 报告包含真实来源URL
# =============================================================================
def test_21_report_contains_real_source_urls(target_earphones):
    prod = ProductIdentity(brand="弱水时砂", model="琉璃X")
    claim = ClaimItem(claim_id=1, original_text="降噪45dB", atomic_statement="降噪45dB", single_verifiable_fact="降噪45dB", category="参数", verification_target="降噪")
    ev = EvidenceItem(
        evidence_id="EVID-REAL-01",
        title="弱水时砂 琉璃X 官方说明书",
        url="https://rosemusic.cn/real_manual.pdf",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="弱水时砂 琉璃X 在标准测试环境下支持最大降噪深度45dB，数据来源于官方声学实验室。",
        evidence_direction="support",
    )
    cr = cross_verifier.verify_single_claim(claim, [ev], target_earphones)
    report = cross_verifier.generate_full_report(prod, [cr], service_mode="byok", is_mock=False)
    assert report.claims_results[0].evidences[0].url == "https://rosemusic.cn/real_manual.pdf"


# =============================================================================
# 测试 22: 报告不包含API Key
# =============================================================================
def test_22_report_contains_no_api_key(target_earphones):
    prod = ProductIdentity(brand="弱水时砂", model="琉璃X")
    claim = ClaimItem(claim_id=1, original_text="降噪45dB", atomic_statement="降噪45dB", single_verifiable_fact="降噪45dB", category="参数", verification_target="降噪")
    cr = cross_verifier.verify_single_claim(claim, [], target_earphones)
    report = cross_verifier.generate_full_report(prod, [cr], service_mode="byok", is_mock=False)
    report_json = report.model_dump_json()
    assert "sk-" not in report_json
    assert "tvly-" not in report_json


# =============================================================================
# 测试 23: 报告不包含Cookie
# =============================================================================
def test_23_report_contains_no_cookie(target_earphones):
    prod = ProductIdentity(brand="弱水时砂", model="琉璃X")
    claim = ClaimItem(claim_id=1, original_text="降噪45dB", atomic_statement="降噪45dB", single_verifiable_fact="降噪45dB", category="参数", verification_target="降噪")
    cr = cross_verifier.verify_single_claim(claim, [], target_earphones)
    report = cross_verifier.generate_full_report(prod, [cr], service_mode="byok", is_mock=False)
    report_json = report.model_dump_json()
    assert "Set-Cookie" not in report_json
    assert "cookie=" not in report_json.lower()


# =============================================================================
# 测试 24: 报告不包含Authorization Header
# =============================================================================
def test_24_report_contains_no_auth_header(target_earphones):
    prod = ProductIdentity(brand="弱水时砂", model="琉璃X")
    claim = ClaimItem(claim_id=1, original_text="降噪45dB", atomic_statement="降噪45dB", single_verifiable_fact="降噪45dB", category="参数", verification_target="降噪")
    cr = cross_verifier.verify_single_claim(claim, [], target_earphones)
    report = cross_verifier.generate_full_report(prod, [cr], service_mode="byok", is_mock=False)
    report_json = report.model_dump_json()
    assert "Bearer " not in report_json
    assert "authorization:" not in report_json.lower()


# =============================================================================
# 测试 25: Mock结果不能进入真实报告
# =============================================================================
def test_25_mock_results_cannot_enter_real_report(target_earphones, fake_provider):
    pipeline = VerificationPipeline()
    report, _ = pipeline.run_real_pipeline(
        service_mode="byok",
        input_type="text",
        source_input="弱水时砂 琉璃X 降噪45dB",
        provider=fake_provider,
    )
    assert report.is_mock is False
    assert "MOCK" not in report.report_id


# =============================================================================
# 测试 26: 人工复核原因正确显示
# =============================================================================
def test_26_human_review_reason_displayed(target_earphones):
    claim = ClaimItem(claim_id=1, original_text="宣称", atomic_statement="宣称", single_verifiable_fact="宣称", category="参数", verification_target="目标")
    ev_prob = EvidenceItem(
        evidence_id="E01",
        title="弱水时砂 琉璃X 日版官方说明书",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="probable",
        excerpt="弱水时砂 琉璃X 日版产品面向日本市场发售，由于无线电频段法规差异，蓝牙功率及配套耳帽与国行版有所区别。",
    )
    result = cross_verifier.verify_single_claim(claim, [ev_prob], target_earphones)
    assert result.needs_manual_review is True
    assert len(result.review_reason) > 0


# =============================================================================
# 测试 27: 总体统计与逐项结论一致
# =============================================================================
def test_27_overall_summary_matches_itemized_verdicts(target_earphones):
    prod = ProductIdentity(brand="弱水时砂", model="琉璃X")
    c1 = ClaimItem(claim_id=1, original_text="降噪45dB", atomic_statement="降噪45dB", single_verifiable_fact="降噪45dB", category="参数", verification_target="降噪")
    c2 = ClaimItem(claim_id=2, original_text="续航35h", atomic_statement="续航35h", single_verifiable_fact="续航35h", category="性能", verification_target="续航")
    ev1 = EvidenceItem(
        evidence_id="E01",
        title="弱水时砂 琉璃X 官方技术白皮书",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="弱水时砂 琉璃X 官方标称双馈主动降噪深度实测可达45.1dB，符合高品质降噪标准。",
        evidence_direction="support",
    )
    cr1 = cross_verifier.verify_single_claim(c1, [ev1], target_earphones)
    cr2 = cross_verifier.verify_single_claim(c2, [], target_earphones)
    
    report = cross_verifier.generate_full_report(prod, [cr1, cr2], service_mode="byok", is_mock=False)
    assert report.conclusion_summary["有证据支持"] == 1
    assert report.conclusion_summary["证据不足"] == 1
    assert "有证据支持 1 项" in report.overall_summary
    assert "证据不足 1 项" in report.overall_summary


# =============================================================================
# 测试 28: confidence_score始终在0至100
# =============================================================================
def test_28_confidence_score_strictly_between_0_and_100(target_earphones):
    c = ClaimItem(claim_id=1, original_text="降噪45dB", atomic_statement="降噪45dB", single_verifiable_fact="降噪45dB", category="参数", verification_target="降噪")
    for ev_list in [[], [EvidenceItem(evidence_id="E1", title="A", source_level="A级", model_match="exact", excerpt="降噪45dB")]]:
        res = cross_verifier.verify_single_claim(c, ev_list, target_earphones)
        assert 0.0 <= res.confidence_score <= 100.0


# =============================================================================
# 测试 29: 四级结论之外的值被拒绝
# =============================================================================
def test_29_verdict_strictly_one_of_four_levels(target_earphones):
    c = ClaimItem(claim_id=1, original_text="降噪45dB", atomic_statement="降噪45dB", single_verifiable_fact="降噪45dB", category="参数", verification_target="降噪")
    res = cross_verifier.verify_single_claim(c, [], target_earphones)
    allowed_verdicts = {"有证据支持", "部分支持", "存在冲突", "证据不足"}
    assert res.verdict in allowed_verdicts
    assert res.conclusion.value in allowed_verdicts


# =============================================================================
# 测试 30: 同一报告中每条声明理由具有证据差异
# =============================================================================
def test_30_different_claims_have_differentiated_reasons(target_earphones):
    prod = ProductIdentity(brand="弱水时砂", model="琉璃X")
    c1 = ClaimItem(claim_id=1, original_text="支持45dB主动降噪", atomic_statement="降噪45dB", single_verifiable_fact="降噪45dB", category="参数", verification_target="降噪指标")
    c2 = ClaimItem(claim_id=2, original_text="整机35小时综合续航", atomic_statement="续航35小时", single_verifiable_fact="续航35小时", category="性能", verification_target="续航指标")
    
    ev1 = EvidenceItem(evidence_id="E01", title="官方规格表", source_level="A级", model_match="exact", excerpt="45dB双馈降噪", evidence_direction="support")
    ev2 = EvidenceItem(evidence_id="E02", title="说明书", source_level="A级", model_match="exact", excerpt="仅在关降噪可达35小时", evidence_direction="partial")
    
    cr1 = cross_verifier.verify_single_claim(c1, [ev1], target_earphones)
    cr2 = cross_verifier.verify_single_claim(c2, [ev2], target_earphones)
    
    report = cross_verifier.generate_full_report(prod, [cr1, cr2], service_mode="byok", is_mock=False)
    assert report.claims_results[0].analysis_reason != report.claims_results[1].analysis_reason
    assert "45dB" in report.claims_results[0].analysis_reason
    assert "35小时" in report.claims_results[1].analysis_reason
