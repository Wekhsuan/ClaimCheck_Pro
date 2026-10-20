"""ClaimCheck Pro 网页解析与合规降级处理器 (URL Extractor & Fallback Handler)

严格遵循：
1. 优先解析 JSON-LD (schema.org/Product) 结构化数据；
2. 遇到登录、验证码、App专属、反自动化限制时立即停止；
3. 不绕过任何访问限制，向用户提供优雅降级至文本/截图模式的指引；
4. 绝不收集或存储用户平台账号密码。
"""

import json
import logging
import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from src.crawlers.ssrf_filter import safe_fetch_html

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

logger = logging.getLogger("claimcheck.url_extractor")


def normalize_product_url(url: str) -> str:
    """标准化商品链接：去除营销推广、追踪统计等无关参数，保留核心路径与关键商品ID"""
    if not url or not url.strip():
        return ""
    clean_url = url.strip()
    try:
        parsed = urlparse(clean_url)
    except Exception:
        return clean_url

    KEEP_PARAMS = {"id", "item_id", "goods_id", "sku", "productid", "product_id", "skuid"}
    query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
    filtered_pairs = []
    for k, v in query_pairs:
        k_lower = k.lower()
        if k_lower.startswith("utm_") or k_lower in {
            "extension_id", "spm", "scm", "pvid", "from", "ref", "fbclid", "gclid", "ad_id", "cps_id"
        }:
            continue
        if k_lower in KEEP_PARAMS:
            filtered_pairs.append((k, v))
        elif not any(k_lower.startswith(p) for p in ["utm_", "cps_", "track_"]):
            pass

    # 特殊规则：京东商品页形如 /10115777872752.html，无需任何 query 参数
    host = (parsed.hostname or "").lower()
    if any(h in host for h in ["jd.com", "jd.hk"]):
        if re.search(r'/\d+\.html', parsed.path):
            filtered_pairs = []

    new_query = urlencode(filtered_pairs)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", new_query, ""))


def identify_platform_and_id(url: str) -> Tuple[str, str]:
    """根据域名与路径识别电商平台名称与商品ID"""
    if not url or not url.strip():
        return "未知平台", "未知"

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return "未知平台", "未知"

    host = (parsed.hostname or "").lower()
    path = parsed.path
    query = parsed.query

    # 1. 识别平台名称
    if any(h in host for h in ["jd.com", "jd.hk"]):
        platform = "京东 (JD.COM)"
    elif any(h in host for h in ["tmall.com", "tmall.hk"]):
        platform = "天猫 (Tmall)"
    elif "taobao.com" in host:
        platform = "淘宝 (Taobao)"
    elif any(h in host for h in ["pinduoduo.com", "yangkeduo.com"]):
        platform = "拼多多 (Pinduoduo)"
    elif any(h in host for h in ["douyin.com", "jinritemai.com"]):
        platform = "抖音电商"
    elif any(h in host for h in ["apple.com", "apple.com.cn"]):
        platform = "Apple官网"
    else:
        platform = "未知平台"

    # 2. 提取商品 ID
    product_id = ""
    # 京东 style: /10115777872752.html
    jd_match = re.search(r'/(\d{6,20})\.html', path)
    if jd_match:
        product_id = jd_match.group(1)

    # 常见参数: id=... 或 goods_id=... 或 productId=...
    if not product_id:
        q_match = re.search(r'(?:[?&]|^)(?:id|item_id|goods_id|skuId|productId)=(\d+)', query, re.IGNORECASE)
        if q_match:
            product_id = q_match.group(1)

    # 路径匹配纯数字
    if not product_id:
        path_match = re.search(r'/(\d{7,20})(?:/|\.|$)', path)
        if path_match:
            product_id = path_match.group(1)

    return platform, (product_id or "未知")


class AccessRestrictedError(Exception):
    """页面访问受限异常 (登录墙/反爬/验证码)，触发合规降级"""
    def __init__(
        self,
        message: str,
        fallback_suggest: str = "text_or_image",
        details: Optional[Dict] = None,
        error_code: str = "PAGE_ACCESS_RESTRICTED",
        platform_name: str = "未知平台",
        product_id: str = "未知",
        original_url: str = "",
        normalized_url: str = "",
        http_status: int = 200,
        final_url: str = "",
        page_title: str = "",
    ):
        super().__init__(message)
        self.message = message
        self.fallback_suggest = fallback_suggest
        self.details = details or {}
        self.error_code = error_code
        self.platform_name = platform_name
        self.product_id = product_id
        self.original_url = original_url
        self.normalized_url = normalized_url
        self.http_status = http_status
        self.final_url = final_url
        self.page_title = page_title


class InsufficientProductInfoError(AccessRestrictedError):
    """商品页面信息不足异常（如仅抓到标题但无规格与卖点）"""
    def __init__(
        self,
        message: str,
        details: Optional[Dict] = None,
        error_code: str = "INSUFFICIENT_PRODUCT_INFO",
        platform_name: str = "未知平台",
        product_id: str = "未知",
        original_url: str = "",
        normalized_url: str = "",
        http_status: int = 200,
        final_url: str = "",
        page_title: str = "",
    ):
        super().__init__(
            message=message,
            fallback_suggest="text_or_image",
            details=details,
            error_code=error_code,
            platform_name=platform_name,
            product_id=product_id,
            original_url=original_url,
            normalized_url=normalized_url,
            http_status=http_status,
            final_url=final_url,
            page_title=page_title,
        )


class ExtractedProductData(BaseModel):
    """从公开页面抽取的商品原始数据"""
    url: str
    source_type: str = Field(default="json_ld", description="数据来源：json_ld / meta_tag / dom")
    name: str = Field(default="", description="商品全称/标题")
    brand: str = Field(default="", description="品牌名称")
    model: str = Field(default="", description="产品型号")
    variant: Optional[str] = Field(default="", description="规格或版本")
    description: str = Field(default="", description="商品详情或核心卖点描述")
    specs_list: List[str] = Field(default_factory=list, description="提取到的参数列表")
    price_info: Optional[str] = Field(default=None, description="标称价格")


# 常见登录墙、滑块验证码及App限制特征关键字
RESTRICTION_PATTERNS = [
    r"passport\.(taobao|jd|meituan)\.com",
    r"login\.(taobao|jd|pinduoduo)\.com",
    r"sec\.taobao\.com",
    r"punish\?punish_type",
    r"x5sec",
    r"人机身份验证",
    r"滑动滑块",
    r"拖动滑块",
    r"图形验证码",
    r"请输入验证码",
    r"请先登录",
    r"扫码登录",
    r"打开.*?(APP|客户端)查看",
    r"App专属商品",
    r"访问频率过高",
    r"waf.*?block",
    r"cloudflare.*?captcha",
    r"请您使用高版本浏览器",
    r"推荐谷歌或者火狐",
    r"pc-risk",
    r"js_security",
]



def detect_access_restrictions(html_content: str, current_url: str = "") -> Optional[str]:
    """检测 HTML 中是否存在登录墙、滑块或反自动化限制特征"""
    # 1. 检查 URL 特征
    for pat in RESTRICTION_PATTERNS:
        if re.search(pat, current_url, re.IGNORECASE):
            return f"检测到跳转至受限页面或登录网关 ({pat})"

    # 2. 检查 HTML 文本中的明显登录/验证码特征
    soup = BeautifulSoup(html_content, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    login_title_keywords = ["登录", "用户登录", "安全验证", "验证码", "访问受限", "Blocked"]
    for kw in login_title_keywords:
        if kw in title:
            return f"页面标题命中受限访问提示: '{title}'"

    # 3. 检查页面正文反爬特征
    text_snippet = soup.get_text()[:4000]
    for pat in RESTRICTION_PATTERNS:
        if re.search(pat, text_snippet, re.IGNORECASE):
            return f"页面内容命中反自动化/验证码特征: '{pat}'"

    return None


def extract_json_ld_product(soup: BeautifulSoup) -> Optional[Dict]:
    """优先提取 schema.org/Product 格式的 JSON-LD 结构化数据"""
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string.strip())
            # 支持数组或单对象
            items = data if isinstance(data, list) else [data]
            for item in items:
                # 检查 @type 是否包含 Product
                itype = item.get("@type", "")
                if (isinstance(itype, str) and "Product" in itype) or (isinstance(itype, list) and "Product" in itype):
                    return item
                # 检查 @graph 嵌套结构
                if "@graph" in item and isinstance(item["@graph"], list):
                    for sub in item["@graph"]:
                        stype = sub.get("@type", "")
                        if "Product" in stype:
                            return sub
        except Exception:
            continue
    return None


def parse_product_from_html(
    html_content: str,
    source_url: str,
    http_status: int = 200,
    final_url: str = "",
) -> ExtractedProductData:
    """从 HTML 文本中解析商品信息，优先 JSON-LD，次级 Meta 和 DOM 结构"""
    resolved_final_url = final_url or source_url
    norm_url = normalize_product_url(source_url)
    platform, prod_id = identify_platform_and_id(source_url)

    soup = BeautifulSoup(html_content, "html.parser")
    page_title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # 0. HTTP 状态码拦截 (401/403/412/429 访问拦截)
    if http_status in [401, 403, 412, 429]:
        raise AccessRestrictedError(
            f"目标页面响应 HTTP 状态码 {http_status}（访问被拒绝或触发平台安全风控）。\n"
            "根据系统合规原则，ClaimCheck Pro 不绕过任何登录与验证码限制。\n"
            "建议：请直接复制商品标题与规格文本，切换到【商品详情文本】模式，或上传【商品宣传截图】继续核验。",
            error_code="PAGE_ACCESS_RESTRICTED",
            platform_name=platform,
            product_id=prod_id,
            original_url=source_url,
            normalized_url=norm_url,
            http_status=http_status,
            final_url=resolved_final_url,
            page_title=page_title,
            details={"name": page_title, "http_status": http_status, "final_url": resolved_final_url, "specs_count": 0},
        )

    # 1. 安全与反爬受限检查：遇到登录/验证码直接阻断降级，绝不暴力绕过
    restriction_reason = detect_access_restrictions(html_content, source_url)
    if restriction_reason:
        err_code = "CAPTCHA_DETECTED" if any(k in restriction_reason for k in ["验证码", "滑块", "人机", "captcha"]) else "PAGE_ACCESS_RESTRICTED"
        raise AccessRestrictedError(
            f"目标页面已触发平台访问限制 ({restriction_reason})。\n"
            "根据系统合规原则，ClaimCheck Pro 不绕过任何登录与验证码限制。\n"
            "建议：请直接复制商品标题与规格文本，切换到【商品详情文本】模式，或上传【商品宣传截图】继续核验。",
            error_code=err_code,
            platform_name=platform,
            product_id=prod_id,
            original_url=source_url,
            normalized_url=norm_url,
            http_status=http_status,
            final_url=resolved_final_url,
            page_title=page_title,
            details={"name": page_title, "http_status": http_status, "final_url": resolved_final_url, "specs_count": 0},
        )

    # 2. 优先策略：提取 JSON-LD Product 数据
    json_ld = extract_json_ld_product(soup)
    if json_ld:
        brand_raw = json_ld.get("brand", "")
        if isinstance(brand_raw, dict):
            brand = brand_raw.get("name", "")
        else:
            brand = str(brand_raw)

        offers = json_ld.get("offers", {})
        price = None
        if isinstance(offers, dict):
            price = offers.get("price") or offers.get("lowPrice")
        elif isinstance(offers, list) and len(offers) > 0:
            price = offers[0].get("price")

        return ExtractedProductData(
            url=source_url,
            source_type="json_ld",
            name=json_ld.get("name", "").strip(),
            brand=brand.strip(),
            model=json_ld.get("model", json_ld.get("sku", "")).strip(),
            variant="",
            description=json_ld.get("description", "").strip(),
            specs_list=[],
            price_info=str(price) if price else None,
        )

    # 3. 次级策略：DOM 与 Meta 标签提取
    name = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        name = og_title["content"].strip()
    elif soup.find("h1"):
        name = soup.find("h1").get_text().strip()
    elif page_title:
        name = page_title

    description = ""
    og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
    if og_desc and og_desc.get("content"):
        description = og_desc["content"].strip()

    specs = []
    for selector in ["ul.parameter2-list", "table.spec-table", "div.param-table", "ul.specs"]:
        container = soup.select_one(selector)
        if container:
            for item in container.find_all(["li", "tr", "p"]):
                txt = item.get_text().strip()
                if txt and len(txt) > 3:
                    specs.append(txt)

    # 4. 校验有效性与反爬占位符检测
    GENERIC_SLOGANS = [
        "正品低价、品质保障", "配送及时、轻松购物", "淘！我喜欢", "理想生活上天猫",
        "请您使用高版本浏览器", "访问受限", "网络开小差", "安全验证", "JD.COM"
    ]
    is_empty_or_slogan = not name or any(s in name for s in GENERIC_SLOGANS)
    if is_empty_or_slogan and not specs and not description:
        raise AccessRestrictedError(
            f"目标页面受到电商平台反爬机制或动态渲染限制（仅返回占位标语 '{name[:30]}'，未包含具体商品数据）。\n"
            "根据系统合规原则，ClaimCheck Pro 不绕过任何登录与验证码限制。\n"
            "建议：请直接复制商品标题与规格文本，切换到【商品详情文本】模式，或上传【商品宣传截图】继续核验。",
            fallback_suggest="text_or_image",
            error_code="DYNAMIC_RENDER_BLOCKED",
            platform_name=platform,
            product_id=prod_id,
            original_url=source_url,
            normalized_url=norm_url,
            http_status=http_status,
            final_url=resolved_final_url,
            page_title=page_title or name,
            details={"name": name, "http_status": http_status, "final_url": resolved_final_url, "specs_count": 0},
        )

    # 规则 6: 如果商品页只能提取标题，不能提取规格和卖点，则明确提示信息不足
    if name and not specs and not description:
        raise InsufficientProductInfoError(
            f"商品页面信息不足：虽读取到标题【{name[:40]}】，但未能提取到商品规格参数与核心卖点。\n"
            "根据核验规则，缺少规格参数无法继续核验。\n"
            "建议：请切换到【商品详情文本】补充参数，或上传【商品宣传截图】继续核验。",
            error_code="INSUFFICIENT_PRODUCT_INFO",
            platform_name=platform,
            product_id=prod_id,
            original_url=source_url,
            normalized_url=norm_url,
            http_status=http_status,
            final_url=resolved_final_url,
            page_title=page_title or name,
            details={"name": name, "http_status": http_status, "final_url": resolved_final_url, "specs_count": 0},
        )

    return ExtractedProductData(
        url=source_url,
        source_type="dom_meta",
        name=name,
        brand="",
        model="",
        variant="",
        description=description,
        specs_list=specs[:10],
    )


def extract_product_from_url(url: str, timeout: int = 15) -> ExtractedProductData:
    """端到端安全抓取公开网页并提取商品信息的主函数"""
    from src.crawlers.ssrf_filter import safe_fetch_html_with_metadata
    fetch_res = safe_fetch_html_with_metadata(url, timeout=timeout)
    html = fetch_res["html"]
    http_status = fetch_res.get("http_status", 200)
    final_url = fetch_res.get("final_url", url)
    return parse_product_from_html(html, url, http_status=http_status, final_url=final_url)

