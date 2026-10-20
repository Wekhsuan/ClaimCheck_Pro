"""ClaimCheck Pro 阶段5自动化测试套件 (Stage 5 Verification & Fact Check Tests)

覆盖范围：
1. 声明原子化拆解 (单次最多5条，单一可验证事实，主观夸张词过滤)
2. 证据来源 A/B/C/D 四级分类
3. 规则 4: D级不得用于强结论
4. 规则 5: C级不得单独证明技术参数
5. 证据 8 项记录规范 (title, url, source_type, source_level, published_at, model_match, excerpt, evidence_direction)
6. 四维型号对齐核验 (品牌、型号、版本、地区)
7. 四级核验结论判定 (T06: 支持/部分支持; T07: 冲突/证据不足)
8. 二次事实自检四项铁律与结论纠偏
9. 法律中立性词汇过滤 (拒绝"欺诈"、"造假"等违法定性)
10. 无搜索API时的行为 (支持手动链接与材料，绝不伪造虚假搜索)
11. 总体综合摘要、人工确认项与购买前建议生成
"""

import os
import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from streamlit_app.schemas import (
    ClaimItem,
    EvidenceItem,
    ProductIdentity,
    SourceLevelEnum,
    VerificationConclusionEnum,
    VerificationReport,
)
from src.verifier.claim_decomposer import ClaimDecomposer
from src.verifier.evidence_classifier import evidence_classifier
from src.verifier.model_alignment import model_alignment_verifier
from src.verifier.fact_checker import fact_self_checker, sanitize_legal_phrasing
from src.verifier.cross_verifier import cross_verifier
from src.search.search_adapter import SearchAdapter, SearchConfig
from streamlit_app.report import ReportGenerator


# =============================================================================
# 1. 声明拆解测试 (最多5条，单一事实，过滤主观废话)
# =============================================================================
def test_claim_decomposer_max_5_and_single_fact():
    decomposer = ClaimDecomposer(max_claims=5)
    
    # 模拟包含 8 条复杂声明与情绪化夸赞的文案
    raw_marketing = """
    遥遥领先！声学极客 SoundPro X1 震撼登场！
    1. 最大主动降噪深度高达48dB，智能自适应消除环境嘈杂低频轰鸣；
    2. 全链路支持LHDC 5.0超高清音频传输，且获得日本JAS Hi-Res Wireless金标认证；
    3. 配合充电仓实现最长40小时综合续航，单次连续听歌9小时；
    4. 采用轻量化航空级铝合金机身，单耳重量仅4.2g极致轻盈；
    5. 支持IPX5生活级防水防汗，运动佩戴无惧雨水；
    6. 搭载蓝牙5.3旗舰芯片，延迟低至35ms；
    7. 绝绝子！年度机皇买它就对了！
    8. 配备定制11mm类钻石振膜，低音震撼澎湃。
    """
    
    claims = decomposer.decompose(raw_marketing)
    
    # 严格检验 1: 单次最多处理 5 条声明
    assert len(claims) <= 5
    assert len(claims) >= 3
    
    # 严格检验 2: 每条声明必须包含 single_verifiable_fact
    for c in claims:
        assert c.single_verifiable_fact, f"声明 {c.claim_id} 缺少单一可验证事实"
        assert c.atomic_statement
        assert c.category in ["参数", "功能", "性能", "材料", "兼容性", "使用条件", "明确体验承诺", "规格参数", "核心功能", "实测性能", "用户体验"]
        # 严格检验 3: 情绪化夸赞词必须被剔除
        for fluff in ["遥遥领先", "震撼登场", "绝绝子", "买它就对了"]:
            assert fluff not in c.atomic_statement
            assert fluff not in c.single_verifiable_fact


# =============================================================================
# 2. 证据来源分级与规则4、规则5测试
# =============================================================================
def test_evidence_classification_and_rules():
    # A级：官方说明书/国标认证
    lvl_a, type_a = evidence_classifier.classify_source(
        title="华为官方规格技术白皮书 (FreeBuds Pro Spec)",
        url="https://consumer.huawei.com/specs",
        excerpt="依据GB/T 12060.7国家标准，最大降噪深度为48dB"
    )
    assert lvl_a.startswith("A级")
    
    # B级：专业实验室实测
    lvl_b, type_b = evidence_classifier.classify_source(
        title="先看评测 降噪深度实验室横评报告",
        url="https://www.xiankan.com/review/123",
        excerpt="人工耳仿真测试显示降噪深度达到47.5dB"
    )
    assert lvl_b.startswith("B级")
    
    # C级：社区论坛真实体验
    lvl_c, type_c = evidence_classifier.classify_source(
        title="知乎耳机圈真实佩戴感受分享",
        url="https://www.zhihu.com/question/50123/answer/99",
        excerpt="日常坐地铁佩戴很舒服，风噪控制一般"
    )
    assert lvl_c.startswith("C级")
    
    # D级：自媒体营销号与无出处软文
    lvl_d, type_d = evidence_classifier.classify_source(
        title="百家号：年度最香爆款清单吐血整理",
        url="https://baijiahao.baidu.com/s?id=123",
        excerpt="种草推荐！型号不明但是超级好用买它不后悔"
    )
    assert lvl_d.startswith("D级")
    
    # 规则 4: D级来源不得用于强结论
    d_ev = EvidenceItem(
        evidence_id="D01",
        title="百家号爆款清单",
        url="https://baijiahao.baidu.com",
        source_level="D级 (电商买家评价/社交线索)",
        excerpt="据说支持48dB降噪"
    )
    assert not evidence_classifier.is_allowed_for_strong_conclusion(d_ev)
    
    # 规则 5: C级来源只用于体验趋势，不得单独证明技术参数
    c_ev = EvidenceItem(
        evidence_id="C01",
        title="贴吧用户体验贴",
        url="https://tieba.baidu.com",
        source_level="C级 (垂直自媒体/论坛体验)",
        excerpt="实测感觉降噪挺猛的"
    )
    assert not evidence_classifier.can_prove_technical_parameter(c_ev, claim_category="规格参数")
    assert not evidence_classifier.can_prove_technical_parameter(c_ev, claim_category="实测性能")
    assert evidence_classifier.can_prove_technical_parameter(c_ev, claim_category="用户体验")


# =============================================================================
# 3. 证据 8 项记录规范与兼容性测试
# =============================================================================
def test_evidence_8_field_specification():
    ev = EvidenceItem(
        evidence_id="EVID-001",
        title="国家无线电及声学质检检测报告",
        url="https://cqc.com.cn/report/9981",
        source_type="国家级质检报告",
        source_level="A级 (官方资料/说明书/国标质检)",
        published_at="2024-05-10",
        model_match="exact",
        excerpt="依据GB/T标准实测最大深度为48.2dB",
        evidence_direction="support",
    )
    
    # 验证 8 项规范字段完整存在
    assert ev.title == "国家无线电及声学质检检测报告"
    assert ev.url == "https://cqc.com.cn/report/9981"
    assert ev.source_type == "国家级质检报告"
    assert "A级" in ev.source_level
    assert ev.published_at == "2024-05-10"
    assert ev.model_match == "exact"
    assert "48.2dB" in ev.excerpt
    assert ev.evidence_direction == "support"
    
    # 验证向后兼容字段映射
    legacy_ev = EvidenceItem(
        evidence_id="LEG-01",
        source_title="旧版数据标题",
        source_url="https://example.com/legacy",
        source_level="B级",
        snippet="旧版数据摘要",
        published_date="2024-01-01",
        model_matched=True,
    )
    assert legacy_ev.title == "旧版数据标题"
    assert legacy_ev.url == "https://example.com/legacy"
    assert legacy_ev.excerpt == "旧版数据摘要"
    assert legacy_ev.published_at == "2024-01-01"
    assert legacy_ev.model_match == "exact"
    assert legacy_ev.evidence_direction == "support"


# =============================================================================
# 4. 型号对齐核验 (品牌、型号、版本、地区)
# =============================================================================
def test_model_alignment_four_dimensions():
    target = {
        "brand": "声学极客",
        "model": "SoundPro X1",
        "variant": "降噪旗舰版",
        "region": "中国大陆",
    }
    
    # 4.1 严格同型号对齐
    res_exact = model_alignment_verifier.verify_alignment(
        target_product=target,
        evidence_text="声学极客 SoundPro X1 降噪旗舰版 (国行版) 官方白皮书",
        evidence_title="SoundPro X1 规格说明",
    )
    assert res_exact.is_aligned is True
    assert res_exact.model_match == "exact"
    
    # 4.2 异型号 (低配青春版套用旗舰版宣传)
    res_mismatch = model_alignment_verifier.verify_alignment(
        target_product=target,
        evidence_text="声学极客 SoundPro SE 青春版仅支持35dB降噪",
        evidence_title="SoundPro SE 参数",
    )
    assert res_mismatch.model_match == "mismatch"
    assert res_mismatch.is_aligned is False
    assert "冲突" in res_mismatch.alignment_notes or "不符" in res_mismatch.alignment_notes or res_mismatch.confidence_penalty > 0


# =============================================================================
# 5. 四级核验结论与二次事实自检测试 (覆盖 T06、T07)
# =============================================================================
def test_cross_verifier_conclusions_and_self_check():
    target_prod = {
        "brand": "声学极客",
        "model": "SoundPro X1",
        "variant": "标准版",
        "region": "中国大陆",
    }
    
    # -------------------------------------------------------------------------
    # 测试 T06A: 【有证据支持】——同型号A级官方规格完全支持
    # -------------------------------------------------------------------------
    claim_supported = ClaimItem(
        claim_id=1,
        original_text="深度降噪高达48dB",
        atomic_statement="降噪深度达到48dB",
        single_verifiable_fact="降噪深度48dB",
        category="规格参数",
        verification_target="降噪深度",
    )
    ev_a = EvidenceItem(
        evidence_id="E01",
        title="声学极客 SoundPro X1 官方技术白皮书",
        url="https://soundgeek.cn/specs",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="依据国家标准测试，SoundPro X1 最大降噪深度为48.2dB",
        evidence_direction="support",
    )
    res_s = cross_verifier.verify_single_claim(claim_supported, [ev_a], target_prod)
    assert res_s.conclusion == VerificationConclusionEnum.SUPPORTED
    assert res_s.confidence >= 0.90
    assert res_s.self_check_passed is True

    # -------------------------------------------------------------------------
    # 测试 T06B: 【部分支持】——核心宣称成立，但省略前置条件
    # -------------------------------------------------------------------------
    claim_partial = ClaimItem(
        claim_id=2,
        original_text="支持40小时综合超长续航",
        atomic_statement="综合续航达到40小时",
        single_verifiable_fact="整机续航40小时",
        category="实测性能",
        verification_target="续航时间",
    )
    ev_partial = EvidenceItem(
        evidence_id="E02",
        title="SoundPro X1 用户手册",
        url="https://soundgeek.cn/manual.pdf",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="单次续航9小时，仅在关闭降噪且AAC编码50%音量特定条件下可达40小时综合续航",
        evidence_direction="partial",
    )
    res_p = cross_verifier.verify_single_claim(claim_partial, [ev_partial], target_prod)
    assert res_p.conclusion == VerificationConclusionEnum.PARTIALLY_SUPPORTED
    assert "省略" in res_p.analysis_reason or "条件" in res_p.analysis_reason

    # -------------------------------------------------------------------------
    # 测试 T07A: 【存在冲突】——宣传雷电4，但官方规格明确为普通 USB 3.2
    # -------------------------------------------------------------------------
    laptop_target = {
        "brand": "幻影",
        "model": "Pro 14",
        "variant": "2024款",
        "region": "中国大陆",
    }
    claim_conflict = ClaimItem(
        claim_id=3,
        original_text="配备满血雷电4接口支持40Gbps",
        atomic_statement="Type-C接口支持雷电4协议40Gbps",
        single_verifiable_fact="搭载雷电4(Thunderbolt 4)接口",
        category="规格参数",
        verification_target="雷电4接口协议",
    )
    ev_conflict_a = EvidenceItem(
        evidence_id="E03",
        title="幻影电脑官方技术支持页面 Pro 14 完整端口规格",
        url="https://phantom-tech.com/specs",
        source_level="A级 (官方资料/说明书/国标质检)",
        model_match="exact",
        excerpt="左侧Type-C为全功能USB 3.2 Gen2 (10Gbps)，不支持Thunderbolt或USB4",
        evidence_direction="contradict",
    )
    res_c = cross_verifier.verify_single_claim(claim_conflict, [ev_conflict_a], laptop_target)
    assert res_c.conclusion == VerificationConclusionEnum.CONFLICT
    assert res_c.confidence >= 0.90

    # -------------------------------------------------------------------------
    # 测试 T07B: 【证据不足】——自检铁律1：未提及不能判断为不支持
    # -------------------------------------------------------------------------
    claim_unknown = ClaimItem(
        claim_id=4,
        original_text="具备独家离子微循环护眼抗疲劳功能",
        atomic_statement="具备离子微循环抗疲劳效果",
        single_verifiable_fact="离子微循环护眼技术",
        category="核心功能",
        verification_target="护眼功效",
    )
    # 无证据输入
    res_u = cross_verifier.verify_single_claim(claim_unknown, [], laptop_target)
    assert res_u.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    assert "证据不足" in res_u.conclusion.value
    # 严禁臆测虚假宣传
    assert "商业欺诈" not in res_u.analysis_reason
    assert "虚假宣传" not in res_u.analysis_reason


# =============================================================================
# 6. 二次事实自检四项铁律纠偏机制专项测试
# =============================================================================
def test_fact_self_checker_four_rules_correction():
    claim = ClaimItem(
        claim_id=1,
        original_text="极速充电100W",
        atomic_statement="充电功率达到100W",
        single_verifiable_fact="100W快充",
        category="规格参数",
        verification_target="充电功率",
    )
    
    # 铁律 1: 无证据不能判定为冲突/不支持
    concl, conf, reason, passed, rules = fact_self_checker.audit_verification(
        claim=claim,
        conclusion=VerificationConclusionEnum.CONFLICT,
        evidences=[],
        reason="未找到100W证据，定性为假宣传",
        confidence=0.85,
    )
    assert concl == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    assert passed is False
    assert "未提及不能判断为不支持" in rules[0]
    
    # 铁律 2: 其他型号证据不能用于当前型号强结论
    other_model_ev = EvidenceItem(
        evidence_id="E99",
        title="Pro 14 青春版拆解",
        source_level="A级",
        model_match="mismatch",
        excerpt="青春版仅支持65W充电",
        evidence_direction="contradict",
    )
    concl2, conf2, reason2, passed2, rules2 = fact_self_checker.audit_verification(
        claim=claim,
        conclusion=VerificationConclusionEnum.CONFLICT,
        evidences=[other_model_ev],
        reason="青春版只有65W，所以当前型号冲突",
        confidence=0.90,
    )
    assert concl2 == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    assert conf2 <= 0.65
    assert passed2 is False
    
    # 铁律 3: 单个低可信来源不能支持高置信技术参数结论
    single_c_ev = EvidenceItem(
        evidence_id="E98",
        title="贴吧水友测速",
        source_level="C级 (垂直自媒体/论坛体验)",
        model_match="exact",
        excerpt="我插上感觉能充100W吧",
        evidence_direction="support",
    )
    concl3, conf3, reason3, passed3, rules3 = fact_self_checker.audit_verification(
        claim=claim,
        conclusion=VerificationConclusionEnum.SUPPORTED,
        evidences=[single_c_ev],
        reason="贴吧老哥说可以支持100W",
        confidence=0.95,
    )
    assert concl3 == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
    assert conf3 <= 0.65
    assert passed3 is False


# =============================================================================
# 7. 法律中立性词汇过滤测试 (杜绝"欺诈"、"造假"定性)
# =============================================================================
def test_legal_neutrality_sanitization():
    raw_text = "商家涉嫌严重商业欺诈与虚假宣传，属于劣质产品坑骗消费者，触犯广告法违法违规！"
    sanitized = sanitize_legal_phrasing(raw_text)
    
    # 确保激进法律定性词被净化为中立事实陈述
    assert "商业欺诈" not in sanitized
    assert "虚假宣传" not in sanitized
    assert "劣质产品" not in sanitized
    assert "坑骗" not in sanitized
    assert "违法违规" not in sanitized
    assert "存在事实出入" in sanitized or "存在差异" in sanitized


# =============================================================================
# 8. 无搜索API时的检索适配测试 (支持手动材料，不模拟假搜索)
# =============================================================================
def test_search_adapter_no_paid_api_and_no_hallucinations():
    adapter = SearchAdapter(SearchConfig())
    target = {"brand": "测试品牌", "model": "TestModel"}
    
    # 8.1 既无搜索API也无手动输入，返回空证据，模式为 none，不伪造实时结果
    res_empty = adapter.retrieve_evidence_for_claim(
        claim_id=1,
        claim_statement="支持48dB降噪",
        target_product=target,
        manual_links=[],
        user_provided_materials="",
    )
    assert len(res_empty.evidences) == 0
    assert res_empty.search_mode == "none"
    assert "绝不伪造虚假搜索" in res_empty.notes or "未配置搜索API" in res_empty.notes
    
    # 8.2 用户提供了官方参数文本材料，适配器从中提取
    materials = "官方规格手册记载：TestModel 最大支持48dB降噪深度，采用双馈主动降噪。"
    res_mat = adapter.retrieve_evidence_for_claim(
        claim_id=1,
        claim_statement="支持48dB降噪",
        target_product=target,
        user_provided_materials=materials,
    )
    assert len(res_mat.evidences) == 1
    assert res_mat.evidences[0].source_type == "用户输入材料"
    assert res_mat.search_mode == "user_materials"


# =============================================================================
# 9. 报告综合摘要、人工确认项与购买建议全要素输出测试
# =============================================================================
def test_full_report_generation_with_summary_and_advice():
    prod = ProductIdentity(
        brand="声学极客",
        model="SoundPro X1",
        version="旗舰版",
        sales_region="中国大陆",
        confidence=0.98,
    )
    claim = ClaimItem(
        claim_id=1,
        original_text="降噪48dB",
        atomic_statement="降噪48dB",
        single_verifiable_fact="降噪48dB",
        verification_target="降噪指标",
    )
    ev = EvidenceItem(
        evidence_id="E01",
        title="官方质检报告",
        url="https://example.com/test",
        source_type="国家级质检报告",
        source_level="A级 (官方资料/说明书/国标质检)",
        published_at="2024-05",
        model_match="exact",
        excerpt="实测48.2dB",
        evidence_direction="support",
    )
    cr = cross_verifier.verify_single_claim(claim, [ev], {"brand": "声学极客", "model": "SoundPro X1"})
    
    report = cross_verifier.generate_full_report(
        product=prod,
        claims_results=[cr],
        service_mode="mock",
        is_mock=True,
    )
    
    # 验证总体摘要存在
    assert report.overall_summary
    assert "声学极客" in report.overall_summary
    
    # 验证人工确认清单与购买建议
    assert len(report.human_verification_items) >= 2
    assert len(report.pre_purchase_advice) >= 2
    
    # 验证 Markdown 报告渲染完整覆盖
    md_output = ReportGenerator.generate_markdown(report)
    assert "## 一、商品身份确认" in md_output
    assert "## 二、总体综合摘要与四级结论统计" in md_output
    assert "单一可验证事实" in md_output
    assert "8项记录规范" in md_output
    assert "## 四、人工确认项与购买前建议" in md_output
    assert "免责声明" in md_output
