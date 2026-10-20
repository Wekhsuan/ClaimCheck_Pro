"""ClaimCheck Pro 证据检索适配层 (Search Adapter)

严格遵循：
7. 没有搜索API时：
   - 允许用户手动输入证据链接；
   - 允许只分析用户提供的资料；
   - 绝不伪造或模拟实时搜索结果；
   - 绝不调用开发者付费的云端搜索服务。
"""

import logging
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from streamlit_app.schemas import EvidenceItem, SourceLevelEnum
from src.verifier.evidence_classifier import evidence_classifier
from src.crawlers.ssrf_filter import safe_fetch_html
from bs4 import BeautifulSoup

logger = logging.getLogger("claimcheck.search_adapter")


class SearchConfig(BaseModel):
    """搜索配置"""
    search_api_type: Optional[str] = Field(default=None, description="搜索API类型：serpapi / bing / none")
    search_api_key: Optional[str] = Field(default=None, description="用户自带的搜索API Key")
    allow_manual_sources: bool = Field(default=True, description="是否允许用户手动录入参考链接")


class EvidenceRetrievalResult(BaseModel):
    """证据检索输出"""
    claim_id: int
    evidences: List[EvidenceItem] = Field(default_factory=list)
    search_mode: str = Field(..., description="检索执行方式：mock_db / manual_inputs / user_materials / search_api / none")
    notes: str = Field(default="", description="检索说明与状态标识")


class SearchAdapter:
    """证据检索适配器"""

    def __init__(self, config: Optional[SearchConfig] = None):
        self.config = config or SearchConfig()

    def retrieve_evidence_for_claim(
        self,
        claim_id: int,
        claim_statement: str,
        target_product: Dict[str, str],
        manual_links: Optional[List[str]] = None,
        user_provided_materials: Optional[str] = None,
        mock_evidences: Optional[List[EvidenceItem]] = None,
    ) -> EvidenceRetrievalResult:
        """为单条声明收集证据。无搜索API时支持手动链接与资料，绝不伪造搜索结果"""
        manual_links = manual_links or []
        user_materials = user_provided_materials or ""

        # 1. Mock 模式：使用预置基准证据
        if mock_evidences is not None:
            return EvidenceRetrievalResult(
                claim_id=claim_id,
                evidences=mock_evidences,
                search_mode="mock_db",
                notes="来源于离线标准知识库，未发起实时网络外部搜索。",
            )

        collected: List[EvidenceItem] = []

        # 2. 用户手动输入的参考链接解析
        if manual_links:
            for idx, m_url in enumerate(manual_links, 1):
                clean_url = m_url.strip()
                if not clean_url or not clean_url.startswith(("http://", "https://")):
                    continue
                try:
                    html = safe_fetch_html(clean_url, timeout=8)
                    soup = BeautifulSoup(html, "html.parser")
                    title = soup.title.string.strip() if soup.title and soup.title.string else clean_url
                    full_text = soup.get_text()[:4000]

                    # 提取与声明关键词相关的摘要
                    snippet = ""
                    for p in soup.find_all(["p", "li", "span"]):
                        p_txt = p.get_text().strip()
                        if any(kw in p_txt for kw in claim_statement.split() if len(kw) >= 2):
                            snippet = p_txt[:200]
                            break
                    if not snippet:
                        snippet = full_text[:180]

                    s_level, s_type = evidence_classifier.classify_source(title, clean_url, excerpt=snippet)

                    collected.append(
                        EvidenceItem(
                            evidence_id=f"MANUAL-{claim_id}-{idx}",
                            title=title[:80],
                            url=clean_url,
                            source_type=s_type,
                            source_level=s_level,
                            published_at="用户录入",
                            model_match="exact" if target_product.get("model", "") in full_text else "unknown",
                            excerpt=snippet,
                            evidence_direction="support" if claim_statement[:4] in snippet else "neutral",
                        )
                    )
                except Exception as e:
                    logger.warning(f"手动输入链接读取失败 ({clean_url}): {e}")

        # 3. 用户在文本中提供的说明书/官方参数资料
        if user_materials and len(user_materials.strip()) > 20:
            if any(term in user_materials for term in claim_statement.split() if len(term) >= 2):
                s_level, s_type = evidence_classifier.classify_source("用户提供说明书/规格资料", excerpt=user_materials)
                collected.append(
                    EvidenceItem(
                        evidence_id=f"USER-DOC-{claim_id}",
                        title="用户提供说明书/参数文本",
                        url="",
                        source_type="用户输入材料",
                        source_level=s_level,
                        published_at="用户上传",
                        model_match="exact",
                        excerpt=user_materials[:250],
                        evidence_direction="support",
                    )
                )

        # 4. 真实搜索 API (仅当用户在 BYOK 中显式提供了搜索 Key 时)
        if self.config.search_api_key and self.config.search_api_type:
            # 预留真实引擎调用，用户自带付费 Key
            pass

        # 5. 若无任何搜索API且用户未提供材料：绝不伪造虚假搜索结果
        if not collected:
            return EvidenceRetrievalResult(
                claim_id=claim_id,
                evidences=[],
                search_mode="none",
                notes="未配置搜索API且未输入手动参考链接。根据系统零费用与真实性原则，绝不伪造虚假搜索，标记为证据不足。",
            )

        return EvidenceRetrievalResult(
            claim_id=claim_id,
            evidences=collected,
            search_mode="manual_inputs" if manual_links else "user_materials",
            notes=f"成功从用户手动输入资料中分析出 {len(collected)} 条核验证据。",
        )
