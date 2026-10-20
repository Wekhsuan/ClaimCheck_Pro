"""ClaimCheck Pro 安全与脱敏核心模块 (Security & Masker)

严格执行零费用架构安全红线：
1. API Key 全链路脱敏显示与记录；
2. 公网 Base URL 强制仅允许 HTTPS；
3. 本地模型端点仅允许 localhost / 127.0.0.1 及合法局域网地址。
"""

import ipaddress
import re
from urllib.parse import urlparse
from typing import Tuple


def mask_api_key(api_key: str) -> str:
    """对 API Key 进行脱敏处理，严禁在日志、界面或持久化中暴露明文
    
    >>> mask_api_key("sk-abcdef1234567890")
    'sk-ab****90'
    >>> mask_api_key("short")
    '******'
    """
    if not api_key:
        return ""
    clean_key = api_key.strip()
    if len(clean_key) <= 6:
        return "******"
    if clean_key.startswith("sk-") and len(clean_key) > 8:
        prefix = clean_key[:5]  # 例如 sk-ab
        suffix = clean_key[-2:]  # 例如 90
        return f"{prefix}****{suffix}"
    prefix = clean_key[:2]
    suffix = clean_key[-2:]
    return f"{prefix}****{suffix}"


def mask_search_api_key(api_key: str) -> str:
    """对搜索 API Key (如 Tavily) 进行脱敏处理
    
    >>> mask_search_api_key("tvly-abcdef1234569A2B")
    'tvly-****9A2B'
    """
    if not api_key:
        return ""
    clean_key = api_key.strip()
    if clean_key.startswith("tvly-") and len(clean_key) >= 9:
        suffix = clean_key[-4:]
        return f"tvly-****{suffix}"
    if len(clean_key) <= 6:
        return "******"
    if len(clean_key) > 8:
        return f"{clean_key[:4]}****{clean_key[-4:]}"
    return f"{clean_key[:2]}****{clean_key[-2:]}"


def mask_key_in_text(text: str, key: str) -> str:
    """在文本或异常日志中脱敏指定 API Key，杜绝异常堆栈泄露明文"""
    if not text or not key or len(key.strip()) < 4:
        return text
    clean_key = key.strip()
    masked = mask_search_api_key(clean_key)
    return text.replace(clean_key, masked)


def validate_byok_url(base_url: str) -> Tuple[bool, str]:
    """验证用户自带公网 API Base URL 的合法性与安全性
    
    安全规则：公网地址强制要求仅允许 HTTPS 传输，杜绝凭据明文被窃听。
    """
    if not base_url or not base_url.strip():
        return False, "Base URL 不能为空"
    
    url = base_url.strip()
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"URL 解析失败: {e}"

    if parsed.scheme.lower() != "https":
        return False, "公网自定义 Base URL 仅允许使用安全的 HTTPS 协议 (禁止使用不加密的 HTTP)"

    if not parsed.netloc:
        return False, "Base URL 必须包含有效的主机域名或地址"

    return True, url.rstrip("/")


def validate_local_url(base_url: str) -> Tuple[bool, str]:
    """验证用户本地模型端点 Base URL 的合法性
    
    允许地址范围：
    1. localhost
    2. 127.0.0.1
    3. 合法局域网内网地址 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    """
    if not base_url or not base_url.strip():
        return False, "本地模型端点地址不能为空"

    url = base_url.strip()
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"本地端点解析失败: {e}"

    if parsed.scheme.lower() not in ["http", "https"]:
        return False, "本地模型端点协议必须为 http 或 https"

    hostname = parsed.hostname
    if not hostname:
        return False, "本地端点必须包含有效主机名或IP"

    # 1. 允许 localhost
    if hostname.lower() == "localhost":
        return True, url.rstrip("/")

    # 2. 检查是否为回环或私有局域网 (RFC 1918)
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_loopback:
            return True, url.rstrip("/")
        
        # 仅允许标准私有局域网网段 (10/8, 172.16/12, 192.168/16)
        lan_networks = [
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
        ]
        if any(ip in net for net in lan_networks):
            return True, url.rstrip("/")

        return False, f"本地模型端点仅允许回环地址(127.0.0.1)或局域网私有地址，禁止配置公网或外部IP: {hostname}"
    except ValueError:
        # 如果是局域网域名（如 .local 或无点的主机名）
        if hostname.endswith(".local") or "." not in hostname:
            return True, url.rstrip("/")
        return False, f"非法的主机名，本地模式不支持未知公网域名: {hostname}"
