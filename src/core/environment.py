"""ClaimCheck Pro 部署环境感知与公网资源配额管控模块

负责区分 LOCAL (本地桌面运行) 与 STREAMLIT_CLOUD (Streamlit Community Cloud 公网部署)，
并执行严格的云端安全限制、内存存储与配额管控。
"""

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple


class DeploymentEnvironment:
    LOCAL = "LOCAL"
    STREAMLIT_CLOUD = "STREAMLIT_CLOUD"


# 云端默认配额限制规范 (防滥用、防 OOM、零持久化存储)
CLOUD_LIMITS = {
    "max_image_size_mb": 8,
    "max_image_count": 5,
    "max_user_text_length": 5000,
    "max_claims_count": 5,
    "max_search_results_per_claim": 3,
    "max_search_requests_per_task": 5,
    "max_model_calls_per_task": 10,
    "max_retries": 1,
    "task_timeout_seconds": 120,
}

# 本地桌面端默认配额限制
LOCAL_LIMITS = {
    "max_image_size_mb": 20,
    "max_image_count": 10,
    "max_user_text_length": 20000,
    "max_claims_count": 10,
    "max_search_results_per_claim": 5,
    "max_search_requests_per_task": 20,
    "max_model_calls_per_task": 50,
    "max_retries": 2,
    "task_timeout_seconds": 300,
}


def detect_deployment_environment() -> str:
    """自动检测当前运行环境为 LOCAL 还是 STREAMLIT_CLOUD
    
    检测依据：
    1. 显式环境变量 DEPLOYMENT_ENV
    2. Streamlit Community Cloud 容器环境特征 (STREAMLIT_SHARING_HOST, /mount/src, /app)
    3. Linux 容器特定主机名前缀
    """
    env_override = os.environ.get("DEPLOYMENT_ENV", "").strip().upper()
    if env_override in (DeploymentEnvironment.LOCAL, DeploymentEnvironment.STREAMLIT_CLOUD):
        return env_override

    # Streamlit Cloud 容器环境变量与路径特征
    is_streamlit_cloud = bool(
        os.environ.get("STREAMLIT_SERVER_ENVIRONMENT")
        or os.environ.get("STREAMLIT_SHARING_HOST")
        or os.environ.get("IS_STREAMLIT_CLOUD")
        or os.path.exists("/mount/src")
        or (os.path.exists("/app") and not sys.platform.startswith("win"))
        or os.environ.get("HOSTNAME", "").lower().startswith("streamlit")
    )

    if is_streamlit_cloud:
        return DeploymentEnvironment.STREAMLIT_CLOUD
    return DeploymentEnvironment.LOCAL


def is_streamlit_cloud() -> bool:
    """是否运行在 Streamlit Community Cloud 公网环境"""
    return detect_deployment_environment() == DeploymentEnvironment.STREAMLIT_CLOUD


def get_current_limits() -> dict:
    """获取当前部署环境对应的配额与限制参数"""
    if is_streamlit_cloud():
        return dict(CLOUD_LIMITS)
    return dict(LOCAL_LIMITS)


def validate_user_text_input(text: str) -> Tuple[bool, str]:
    """校验用户输入的商品详情文本长度"""
    if not text:
        return True, ""
    limits = get_current_limits()
    max_len = limits["max_user_text_length"]
    if len(text) > max_len:
        return False, f"输入文本长度超限：当前长度为 {len(text)} 字符，公网限制最大为 {max_len} 字符。"
    return True, ""


def validate_uploaded_images(files: list) -> Tuple[bool, str]:
    """校验上传的截图文件数量与单张体积"""
    if not files:
        return True, ""
    limits = get_current_limits()
    max_count = limits["max_image_count"]
    max_mb = limits["max_image_size_mb"]

    if len(files) > max_count:
        return False, f"单次上传图片数量超限：当前上传了 {len(files)} 张，限制最多 {max_count} 张。"

    for f in files:
        size_bytes = getattr(f, "size", 0)
        size_mb = size_bytes / (1024 * 1024)
        if size_mb > max_mb:
            name = getattr(f, "name", "未知图片")
            return False, f"图片 [{name}] 体积超限 ({size_mb:.1f}MB)，单张图片最大允许 {max_mb}MB。"

    return True, ""
