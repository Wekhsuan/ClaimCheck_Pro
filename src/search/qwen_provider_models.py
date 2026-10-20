# -*- coding: utf-8 -*-
"""Qwen Provider Models Catalog (千问模型与平台能力独立配置文件)

根据《千问搜索服务改造规范》：
1. 明确区分两大服务来源：
   - 千问AI平台 (MaaS): https://maas.qianwenaiapi.com/compatible-mode/v1
   - 阿里云百炼 (DashScope): https://dashscope.aliyuncs.com/compatible-mode/v1
2. 动态维护千问模型与能力矩阵，禁止写死在前端页面或单处代码；
3. 支持动态过滤与“手动输入模型ID”校验。
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class QwenModelInfo(BaseModel):
    """千问模型元数据与多维能力定义"""
    model_id: str = Field(..., description="官方模型标识")
    display_name: str = Field(..., description="前端呈现名称")
    provider_platform: str = Field(..., description="所属平台: qianwen_ai / dashscope / both")
    supports_chat: bool = Field(default=True, description="是否支持标准 Chat Completions")
    supports_responses: bool = Field(default=True, description="是否支持 Responses API 架构")
    supports_web_search: bool = Field(default=True, description="是否支持 web_search 联网检索")
    supports_web_extractor: bool = Field(default=False, description="是否支持 web_extractor 网页正文提取器")
    supports_vision: bool = Field(default=False, description="是否支持多模态图片输入与视觉解析")
    supports_source_urls: bool = Field(default=True, description="是否能够返回真实可溯源的来源 URL")
    description: str = Field(default="", description="功能特性简短描述")


# 平台预设配置
QWEN_PLATFORM_CONFIGS: Dict[str, Dict[str, Any]] = {
    "qianwen_ai": {
        "platform_id": "qianwen_ai",
        "name": "千问AI平台",
        "base_url": "https://maas.qianwenaiapi.com/compatible-mode/v1",
        "default_mode": "responses",
        "default_model": "qwen3.8-flash",
        "tip": "💡 请使用千问AI平台控制台生成的 API Key。",
        "placeholder": "sk-...",
        "recommended_mode_tip": "推荐使用 Responses API 模式，完整挂载 web_search 与 web_extractor 获取真实正文与来源超链接。",
    },
    "dashscope": {
        "platform_id": "dashscope",
        "name": "阿里云百炼DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_mode": "chat_completions",
        "default_model": "qwen-plus",
        "tip": "💡 请使用阿里云百炼控制台生成的 DashScope API Key。",
        "placeholder": "sk-...",
        "recommended_mode_tip": "Chat Completions 模式通过 enable_search=true 联网，若无来源URL返回将标明不可追溯并禁止评定为A级证据。",
    },
}


# 模型完整目录
QWEN_MODELS_CATALOG: Dict[str, QwenModelInfo] = {
    # ------------------ 千问AI平台专区 ------------------
    "qwen3.8-flash": QwenModelInfo(
        model_id="qwen3.8-flash",
        display_name="Qwen 3.8 Flash (极速/多模态/搜索/正文提取 · 默认推荐)",
        provider_platform="qianwen_ai",
        supports_chat=True,
        supports_responses=True,
        supports_web_search=True,
        supports_web_extractor=True,
        supports_vision=True,
        supports_source_urls=True,
        description="新一代极速多模态模型，支持图片理解与 Responses API 深度联网",
    ),
    "qwen3.8-max": QwenModelInfo(
        model_id="qwen3.8-max",
        display_name="Qwen 3.8 Max (超强推理/多模态/深度联网)",
        provider_platform="qianwen_ai",
        supports_chat=True,
        supports_responses=True,
        supports_web_search=True,
        supports_web_extractor=True,
        supports_vision=True,
        supports_source_urls=True,
        description="旗舰级多模态模型，具备高复杂度因果推理与深度交叉验证能力",
    ),
    "qwen3.7-plus": QwenModelInfo(
        model_id="qwen3.7-plus",
        display_name="Qwen 3.7 Plus (均衡增强型)",
        provider_platform="qianwen_ai",
        supports_chat=True,
        supports_responses=True,
        supports_web_search=True,
        supports_web_extractor=True,
        supports_vision=False,
        supports_source_urls=True,
        description="高性能文本模型，支持大批量并发与 Responses API 搜索",
    ),
    "qwen3.7-flash": QwenModelInfo(
        model_id="qwen3.7-flash",
        display_name="Qwen 3.7 Flash (轻量高效型)",
        provider_platform="qianwen_ai",
        supports_chat=True,
        supports_responses=True,
        supports_web_search=True,
        supports_web_extractor=True,
        supports_vision=False,
        supports_source_urls=True,
        description="极低延迟轻量级模型，适用于高频快速检索场景",
    ),

    # ------------------ 阿里云百炼 DashScope 专区 ------------------
    "qwen-plus": QwenModelInfo(
        model_id="qwen-plus",
        display_name="Qwen Plus (百炼均衡版)",
        provider_platform="dashscope",
        supports_chat=True,
        supports_responses=True,
        supports_web_search=True,
        supports_web_extractor=False,
        supports_vision=False,
        supports_source_urls=False,
        description="阿里云百炼经典通用模型，支持 enable_search 联网回答",
    ),
    "qwen-max": QwenModelInfo(
        model_id="qwen-max",
        display_name="Qwen Max (百炼旗舰版)",
        provider_platform="dashscope",
        supports_chat=True,
        supports_responses=True,
        supports_web_search=True,
        supports_web_extractor=False,
        supports_vision=False,
        supports_source_urls=False,
        description="百炼旗舰模型，具备卓越数学推理与通用语言能力",
    ),
    "qwen-turbo": QwenModelInfo(
        model_id="qwen-turbo",
        display_name="Qwen Turbo (百炼轻量版)",
        provider_platform="dashscope",
        supports_chat=True,
        supports_responses=False,
        supports_web_search=True,
        supports_web_extractor=False,
        supports_vision=False,
        supports_source_urls=False,
        description="百炼经济型高通量文本模型",
    ),
}


def get_qwen_models_for_platform(platform: str, api_mode: Optional[str] = None) -> List[QwenModelInfo]:
    """根据所选服务平台和调用模式动态过滤可用的模型列表"""
    target_platform = (platform or "qianwen_ai").lower().strip()
    result = []
    for model_info in QWEN_MODELS_CATALOG.values():
        if model_info.provider_platform in [target_platform, "both"]:
            if api_mode == "responses" and not model_info.supports_responses:
                continue
            result.append(model_info)
    return result


def validate_custom_model_id(model_id: str) -> Tuple[bool, str]:
    """校验手动输入的官方 Model ID 格式合法性"""
    clean_id = (model_id or "").strip()
    if not clean_id:
        return False, "模型 ID 不能为空"
    if len(clean_id) < 3 or len(clean_id) > 64:
        return False, "模型 ID 长度应在 3 ~ 64 个字符之间"
    # 允许字母、数字、点号、短横线、下划线及冒号 (如 qwen2.5-vl:7b, qwen3.8-flash)
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\.\-_:]{2,63}$", clean_id):
        return False, "模型 ID 格式不规范，仅允许以字母数字开头，包含字母、数字、点、横杠、下划线与冒号"
    return True, clean_id


def get_or_create_model_info(model_id: str, platform: str = "qianwen_ai") -> QwenModelInfo:
    """获取已知模型定义或为手动输入的自定义模型构建动态能力元数据"""
    clean_id = (model_id or "").strip()
    if clean_id in QWEN_MODELS_CATALOG:
        return QWEN_MODELS_CATALOG[clean_id]

    # 对于手动输入的模型，不可默认其支持搜索或视觉，初始设定需经过探活测试
    vision_kws = ["vl", "vision", "3.8"]
    is_vision = any(k in clean_id.lower() for k in vision_kws)
    return QwenModelInfo(
        model_id=clean_id,
        display_name=f"{clean_id} (自定义输入)",
        provider_platform=platform,
        supports_chat=True,
        supports_responses=(platform == "qianwen_ai"),
        supports_web_search=False,  # 绝不能盲目假定未知模型支持搜索
        supports_web_extractor=False,
        supports_vision=is_vision,
        supports_source_urls=False,
        description="用户手动输入的自定义模型标识，需通过能力探活确认支持的特性",
    )


def is_vision_supported(model_id: str) -> bool:
    """快速检查模型是否原生支持多模态视觉图片输入"""
    info = get_or_create_model_info(model_id)
    return bool(info.supports_vision)
