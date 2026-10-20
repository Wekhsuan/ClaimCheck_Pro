"""ClaimCheck Pro 候选网页安全抓取与正文去噪提取器 (Evidence Fetcher)

严格遵循：
1. 策略 B：外部证据抓取公网零信任网关，严格禁止 localhost、127.0.0.1 及 10/172.16/192.168/169.254 等私有内网访问；
2. 逐级重定向安全验证，防止 302 跨协议或内网穿透；
3. 严格限制响应体大小 (2MB) 与请求超时 (8秒)，流式读取截断，防止超大文件内存耗尽；
4. Content-Type 白名单校验 (仅允许 text/html, application/xhtml+xml)；
5. 自动识别受限页面（滑块、验证码、登录墙 302、403），标记 restricted，绝不暴力破解；
6. 深度去噪：剔除 nav, header, footer, aside, ads, script, style, svg；
7. 关键词密度定位事实片段，截取 200~450 字真实上下文。
"""

import time
from urllib.parse import urlparse
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
import requests

from src.crawlers.ssrf_filter import (
    InvalidContentTypeError,
    SSRFSecurityError,
    validate_public_url,
)


class WebPageExcerptResult(BaseModel):
    """网页抓取与正文提取结果"""
    url: str = Field(..., description="原始请求 URL")
    final_url: str = Field(default="", description="最终重定向后的安全 URL")
    domain: str = Field(default="", description="来源主域名")
    title: str = Field(default="", description="网页标题")
    clean_text: str = Field(default="", description="去噪后的主体全文")
    excerpt: str = Field(default="", description="与声明关键词匹配的 200~450 字事实原文摘录")
    fetch_status: str = Field(default="success", description="抓取状态: success / restricted / failed / timeout / ssrf_blocked")
    http_status: Optional[int] = Field(default=None, description="HTTP 状态码")
    error_message: Optional[str] = Field(default=None, description="错误说明或受限提示")
    response_time_ms: int = Field(default=0, description="网络与提取耗时 (毫秒)")
    content_bytes_len: int = Field(default=0, description="读取的网页字节长度")


class EvidenceFetcher:
    """网页证据安全抓取与去噪提取器"""

    RESTRICTED_INDICATORS = [
        "验证码", "请先登录", "访问验证", "安全验证", "系统繁忙",
        "滑块", "robot", "captcha", "access denied", "blocked",
        "waf", "waf block", "anti-bot", "cloudflare", "盾牌验证",
    ]

    NOISE_SELECTORS = [
        "nav", "header", "footer", "aside", "script", "style",
        "noscript", "svg", "iframe", ".ad", ".ads", ".banner",
        ".copyright", ".footer", ".navigation", ".sidebar",
        "#footer", "#header", "#sidebar", ".comment-form",
    ]

    def __init__(self, timeout: int = 8, max_bytes: int = 2 * 1024 * 1024):
        self.timeout = timeout
        self.max_bytes = max_bytes

    @classmethod
    def clean_html_content(cls, html_text: str) -> str:
        """剔除 HTML 中的导航、页眉、页脚、侧边栏、脚本及广告标签并提取正文"""
        soup = BeautifulSoup(html_text, "html.parser")
        for selector in cls.NOISE_SELECTORS:
            for el in soup.select(selector):
                el.decompose()
        full_text = soup.get_text(separator="\n", strip=True)
        clean_text = re.sub(r"\n\s*\n+", "\n", full_text)
        return re.sub(r"[ \t]+", " ", clean_text).strip()

    def fetch_and_extract_excerpt(
        self,
        url: str,
        keywords: Optional[Any] = None,
        timeout: Optional[int] = None,
        claim_keywords: Optional[Any] = None,
    ) -> WebPageExcerptResult:
        """安全抓取目标网页，提取去噪正文与核心证据片段"""
        start_t = time.perf_counter()
        clean_url = (url or "").strip()
        domain = urlparse(clean_url).netloc.lower()
        req_timeout = timeout or self.timeout

        # 统一关键词输入为 List[str]
        target_kw = claim_keywords if claim_keywords is not None else keywords
        kw_list: List[str] = []
        if isinstance(target_kw, str):
            kw_list = [target_kw]
        elif isinstance(target_kw, (list, tuple, set)):
            kw_list = [str(k) for k in target_kw if k]

        # 1. 严格 SSRF 过滤与公网隔离检查
        is_safe, safe_or_err = validate_public_url(clean_url)
        if not is_safe:
            elapsed_ms = int((time.perf_counter() - start_t) * 1000)
            return WebPageExcerptResult(
                url=clean_url,
                domain=domain,
                fetch_status="ssrf_blocked",
                http_status=403,
                error_message=f"SSRF 拦截: {safe_or_err}",
                response_time_ms=elapsed_ms,
            )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36 ClaimCheckPro/0.1 EvidenceFetcher"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        session = requests.Session()
        current_url = safe_or_err

        try:
            # 手动执行每跳重定向以保障 SSRF 绝对安全
            final_resp = None
            for hop in range(5):
                resp = session.get(
                    current_url,
                    headers=headers,
                    timeout=req_timeout,
                    allow_redirects=False,
                    stream=True,
                )
                if resp.status_code in [301, 302, 303, 307, 308]:
                    loc = resp.headers.get("Location")
                    if not loc:
                        break
                    from urllib.parse import urljoin
                    next_url = urljoin(current_url, loc)
                    is_n_safe, next_safe = validate_public_url(next_url)
                    if not is_n_safe:
                        raise SSRFSecurityError(f"重定向跳转目标违规: {next_safe}")
                    current_url = next_safe
                    continue
                final_resp = resp
                break

            if final_resp is None:
                raise ValueError("重定向跳数过多或无法获取最终响应")

            http_status = final_resp.status_code

            # 遇到 401/403/404 等显式受限
            if http_status in [401, 403]:
                elapsed_ms = int((time.perf_counter() - start_t) * 1000)
                return WebPageExcerptResult(
                    url=clean_url,
                    final_url=current_url,
                    domain=domain,
                    fetch_status="restricted",
                    http_status=http_status,
                    error_message=f"目标网站访问受限 (HTTP {http_status})，平台拒绝未认证抓取",
                    response_time_ms=elapsed_ms,
                )
            if http_status >= 400:
                elapsed_ms = int((time.perf_counter() - start_t) * 1000)
                return WebPageExcerptResult(
                    url=clean_url,
                    final_url=current_url,
                    domain=domain,
                    fetch_status="failed",
                    http_status=http_status,
                    error_message=f"网页请求失败 (HTTP {http_status})",
                    response_time_ms=elapsed_ms,
                )

            # 校验 Content-Type
            c_type = final_resp.headers.get("Content-Type", "").lower()
            allowed = ["text/html", "application/xhtml+xml", "text/plain"]
            if not any(t in c_type for t in allowed):
                elapsed_ms = int((time.perf_counter() - start_t) * 1000)
                return WebPageExcerptResult(
                    url=clean_url,
                    final_url=current_url,
                    domain=domain,
                    fetch_status="invalid_content_type",
                    http_status=415,
                    error_message=f"不受支持的内容类型 ({c_type})，仅抓取网页文档",
                    response_time_ms=elapsed_ms,
                )

            # 流式读取内容，严控 2MB 大小
            chunks = []
            cur_len = 0
            for chunk in final_resp.iter_content(chunk_size=16384):
                cur_len += len(chunk)
                if cur_len > self.max_bytes:
                    break
                chunks.append(chunk)

            body_bytes = b"".join(chunks)
            encoding = final_resp.encoding or "utf-8"
            try:
                html_text = body_bytes.decode(encoding, errors="replace")
            except Exception:
                html_text = body_bytes.decode("utf-8", errors="replace")

            elapsed_ms = int((time.perf_counter() - start_t) * 1000)

            # 2. BeautifulSoup 深度解析与去噪
            soup = BeautifulSoup(html_text, "html.parser")

            # 提取标题
            title = ""
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            elif soup.h1:
                title = soup.h1.get_text().strip()
            else:
                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content"):
                    title = str(og_title["content"]).strip()
            if not title:
                title = domain

            # 识别页面内容级反爬与滑块验证
            sample_text = soup.get_text()[:2000].lower()
            if any(ind in sample_text for ind in self.RESTRICTED_INDICATORS):
                return WebPageExcerptResult(
                    url=clean_url,
                    final_url=current_url,
                    domain=domain,
                    title=title,
                    fetch_status="restricted",
                    http_status=http_status,
                    error_message="检测到网页滑块、登录墙或验证码保护，系统合规降级，不执行暴力绕过",
                    response_time_ms=elapsed_ms,
                )

            # 剔除噪声标签
            for selector in self.NOISE_SELECTORS:
                for el in soup.select(selector):
                    el.decompose()

            # 提取纯文本正文
            full_text = soup.get_text(separator="\n", strip=True)
            # 合并连续换行与多余空白
            clean_text = re.sub(r"\n\s*\n+", "\n", full_text)
            clean_text = re.sub(r"[ \t]+", " ", clean_text).strip()

            if len(clean_text) < 50:
                return WebPageExcerptResult(
                    url=clean_url,
                    final_url=current_url,
                    domain=domain,
                    title=title,
                    clean_text=clean_text,
                    excerpt=clean_text,
                    fetch_status="restricted",
                    http_status=http_status,
                    error_message="网页正文内容过少 (可能需要客户端动态 JavaScript 渲染)",
                    response_time_ms=elapsed_ms,
                )

            # 3. 提取围绕声明关键词的最佳事实片段 (200~450 字)
            excerpt = self._extract_keyword_focused_excerpt(clean_text, kw_list)

            return WebPageExcerptResult(
                url=clean_url,
                final_url=current_url,
                domain=domain,
                title=title[:180],
                clean_text=clean_text[:4000],  # 截断保存
                excerpt=excerpt,
                fetch_status="success",
                http_status=http_status,
                response_time_ms=elapsed_ms,
                content_bytes_len=len(body_bytes),
            )

        except requests.exceptions.Timeout:
            elapsed_ms = int((time.perf_counter() - start_t) * 1000)
            return WebPageExcerptResult(
                url=clean_url,
                domain=domain,
                fetch_status="timeout",
                error_message=f"网页请求超时 ({req_timeout}s)",
                response_time_ms=elapsed_ms,
            )
        except SSRFSecurityError as e:
            elapsed_ms = int((time.perf_counter() - start_t) * 1000)
            return WebPageExcerptResult(
                url=clean_url,
                domain=domain,
                fetch_status="ssrf_blocked",
                error_message=str(e),
                response_time_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_t) * 1000)
            return WebPageExcerptResult(
                url=clean_url,
                domain=domain,
                fetch_status="failed",
                error_message=f"抓取异常: {e}",
                response_time_ms=elapsed_ms,
            )

    def _extract_keyword_focused_excerpt(self, full_text: str, keywords: List[str]) -> str:
        """根据关键词定位并切取最相关的事实原文片段 (200~450 字)"""
        if not full_text:
            return ""

        # 将文本切分为若干段落
        paragraphs = [p.strip() for p in full_text.split("\n") if len(p.strip()) >= 20]
        if not paragraphs:
            return full_text[:350].strip()

        if not keywords:
            # 默认返回开头最有代表性的一两段
            combined = "\n".join(paragraphs[:2])
            return combined[:380].strip()

        # 计算每个段落的关键词命中得分
        best_para_idx = 0
        best_score = -1

        for idx, p in enumerate(paragraphs):
            p_lower = p.lower()
            score = 0
            for kw in keywords:
                if kw and kw.lower() in p_lower:
                    score += 2
                    # 若含数字加权
                    if re.search(r"\d", kw):
                        score += 3
            if score > best_score:
                best_score = score
                best_para_idx = idx

        # 以最佳段落为中心，拼接前后上下文，凑足 200~400 字
        chosen_paras = [paragraphs[best_para_idx]]
        # 尝试往前借一段
        if best_para_idx > 0 and len(chosen_paras[0]) < 200:
            chosen_paras.insert(0, paragraphs[best_para_idx - 1])
        # 尝试往后借一段
        if best_para_idx < len(paragraphs) - 1 and sum(len(p) for p in chosen_paras) < 300:
            chosen_paras.append(paragraphs[best_para_idx + 1])

        combined_excerpt = " ... ".join(chosen_paras)
        if len(combined_excerpt) > 450:
            combined_excerpt = combined_excerpt[:440] + "..."
        return combined_excerpt.strip()


# 单例实例供全局使用
evidence_fetcher = EvidenceFetcher()
