"""ClaimCheck Pro Search Provider 工厂类 (Search Provider Factory)

支持动态构建 SearchProvider 实例：
- mode == "tavily": 用户自带 Tavily API Provider
- mode == "manual": 用户手动参考链接 Provider
- mode == "none" 或其他: 默认无网络搜索 Provider
"""

from typing import Any, Dict, Optional
from src.search.base import SearchProvider
from src.search.kimi_provider import KimiSearchProvider
from src.search.manual_provider import ManualEvidenceProvider
from src.search.no_search_provider import NoSearchProvider
from src.search.qwen_provider import QwenSearchProvider
from src.search.tavily_provider import TavilySearchProvider


class SearchProviderFactory:
    """搜索提供者工厂"""

    @staticmethod
    def create_provider(mode: str, config: Optional[Dict[str, Any]] = None) -> SearchProvider:
        mode_clean = (mode or "").lower().strip()
        cfg = config or {}

        if mode_clean == "tavily":
            return TavilySearchProvider(
                api_key=cfg.get("api_key", ""),
                max_results=cfg.get("max_results", 5),
                search_language=cfg.get("language", "zh"),
                timeout=cfg.get("timeout", 15),
                prefer_official_sources=cfg.get("prefer_official", True),
                include_user_reviews=cfg.get("include_user_reviews", False),
            )
        elif mode_clean == "kimi":
            return KimiSearchProvider(
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", "https://api.moonshot.cn/v1"),
                search_mode=cfg.get("search_mode", "basic"),
                max_results=cfg.get("max_results", 5),
                max_fetches=cfg.get("max_fetches", 3),
                timeout=cfg.get("timeout", 15),
            )
        elif mode_clean == "qwen":
            return QwenSearchProvider(
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", ""),
                model_name=cfg.get("model_name", ""),
                api_mode=cfg.get("api_mode", ""),
                max_search_count=cfg.get("max_search_count", 5),
                enable_web_extractor=cfg.get("enable_web_extractor", True),
                timeout=cfg.get("timeout", 20),
                provider_platform=cfg.get("provider_platform", None),
            )
        elif mode_clean == "manual":
            return ManualEvidenceProvider(
                initial_items=cfg.get("manual_items", []),
            )
        else:
            return NoSearchProvider()
