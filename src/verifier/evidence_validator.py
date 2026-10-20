"""ClaimCheck Pro 证据有效性判定与独立性去重引擎 (Evidence Validator & Deduplicator)

严格遵循：
第四阶段规范：
1. 证据有效性规则 (10项标准)
2. 证据来源分级最终确认 (A/B/C/D级准入与排除)
3. 证据独立性判断与重复转载去重 (避免虚增证据与置信度)
4. 未采用证据追踪 (保留 evidence_id, exclusion_reason, model_match, mismatch_reason)
"""

import hashlib
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse

from streamlit_app.schemas import ClaimItem, EvidenceItem
from src.verifier.evidence_classifier import evidence_classifier
from src.verifier.model_alignment import model_alignment_verifier, normalize_str


def calculate_content_fingerprint(text: str) -> str:
    """计算证据文本内容指纹 (去除标点、多余空格后取核心摘要MD5)"""
    norm = re.sub(r"[\s\-_，。！？、；：“”‘’（）\(\)\[\]【】]", "", text.lower())
    if not norm:
        return ""
    # 取前 120 个有效字符计算指纹
    sample = norm[:120]
    return hashlib.md5(sample.encode("utf-8")).hexdigest()[:12]


def calculate_text_similarity(text1: str, text2: str) -> float:
    """计算两段文本的相似度 (0.0 ~ 1.0)"""
    if not text1 or not text2:
        return 0.0
    norm1 = normalize_str(text1)
    norm2 = normalize_str(text2)
    if norm1 == norm2:
        return 1.0
    return SequenceMatcher(None, norm1, norm2).ratio()


class ValidationResult:
    """证据单条校验结果"""
    def __init__(
        self,
        evidence: EvidenceItem,
        is_valid: bool,
        validity_score: float,
        validity_reason: str,
        exclusion_reason: Optional[str] = None,
        claim_relevance: float = 1.0,
        evidence_strength: str = "strong",
    ):
        self.evidence = evidence
        self.is_valid = is_valid
        self.validity_score = validity_score
        self.validity_reason = validity_reason
        self.exclusion_reason = exclusion_reason
        self.claim_relevance = claim_relevance
        self.evidence_strength = evidence_strength


class EvidenceValidator:
    """证据有效性校验与多源去重器"""

    def validate_and_deduplicate(
        self,
        claim: ClaimItem,
        evidences: List[EvidenceItem],
        target_product: Dict[str, str],
    ) -> Tuple[List[EvidenceItem], List[Dict[str, Any]], Dict[str, int]]:
        """对候选证据池执行有效性评估、来源准入校验、型号对齐及独立性去重
        
        返回:
            (valid_evidences, excluded_evidences, stats_dict)
        """
        valid_pool: List[EvidenceItem] = []
        excluded_pool: List[Dict[str, Any]] = []

        seen_fingerprints: Dict[str, str] = {}  # fingerprint -> first_evidence_id
        seen_domains_and_texts: List[Tuple[str, str, str]] = []  # (cluster_id, evidence_id, norm_text)

        cluster_counter = 1

        for ev in evidences:
            # 1. 基础内容规范检查
            excerpt = (ev.excerpt or ev.snippet or "").strip()
            title = (ev.title or ev.source_title or "").strip()
            url = (ev.url or ev.source_url or "").strip()

            # 计算内容指纹
            fp = calculate_content_fingerprint(excerpt)
            ev.content_fingerprint = fp

            # 2. 检查 10 项有效性规则
            is_valid = True
            validity_score = 1.0
            reasons = []
            exclusion_reason = None
            evidence_strength = "strong"

            # 规则 1: URL 必须真实存在 (基本格式校验)
            if url:
                parsed_url = urlparse(url)
                if not parsed_url.scheme or not parsed_url.netloc:
                    is_valid = False
                    validity_score = 0.0
                    exclusion_reason = "URL格式非法或不存在有效域名"
            else:
                # 若完全无 URL，且非官方说明书，视为来源不可追溯
                if "A级" not in ev.source_level:
                    validity_score -= 0.3
                    reasons.append("缺少真实可溯源公开URL")

            # 规则 2: 网页正文或说明书正文读取成功
            if len(excerpt) < 20:
                is_valid = False
                validity_score = 0.0
                exclusion_reason = "正文摘录内容过短(<20字)或抓取失败"
            elif any(err_kw in excerpt for err_kw in ["滑动验证", "请登录后查看", "安全验证", "访问受限", "ERR_PAGE_RESTRICTED"]):
                is_valid = False
                validity_score = 0.0
                exclusion_reason = "页面受反爬或验证码保护，有效正文缺失"

            # 规则 3: 与当前声明直接相关性计算
            relevance = self._calculate_claim_relevance(claim, excerpt, title)
            ev.claim_relevance_score = relevance
            if relevance < 0.20:
                is_valid = False
                validity_score = 0.0
                exclusion_reason = f"证据内容与声明({claim.atomic_statement})缺乏直接相关事实"

            # 规则 4 & 5: 型号对齐检查
            align_res = model_alignment_verifier.verify_alignment(
                target_product=target_product,
                evidence_text=excerpt,
                evidence_title=title,
            )
            ev.model_match = align_res.model_match
            ev.model_matched = align_res.is_aligned

            if align_res.model_match == "mismatch":
                is_valid = False
                validity_score = 0.0
                exclusion_reason = align_res.mismatch_reason or "明确属于其他型号或版本(mismatch)，已排除"

            # 规则 6 & 8: 来源等级准入校验 (D级不得进入有效证据池)
            lvl = ev.source_level
            if lvl.startswith("D") or "D级" in lvl:
                is_valid = False
                validity_score = 0.0
                exclusion_reason = "属于D级营销软文/无出处转载/信息模糊来源，不予采纳"
            elif lvl.startswith("C") or "C级" in lvl:
                evidence_strength = "weak"
                validity_score = min(validity_score, 0.65)
                # 规则: C级不能单独证明技术参数
                if claim.category in ["参数", "规格参数", "性能", "实测性能"]:
                    validity_score = 0.45
                    reasons.append("C级论坛社媒评论不能单独证明技术参数")
            elif lvl.startswith("B") or "B级" in lvl:
                evidence_strength = "medium"
                validity_score = min(validity_score, 0.88)
            else:
                evidence_strength = "strong"

            # 3. 独立性与去重判定 (Section VI)
            is_independent = True
            duplicate_of = None
            assigned_cluster = f"cluster_{cluster_counter}"

            if is_valid:
                # 检查指纹完全一致
                if fp and fp in seen_fingerprints:
                    is_independent = False
                    duplicate_of = seen_fingerprints[fp]
                    assigned_cluster = f"cluster_fp_{fp}"
                else:
                    # 检查文本高相似度转载 (相似度 >= 0.82)
                    for c_id, orig_eid, norm_text in seen_domains_and_texts:
                        sim = SequenceMatcher(None, normalize_str(excerpt[:150]), norm_text[:150]).ratio()
                        if sim >= 0.82:
                            is_independent = False
                            duplicate_of = orig_eid
                            assigned_cluster = c_id
                            break

                if is_independent:
                    if fp:
                        seen_fingerprints[fp] = ev.evidence_id
                    seen_domains_and_texts.append((assigned_cluster, ev.evidence_id, normalize_str(excerpt[:150])))
                    cluster_counter += 1

            ev.is_valid_evidence = is_valid
            ev.validity_score = round(max(0.0, min(1.0, validity_score)), 2)
            ev.validity_reason = "；".join(reasons) if reasons else ("有效证据" if is_valid else "无效证据")
            ev.exclusion_reason = exclusion_reason
            ev.evidence_strength = evidence_strength if is_valid else "unusable"
            ev.is_independent_source = is_independent
            ev.duplicate_of_evidence_id = duplicate_of
            ev.source_cluster_id = assigned_cluster

            if is_valid:
                valid_pool.append(ev)
            else:
                excluded_pool.append({
                    "evidence_id": ev.evidence_id,
                    "title": ev.title,
                    "url": ev.url,
                    "exclusion_reason": exclusion_reason or "未满足证据有效性门限",
                    "model_match": ev.model_match,
                    "mismatch_reason": align_res.mismatch_reason or exclusion_reason or "",
                    "source_level": ev.source_level,
                })

        # 统计数量
        independent_count = sum(1 for e in valid_pool if e.is_independent_source)
        stats = {
            "candidate_count": len(evidences),
            "valid_count": len(valid_pool),
            "independent_count": independent_count,
            "excluded_count": len(excluded_pool),
        }

        return valid_pool, excluded_pool, stats

    def _calculate_claim_relevance(self, claim: ClaimItem, excerpt: str, title: str) -> float:
        """计算证据内容与宣传声明的核心事实相关度 (0.0 ~ 1.0)"""
        combined = f"{title} {excerpt}".lower()
        target_fact = (claim.single_verifiable_fact or claim.atomic_statement or claim.original_text or "").lower()
        if not target_fact:
            return 0.5

        # 1. 提取声明中的关键词与 2-gram
        clean_target = re.sub(r"[\s\-_，。！？、；：“”‘’（）\(\)\[\]【】/]+", " ", target_fact).strip()
        tokens = [t for t in clean_target.split() if len(t) >= 2]
        chinese_chars = re.findall(r"[\u4e00-\u9fa5]", clean_target)
        bigrams = ["".join(chinese_chars[i:i+2]) for i in range(len(chinese_chars) - 1)]
        all_terms = list(set(tokens + bigrams))

        matched_terms = sum(1 for t in all_terms if t in combined)
        term_ratio = matched_terms / max(1, len(all_terms)) if all_terms else 0.5

        # 2. 提取并比对核心数值 (支持如 48 匹配 48.2)
        target_nums = re.findall(r"\d+", target_fact)
        evidence_nums = re.findall(r"\d+", combined)
        matched_nums = sum(1 for n in target_nums if any(n in en for en in evidence_nums)) if target_nums else 1
        num_ratio = matched_nums / max(1, len(target_nums)) if target_nums else 1.0

        # 3. 核验指标偏置 (verification_target)
        v_target = (claim.verification_target or "").lower()
        v_bonus = 0.2 if v_target and any(part in combined for part in v_target.split() if len(part) >= 2) else 0.0

        score = (term_ratio * 0.5) + (num_ratio * 0.4) + v_bonus
        return min(round(max(0.0, score), 2), 1.0)


# 全局单例
evidence_validator = EvidenceValidator()
