"""ClaimCheck Pro 证据来源分级器 (Evidence Classifier)

严格遵循：
3. 证据来源分为四级：
   - A级：品牌官网、官方说明书、官方规格和认证资料
   - B级：专业评测和完整测试资料
   - C级：评论、论坛和社交反馈
   - D级：软文、转载、型号不明内容
4. D级来源不得用于强结论；
5. C级来源只用于体验趋势，不得单独证明技术参数。
"""

import re
from typing import Tuple
from streamlit_app.schemas import EvidenceItem

# A级：官方与权威认证机构域名/特征
LEVEL_A_PATTERNS = [
    r"(\.gov\.cn|gov\.cn)",
    r"(cqc\.com\.cn|cnca\.gov\.cn|miit\.gov\.cn)",
    r"(jas-audio\.or\.jp|bluetooth\.com|usb\.org|wi-fi\.org|fcc\.gov)",
    r"(spec|manual|support|whitepaper|specs|cert|download|service)\.",
    r"(官方|说明书|用户手册|技术白皮书|规格表|质检检测报告|认证公示|国标|GB/T|CCC认证|3C认证|Hi-Res认证)",
]

# B级：专业实验室与权威媒体
LEVEL_B_PATTERNS = [
    r"(rtings\.com|dxomark\.com|anandtech\.com|soomal\.com|chongdiantou\.com|igaoji\.com|geekpark\.net)",
    r"(数码多|充电头网|爱搞机|先看评测|极客湾|ZEALER|RTINGS|DxOMark)",
    r"(拆解报告|实验室实测|仪器测试|横评|测试数据|功率分析仪|示波器实测|频响曲线|人工耳仿真)",
]

# C级：社区论坛与用户真实评价
LEVEL_C_PATTERNS = [
    r"(zhihu\.com|tieba\.baidu\.com|coolapk\.com|reddit\.com|weibo\.com|smzdm\.com)",
    r"(知乎|贴吧|酷安|什么值得买|Reddit|微博|论坛|买家评价|真实体验|佩戴感受|日常使用总结)",
]

# D级：营销软文与模糊转载
LEVEL_D_PATTERNS = [
    r"(baijiahao\.baidu\.com|sohu\.com|163\.com/dy|toutiao\.com|kuaibao\.qq\.com)",
    r"(种草|好物推荐|爆款清单|营销号|转自|软文|无来源转载|型号不明|买它不后悔|吐血整理)",
]


class EvidenceClassifier:
    """证据来源自动分级器"""

    @staticmethod
    def classify_source(
        title: str,
        url: str = "",
        source_type: str = "",
        excerpt: str = "",
        traceable: bool = True,
    ) -> Tuple[str, str]:
        """判定证据来源等级 (A/B/C/D) 与规范类型描述
        
        返回: (source_level, source_type)
        """
        clean_url = (url or "").strip()
        has_valid_url = bool(clean_url and (clean_url.startswith("http://") or clean_url.startswith("https://")))

        # 铁律：没有来源 URL 或不可追溯时，绝对不能成为 A 级官方证据或 B 级评测证据
        if not traceable or not has_valid_url:
            return "D级 (电商买家评价/社交线索)", "无来源URL/不可追溯资料"

        combined = f"{title} {url} {source_type} {excerpt}".lower()

        # 1. 优先 A 级特征判定
        for pat in LEVEL_A_PATTERNS:
            if re.search(pat, combined, re.IGNORECASE):
                stype = "官方资料/说明书" if "manual" in combined or "说明书" in combined else "官方规格与认证"
                return "A级 (官方资料/说明书/国标质检)", stype

        # 2. B 级专业评测
        for pat in LEVEL_B_PATTERNS:
            if re.search(pat, combined, re.IGNORECASE):
                stype = "第三方专业实测" if "实测" in combined or "拆解" in combined else "专业科技媒体评测"
                return "B级 (权威实验室/科技媒体评测)", stype

        # 3. D 级营销软文与转载 (优先于普通社媒识别，阻断营销号)
        for pat in LEVEL_D_PATTERNS:
            if re.search(pat, combined, re.IGNORECASE):
                return "D级 (电商买家评价/社交线索)", "自媒体软文/无出处转载"

        # 4. C 级论坛与社区用户反馈
        for pat in LEVEL_C_PATTERNS:
            if re.search(pat, combined, re.IGNORECASE):
                return "C级 (垂直自媒体/论坛体验)", "社区讨论与用户长评"

        # 兜底：若有 url 则倾向 C 级，若无出处则归 D 级
        if url and ("http://" in url or "https://" in url):
            return "C级 (垂直自媒体/论坛体验)", "网络公开资料"
        return "D级 (电商买家评价/社交线索)", "未标明权威出处内容"

    @staticmethod
    def is_allowed_for_strong_conclusion(evidence: EvidenceItem) -> bool:
        """规则 4: D级来源不得用于强结论 (如判定'有证据支持'或'存在冲突')"""
        level = evidence.source_level
        if level.startswith("D") or "D级" in level:
            return False
        return True

    @staticmethod
    def can_prove_technical_parameter(evidence: EvidenceItem, claim_category: str) -> bool:
        """规则 5: C级来源只用于体验趋势，不得单独证明技术参数"""
        level = evidence.source_level
        # 若声明属于参数或性能，C 级不得作为单独成立依据
        if claim_category in ["规格参数", "实测性能", "参数", "性能"]:
            if level.startswith("C") or "C级" in level:
                return False
        return True


# 全局单例
evidence_classifier = EvidenceClassifier()
