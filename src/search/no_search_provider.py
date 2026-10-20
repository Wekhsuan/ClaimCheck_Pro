"""NoSearchProvider - 默认未配置搜索服务提供者

当用户未配置搜索服务时使用：
- is_configured() 恒返回 False；
- search() 严格返回空列表，绝不伪造或模拟任何搜索结果；
- 页面明确提示当前不会发起实时网络检索。
"""

from src.search.base import (
    SearchCapabilities,
    SearchConnectionResult,
    SearchProvider,
    SearchResultItem,
)


class NoSearchProvider(SearchProvider):
    """未配置网络搜索服务实现"""

    def provider_name(self) -> str:
        return "NoSearchProvider"

    def is_configured(self) -> bool:
        return False

    def test_connection(self) -> SearchConnectionResult:
        return SearchConnectionResult(
            success=False,
            provider_name=self.provider_name(),
            supports_search=False,
            response_time_ms=0,
            results_count=0,
            error_message="网络搜索服务未配置。当前不会发起实时网络检索。",
            masked_api_key="",
            capabilities=SearchCapabilities(
                supports_text_model=None,
                supports_web_search=False,
                supports_source_urls=False,
                supports_web_extractor=False,
                supports_responses_api=False,
            ),
            status_tag="not_configured",
        )

    def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
        """严格返回空列表，绝不制造或伪造虚假搜索结果"""
        return []

    def sanitize_result(self, raw_item: Dict[str, Any], query: str, rank: int = 0) -> SearchResultItem:
        return SearchResultItem(
            title="",
            url="",
            snippet="",
            domain="",
            provider=self.provider_name(),
            query=query,
            result_rank=rank,
            traceable=False,
        )

    def capabilities(self) -> Dict[str, Any]:
        return {
            "can_search": False,
            "requires_api_key": False,
            "status_text": "未配置",
            "description": "当前不会执行实时网络搜索，仅依赖用户提供的详情文本或截图进行分析。",
        }
