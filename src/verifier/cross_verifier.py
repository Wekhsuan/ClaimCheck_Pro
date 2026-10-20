"""ClaimCheck Pro 多源证据交叉验证引擎 (Cross Verifier Engine - Phase 4)

严格遵循：
第四阶段规范：
1. 单次最多处理 5 条宣传声明；
2. 证据来源严格分为 A/B/C/D 四级，D级排除，C级不单独证明技术参数；
3. 严格同型号对齐 (exact / probable / series_only / mismatch / unknown)，排除 mismatch；
4. 证据独立性与去重 (排除重复搬运与聚合转载)；
5. 输出结论必须且只能为四级结论：
   - 有证据支持
   - 部分支持
   - 存在冲突
   - 证据不足
6. 置信度评分体系 (0~100) 与分级 (高/中高/中/低)，含各组成因子可解释细项；
7. 理由具体差异化生成，回答六大核心问题，相似度超阈值触发确定性重构；
8. 二次事实自检15项铁律回路；
9. 人工复核机制判定 (needs_manual_review)；
10. 全篇总体综合报告与决策建议。
"""

import time
import uuid
from typing import Dict, List, Optional, Any

from streamlit_app.schemas import (
    ClaimItem,
    EvidenceItem,
    ProductIdentity,
    VerificationConclusionEnum,
    ClaimVerificationResult,
    VerificationReport,
)
from src.verifier.evidence_classifier import evidence_classifier
from src.verifier.model_alignment import model_alignment_verifier
from src.verifier.evidence_validator import evidence_validator
from src.verifier.reason_generator import reason_generator
from src.verifier.human_review import human_review_engine
from src.verifier.fact_checker import fact_self_checker, sanitize_legal_phrasing


class CrossVerifier:
    """多源交叉验证核心引擎 (阶段 4 强化版)"""

    def verify_single_claim(
        self,
        claim: ClaimItem,
        evidences: List[EvidenceItem],
        target_product: Dict[str, str],
        search_status: str = "executed",
    ) -> ClaimVerificationResult:
        """对单条声明执行有效性过滤、独立性去重、同型号核验、多源比对、置信度打分与二次自检"""
        # 1. 证据有效性判定与独立性去重 (Section IV, V, VI)
        valid_evidences, excluded_evidences, stats = evidence_validator.validate_and_deduplicate(
            claim=claim,
            evidences=evidences,
            target_product=target_product,
        )

        # 2. 交叉验证逻辑判定四级结论 (Section VII)
        initial_conclusion = VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
        initial_confidence_ratio = 0.50

        # 分离支持、冲突与部分支持证据 (仅限有效且型号匹配属于 exact 或 probable)
        aligned_evs = [e for e in valid_evidences if e.model_match in ["exact", "probable"]]
        supporting_evs = [e for e in aligned_evs if e.evidence_direction == "support"]
        conflicting_evs = [e for e in aligned_evs if e.evidence_direction == "contradict"]
        partial_evs = [e for e in aligned_evs if e.evidence_direction == "partial"]

        # 判定 A: 存在冲突 (高可信 A/B 级证据同型号明确反证)
        if conflicting_evs:
            strong_conflicts = [
                e for e in conflicting_evs
                if (e.source_level.startswith("A") or e.source_level.startswith("B"))
            ]
            if strong_conflicts:
                initial_conclusion = VerificationConclusionEnum.CONFLICT
                initial_confidence_ratio = 0.92
            else:
                initial_conclusion = VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
                initial_confidence_ratio = 0.60

        # 判定 B: 有证据支持 (同型号 A 级或多个 B 级充分佐证)
        elif supporting_evs:
            has_strong_support = any(
                e.source_level.startswith("A") or e.source_level.startswith("B")
                for e in supporting_evs
            )
            if has_strong_support:
                # 检查是否包含省略前提条件的特征 (避免误伤正常参数规格表述)
                omitted_condition_kws = ["仅在", "需满足", "前置条件", "特定条件", "关闭降噪后", "仅限特定", "需搭配专用"]
                has_omitted_condition = partial_evs or any(
                    any(kw in e.excerpt for kw in omitted_condition_kws)
                    for e in supporting_evs
                )
                if has_omitted_condition:
                    initial_conclusion = VerificationConclusionEnum.PARTIALLY_SUPPORTED
                    initial_confidence_ratio = 0.88
                else:
                    initial_conclusion = VerificationConclusionEnum.SUPPORTED
                    initial_confidence_ratio = 0.95
            else:
                # 仅有 C 级用户体验
                if claim.category in ["用户体验", "明确体验承诺"]:
                    initial_conclusion = VerificationConclusionEnum.PARTIALLY_SUPPORTED
                    initial_confidence_ratio = 0.70
                else:
                    initial_conclusion = VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
                    initial_confidence_ratio = 0.55

        # 判定 C: 部分支持 (显式部分支持证据)
        elif partial_evs:
            initial_conclusion = VerificationConclusionEnum.PARTIALLY_SUPPORTED
            initial_confidence_ratio = 0.85

        # 判定 D: 证据不足 (无有效证据、未配置搜索或未对齐同型号)
        else:
            initial_conclusion = VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
            initial_confidence_ratio = 0.50

        # 3. 置信度评分体系量化计算 (0~100) (Section VIII)
        confidence_score, confidence_components, confidence_reason = self._calculate_confidence_score(
            verdict=initial_conclusion,
            valid_evidences=valid_evidences,
            stats=stats,
            claim=claim,
        )

        # 最高来源等级计算
        highest_source_level = "无"
        for ev in valid_evidences:
            lvl = ev.source_level
            if "A级" in lvl or lvl.startswith("A"):
                highest_source_level = "A级"
                break
            elif ("B级" in lvl or lvl.startswith("B")) and highest_source_level in ["无", "C级", "D级"]:
                highest_source_level = "B级"
            elif ("C级" in lvl or lvl.startswith("C")) and highest_source_level in ["无", "D级"]:
                highest_source_level = "C级"
            elif ("D级" in lvl or lvl.startswith("D")) and highest_source_level == "无":
                highest_source_level = "D级"

        # 4. 生成具体差异化分析理由 (Section IX)
        detailed_reason = reason_generator.generate_detailed_reason(
            claim=claim,
            verdict=initial_conclusion,
            valid_evidences=valid_evidences,
            excluded_evidences=excluded_evidences,
            target_product=target_product,
            stats=stats,
            highest_source_level=highest_source_level,
            limitations="受限于公开数据可查范围，不同固件版本或硬件批次可能存在微调，建议以出厂铭牌为准。",
        )

        # 5. 二次事实自检回路 (Section X)
        self_check_report = fact_self_checker.audit_verification(
            claim=claim,
            conclusion=initial_conclusion,
            evidences=valid_evidences,
            reason=detailed_reason,
            confidence=initial_confidence_ratio,
            search_status=search_status,
            candidate_evidence_ids=[e.evidence_id for e in evidences],
        )

        final_conclusion = self_check_report.final_conclusion
        final_confidence_ratio = self_check_report.final_confidence
        final_reason = self_check_report.final_reason
        self_check_passed = self_check_report.passed
        rules_evaluated = self_check_report.rules_evaluated

        # 置信度评分严格来自 6 维度量化评分 (0~100)
        final_score = confidence_score
        if not self_check_passed:
            final_score = min(final_score, round(self_check_report.final_confidence * 100.0, 1))

        # 6. 人工复核触发判定 (Section XI)
        needs_review, review_reason = human_review_engine.evaluate_human_review_need(
            claim=claim,
            verdict=final_conclusion,
            confidence_score=final_score,
            valid_evidences=valid_evidences,
            excluded_evidences=excluded_evidences,
            target_product=target_product,
            self_check_passed=self_check_passed,
        )

        # 7. 生成购买前微建议
        pre_tips = []
        if final_conclusion == VerificationConclusionEnum.CONFLICT:
            pre_tips.append("该参数与官方公开记载存在出入，下单前建议直接咨询品牌官方客服核实具体批次规格。")
        elif final_conclusion == VerificationConclusionEnum.PARTIALLY_SUPPORTED:
            pre_tips.append("请特别注意该功能的触发前提条件（如线材、充电头功率或配套 App 版本）。")
        elif final_conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE:
            pre_tips.append("该项指标缺乏公开权威检测资料，若为核心刚需，建议要求卖家出示正规质检证明。")
        else:
            pre_tips.append("同型号官方数据与实测相互印证，该项可信度高。")

        return ClaimVerificationResult(
            claim=claim,
            conclusion=final_conclusion,
            evidences=valid_evidences,
            analysis_reason=sanitize_legal_phrasing(final_reason),
            confidence=final_confidence_ratio,
            self_check_passed=self_check_passed,
            self_check_notes="通过事实自检：逻辑严密，无幻觉与越界断言。" if self_check_passed else "自检纠偏：已按铁律修正结论并抑制过度推断。",
            self_check_rules_evaluated=rules_evaluated,
            pre_purchase_tips=pre_tips,
            # 阶段 4 强化属性
            claim_id=claim.claim_id,
            original_claim=claim.original_text,
            normalized_claim=claim.normalized_claim or claim.atomic_statement,
            claim_category=claim.category,
            verdict=final_conclusion.value,
            confidence_score=final_score,
            confidence_level="高" if final_score >= 80 else ("中高" if final_score >= 65 else ("中" if final_score >= 45 else "低")),
            evidence_count=stats["candidate_count"],
            valid_evidence_count=stats["valid_count"],
            independent_source_count=stats["independent_count"],
            highest_source_level=highest_source_level,
            supporting_evidence_ids=[e.evidence_id for e in supporting_evs if e.evidence_id],
            contradicting_evidence_ids=[e.evidence_id for e in conflicting_evs if e.evidence_id],
            partial_evidence_ids=[e.evidence_id for e in partial_evs if e.evidence_id],
            excluded_evidences=excluded_evidences,
            limitations="受限于公开数据可查范围，若涉及硬件改版或固件升级，可能存在轻微差异。",
            user_advice="建议在购买前确认同型号的硬件生产批次及标配附件。",
            needs_manual_review=needs_review,
            review_reason=review_reason,
            self_check_status=self_check_report.status,
            self_check_issues=self_check_report.issues,
            confidence_components=confidence_components,
            confidence_reason=confidence_reason,
        )

    def generate_full_report(
        self,
        product: ProductIdentity,
        claims_results: List[ClaimVerificationResult],
        service_mode: str = "mock",
        is_mock: bool = True,
        search_status: str = "not_configured",
        ai_provider_name: str = "",
        ai_model_name: str = "",
        search_provider_name: str = "",
        search_query_count: int = 0,
        candidate_webpage_count: int = 0,
        extracted_webpage_count: int = 0,
        run_id: str = "",
    ) -> VerificationReport:
        """汇总全套核验结果，执行相似度校验，产出综合摘要、人工确认项与购买前建议"""
        # 1. 执行分析理由相似度检查并差异化重构 (Section IX)
        target_prod_dict = {
            "brand": product.brand,
            "model": product.model,
            "variant": product.version,
            "region": product.sales_region,
        }
        claims_results, has_sim_warning = reason_generator.check_and_differentiate_reasons(
            claims_results=claims_results,
            target_product=target_prod_dict,
            similarity_threshold=0.85,
        )

        counts = {
            VerificationConclusionEnum.SUPPORTED.value: 0,
            VerificationConclusionEnum.PARTIALLY_SUPPORTED.value: 0,
            VerificationConclusionEnum.CONFLICT.value: 0,
            VerificationConclusionEnum.INSUFFICIENT_EVIDENCE.value: 0,
        }
        for cr in claims_results:
            c_val = cr.conclusion.value if hasattr(cr.conclusion, "value") else str(cr.conclusion)
            counts[c_val] = counts.get(c_val, 0) + 1

        total_claims = len(claims_results)
        supported_count = counts.get(VerificationConclusionEnum.SUPPORTED.value, 0)
        partial_count = counts.get(VerificationConclusionEnum.PARTIALLY_SUPPORTED.value, 0)
        conflict_count = counts.get(VerificationConclusionEnum.CONFLICT.value, 0)
        insufficient_count = counts.get(VerificationConclusionEnum.INSUFFICIENT_EVIDENCE.value, 0)

        # 统计证据总量与人工复核项
        total_cand_evs = sum(cr.evidence_count for cr in claims_results)
        total_valid_evs = sum(cr.valid_evidence_count for cr in claims_results)
        total_indep_evs = sum(cr.independent_source_count for cr in claims_results)
        manual_rev_cnt = sum(1 for cr in claims_results if cr.needs_manual_review)

        # 找出风险最高与支持最充分的声明 (Section XII)
        highest_risk_claim = "暂无明显高风险声明"
        for cr in claims_results:
            if cr.conclusion == VerificationConclusionEnum.CONFLICT:
                highest_risk_claim = f"声明 #{cr.claim_id}: {cr.original_claim} (结论：存在冲突)"
                break
            elif cr.confidence_score < 45.0:
                highest_risk_claim = f"声明 #{cr.claim_id}: {cr.original_claim} (置信度仅为 {cr.confidence_score}分)"

        most_supported_claim = "暂无高置信支持声明"
        best_score = -1.0
        for cr in claims_results:
            if cr.conclusion == VerificationConclusionEnum.SUPPORTED and cr.confidence_score > best_score:
                best_score = cr.confidence_score
                most_supported_claim = f"声明 #{cr.claim_id}: {cr.original_claim} (置信度：{cr.confidence_score}分，A级佐证)"

        # 2. 总体综合摘要 (Section XII)
        summary_lines = [
            f"本次针对【{product.brand} {product.model} ({product.version})】共抽取核验了 {total_claims} 项核心宣传声明。",
            f"核验结果统计：有证据支持 {supported_count} 项，部分支持 {partial_count} 项，存在冲突 {conflict_count} 项，证据不足 {insufficient_count} 项。",
            f"共分析候选证据线索 {total_cand_evs} 项，筛选确认有效证据 {total_valid_evs} 项（含独立来源 {total_indep_evs} 个）。",
        ]
        if manual_rev_cnt > 0:
            summary_lines.append(f"⚠️ 提示：其中有 {manual_rev_cnt} 项声明因型号轻微差异、版本跨度或条件争议标记为【需人工复核】。")
        if conflict_count > 0:
            summary_lines.append("⚠️ 特别关注：检测到宣传宣称与同型号官方资料存在实质出入，建议重点咨询官方客服。")
        elif partial_count > 0:
            summary_lines.append("💡 提示：核心宣称基本属实，但商家宣传省略了重要生效条件，需了解前置门槛。")
        elif supported_count == total_claims and total_claims > 0:
            summary_lines.append("✅ 结论优异：各项宣传均获得同型号官方规格或权威第三方实测强有力支持。")

        if search_status == "not_configured":
            summary_lines.append("（注意：系统未配置网络搜索服务，结论仅基于当前输入文案与提供的材料，未执行全网检索）")

        overall_summary = " ".join(summary_lines)

        # 3. 人工确认项与购买前建议
        human_items = [
            f"核对机身铭牌与系统信息中显示的型号是否为 '{product.model}'，谨防同系列低配混淆。",
            "优先在品牌官方服务支持页面输入机身SN序列号，核验证明与三包质保凭据。",
        ]
        if conflict_count > 0:
            human_items.append("针对存在出入的技术参数，在下单前要求商家或官方客服出具书面规格承诺或盖章检测报告。")

        pre_advice = [
            "建议通过品牌官方自营旗舰店或授权经销商购买，索取正规发票以保障退换三包权益。",
            "若商品涉及快充功率、降噪深度或协议兼容，请提前确认自身设备及充电头的配套支持情况。",
            "收到商品后先通电试机，核对产品内置固件显示的型号代号与外包装是否完全一致再确认收货。",
        ]

        report_id = run_id or f"RPT-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"

        return VerificationReport(
            report_id=report_id,
            task_timestamp=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            service_mode=service_mode,
            is_mock=is_mock,
            product=product,
            claims_results=claims_results,
            conclusion_summary=counts,
            overall_summary=overall_summary,
            human_verification_items=human_items,
            pre_purchase_advice=pre_advice,
            # 阶段 4 扩展字段
            ai_provider_name=ai_provider_name,
            ai_model_name=ai_model_name,
            search_provider_name=search_provider_name,
            search_query_count=search_query_count,
            candidate_webpage_count=candidate_webpage_count,
            extracted_webpage_count=extracted_webpage_count,
            candidate_evidence_count=total_cand_evs,
            valid_evidence_count=total_valid_evs,
            independent_source_count=total_indep_evs,
            manual_review_count=manual_rev_cnt,
            highest_risk_claim=highest_risk_claim,
            most_supported_claim=most_supported_claim,
            main_limitations="本核验结论基于公开可查网络资料、说明书及实测数据，不排除厂商固件升级或后续硬件改版可能。",
            pre_purchase_checklist=human_items,
            run_id=report_id,
            search_status=search_status,
        )

    def _calculate_confidence_score(
        self,
        verdict: VerificationConclusionEnum,
        valid_evidences: List[EvidenceItem],
        stats: Dict[str, int],
        claim: ClaimItem,
    ) -> Tuple[float, Dict[str, float], str]:
        """计算量化置信度分值 (0~100) 并给出权重解释细项"""
        # 1. 来源可信度 (25%)
        # A级=25, B级=18, C级=8, D级=0
        src_score = 0.0
        if any(e.source_level.startswith("A") or "A级" in e.source_level for e in valid_evidences):
            src_score = 25.0
        elif any(e.source_level.startswith("B") or "B级" in e.source_level for e in valid_evidences):
            src_score = 18.0
        elif any(e.source_level.startswith("C") or "C级" in e.source_level for e in valid_evidences):
            src_score = 8.0

        # 2. 型号匹配度 (25%)
        # exact=25, probable=18, series_only=8, unknown=2, mismatch=0
        model_score = 0.0
        if any(e.model_match == "exact" for e in valid_evidences):
            model_score = 25.0
        elif any(e.model_match == "probable" for e in valid_evidences):
            model_score = 18.0
        elif any(e.model_match == "series_only" for e in valid_evidences):
            model_score = 8.0
        elif any(e.model_match == "unknown" for e in valid_evidences):
            model_score = 2.0

        # 3. 声明相关度 (15%)
        rel_scores = [getattr(e, "claim_relevance_score", 0.8) for e in valid_evidences]
        max_rel = max(rel_scores) if rel_scores else 0.5
        relevance_score = round(max_rel * 15.0, 1)

        # 4. 独立证据数量 (15%)
        indep_cnt = stats.get("independent_count", 0)
        if indep_cnt >= 3:
            indep_score = 15.0
        elif indep_cnt == 2:
            indep_score = 12.0
        elif indep_cnt == 1:
            indep_score = 8.0
        else:
            indep_score = 0.0

        # 5. 证据方向一致性 (15%)
        # 支持与冲突均有 -> 5分; 全一致且无冲突 -> 15分; 纯证据不足 -> 8分
        has_supp = any(e.evidence_direction == "support" for e in valid_evidences)
        has_conf = any(e.evidence_direction == "contradict" for e in valid_evidences)
        if has_supp and has_conf:
            consist_score = 5.0
        elif has_supp or has_conf or any(e.evidence_direction == "partial" for e in valid_evidences):
            consist_score = 15.0
        else:
            consist_score = 8.0

        # 6. 页面完整性与时效性 (5%)
        complete_score = 5.0 if valid_evidences and all(len(e.excerpt) >= 50 for e in valid_evidences) else 3.0

        # 总分与截断
        total_score = round(src_score + model_score + relevance_score + indep_score + consist_score + complete_score, 1)
        total_score = max(0.0, min(100.0, total_score))

        components = {
            "来源权威度(25%)": src_score,
            "型号严格匹配(25%)": model_score,
            "声明直接相关(15%)": relevance_score,
            "独立来源数量(15%)": indep_score,
            "证据方向一致(15%)": consist_score,
            "正文完整与时效(5%)": complete_score,
        }

        reasons = [
            f"来源权威得分: {src_score}/25分",
            f"型号对齐得分: {model_score}/25分",
            f"相关度得分: {relevance_score}/15分",
            f"独立证据源: {indep_score}/15分 (共{indep_cnt}个独立源)",
            f"一致性得分: {consist_score}/15分",
        ]
        confidence_reason = "；".join(reasons)

        return total_score, components, confidence_reason


# 全局单例
cross_verifier = CrossVerifier()
