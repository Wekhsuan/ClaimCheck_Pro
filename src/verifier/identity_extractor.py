"""ClaimCheck Pro 商品身份抽取与多候选确认机制 (Identity Extractor)

输出字段规范：
- name: 商品全称
- brand: 品牌
- model: 标准型号
- variant: 版本/规格
- region: 销售地区
- identity_confidence: 抽取置信度 (0.0~1.0)
- identity_evidence: 抽取依据线索
- candidates: 最多3个候选商品 (供用户交互确认)
"""

import re
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ProductCandidate(BaseModel):
    """候选商品项"""
    candidate_id: str
    name: str
    brand: str
    model: str
    variant: str = "标准版"
    region: str = "中国大陆"
    matching_score: float = Field(..., ge=0.0, le=1.0, description="与输入特征的匹配度评分")
    evidence_snippet: str = Field(..., description="命中特征依据")


class ProductIdentityResult(BaseModel):
    """商品身份抽取最终结构"""
    name: str = Field(default="未知商品", description="商品全称")
    brand: str = Field(default="未知品牌", description="品牌")
    model: str = Field(default="未知型号", description="标准型号")
    variant: str = Field(default="标准版", description="版本/规格")
    region: str = Field(default="中国大陆", description="销售地区/网络制式")
    identity_confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="身份置信度")
    identity_evidence: str = Field(default="", description="抽取依据线索说明")
    product_id: str = Field(default="", description="商品编号/货号/SKU")
    
    # 多候选确认控制
    has_multiple_candidates: bool = Field(default=False, description="是否存在多个相似候选型号")
    candidates: List[ProductCandidate] = Field(default_factory=list, description="最多3个候选商品")
    user_confirmed: bool = Field(default=False, description="是否已经过用户显式确认")


# 常见品牌字典库 (包含主流数码与声学品牌)
COMMON_BRANDS = [
    ("弱水时砂", "Rose Technics"),
    ("声学极客", "SoundGeek"),
    ("极能", "PowerMax"),
    ("幻影", "Phantom"),
    ("御盾", "YuShield"),
    ("苹果", "Apple"),
    ("华为", "HUAWEI"),
    ("小米", "Xiaomi"),
    ("索尼", "Sony"),
    ("漫步者", "Edifier"),
    ("森海塞尔", "Sennheiser"),
    ("铁三角", "Audio-Technica"),
    ("博士", "Bose"),
    ("JBL", "JBL"),
    ("水月雨", "Moondrop"),
    ("飞傲", "FiiO"),
    ("联想", "Lenovo"),
    ("戴尔", "Dell"),
    ("华硕", "ASUS"),
    ("绿联", "UGREEN"),
    ("安克", "Anker"),
    ("倍思", "Baseus"),
]

# 常见版本与规格关键词
VARIANT_KEYWORDS = [
    "标准版", "旗舰版", "降噪版", "商务灰", "曜石黑", "典藏版",
    "青春版", "至尊版", "Pro版", "Max版", "Ultra版", "Plus版",
    "16G/1TB", "32G/1TB", "8G/256G", "65W", "100W", "20000mAh"
]

# 销售地区识别规则
REGION_KEYWORDS = [
    ("港版", "中国香港"),
    ("美版", "美国"),
    ("日版", "日本"),
    ("欧版", "欧洲"),
    ("国行", "中国大陆"),
    ("中国大陆", "中国大陆"),
]


# 常见技术协议与噪声词 (防止被误判为商品型号)
COMMON_NOISE_TERMS = {
    "the", "and", "usb", "type", "with", "lhdc", "ldac", "aac", "sbc", "aptx",
    "anc", "enc", "tws", "type-c", "usb-a", "usb-c", "quick", "charge",
    "bluetooth", "hdmi", "wifi", "oled", "amoled", "ips", "hdr", "mah", "gb", "tb",
    "pd", "qc", "pps", "rgb"
}


def extract_product_identity(
    text_content: str,
    pre_extracted: Optional[Dict] = None,
) -> ProductIdentityResult:
    """从文本/OCR/爬取元数据中精准抽取商品身份并生成多候选"""
    pre_extracted = pre_extracted or {}
    text = (text_content or "").strip()

    # 1. 优先使用预抽取数据 (如 JSON-LD)
    brand = pre_extracted.get("brand", "").strip()
    model = pre_extracted.get("model", "").strip()
    name = pre_extracted.get("name", "").strip()
    variant = pre_extracted.get("variant", "").strip()
    product_id = pre_extracted.get("product_id", "").strip()

    brand_evidence = f"来自结构化数据(如JSON-LD)提取品牌: {brand}" if brand else ""
    model_evidence = f"来自结构化数据(如JSON-LD)提取型号: {model}" if model else ""

    # 1.1 提取商品编号/货号/SKU
    if not product_id:
        id_match = re.search(
            r"(?:商品编号|商品编码|货号|SKU|Item ID|ID)[:：\s]*([A-Za-z0-9\-]+)",
            text,
            re.IGNORECASE,
        )
        if id_match:
            product_id = id_match.group(1).strip()

    # 2. 品牌识别
    if not brand:
        # 优先显式品牌字段 (如 品牌：弱水时砂)
        brand_label_match = re.search(r"(?:品牌名称|品牌|Brand)[:：\s]*([^\s,，;；\n]+)", text, re.IGNORECASE)
        if brand_label_match:
            cand_b = brand_label_match.group(1).strip()
            if cand_b and len(cand_b) <= 20 and cand_b not in ["通用品牌", "未知", "暂无"]:
                brand = cand_b
                brand_evidence = f"从显式品牌字段提取: '{brand}'"

    if not brand:
        for b_cn, b_en in COMMON_BRANDS:
            if b_cn in text or b_en.lower() in text.lower():
                brand = b_cn
                brand_evidence = f"在文本中匹配到品牌关键词 '{b_cn}/{b_en}'"
                break

    if not brand:
        # 启发式：提取前两个词或书名号
        bracket_match = re.search(r"【(.*?)】", text)
        if bracket_match:
            brand = bracket_match.group(1)[:6]
            brand_evidence = f"从标题标签提取疑似品牌 '{brand}'"
        else:
            brand = "通用品牌"
            brand_evidence = "未检测到已知知名品牌，标记为通用品牌"

    # 找到匹配品牌的英文别名 (避免将品牌英文名误判为产品型号)
    brand_en = ""
    for b_cn, b_en in COMMON_BRANDS:
        if b_cn == brand:
            brand_en = b_en.lower()
            break

    # 3. 型号识别与候选收集
    detected_models = []

    # 优先匹配带有显式标签的型号 (如 "标准型号：PB-20065" 或 "Model: SoundPro X1")
    label_matches = re.findall(
        r"(?:标准型号|产品型号|商品型号|型号|机型|Model|MODEL)[:：\s]*([A-Za-z0-9\-]+)",
        text,
        re.IGNORECASE,
    )
    for lm in label_matches:
        clean_lm = lm.strip()
        if (
            len(clean_lm) >= 2
            and clean_lm.lower() not in COMMON_NOISE_TERMS
            and clean_lm.lower() != brand_en
            and clean_lm not in detected_models
        ):
            detected_models.append(clean_lm)

    # 次级正则匹配英文加数字的典型型号模式 (如 SoundPro X1, SoundPro X1-Pro, PB-20065, Pro 14, YD-Q900)
    model_patterns = [
        r"\b([A-Za-z]{2,10}[-\s]?[A-Za-z0-9]{1,10}(?:[-_][A-Za-z0-9]{1,10})*(?:\s*(?:Pro|Plus|Max|Ultra|SE))?)\b",
        r"\b(PB-\d{4,6}|YD-[A-Z0-9]{3,6}|X\d{1,2}|GT\d{1,2})\b",
    ]
    for pat in model_patterns:
        matches = re.findall(pat, text, re.IGNORECASE)
        for m in matches:
            clean_m = m.strip()
            if (
                len(clean_m) >= 3
                and clean_m.lower() not in COMMON_NOISE_TERMS
                and clean_m.lower() != brand_en
                and clean_m not in detected_models
            ):
                detected_models.append(clean_m)

    # 4. 版本与销售地区
    for vk in VARIANT_KEYWORDS:
        if vk in text and not variant:
            variant = vk

    region = "中国大陆"
    for r_kw, r_val in REGION_KEYWORDS:
        if r_kw in text:
            region = r_val
            break

    # 5. 多候选分析逻辑
    candidates: List[ProductCandidate] = []
    # 若无权威结构化预抽取型号，且检测到 2 个及以上不同的型号特征，生成候选商品供用户确认
    if not model and len(detected_models) >= 2:
        for idx, m_cand in enumerate(detected_models[:3], 1):
            cand_variant = "Pro版" if "Pro" in m_cand else ("标准版" if idx == 1 else "高配版")
            score = 0.95 - (idx - 1) * 0.1
            candidates.append(
                ProductCandidate(
                    candidate_id=f"cand_0{idx}",
                    name=f"{brand} {m_cand} {cand_variant}",
                    brand=brand,
                    model=m_cand,
                    variant=cand_variant,
                    region=region,
                    matching_score=round(score, 2),
                    evidence_snippet=f"在商品宣传文案中检测到并列或关联型号 '{m_cand}'",
                )
            )

    # 若未找到型号，从检测到的候选或文本中提炼
    if not model:
        if detected_models:
            model = detected_models[0]
            model_evidence = f"从文本正则中提取到型号: {model}"
        else:
            model = "标准型"
            model_evidence = "未检测到明确型号代号，采用标准默认值"

    if not name:
        # 取第一行或前40字作为标题
        first_line = text.splitlines()[0] if text else "商品"
        name = first_line[:50]

    has_multi = len(candidates) > 1
    confidence = 0.96 if (brand != "通用品牌" and model != "标准型") else 0.75

    # 组装证据说明
    evidence_parts = []
    if brand_evidence:
        evidence_parts.append(brand_evidence)
    if model_evidence:
        evidence_parts.append(model_evidence)
    if product_id:
        evidence_parts.append(f"识别到商品编号/货号: {product_id}")
    if variant:
        evidence_parts.append(f"识别到规格版本: {variant}")
    evidence_parts.append(f"销售地区识别为: {region}")

    return ProductIdentityResult(
        name=name,
        brand=brand,
        model=model,
        variant=variant or "标准版",
        region=region,
        product_id=product_id,
        identity_confidence=confidence,
        identity_evidence="；".join(evidence_parts),
        has_multiple_candidates=has_multi,
        candidates=candidates,
        user_confirmed=not has_multi,  # 若只有单型号则默认就绪，若有多候选则需确认
    )
