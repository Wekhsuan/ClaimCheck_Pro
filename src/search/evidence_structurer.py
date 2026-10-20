"""ClaimCheck Pro 候选证据分级与结构化组装器 (Evidence Structurer)

严格遵循：
1. 整合网络搜索结果与真实抓取正文；
2. 执行来源 A/B/C/D 四级严格分类 (官方/专业评测/社区论坛/营销软文)；
3. 执行品牌、型号、版本、地区四维型号对齐 (exact/compatible/mismatch/unknown)；
4. 结构化输出 EvidenceItem，支撑前台展示与后续定性核验；
5. 记录抓取状态与来源真实性，严禁虚构。
"""

from urllib.parse import urlparse
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.crawlers.evidence_fetcher import WebPageExcerptResult
from src.search.base import SearchResultItem
from src.verifier.evidence_classifier import EvidenceClassifier
from src.verifier.model_alignment import ModelAlignmentVerifier
from streamlit_app.schemas import EvidenceItem


class EvidenceStructurer:
    """证据来源初步分级与结构化处理器"""

    @staticmethod
    def is_official_domain(url: str, brand: str = "") -> bool:
        """根据 URL 与品牌特征判断是否属于官方基准域名"""
        if not url:
            return False
        domain = urlparse(url).netloc.lower()
        if any(gov in domain for gov in [".gov.cn", "gov.cn", "cqc.com.cn", "miit.gov.cn"]):
            return True
        if brand and len(brand) >= 2:
            brand_clean = brand.lower().replace(" ", "").replace("-", "")
            if brand_clean in domain:
                return True
        return False

    @classmethod
    def structure_evidence(
        cls,
        claim_id: int,
        search_item: SearchResultItem,
        fetch_res: WebPageExcerptResult,
        target_product: Dict[str, str],
        index: int = 1,
    ) -> EvidenceItem:
        """将搜索结果与网页提取正文组装为标准 EvidenceItem"""
        title = fetch_res.title.strip() or search_item.title.strip() or search_item.domain
        url = search_item.url or fetch_res.url
        domain = search_item.domain or fetch_res.domain

        # 1. 真实正文摘录优先；抓取受限或失败时回退至搜索摘要并标注
        if fetch_res.fetch_status == "success" and fetch_res.excerpt:
            excerpt = fetch_res.excerpt.strip()
        elif fetch_res.fetch_status == "restricted":
            excerpt = f"【页面受限】{search_item.snippet} (因平台访问保护无法自动提取正文)"
        else:
            excerpt = search_item.snippet or "（暂无网页正文）"

        # 2. 证据来源 A/B/C/D 分级
        raw_level, source_type = EvidenceClassifier.classify_source(
            title=title,
            url=url,
            source_type=search_item.provider,
            excerpt=excerpt,
            traceable=getattr(search_item, "traceable", True),
        )

        # 提取简洁等级标识 (A级 / B级 / C级 / D级)
        if "A级" in raw_level:
            source_level = "A级"
        elif "B级" in raw_level:
            source_level = "B级"
        elif "C级" in raw_level:
            source_level = "C级"
        else:
            source_level = "D级"

        # 铁律 8: 搜索摘要不能直接作为A级证据 (必须成功提取到真实网页正文)
        if source_level == "A级" and (fetch_res.fetch_status != "success" or not (fetch_res.excerpt or "").strip()):
            source_level = "B级"

        # 3. 四维型号对齐检查
        align_res = ModelAlignmentVerifier.verify_alignment(
            target_product=target_product,
            evidence_text=excerpt,
            evidence_title=title,
        )
        model_match = align_res.model_match

        # 4. 构建标准 EvidenceItem
        return EvidenceItem(
            evidence_id=f"ev_{claim_id}_{index}",
            title=title,
            url=url,
            source_type=source_type,
            source_level=source_level,
            published_at=search_item.published_at or "",
            model_match=model_match,
            excerpt=excerpt,
            evidence_direction="support",  # 默认占位，第四阶段深入判定
            # 兼容字段
            source_title=title,
            source_url=url,
            snippet=search_item.snippet,
        )


# 全局单例
evidence_structurer = EvidenceStructurer()
