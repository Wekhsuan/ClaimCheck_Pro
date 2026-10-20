"""ClaimCheck Pro V0.1 配置管理模块

严格限制路径在工作区内部 (跨平台支持 Windows/Linux/macOS)
"""

import os
from pathlib import Path
from pydantic import BaseModel, Field

# 根目录与关键目录定义 (动态解析项目根目录，兼容本地与 Streamlit Cloud)
BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / ".cache"
DOWNLOADS_DIR = BASE_DIR / "downloads"
OUTPUT_DIR = BASE_DIR / "output"
REPORTS_DIR = BASE_DIR / "reports"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
MOCK_DATA_DIR = BASE_DIR / "mock_data"
STREAMLIT_APP_DIR = BASE_DIR / "streamlit_app"

# 确保目录存在
for directory in [CACHE_DIR, DOWNLOADS_DIR, OUTPUT_DIR, REPORTS_DIR, SCREENSHOTS_DIR, MOCK_DATA_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

class ServiceConfig(BaseModel):
    """服务配置模型"""
    service_mode: str = Field(default="mock", description="服务模式：mock / byok / local")
    
    # BYOK 占位配置 (V0.1阶段不调用实际云端)
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    openai_api_key: str = Field(default="")
    openai_model_name: str = Field(default="gpt-4o-mini")
    openai_vision_model: str = Field(default="gpt-4o-mini")
    
    # 本地模型占位配置
    local_base_url: str = Field(default="http://127.0.0.1:11434/v1")
    local_model_name: str = Field(default="qwen2.5:7b")
    
    # 预算与安全控制限制
    max_claims: int = Field(default=5, description="单次最大声明数")
    max_search_results: int = Field(default=5, description="每条声明最大检索数")
    max_model_calls: int = Field(default=5, description="单任务最大模型调用次数")
    timeout_seconds: int = Field(default=60, description="单任务超时时间(秒)")
    enable_background_tasks: bool = Field(default=False, description="是否开启后台自动任务")

# 全局默认配置实例
default_config = ServiceConfig()
