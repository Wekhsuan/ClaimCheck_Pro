"""ClaimCheck Pro 友好错误与空状态标准化处理器
严格遵循阶段五规范：
所有错误与空状态必须明确阐述：
1. 发生了什么 (what_happened)
2. 为什么发生 (why_it_happened)
3. 用户下一步能做什么 (what_to_do_next)
严禁向普通用户展示长篇 Python 堆栈或模糊提示。
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class FriendlyErrorDetail(BaseModel):
    """友好错误与空状态详情"""
    error_code: str = Field(..., description="标准错误标识代码")
    error_stage: str = Field(..., description="所属业务阶段")
    title: str = Field(..., description="友好简明标题")
    what_happened: str = Field(..., description="发生了什么")
    why_it_happened: str = Field(..., description="为什么发生")
    what_to_do_next: str = Field(..., description="用户下一步能做什么")
    retryable: bool = Field(default=False, description="是否支持一键重试")
    technical_note: Optional[str] = Field(default="", description="技术备注（不含敏感Key）")

    def to_legacy_user_message(self) -> str:
        return (
            f"**现象**：{self.what_happened}\n\n"
            f"**原因**：{self.why_it_happened}\n\n"
            f"**建议**：{self.what_to_do_next}"
        )


# 12 类标准空状态与错误定义
ERROR_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "NO_INPUT": {
        "error_stage": "提交商品资料",
        "title": "尚未提供商品资料",
        "what_happened": "系统未检测到任何待核验的商品内容。",
        "why_it_happened": "商品链接框为空、详情文本未粘贴或未上传商品宣传截图。",
        "what_to_do_next": "请在上方输入公开商品链接、粘贴规格文本或上传清晰宣传截图，也可展开【试用预置演示案例】一键体验。",
        "retryable": False,
    },
    "NO_VALID_CLAIMS": {
        "error_stage": "拆解宣传声明",
        "title": "未提取到可验证宣传声明",
        "what_happened": "系统无法从当前提供的资料中提炼出具备明确客观标准的宣传事实。",
        "why_it_happened": "输入内容可能仅包含主观形容词（如“尊贵享受”、“高端大气”）、平台导航废话或截图文字严重模糊。",
        "what_to_do_next": "请补充包含具体数值、单位、功能、材料、功率或续航规格的商品参数文本重新尝试。",
        "retryable": False,
    },
    "PAGE_ACCESS_RESTRICTED": {
        "error_stage": "读取商品信息",
        "title": "商品网页读取访问受限",
        "what_happened": "自动读取商品公开链接失败，触发了目标电商平台的访问保护机制。",
        "why_it_happened": "京东、淘宝、拼多多等电商平台对自动化访问设置了反爬风控、验证码或强制登录墙。",
        "what_to_do_next": "推荐点击下方【粘贴商品详情文本】直接粘贴商品文案，或上传商品宣传截图继续无缝核验。",
        "retryable": True,
    },
    "MODEL_NOT_CONNECTED": {
        "error_stage": "AI模型服务连接",
        "title": "AI 语言模型服务未连接",
        "what_happened": "系统无法与配置的语言模型服务端点建立有效通信。",
        "why_it_happened": "当前处于真实服务模式（BYOK/Local），但 API Key 无效、Base URL 地址错误或本地模型服务（如 Ollama）未启动。",
        "what_to_do_next": "请展开顶部【服务模式与端点设置】，检查 API Key 与端点地址是否正确，并点击【测试连接】验证。",
        "retryable": True,
    },
    "SEARCH_NOT_CONFIGURED": {
        "error_stage": "网络证据检索",
        "title": "网络搜索服务未配置",
        "what_happened": "系统当前未配置独立的实时网络搜索服务，无法发起公网检索。",
        "why_it_happened": "当前网络搜索模式选择为“未配置 (none)”，且未录入用户自带搜索 Key 或手动参考材料。",
        "what_to_do_next": "您可以在【服务设置】中配置用户自带 Tavily API Key，或在【高级选项】中手动补充官方技术材料链接继续核验。",
        "retryable": False,
    },
    "SEARCH_CONNECTION_FAILED": {
        "error_stage": "网络搜索服务连接",
        "title": "搜索服务探测连接失败",
        "what_happened": "向搜索服务提供商发送探测请求时未能获得成功响应。",
        "why_it_happened": "搜索 API Key 无效、账户配额耗尽 (HTTP 429) 或网络连接超时。",
        "what_to_do_next": "请检查 Tavily API Key 是否正确有效，确认账户内仍有调用余量，稍后重试测试连接。",
        "retryable": True,
    },
    "SEARCH_RESULT_EMPTY": {
        "error_stage": "公开网页检索",
        "title": "公网未检索到匹配结果",
        "what_happened": "根据商品型号与核心关键词在公开网络上未检索到有效网页线索。",
        "why_it_happened": "商品可能属于全新上市冷门产品、定制非标型号，或者宣传关键词过于宽泛未收录。",
        "what_to_do_next": "建议在【高级选项】中手动提供品牌官方说明书、技术参数表页面链接作为核验依据。",
        "retryable": False,
    },
    "CANDIDATE_WEBPAGE_RESTRICTED": {
        "error_stage": "候选网页正文抓取",
        "title": "候选证据网页抓取受限",
        "what_happened": "尝试提取候选证据网页正文时遭遇登录墙或滑块验证拦截。",
        "why_it_happened": "第三方参考站点设置了严格防抓取策略或需要会员登录后方可阅读全文。",
        "what_to_do_next": "系统已合规排除受阻网页，您可手动打开该网页复制正文片段粘贴至【高级选项-补充材料】中。",
        "retryable": False,
    },
    "MODEL_MISMATCH_OR_UNCERTAIN": {
        "error_stage": "商品型号对齐审查",
        "title": "商品型号指向存在歧义",
        "what_happened": "检索到的参考资料与被核验商品型号未完全对应（如同系列不同子型号或仅同品牌）。",
        "why_it_happened": "商家宣传文案可能混淆了标准版与旗舰版，或公开资料仅涵盖基础系列产品。",
        "what_to_do_next": "请核对商品机身铭牌上的精确型号代号，在商品身份卡片中修正标准型号后重新核验。",
        "retryable": True,
    },
    "INSUFFICIENT_EVIDENCE": {
        "error_stage": "多源交叉核验",
        "title": "核验凭证不足（非假货定性）",
        "what_happened": "针对该项宣传声明，系统在当前检索范围内未搜集到同型号高可信度实测或官方数据支持。",
        "why_it_happened": "公开网络缺乏针对该特性的专项实验室实测或拆解报告，官方规格书未明确披露对应指标数值。",
        "what_to_do_next": "建议在购买前直接向品牌官方客服索取第三方质检报告，并保留商家聊天承诺记录以备维权。",
        "retryable": False,
    },
    "USER_CANCELLED": {
        "error_stage": "流程调度控制",
        "title": "核验任务已由用户取消",
        "what_happened": "当前核验分析流水线已被主动中止。",
        "why_it_happened": "用户点击了取消或新建核验操作，已终止正在运行的推理与网络请求。",
        "what_to_do_next": "您可以修改输入资料、调整服务设置后重新点击【开始核验分析】。",
        "retryable": False,
    },
    "REPORT_GENERATION_FAILED": {
        "error_stage": "专业报告装配",
        "title": "核验报告组装生成异常",
        "what_happened": "核验流水线在组装最终报告或保存本地落盘时遭遇异常中断。",
        "why_it_happened": "中间数据校验未通过、本地磁盘写入权限不足或意外网络连接断开。",
        "what_to_do_next": "请检查磁盘写入权限，或点击上方【开始核验分析】重新触发全流程核验。",
        "retryable": True,
    },
}


def create_friendly_error(error_code: str, custom_technical_note: str = "") -> FriendlyErrorDetail:
    """创建标准化的友好错误详情对象"""
    defn = ERROR_DEFINITIONS.get(error_code, {
        "error_stage": "系统执行",
        "title": "操作未完成",
        "what_happened": f"系统在执行过程中遭遇意外状况 (代码: {error_code})。",
        "why_it_happened": "服务响应异常或输入数据格式不符合预期规范。",
        "what_to_do_next": "建议刷新页面重新尝试，或检查输入内容后再次核验。",
        "retryable": True,
    })

    return FriendlyErrorDetail(
        error_code=error_code,
        error_stage=defn["error_stage"],
        title=defn["title"],
        what_happened=defn["what_happened"],
        why_it_happened=defn["why_it_happened"],
        what_to_do_next=defn["what_to_do_next"],
        retryable=defn.get("retryable", False),
        technical_note=custom_technical_note,
    )
