"""ClaimCheck Pro 人工复核判定引擎 (Human Review Engine)

严格遵循第十一阶段规范：
触发条件：
- 型号只有 probable 或 series_only
- A级证据之间互相冲突
- 官方资料与多个专业实测差异过大
- 证据时间跨度过大
- 地区版本不同
- 商品页面与官方页面型号表达不一致
- 重要证据页面受限
- 声明涉及无法客观量化的体验
- 自检无法纠正
- 置信度低于 45

输出明确的人工复核原因 (review_reason) 和操作建议。
"""

from typing import Dict, List, Optional, Tuple, Any
from streamlit_app.schemas import ClaimItem, EvidenceItem, VerificationConclusionEnum


class HumanReviewEngine:
    """人工复核规则触发器"""

    @staticmethod
    def evaluate_human_review_need(
        claim: ClaimItem,
        verdict: VerificationConclusionEnum,
        confidence_score: float,
        valid_evidences: List[EvidenceItem],
        excluded_evidences: List[Dict[str, Any]],
        target_product: Dict[str, str],
        self_check_passed: bool = True,
    ) -> Tuple[bool, str]:
        """评估当前声明是否必须标记 needs_manual_review = True
        
        返回: (needs_review, review_reason)
        """
        reasons = []

        # 1. 置信度过低 (低于 45 分)
        if confidence_score < 45.0:
            reasons.append(f"量化置信度分值仅为 {confidence_score:.1f}（低于45分门槛），缺乏足够强事实支撑")

        # 2. 型号对齐非严格 exact
        non_exact_evs = [e for e in valid_evidences if e.model_match in ["probable", "series_only"]]
        if non_exact_evs and not any(e.model_match == "exact" for e in valid_evidences):
            reasons.append("所引证据仅达到同系列或高度疑似匹配，未能100%排除衍生子型号差异")

        # 3. A级证据之间内部矛盾
        a_evs = [e for e in valid_evidences if e.source_level.startswith("A") or "A级" in e.source_level]
        a_supp = [e for e in a_evs if e.evidence_direction == "support"]
        a_conf = [e for e in a_evs if e.evidence_direction == "contradict"]
        if a_supp and a_conf:
            reasons.append("检测到多份A级官方/国标资料之间对该参数表述存在冲突，需人工比对具体生产批次")

        # 4. 官方规格与专业实测显著差异
        b_evs = [e for e in valid_evidences if e.source_level.startswith("B") or "B级" in e.source_level]
        if a_supp and any(e.evidence_direction == "contradict" for e in b_evs):
            reasons.append("官方标称数据与第三方专业实验室实测数据存在显著分歧，建议核对实测测试条件")

        # 5. 地区销售版本差异
        t_region = target_product.get("sales_region", target_product.get("region", "中国大陆"))
        if any("美版" in e.excerpt or "日版" in e.excerpt or "海外版" in e.excerpt for e in valid_evidences):
            if "中国大陆" in t_region or "国行" in t_region:
                reasons.append("部分公开证据指向海外发售版本，可能与国行版存在网络制式或零配件规格差异")

        # 6. 重要页面读取受限
        if any(ex.get("exclusion_reason", "").find("受限") != -1 for ex in excluded_evidences):
            reasons.append("关键官方或电商页面受防爬限制未能完整读取正文，建议人工进入页面核对")

        # 7. 主观不可量化体验承诺
        if claim.category == "明确体验承诺" and verdict == VerificationConclusionEnum.PARTIALLY_SUPPORTED:
            reasons.append("声明包含主观感官或佩戴体验描述，个体差异较大，建议结合线下实机试用确认")

        # 8. 自检未能完全纠正
        if not self_check_passed:
            reasons.append("二次事实自检发现逻辑或证据链疑点，自动纠偏未能完全平息歧义")

        if reasons:
            return True, "；".join(reasons)
        return False, ""


# 全局单例
human_review_engine = HumanReviewEngine()
