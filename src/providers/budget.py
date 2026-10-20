"""ClaimCheck Pro 调用预算与开销管理模块 (Budget Guard)

严格防止超额调用，杜绝隐性费用，执行预算拦截
"""

from typing import Dict
from pydantic import BaseModel, Field


class BudgetExceededError(Exception):
    """超出调用预算异常"""
    pass


class BudgetLimits(BaseModel):
    """调用预算上限配置"""
    max_claims: int = Field(default=5, description="单次最多核验声明数")
    max_search_results: int = Field(default=5, description="每条声明最大检索数")
    max_model_calls: int = Field(default=5, description="单任务最大模型调用次数")
    max_tokens_per_call: int = Field(default=2048, description="单次调用最大Token数")
    max_retries: int = Field(default=2, description="最大自动重试次数")
    timeout_seconds: int = Field(default=60, description="单任务超时时间(秒)")


class BudgetTracker:
    """单次任务预算跟踪器"""

    def __init__(self, limits: BudgetLimits = None):
        self.limits = limits or BudgetLimits()
        self.total_model_calls = 0
        self.total_tokens_estimated = 0
        self.total_search_queries = 0

    def record_model_call(self, estimated_tokens: int = 500):
        """记录一次模型调用并检查是否超额"""
        if self.total_model_calls >= self.limits.max_model_calls:
            raise BudgetExceededError(
                f"已达到单任务最大模型调用次数上限 ({self.limits.max_model_calls} 次)。"
                "为保护用户账户余额，系统已自动停止进一步调用，不回退至任何付费服务。"
            )
        self.total_model_calls += 1
        self.total_tokens_estimated += estimated_tokens

    def record_search_query(self):
        """记录一次网络检索"""
        max_searches = self.limits.max_claims * self.limits.max_search_results
        if self.total_search_queries >= max_searches:
            raise BudgetExceededError(
                f"已达到单任务最大网络检索次数上限 ({max_searches} 条)。系统已自动停止进一步检索。"
            )
        self.total_search_queries += 1

    def get_preflight_summary(
        self,
        claims_count: int,
        service_mode: str,
        search_mode: str = "none",
        manual_evidence_count: int = 0,
    ) -> Dict[str, str]:
        """生成任务开始前的预计开销提示信息"""
        actual_claims = min(claims_count, self.limits.max_claims)
        est_model_calls = min(actual_claims + 1, self.limits.max_model_calls)

        if search_mode == "tavily":
            search_requests = f"最多 {actual_claims} 次 (每条声明1次)"
            search_results_cap = f"每次最多 {self.limits.max_search_results} 条"
            search_payer = "用户自有 Tavily 账户 (由用户自理，开发者0代付)"
        elif search_mode == "manual":
            search_requests = "0 次 (人工提供)"
            search_results_cap = f"已载入 {manual_evidence_count} 条证据链接"
            search_payer = "零费用 (用户手动补充)"
        else:
            search_requests = "0 次 (未配置搜索)"
            search_results_cap = "不发起网络检索"
            search_payer = "零费用 (不产生网络检索)"

        payer = {
            "mock": "零费用 (Mock 离线预置数据)",
            "byok": "用户自带第三方账户 (由用户自理，开发者0代付)",
            "local": "用户自有本地硬件资源 (0第三方调用费用)",
        }.get(service_mode, "用户自理")

        return {
            "claims_count": f"{actual_claims} 条 (上限 {self.limits.max_claims} 条)",
            "estimated_model_calls": f"约 {est_model_calls} 次 (上限 {self.limits.max_model_calls} 次)",
            "estimated_searches": search_requests,
            "search_requests_count": search_requests,
            "max_search_results_per_claim": f"{self.limits.max_search_results} 条",
            "search_results_cap": search_results_cap,
            "max_retries": f"{self.limits.max_retries} 次",
            "timeout_limit": f"{self.limits.timeout_seconds} 秒",
            "payer": payer,
            "search_payer": search_payer,
            "search_mode": search_mode,
        }
