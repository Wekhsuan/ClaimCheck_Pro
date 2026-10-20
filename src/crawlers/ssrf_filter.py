"""ClaimCheck Pro SSRF 与安全网络过滤器 (SSRF & Web Security Guard)

严格执行安全红线：
1. 仅允许 http 和 https 协议；
2. 拦截回环(127.0.0.0/8)、私有内网(10/8, 172.16/12, 192.168/16)、链路本地(169.254/16)及广播地址；
3. 防御 301/302 跨协议重定向型 SSRF；
4. 校验 Content-Type，仅允许网页内容，拒绝非网页流或二进制大文件。
"""

import ipaddress
import socket
from urllib.parse import urlparse
from typing import Tuple, Optional
import requests


class SSRFSecurityError(Exception):
    """SSRF 安全违规异常"""
    pass


class InvalidContentTypeError(Exception):
    """非网页内容类型异常"""
    pass


def is_ip_safe(ip_str: str) -> bool:
    """检查单个 IP 是否为安全的公网地址，杜绝访问私有或危险内网"""
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.is_loopback:
            return False
        if ip.is_private:
            return False
        if ip.is_reserved:
            return False
        if ip.is_link_local:
            return False
        if ip.is_multicast:
            return False
        if ip.is_unspecified:
            return False
        # 拦截 0.0.0.0/8
        if isinstance(ip, ipaddress.IPv4Address) and str(ip).startswith("0."):
            return False
        return True
    except ValueError:
        return False


def validate_public_url(url: str) -> Tuple[bool, str]:
    """验证 URL 格式是否合法且指向公网安全目标"""
    if not url or not url.strip():
        return False, "URL 不能为空"

    clean_url = url.strip()
    try:
        parsed = urlparse(clean_url)
    except Exception as e:
        return False, f"URL 解析失败: {e}"

    # 1. 协议限制：只允许 http 和 https
    scheme = parsed.scheme.lower()
    if scheme not in ["http", "https"]:
        return False, f"不支持的协议 '{scheme}'，仅允许 http 和 https 访问"

    # 2. 必须包含主机名
    hostname = parsed.hostname
    if not hostname:
        return False, "URL 必须包含有效的主机名或域名"

    # 3. 拦截 localhost 或 .local
    if hostname.lower() in ["localhost", "localhost.localdomain"] or hostname.lower().endswith(".local"):
        return False, "安全拦截：禁止访问本地回环或局域网主机"

    # 4. 解析目标 IP 并进行安全检测
    try:
        # 获取所有解析 IP
        addr_info = socket.getaddrinfo(hostname, None)
        ips = {item[4][0] for item in addr_info}
        for ip in ips:
            if not is_ip_safe(ip):
                return False, f"安全拦截：目标域名解析到非公网私有或危险保留地址 ({ip})，禁止访问"
    except socket.gaierror as e:
        return False, f"DNS 解析失败：无法解析目标域名 '{hostname}' ({e})"
    except Exception as e:
        return False, f"网络地址安全检测发生异常: {e}"

    return True, clean_url


def safe_fetch_html_with_metadata(url: str, timeout: int = 15, max_bytes: int = 5 * 1024 * 1024) -> dict:
    """安全拉取公开网页 HTML 内容并返回元数据 (html, http_status, final_url)
    
    包含：
    1. URL 安全校验与重定向跟踪防护
    2. Content-Type 检查 (仅允许网页)
    3. 最大响应体大小限制 (默认5MB，防止消耗内存)
    """
    is_valid, validated_url = validate_public_url(url)
    if not is_valid:
        raise SSRFSecurityError(validated_url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36 ClaimCheckPro/0.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    # 创建自定义 session 禁止无节制自动重定向，手动验证每跳重定向安全
    session = requests.Session()
    current_url = validated_url

    for hop in range(5):  # 最大5次重定向
        resp = session.get(current_url, headers=headers, timeout=timeout, allow_redirects=False, stream=True)

        # 处理 301/302 重定向
        if resp.status_code in [301, 302, 303, 307, 308]:
            redirect_target = resp.headers.get("Location")
            if not redirect_target:
                break
            # 补齐相对路径
            from urllib.parse import urljoin
            next_url = urljoin(current_url, redirect_target)
            
            # 校验重定向目标安全
            is_target_safe, safe_or_err = validate_public_url(next_url)
            if not is_target_safe:
                raise SSRFSecurityError(f"重定向链中发现危险目标: {safe_or_err}")
            current_url = safe_or_err
            continue

        # 检查最终响应状态
        # 检查 Content-Type
        content_type = resp.headers.get("Content-Type", "").lower()
        allowed_types = ["text/html", "application/xhtml+xml", "text/plain"]
        if not any(t in content_type for t in allowed_types):
            raise InvalidContentTypeError(
                f"拒绝接收非网页内容类型 (Content-Type: '{content_type}')，仅允许文本或HTML网页"
            )

        # 读取内容并限制最大字节数
        content_chunks = []
        total_len = 0
        for chunk in resp.iter_content(chunk_size=16384):
            total_len += len(chunk)
            if total_len > max_bytes:
                raise ValueError(f"网页内容体积超过限制 ({max_bytes} 字节)")
            content_chunks.append(chunk)

        body_bytes = b"".join(content_chunks)
        # 尝试使用正确的编码解码
        encoding = resp.encoding or "utf-8"
        try:
            html_text = body_bytes.decode(encoding, errors="replace")
        except Exception:
            html_text = body_bytes.decode("utf-8", errors="replace")

        return {
            "html": html_text,
            "http_status": resp.status_code,
            "final_url": current_url,
        }

    raise ValueError("重定向跳转次数过多 (超过5次)")


def safe_fetch_html(url: str, timeout: int = 15, max_bytes: int = 5 * 1024 * 1024) -> str:
    """安全拉取公开网页 HTML 内容 (向后兼容)"""
    res = safe_fetch_html_with_metadata(url, timeout=timeout, max_bytes=max_bytes)
    return res["html"]
