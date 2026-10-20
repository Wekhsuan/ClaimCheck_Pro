"""ManualEvidenceProvider - 用户手动录入参考链接证据提供者

当用户未配置搜索API或希望针对特定官网/说明书核验时：
1. 支持用户录入品牌官网、说明书、规格页、评测链接；
2. 校验 URL 格式与域名；
3. 本阶段完成录入、格式校验、备注与增删改；
4. 不发起全网盲搜，严格限制在用户提供的证据源内。
"""

import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from src.search.base import (
    ManualEvidenceItem,
    SearchCapabilities,
    SearchConnectionResult,
    SearchProvider,
    SearchResultItem,
    clean_suspicious_control_characters,
    validate_web_url,
)


class ManualEvidenceProvider(SearchProvider):
    """用户手动证据管理与检索适配器"""

    ALLOWED_SOURCE_TYPES = ["official", "spec", "manual", "review", "other"]

    def __init__(self, initial_items: Optional[List[ManualEvidenceItem]] = None):
        self.items: List[ManualEvidenceItem] = initial_items or []

    def provider_name(self) -> str:
        return "ManualEvidenceProvider"

    def is_configured(self) -> bool:
        """手动模式在录入至少一条有效证据时视为就绪"""
        return len(self.items) > 0

    def capabilities(self) -> Dict[str, Any]:
        return {
            "can_search": True,
            "can_extract": False,
            "requires_api_key": False,
            "status_text": f"手动证据模式 (已录入 {len(self.items)} 条)",
            "allowed_source_types": self.ALLOWED_SOURCE_TYPES,
            "items_count": len(self.items),
        }

    def test_connection(self) -> SearchConnectionResult:
        """手动模式无需外部 API Key"""
        has_items = len(self.items) > 0
        return SearchConnectionResult(
            success=True,
            provider_name=self.provider_name(),
            supports_search=has_items,
            response_time_ms=0,
            results_count=len(self.items),
            status_code=200,
            error_message=f"已载入 {len(self.items)} 条手动证据" if has_items else "尚未录入任何手动证据链接",
            masked_api_key="manual_mode (免Key)",
            capabilities=SearchCapabilities(
                supports_text_model=None,
                supports_web_search=False,
                supports_source_urls=True,
                supports_web_extractor=False,
                supports_responses_api=False,
            ),
            status_tag="connected_searchable" if has_items else "not_configured",
        )

    def add_evidence(
        self,
        url: str,
        title: str = "",
        source_type: str = "official",
        user_note: str = "",
    ) -> Tuple[bool, str]:
        """录入并校验一条手动证据链接"""
        clean_url = (url or "").strip()
        if not clean_url:
            return False, "URL 不能为空"

        is_valid_url, err_msg = validate_web_url(clean_url)
        if not is_valid_url:
            return False, err_msg

        # 重复检查
        for item in self.items:
            if item.url.lower() == clean_url.lower():
                return False, "该证据链接已存在于当前列表中，请勿重复添加"

        parsed = urlparse(clean_url)
        clean_title = clean_suspicious_control_characters(title.strip()) or parsed.netloc
        clean_note = clean_suspicious_control_characters(user_note.strip())
        s_type = source_type if source_type in self.ALLOWED_SOURCE_TYPES else "other"
        now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        evidence = ManualEvidenceItem(
            url=clean_url,
            title=clean_title,
            source_type=s_type,
            user_note=clean_note,
            added_at=now_time,
        )
        self.items.append(evidence)
        return True, "证据链接添加成功"

    def remove_evidence(self, index: int) -> bool:
        """根据索引删除手动证据"""
        if 0 <= index < len(self.items):
            del self.items[index]
            return True
        return False

    def clear_evidence(self):
        """清空所有手动证据"""
        self.items.clear()

    def get_items(self) -> List[ManualEvidenceItem]:
        """获取当前所有手动证据"""
        return list(self.items)

    def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
        """将用户手动录入的证据转换为标准化 SearchResultItem"""
        results: List[SearchResultItem] = []
        limit = max(1, int(max_results or 5))

        for idx, item in enumerate(self.items[:limit], 1):
            results.append(self.sanitize_result(item.model_dump(), query, rank=idx))

        return results

    def sanitize_result(self, raw_item: Dict[str, Any], query: str, rank: int = 0) -> SearchResultItem:
        raw_url = str(raw_item.get("url", "")).strip()
        domain = urlparse(raw_url).netloc.lower() if raw_url else ""
        s_type = raw_item.get("source_type", "official")
        user_note = raw_item.get("user_note", "")
        title = raw_item.get("title", "") or domain

        snippet = f"[{s_type}] {user_note}" if user_note else f"用户手动提供证据源 ({s_type})"

        is_traceable = bool(raw_url and (raw_url.startswith("http://") or raw_url.startswith("https://")))

        return SearchResultItem(
            title=clean_suspicious_control_characters(title),
            url=raw_url,
            snippet=clean_suspicious_control_characters(snippet),
            domain=domain,
            published_at=raw_item.get("added_at"),
            provider="manual",
            query=query,
            result_rank=rank,
            traceable=is_traceable,
            search_request_id="manual_input",
        )
