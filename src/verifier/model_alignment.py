"""ClaimCheck Pro 同型号对齐检查器 (Model Alignment Verifier)

严格遵循：
9. 实施型号对齐四个维度：
   - 品牌 (Brand)
   - 型号 (Model)
   - 版本 (Variant/Version)
   - 地区 (Region)
杜绝“拿A型号参数否定B型号宣传”的虚假比对错误。
"""

import re
from typing import Dict, Optional, Tuple
from pydantic import BaseModel, Field


class AlignmentResult(BaseModel):
    """型号对齐评估结果 (阶段 4 强化规范)"""
    is_aligned: bool = Field(..., description="是否属于有效对齐的同型号证据(exact或probable)")
    model_match: str = Field(..., description="对齐等级：exact(严格对齐)/probable(高度疑似)/series_only(仅同系列)/mismatch(型号冲突不符)/unknown(未知型号)")
    brand_match: bool = Field(default=True, description="品牌是否一致")
    variant_match: bool = Field(default=True, description="版本/规格是否吻合")
    region_match: bool = Field(default=True, description="销售地区/网络制式是否匹配")
    confidence_penalty: float = Field(default=0.0, description="跨版本或跨地区带来的置信度惩罚")
    alignment_notes: str = Field(..., description="对齐逻辑说明")
    mismatch_reason: Optional[str] = Field(default=None, description="若不符(mismatch)的明确原因说明")


def normalize_str(s: Optional[str]) -> str:
    """归一化字符串：小写、去除空格和特殊标点"""
    if not s:
        return ""
    clean = re.sub(r"[\s\-_（）\(\)\[\]【】]", "", s.lower())
    return clean


class ModelAlignmentVerifier:
    """型号对齐验证器 (阶段 4 严格对齐五大状态)"""

    @staticmethod
    def verify_alignment(
        target_product: Dict[str, str],
        evidence_text: str,
        evidence_title: str = "",
    ) -> AlignmentResult:
        """比对证据内容与目标商品的 品牌/型号/版本/地区 是否严格对齐
        
        状态划分规则：
        1. exact: 品牌、型号和主要版本完全一致。
        2. probable: 型号高度一致，但版本、地区或容量字段存在轻微不确定性。
        3. series_only: 只确认同一系列，未确认具体型号。
        4. mismatch: 明确属于其他型号或版本。
        5. unknown: 页面没有足够信息确认型号。
        """
        t_brand = target_product.get("brand", "").strip()
        t_model = target_product.get("model", "").strip()
        t_variant = target_product.get("version", target_product.get("variant", "")).strip()
        t_region = target_product.get("sales_region", target_product.get("region", "中国大陆")).strip()

        combined_evidence = f"{evidence_title} {evidence_text}"
        norm_evidence = normalize_str(combined_evidence)
        norm_t_model = normalize_str(t_model)

        # 1. 品牌核对
        brand_match = True
        if t_brand and t_brand != "通用品牌":
            brand_parts = [bp for bp in re.split(r"[\(\)\s/]+", t_brand) if len(bp) >= 2]
            matched_b = any(normalize_str(bp) in norm_evidence for bp in brand_parts) if brand_parts else True
            if not matched_b:
                # 若型号在证据中极长且精准匹配，可能标题省略了品牌
                if norm_t_model and norm_t_model in norm_evidence and len(norm_t_model) >= 5:
                    brand_match = True
                else:
                    brand_match = False

        # 2. 型号与变体核对
        model_match = "unknown"
        mismatch_reason = None
        confidence_penalty = 0.0

        if not brand_match:
            model_match = "mismatch"
            mismatch_reason = f"证据中的品牌与目标品牌({t_brand})不符"
            confidence_penalty = 1.0

        elif norm_t_model and norm_t_model in norm_evidence:
            # 型号主体完全吻合
            # 检查是否有派生降级版本冲突 (例如目标是 X1，但证据通篇限定为 X1 SE / X1 青春版 / X1 Lite)
            variant_conflict_kws = ["青春版", "se版", "lite版", "低配版", "入门版", "se", "lite"]
            target_has_modifier = any(kw in norm_t_model for kw in ["se", "lite", "青春版", "低配"])
            evidence_has_modifier = any(kw in norm_evidence for kw in variant_conflict_kws)

            if evidence_has_modifier and not target_has_modifier:
                model_match = "mismatch"
                mismatch_reason = f"证据指向该系列低配/派生版本（如SE/Lite/青春版），与目标型号({t_model})不符"
                confidence_penalty = 0.6
            else:
                model_match = "exact"

        else:
            # 目标型号未直接出现，检查是否提及其他明确不同型号或冲突代号
            if any(kw in norm_evidence for kw in ["se", "lite", "青春版", "低配"]):
                model_match = "mismatch"
                mismatch_reason = f"证据提及其他衍生/低配型号，与目标型号({t_model})不符"
                confidence_penalty = 0.6
            else:
                # 提取型号主体单词（如 SoundPro X1 -> soundpro）
                model_tokens = [tok for tok in re.split(r"[\s\-_]+", t_model.lower()) if len(tok) >= 3]
                if model_tokens and any(tok in norm_evidence for tok in model_tokens):
                    model_match = "series_only"
                    confidence_penalty = 0.4
                elif any(w in norm_evidence for w in ["系列", "产品线"]) and brand_match:
                    model_match = "series_only"
                    confidence_penalty = 0.4
                else:
                    model_match = "unknown"
                    confidence_penalty = 0.5

        # 3. 版本/规格核对 (仅在显式发现冲突版本时才降级为 probable)
        variant_match = True
        if model_match == "exact" and t_variant:
            # 检查证据是否提到冲突的具体年份或版本号 (如目标是 2024款，证据写 2022款/2023款)
            year_match_target = re.search(r"(202\d)款?", t_variant)
            year_match_evidence = re.search(r"(202\d)款?", combined_evidence)
            if year_match_target and year_match_evidence:
                if year_match_target.group(1) != year_match_evidence.group(1):
                    variant_match = False
                    model_match = "probable"
                    confidence_penalty += 0.15

        # 4. 销售地区核对 (如国行 vs 美版/日版)
        region_match = True
        if model_match == "exact":
            if "美版" in combined_evidence and "美版" not in t_region:
                region_match = False
                model_match = "probable"
                confidence_penalty += 0.15
            elif "日版" in combined_evidence and "日版" not in t_region:
                region_match = False
                model_match = "probable"
                confidence_penalty += 0.15

        # 判定是否属于有效对齐 (仅 exact 和 probable 属于强对齐，series_only/unknown/mismatch 不属于强对齐)
        is_aligned = brand_match and (model_match in ["exact", "probable"]) and (model_match != "mismatch")

        # 构造结论说明
        notes_parts = []
        if not brand_match:
            notes_parts.append(f"品牌不吻合(目标: {t_brand})")
        if model_match == "exact":
            notes_parts.append(f"型号严格同型号对齐({t_model})")
        elif model_match == "probable":
            notes_parts.append(f"型号高度吻合但版本/地区存在轻微不确定({t_model})")
        elif model_match == "series_only":
            notes_parts.append(f"仅确认属于同系列产品，未确认具体型号({t_model})")
        elif model_match == "mismatch":
            notes_parts.append(mismatch_reason or f"型号显著冲突，疑似异型号混淆({t_model})")
        else:
            notes_parts.append("证据中未检测到明确同型号标识")

        if not variant_match:
            notes_parts.append(f"版本可能存在差异({t_variant})")
        if not region_match:
            notes_parts.append("地区销售版本存在差异")

        return AlignmentResult(
            is_aligned=is_aligned,
            model_match=model_match,
            brand_match=brand_match,
            variant_match=variant_match,
            region_match=region_match,
            confidence_penalty=min(round(confidence_penalty, 2), 0.8),
            alignment_notes="；".join(notes_parts),
            mismatch_reason=mismatch_reason,
        )


# 单例实例
model_alignment_verifier = ModelAlignmentVerifier()
