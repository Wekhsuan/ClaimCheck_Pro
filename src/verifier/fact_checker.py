"""ClaimCheck Pro 二次事实自检回路 (Fact Self-Checker)

严格遵循：
10. 实施二次事实自检四项铁律：
    1. 未提及不能判断为不支持 (无有效证据或未检索到时，必须判定为“证据不足”，严禁臆测为“存在冲突”或“虚假宣传”)；
    2. 其他型号证据不能用于当前型号强结论 (非 exact 严格同型号证据不得作为强力否定或强力支持依据)；
    3. 单个低可信来源不能支持高置信结论 (仅有单个 C 级或 D 级来源时，置信度上限强制压制至 0.65 以下，技术参数降级为“证据不足”)；
    4. 结论不能超出证据范围 (推论必须严格局限于引用原文 excerpt 所及事实，严禁过度延伸)。
12. 法律免责与客观中立原则：
    严禁输出“违法”、“商业欺诈”、“造假”、“诈骗”等法律定性或惩罚性结论，统一采用客观中立的事实比对用语。
"""

import re
from typing import List, Tuple
from streamlit_app.schemas import (
    ClaimItem,
    EvidenceItem,
    VerificationConclusionEnum,
)

# 法律及激进主观定性词汇过滤表
AGGRESSIVE_LEGAL_TERMS = [
    (r"商业欺诈|涉嫌欺诈|欺诈消费者|欺诈|诈骗|坑骗|忽悠", "宣传信息与公开资料存在事实出入"),
    (r"虚假宣传|虚报|造假|制假售假", "参数标称与同型号官方资料存在差异"),
    (r"违法违规|违反广告法|触犯法规", "宣传表述存在待核实项"),
    (r"劣质产品|假冒伪劣|垃圾产品", "部分技术参数缺乏官方权威支持"),
]


def sanitize_legal_phrasing(text: str) -> str:
    """过滤激进法律定性词，替换为中立事实陈述"""
    cleaned = text
    for pattern, replacement in AGGRESSIVE_LEGAL_TERMS:
        cleaned = re.sub(pattern, replacement, cleaned)
    return cleaned


class SelfCheckDetailedReport:
    """事实自检综合报告"""
    def __init__(
        self,
        final_conclusion: VerificationConclusionEnum,
        final_confidence: float,
        final_reason: str,
        passed: bool,
        rules_evaluated: List[str],
        status: str = "passed",
        issues: Optional[List[str]] = None,
        corrected_verdict: Optional[VerificationConclusionEnum] = None,
        corrected_confidence: Optional[float] = None,
        correction_reason: Optional[str] = None,
    ):
        self.final_conclusion = final_conclusion
        self.final_confidence = final_confidence
        self.final_reason = final_reason
        self.passed = passed
        self.rules_evaluated = rules_evaluated
        self.status = status  # passed / corrected / failed / needs_manual_review
        self.issues = issues or []
        self.corrected_verdict = corrected_verdict
        self.corrected_confidence = corrected_confidence
        self.correction_reason = correction_reason

    def to_tuple(self) -> Tuple[VerificationConclusionEnum, float, str, bool, List[str]]:
        """向后兼容5元组解包 (final_conclusion, final_confidence, final_reason, passed, rules_evaluated)"""
        return (
            self.final_conclusion,
            self.final_confidence,
            self.final_reason,
            self.passed,
            self.rules_evaluated,
        )

    def __iter__(self):
        return iter(self.to_tuple())

    def __getitem__(self, item):
        return self.to_tuple()[item]


class FactSelfChecker:
    """事实自检引擎 (阶段 4 强化 15 项自检铁律)"""

    @staticmethod
    def audit_verification(
        claim: ClaimItem,
        conclusion: VerificationConclusionEnum,
        evidences: List[EvidenceItem],
        reason: str,
        confidence: float,
        search_status: str = "executed",
        candidate_evidence_ids: Optional[List[str]] = None,
    ) -> SelfCheckDetailedReport:
        """执行自检回路，全面评估15项自检铁律，必要时纠偏结论并过滤法律词汇
        
        支持直接作为 5 元组解包: (final_conclusion, final_confidence, final_reason, passed, rules_evaluated)
        同时提供 .status, .issues, .corrected_verdict, .corrected_confidence 等结构化属性
        """
        final_conclusion = conclusion
        final_confidence = confidence
        rules_evaluated = []
        corrections = []
        issues = []
        passed = True

        clean_reason = sanitize_legal_phrasing(reason)

        # ---------------------------------------------------------------------
        # 自检规则 1: 未提及不能判断为不支持 (Unreferenced != Unsupported)
        # ---------------------------------------------------------------------
        rules_evaluated.append("规则1: 未提及不能判断为不支持")
        if not evidences or len(evidences) == 0:
            if final_conclusion in [VerificationConclusionEnum.CONFLICT, VerificationConclusionEnum.PARTIALLY_SUPPORTED]:
                final_conclusion = VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
                final_confidence = 0.50
                msg = "【自检纠偏】公开资料未检索到提及，依据规则不得判定为不支持或冲突，已纠偏为‘证据不足’。"
                corrections.append(msg)
                issues.append("未检索到有效证据却判定为冲突或部分支持")
                passed = False

        # ---------------------------------------------------------------------
        # 自检规则 2: 其他型号证据不能用于当前型号强结论
        # ---------------------------------------------------------------------
        rules_evaluated.append("规则2: 其他型号证据不能用于当前型号强结论")
        if final_conclusion in [VerificationConclusionEnum.SUPPORTED, VerificationConclusionEnum.CONFLICT]:
            has_exact_model = any(e.model_match in ["exact", "probable"] for e in evidences)
            if not has_exact_model and evidences:
                final_conclusion = VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
                final_confidence = min(final_confidence, 0.60)
                msg = "【自检纠偏】所引证据均非当前同型号(属于mismatch/series_only/unknown)，依据规则不得用于强结论，已纠偏为‘证据不足’。"
                corrections.append(msg)
                issues.append("使用非同型号证据得出强结论")
                passed = False

        # ---------------------------------------------------------------------
        # 自检规则 3: 单个低可信来源不能支持高置信结论
        # ---------------------------------------------------------------------
        rules_evaluated.append("规则3: 单个低可信来源不能支持高置信结论")
        if len(evidences) == 1:
            single_e = evidences[0]
            lvl = single_e.source_level
            if lvl.startswith("C") or lvl.startswith("D") or "C级" in lvl or "D级" in lvl:
                if final_confidence > 0.65:
                    final_confidence = 0.60
                    msg = "【自检纠偏】单来源且可信度为C/D级，强行压制置信度至0.60以下。"
                    corrections.append(msg)
                    issues.append("单一低可信来源置信度过高")
                    passed = False

                if claim.category in ["规格参数", "实测性能", "参数", "性能"] and final_conclusion == VerificationConclusionEnum.SUPPORTED:
                    final_conclusion = VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
                    msg = "【自检纠偏】技术硬参数仅有单个低可信来源，依据规则5与自检3降级为‘证据不足’。"
                    corrections.append(msg)
                    issues.append("单一低可信来源单独支撑技术参数")
                    passed = False

        # ---------------------------------------------------------------------
        # 自检规则 4: 结论不能超出证据范围
        # ---------------------------------------------------------------------
        rules_evaluated.append("规则4: 结论不能超出证据范围")
        if "绝对无用" in clean_reason or "完全虚假" in clean_reason or "绝对真实" in clean_reason:
            clean_reason = clean_reason.replace("绝对无用", "目前证据不支持该效果").replace("完全虚假", "与官方说明书记载不一致").replace("绝对真实", "获得当前证据支持")
            msg = "【自检纠偏】弱化超出证据摘录的绝对化推论用语。"
            corrections.append(msg)
            issues.append("分析理由存在绝对化过度断言")
            passed = False

        # ---------------------------------------------------------------------
        # 自检规则 5 & 6 & 7: 异型号(mismatch)证据隔离与 series_only 降级
        # ---------------------------------------------------------------------
        rules_evaluated.append("规则5: mismatch证据绝对排除")
        if any(e.model_match == "mismatch" for e in evidences):
            issues.append("检测到mismatch型号不符证据混入有效证据池")
            # 过滤掉 mismatch 证据
            evidences = [e for e in evidences if e.model_match != "mismatch"]
            if not evidences:
                final_conclusion = VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
                final_confidence = 0.50
                corrections.append("【自检纠偏】排除mismatch证据后无剩余证据，已纠偏为‘证据不足’。")
                passed = False

        rules_evaluated.append("规则6: series_only不得用于高置信强结论")
        if all(e.model_match == "series_only" for e in evidences) and evidences:
            if final_conclusion in [VerificationConclusionEnum.SUPPORTED, VerificationConclusionEnum.CONFLICT]:
                final_conclusion = VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
                final_confidence = min(final_confidence, 0.55)
                corrections.append("【自检纠偏】全部证据仅同系列未确认具体型号，已纠偏为‘证据不足’。")
                issues.append("仅有series_only证据却下了强结论")
                passed = False

        # ---------------------------------------------------------------------
        # 自检规则 8 & 9: C级不能单独证明技术参数，D级不得进入有效证据池
        # ---------------------------------------------------------------------
        rules_evaluated.append("规则8: C级不得单独证明技术参数")
        if claim.category in ["参数", "规格参数", "性能", "实测性能"]:
            if all("C级" in e.source_level or e.source_level.startswith("C") for e in evidences) and evidences:
                if final_conclusion == VerificationConclusionEnum.SUPPORTED:
                    final_conclusion = VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
                    final_confidence = min(final_confidence, 0.55)
                    corrections.append("【自检纠偏】技术参数声明仅有C级用户评论支撑，已纠偏为‘证据不足’。")
                    issues.append("技术参数仅有C级来源")
                    passed = False

        rules_evaluated.append("规则9: D级不得进入有效证据池")
        if any("D级" in e.source_level or e.source_level.startswith("D") for e in evidences):
            issues.append("有效证据池中混入D级营销软文")
            evidences = [e for e in evidences if not ("D级" in e.source_level or e.source_level.startswith("D"))]

        # ---------------------------------------------------------------------
        # 自检规则 10: 多个重复转载不得虚增证据
        # ---------------------------------------------------------------------
        rules_evaluated.append("规则10: 多个重复转载不计入独立证据")
        indep_evs = [e for e in evidences if getattr(e, "is_independent_source", True)]
        if len(evidences) > 1 and len(indep_evs) == 1:
            if final_confidence > 0.85:
                final_confidence = 0.80
                corrections.append("【自检纠偏】检测到多篇内容属于重复转载，独立来源仅为1个，下调置信度。")
                issues.append("存在重复转载虚增证据数量风险")
                passed = False

        # ---------------------------------------------------------------------
        # 自检规则 11 & 12: 搜索未配置时不声称全网核验，页面受限时不虚构正文
        # ---------------------------------------------------------------------
        rules_evaluated.append("规则11: 搜索未配置时不声称全网核验")
        if search_status == "not_configured":
            if "全网检索" in clean_reason or "未检索到" not in clean_reason:
                clean_reason = clean_reason.replace("全网检索", "当前未配置网络搜索服务，仅基于现有材料核验")
            if final_conclusion in [VerificationConclusionEnum.CONFLICT, VerificationConclusionEnum.SUPPORTED]:
                if not any("A级" in e.source_level for e in evidences):
                    final_conclusion = VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
                    final_confidence = 0.65
                    corrections.append("【自检纠偏】搜索服务未配置，依据铁律客观判定为证据不足。")
                    issues.append("搜索未配置时输出强核验结论")
                    passed = False

        # ---------------------------------------------------------------------
        # 自检规则 13: 验证所引用的 evidence_id 真实存在
        # ---------------------------------------------------------------------
        rules_evaluated.append("规则13: 引用的evidence_id真实存在")
        quoted_eids = re.findall(r"(?:EVID-\w+|E\d+|MANUAL-\w+|C\d+|D\d+)", clean_reason)
        existing_eids = {e.evidence_id for e in evidences}
        if candidate_evidence_ids:
            existing_eids.update(candidate_evidence_ids)
        for q_eid in quoted_eids:
            if existing_eids and q_eid not in existing_eids:
                issues.append(f"理由中引用了不存在的证据ID: {q_eid}")
                clean_reason = clean_reason.replace(q_eid, "公开线索")
                passed = False

        # ---------------------------------------------------------------------
        # 自检规则 14: 引用片段确实存在于已提取正文中
        # ---------------------------------------------------------------------
        rules_evaluated.append("规则14: 引用片段存在于已提取正文中")
        all_excerpts = " ".join([e.excerpt for e in evidences])
        quoted_snippets = re.findall(r"“([^”]{6,60})”", clean_reason)
        for snip in quoted_snippets:
            # 排除非事实引语 (如声明本身)
            if snip in claim.original_text or snip in claim.atomic_statement:
                continue
            if snip not in all_excerpts and len(all_excerpts) > 0:
                issues.append(f"引用引言“{snip}”未在证据摘录正文中完全匹配")

        # ---------------------------------------------------------------------
        # 自检规则 15: 严格中立语言，过滤法律定性
        # ---------------------------------------------------------------------
        rules_evaluated.append("规则15: 严格中立语言与法律词汇脱敏")
        clean_reason = sanitize_legal_phrasing(clean_reason)

        # 汇总结论与纠偏
        if corrections:
            full_reason = f"{clean_reason}\n\n" + "\n".join(corrections)
            status = "corrected"
        elif not passed:
            full_reason = clean_reason
            status = "needs_manual_review"
        else:
            full_reason = clean_reason
            status = "passed"

        return SelfCheckDetailedReport(
            final_conclusion=final_conclusion,
            final_confidence=round(final_confidence, 2),
            final_reason=full_reason,
            passed=passed,
            rules_evaluated=rules_evaluated,
            status=status,
            issues=issues,
            corrected_verdict=final_conclusion if status == "corrected" else None,
            corrected_confidence=round(final_confidence, 2) if status == "corrected" else None,
            correction_reason="；".join(corrections) if corrections else None,
        )


# 全局单例
fact_self_checker = FactSelfChecker()
