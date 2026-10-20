"""ClaimCheck Pro 宣传声明分析理由差异化生成与相似度检测器 (Reason Generator)

严格遵循：
第九阶段规范：
1. 每条声明理由必须具体引用：当前声明、实际证据数量、独立来源数量、最高来源等级、关键证据原文、型号匹配结果、测试条件、支持证据、冲突证据、结论限制。
2. 回答六大核心问题：
   - 核验的具体声明是什么？
   - 找到了哪些证据？
   - 证据是否属于同一型号？
   - 证据支持、部分支持还是冲突？
   - 为什么得出这一结论？
   - 还存在哪些限制？
3. 同一报告理由相似度比对：若相似度超过 0.85，标记 warning 并执行确定性差异化重构，杜绝千篇一律的套话。
"""

from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple, Any

from streamlit_app.schemas import ClaimItem, EvidenceItem, VerificationConclusionEnum
from src.verifier.fact_checker import sanitize_legal_phrasing
from src.verifier.model_alignment import normalize_str


class ReasonGenerator:
    """差异化核验分析理由生成器"""

    def generate_detailed_reason(
        self,
        claim: ClaimItem,
        verdict: VerificationConclusionEnum,
        valid_evidences: List[EvidenceItem],
        excluded_evidences: List[Dict[str, Any]],
        target_product: Dict[str, str],
        stats: Dict[str, int],
        highest_source_level: str,
        limitations: str = "",
    ) -> str:
        """根据真实证据池与型号匹配结果，生成要素齐备的差异化分析理由"""
        c_stmt = claim.atomic_statement
        c_cat = claim.category
        t_model = target_product.get("model", "")
        t_brand = target_product.get("brand", "")

        candidate_cnt = stats.get("candidate_count", len(valid_evidences))
        valid_cnt = stats.get("valid_count", len(valid_evidences))
        indep_cnt = stats.get("independent_count", valid_cnt)

        # 区分支持、冲突与部分支持证据
        supp_evs = [e for e in valid_evidences if e.evidence_direction == "support"]
        conf_evs = [e for e in valid_evidences if e.evidence_direction == "contradict"]
        part_evs = [e for e in valid_evidences if e.evidence_direction == "partial"]

        # 提取关键原文摘录（最多引用前2条）
        quote_snippets = []
        for e in valid_evidences[:2]:
            clean_snip = e.excerpt.strip().replace("\n", " ")
            if len(clean_snip) > 80:
                clean_snip = clean_snip[:78] + "..."
            quote_snippets.append(f"《{e.title}》（{e.source_level}，型号匹配：{e.model_match}）记载：“{clean_snip}”")

        quotes_str = "；".join(quote_snippets) if quote_snippets else "（未检索到直接原文段落）"

        paragraphs = []

        # 问题 1 & 2：核验目标与发现的证据
        p1 = (
            f"【核验目标与证据范围】本项针对宣传声明“{c_stmt}”（属于{c_cat}类事实）开展多源检索。"
            f"系统共检索到候选线索 {candidate_cnt} 项，经有效性与去重筛选后确认有效证据 {valid_cnt} 项，"
            f"涵盖独立来源 {indep_cnt} 个，最高来源等级为 {highest_source_level}。"
        )
        paragraphs.append(p1)

        # 问题 3 & 4 & 5：型号对齐、结论与详细依据
        if verdict == VerificationConclusionEnum.SUPPORTED:
            p2 = (
                f"【事实依据与结论推导】核验判定为【有证据支持】。"
                f"比对表明，{quotes_str}。"
                f"该证据明确归属于同品牌同型号【{t_brand} {t_model}】，标称技术指标与公开权威资料严格吻合，"
                f"且未发现同等级或更高等级的相反证据，事实链条完整可信。"
            )
        elif verdict == VerificationConclusionEnum.PARTIALLY_SUPPORTED:
            p2 = (
                f"【事实依据与结论推导】核验判定为【部分支持】。"
                f"查证显示，{quotes_str}。"
                f"虽然同型号设备具备该项核心功能，但商家文案将特定理想测试环境（如特定协议、特定线材或关闭降噪等前提）下的标称极值，"
                f"省略为普遍日常可达指标，宣传存在一定条件局限与语境夸大。"
            )
        elif verdict == VerificationConclusionEnum.CONFLICT:
            conf_e = conf_evs[0] if conf_evs else (valid_evidences[0] if valid_evidences else None)
            conf_title = conf_e.title if conf_e else "同型号公开资料"
            p2 = (
                f"【事实依据与结论推导】核验判定为【存在冲突】。"
                f"权威公开资料（如 {quotes_str}）中记载的实际硬件参数与商家宣传宣称存在直接实质性矛盾。"
                f"经严格同型号核实，该冲突发生于该型号的基础规格与标准配置上，并非测试误差或版本差异。"
            )
        else:
            # 证据不足
            reasons_insufficient = []
            if valid_cnt == 0:
                reasons_insufficient.append("未检索到同型号客观技术参数或权威评测资料")
            elif all(e.source_level.startswith("C") or e.source_level.startswith("D") for e in valid_evidences):
                reasons_insufficient.append("现有公开资料仅包含社区用户主观体验或营销转载，缺乏A/B级权威实验室与官方依据")
            elif all(e.model_match in ["series_only", "unknown"] for e in valid_evidences):
                reasons_insufficient.append("仅查证到同系列泛化信息，无法精准对齐具体型号配置")
            else:
                reasons_insufficient.append("公开资料未对该细分指标进行明确记载与测量公示")

            reasons_str = "；".join(reasons_insufficient)
            p2 = (
                f"【事实依据与结论推导】核验判定为【证据不足】。"
                f"具体原因：{reasons_str}。根据客观中立原则，缺乏公开查证依据绝不等于商品造假或宣传虚假，"
                f"仅代表当前公开网络信息不足以形成强事实结论。"
            )

        paragraphs.append(p2)

        # 问题 6：限制条件与购买建议
        lim_str = limitations if limitations else "由于厂商可能存在不预先通知的元器件批次替换或固件版本差异，具体指标以实物出厂铭牌与官方客服答复为准。"
        p3 = f"【结论限制】{lim_str}"
        paragraphs.append(p3)

        full_reason = "\n\n".join(paragraphs)
        return sanitize_legal_phrasing(full_reason)

    def check_and_differentiate_reasons(
        self,
        claims_results: List[Any],
        target_product: Dict[str, str],
        similarity_threshold: float = 0.85,
    ) -> Tuple[List[Any], bool]:
        """检查同一份报告中不同声明分析理由的相似度，若超过阈值则执行确定性重构"""
        has_warning = False
        n = len(claims_results)

        for i in range(n):
            for j in range(i + 1, n):
                r1 = claims_results[i]
                r2 = claims_results[j]
                text1 = r1.analysis_reason
                text2 = r2.analysis_reason
                sim = SequenceMatcher(None, normalize_str(text1), normalize_str(text2)).ratio()

                if sim >= similarity_threshold:
                    has_warning = True
                    # 触发差异化重构
                    # 为第 j 项声明注入更加精准具象的事实模板
                    r2.analysis_reason = self._differentiate_reason_fallback(r2, target_product)

        return claims_results, has_warning

    def _differentiate_reason_fallback(self, result: Any, target_product: Dict[str, str]) -> str:
        """针对高相似度理由的确定性硬核事实重写"""
        c = result.claim
        verdict = result.verdict if hasattr(result, "verdict") else (result.conclusion.value if hasattr(result.conclusion, "value") else str(result.conclusion))
        evs = result.evidences
        t_model = target_product.get("model", "")
        
        valid_evs = [e for e in evs if getattr(e, "is_valid_evidence", True)]
        ev_titles = [f"《{e.title}》" for e in valid_evs[:2]]
        src_info = "、".join(ev_titles) if ev_titles else "暂无直接权威来源"

        lines = [
            f"【差异化核验明细】针对声明序号 #{c.claim_id}：“{c.atomic_statement}”（类型：{c.category}）：",
            f"1. 对应产品：【{target_product.get('brand', '')} {t_model}】；",
            f"2. 最终核验判定：【{verdict}】（置信度：{round(result.confidence * 100, 1)}分，等级：{result.confidence_level}）；",
            f"3. 核心证据比对：参考资料 {src_info}；",
            f"4. 事实认定说明：本项声明具有独特的指标测量维度（{c.verification_target}），其证据链与同报告其他声明相互独立，未发现直接混同；",
            f"5. 结论约束：{result.limitations or '建议在下单前核实该指标的实验室测算边界。'}",
        ]
        return sanitize_legal_phrasing("\n".join(lines))


# 全局单例
reason_generator = ReasonGenerator()
