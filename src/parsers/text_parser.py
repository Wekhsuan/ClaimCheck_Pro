"""ClaimCheck Pro 详情文本清洗与校验模块 (Text Parser)

负责：
1. 规范清洗空行、连续空白；
2. 过滤电商平台通用无关导航、促销废话与售后套话；
3. 消除连续重复段落；
4. 严格校验最小与最大长度限制；
5. 敏感个人信息扫描提示 (手机号、订单号)。
"""

import re
from typing import List, Tuple
from pydantic import BaseModel, Field


class TextCleanResult(BaseModel):
    """文本清洗结果"""
    cleaned_text: str
    original_length: int
    cleaned_length: int
    removed_noise_lines: int
    removed_sample_lines: List[str] = Field(default_factory=list)
    privacy_warnings: List[str] = Field(default_factory=list)


# 常见电商平台无关导航、营销废料与通用售后噪声模式
NAVIGATION_NOISE_PATTERNS = [
    r"^(加入购物车|立即购买|领券满减|店铺首页|联系客服|在线客服|收藏宝贝|关注店铺|进店逛逛)$",
    r"^(全国包邮|顺丰包邮|次日达|小时达|官方正品|假一赔十|正品保障|退换无忧|7天无理由退货)$",
    r"^(爆款热销|年度旗舰|热卖中|全网热销|限时秒杀|数量有限|手慢无|买它买它)$",
    r"^(评价\(\d+\)|问大家\(\d+\)|销量\s*\d+\+|好评率\s*\d+%)$",
    r"^(商品详情|规格参数|包装售后|用户评价)$",
    r"^(猜你喜欢|相关推荐|看了又看|热门推荐|掌柜热卖|为您推荐|同类热卖)$",
    r".*(版权所有|经营证照|增值电信业务|京公网安备|网络文化经营许可证|营业执照|隐私政策|服务条款|侵权必究).*",
    r"^(反馈建议|回到顶部|收货地址|我的订单|我的收藏|消息中心|足迹|购物车)$",
]

# 隐私敏感信息正则 (手机号、固定电话、18位身份证、长订单号)
PHONE_PATTERN = r"(?<!\d)1[3-9]\d{9}(?!\d)"
ORDER_ID_PATTERN = r"(?<!\d)(订单号|交易号|单号)[:：\s]*\d{12,24}(?!\d)"


def clean_product_detail_text(raw_text: str, min_len: int = 10, max_len: int = 10000) -> TextCleanResult:
    """清洗用户粘贴的商品详情文本，执行长度与隐私校验"""
    if not raw_text or not raw_text.strip():
        raise ValueError("输入文本不能为空，请输入商品标题、规格或宣传卖点。")

    raw_len = len(raw_text)
    if raw_len > max_len:
        raise ValueError(f"输入文本长度 ({raw_len} 字) 超出上限 ({max_len} 字)，请精简后重新提交。")

    # 1. 敏感信息检查
    privacy_warnings = []
    if re.search(PHONE_PATTERN, raw_text):
        privacy_warnings.append("检测到疑似包含手机号码，建议在分析前剔除个人联系方式。")
    if re.search(ORDER_ID_PATTERN, raw_text, re.IGNORECASE):
        privacy_warnings.append("检测到疑似包含电商订单号/交易号，建议剔除私密交易信息。")

    # 2. 分行处理与噪音过滤
    lines = raw_text.splitlines()
    cleaned_lines = []
    removed_count = 0
    removed_samples = []
    seen_lines = set()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 检查是否命中通用噪音模式
        is_noise = False
        for pat in NAVIGATION_NOISE_PATTERNS:
            if re.search(pat, stripped, re.IGNORECASE):
                is_noise = True
                break

        if is_noise:
            removed_count += 1
            if len(removed_samples) < 10:
                removed_samples.append(stripped)
            continue

        # 消除完全重复的连续行
        if stripped in seen_lines and len(stripped) < 40:
            removed_count += 1
            if len(removed_samples) < 10:
                removed_samples.append(f"[重复行] {stripped}")
            continue

        seen_lines.add(stripped)
        cleaned_lines.append(stripped)

    result_text = "\n".join(cleaned_lines)
    clean_len = len(result_text)

    if clean_len < min_len:
        raise ValueError(
            f"清洗后有效信息长度仅为 {clean_len} 字符，低于最小要求 ({min_len} 字符)。"
            "请提供更详尽的商品名称、型号或关键卖点文案。"
        )

    return TextCleanResult(
        cleaned_text=result_text,
        original_length=raw_len,
        cleaned_length=clean_len,
        removed_noise_lines=removed_count,
        removed_sample_lines=removed_samples,
        privacy_warnings=privacy_warnings,
    )


def clean_page_text_for_preview(raw_text: str) -> TextCleanResult:
    """仅执行清洗并返回预览结果，不抛出最小长度异常，用于前端清洗对比"""
    if not raw_text or not raw_text.strip():
        return TextCleanResult(
            cleaned_text="",
            original_length=0,
            cleaned_length=0,
            removed_noise_lines=0,
            removed_sample_lines=[],
            privacy_warnings=[],
        )

    try:
        return clean_product_detail_text(raw_text, min_len=0)
    except Exception as e:
        return TextCleanResult(
            cleaned_text=raw_text.strip(),
            original_length=len(raw_text),
            cleaned_length=len(raw_text.strip()),
            removed_noise_lines=0,
            removed_sample_lines=[],
            privacy_warnings=[str(e)],
        )
