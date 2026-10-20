"""ClaimCheck Pro 搜索服务包 (Search Providers)
"""

from src.search.base import (
    ManualEvidenceItem,
    SearchCapabilities,
    SearchConnectionResult,
    SearchProvider,
    SearchResultItem,
    clean_suspicious_control_characters,
    validate_web_url,
)
from src.search.kimi_provider import KimiSearchProvider
from src.search.manual_provider import ManualEvidenceProvider
from src.search.no_search_provider import NoSearchProvider
from src.search.qwen_provider import QwenSearchProvider
from src.search.tavily_provider import TavilySearchProvider
from src.search.query_generator import LayeredQueryGenerator, SearchQueryItem
from src.search.evidence_structurer import EvidenceStructurer, evidence_structurer
from src.crawlers.evidence_fetcher import EvidenceFetcher, WebPageExcerptResult, evidence_fetcher
from src.search.factory import SearchProviderFactory

__all__ = [
    "SearchProvider",
    "SearchResultItem",
    "ManualEvidenceItem",
    "SearchCapabilities",
    "SearchConnectionResult",
    "NoSearchProvider",
    "TavilySearchProvider",
    "KimiSearchProvider",
    "QwenSearchProvider",
    "ManualEvidenceProvider",
    "SearchProviderFactory",
    "LayeredQueryGenerator",
    "SearchQueryItem",
    "EvidenceStructurer",
    "evidence_structurer",
    "EvidenceFetcher",
    "WebPageExcerptResult",
    "evidence_fetcher",
    "clean_suspicious_control_characters",
    "validate_web_url",
]
