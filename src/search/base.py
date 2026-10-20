"""ClaimCheck Pro Search Provider 统一抽象接口与数据规范 (Search Provider Base)

严格遵循零费用原则与数据真实性规范：
1. 开发者不得承担搜索费用，不得内置共享Key；
2. 搜索服务与模型 API (LLM) 彻底分离；
3. 未配置搜索时，严禁伪造任何网络检索结果；
4. 全面脱敏 API Key，严禁泄露至日志或界面。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import re
from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    """统一搜索结果结构"""
    title: str = Field(default="", description="网页标题")
    url: str = Field(default="", description="规范化完整 URL")
    snippet: str = Field(default="", description="搜索摘要")
    domain: str = Field(default="", description="来源主域名")
    published_at: Optional[str] = Field(default=None, description="发布时间或抓取时间")
    provider: str = Field(default="", description="搜索提供者标识 (tavily / kimi / qwen / manual / none)")
    result_rank: int = Field(default=0, description="在当前搜索结果集中的排序序号 (1-indexed)")
    query: str = Field(default="", description="命中的检索查询词")
    traceable: bool = Field(default=True, description="是否包含真实可溯源来源URL")
    search_request_id: str = Field(default="", description="搜索请求跟踪ID")


class ManualEvidenceItem(BaseModel):
    """手动补充证据结构"""
    url: str = Field(..., description="证据网页完整 URL")
    title: str = Field(default="", description="网页标题或说明")
    source_type: str = Field(default="official", description="来源类型: official/spec/manual/review/other")
    user_note: str = Field(default="", description="用户补充说明")
    added_at: str = Field(default="", description="添加时间戳")


class SearchCapabilities(BaseModel):
    """多维独立能力检测矩阵"""
    supports_text_model: Optional[bool] = Field(default=None, description="文本模型通信是否正常 (None=不适用/纯搜索接口)")
    supports_web_search: bool = Field(default=False, description="联网搜索工具是否可用")
    supports_source_urls: bool = Field(default=False, description="是否支持返回真实来源 URL")
    supports_web_extractor: bool = Field(default=False, description="是否支持网页正文提取器")
    supports_responses_api: bool = Field(default=False, description="是否支持 Responses API 架构")
    supports_vision: bool = Field(default=False, description="是否支持图片理解/多模态输入")
    model_exists: Optional[bool] = Field(default=None, description="模型是否存在于平台中")
    platform_matched: Optional[bool] = Field(default=None, description="平台与API Key是否一致")


class StepTestResult(BaseModel):
    """子能力独立检测结果"""
    step_name: str = Field(default="", description="步骤标识: auth_chat / responses_api / web_search / web_extractor")
    status: str = Field(default="pending", description="状态: success / failed / timeout / skipped")
    latency_ms: int = Field(default=0, description="子步骤耗时 (ms)")
    error_code: Optional[int] = Field(default=None, description="HTTP 状态码或错误代码")
    error_message: Optional[str] = Field(default=None, description="错误说明")
    supported: bool = Field(default=False, description="该能力是否可用")
    traceable: bool = Field(default=False, description="是否包含真实可溯源 URL")
    source_count: int = Field(default=0, description="返回的来源数量")


class SearchConnectionResult(BaseModel):
    """搜索连通性与密钥测试结果"""
    success: bool = Field(..., description="是否连接成功并具备可追溯搜索能力")
    provider_name: str = Field(..., description="提供者名称")
    supports_search: bool = Field(default=True, description="搜索功能是否就绪")
    response_time_ms: int = Field(default=0, description="请求往返耗时 (毫秒)")
    results_count: int = Field(default=0, description="返回结果数")
    status_code: Optional[int] = Field(default=None, description="HTTP 状态码")
    error_message: Optional[str] = Field(default=None, description="错误说明 (用户友好的中文翻译)")
    masked_api_key: str = Field(default="", description="脱敏后的 API Key")
    capabilities: SearchCapabilities = Field(default_factory=SearchCapabilities, description="5维能力检测详情")
    status_tag: str = Field(default="", description="细分搜索服务状态标签 (如: connected_searchable, chat_ok_search_fail 等)")
    extractor_status: str = Field(default="ok", description="网页提取器状态: ok / degraded / timeout / failed / skipped")
    steps: Dict[str, StepTestResult] = Field(default_factory=dict, description="独立分步测试记录")
    diagnostics: Optional[Dict[str, Any]] = Field(default=None, description="超时与网络诊断信息")
    call_debug_info: Optional[Dict[str, Any]] = Field(default=None, description="脱敏调用追踪信息 (实际端点、模式、模型等)")
    source_diagnostics: Optional[Dict[str, Any]] = Field(default=None, description="搜索响应结构与来源解析脱敏诊断")


def clean_suspicious_control_characters(text: str) -> str:
    """清理字符串中的可疑控制字符，保留正常排版空白"""
    if not text:
        return ""
    # 过滤 ASCII 控制字符 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F, 0x7F
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(text))
    return cleaned.strip()


def validate_web_url(url: str) -> Tuple[bool, str]:
    """校验 URL 是否属于合法的外网 HTTP/HTTPS 协议与域名"""
    if not url or not str(url).strip():
        return False, "URL 不能为空"
    clean_u = str(url).strip()
    try:
        parsed = urlparse(clean_u)
        if parsed.scheme.lower() not in ["http", "https"]:
            return False, "仅支持 HTTP 或 HTTPS 协议链接"
        if not parsed.netloc or "." not in parsed.netloc:
            return False, "链接必须包含有效的主机域名"
        return True, clean_u
    except Exception as e:
        return False, f"URL 解析失败: {e}"


class SearchProvider(ABC):
    """Search Provider 统一抽象接口基类"""

    @abstractmethod
    def test_connection(self) -> SearchConnectionResult:
        """测试搜索服务连通性与密钥有效性 (仅执行最小请求，避免费用消耗)"""
        pass

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
        """根据查询词检索公开网页，返回真实标题、URL、摘要和域名"""
        pass

    def fetch(self, url: str) -> Optional[Dict[str, Any]]:
        """根据网页 URL 获取其正文内容 (若 Provider 支持原生网页提取则实现，如 Kimi /tools/fetch)"""
        return None

    @abstractmethod
    def provider_name(self) -> str:
        """返回 Provider 名称标识"""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """是否已配置有效凭据或数据源"""
        pass

    @abstractmethod
    def sanitize_result(self, raw_item: Dict[str, Any], query: str, rank: int = 0) -> SearchResultItem:
        """清洗原始搜索结果，验证 URL 合法性并标准化输出结构"""
        pass

    @abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        """返回当前 Provider 的能力元数据"""
        pass
