"""ClaimCheck Pro 宣传声明原子化拆解与质量控制引擎 (Claim Decomposer & Quality Filter)

严格遵循阶段 1 规范：
1. 拦截占位符、模板变量、字段标签、品牌名称与商品编号；
2. 品牌名称 (如“弱水时砂”) 与商品编号 (如“1008695271”) 严格归属商品身份元数据，绝不作为声明；
3. 严格遵循 7 大允许类别：参数 / 功能 / 性能 / 材料 / 兼容性 / 使用条件 / 明确体验承诺；
4. 实现 claim_quality_score (0.0~1.0) 算法，只有 is_verifiable == True 且 score >= 0.65 才可入选；
5. 动态数量控制 (1~5条，不足时不强凑)；
6. 0 条有效声明时明确返回空列表并记录未采用候选及原因，由上层流水线安全中断提示用户；
7. 严禁回退至任何 Mock 案例。
"""

import re
from typing import Dict, List, Optional, Set, Tuple

from streamlit_app.schemas import (
    ALLOWED_CLAIM_CATEGORIES,
    ClaimItem,
    FilteredCandidate,
    ProductIdentity,
)

# 排除的主观情绪与营销口号词
SUBJECTIVE_FLUFF_PATTERNS = [
    r"遥遥领先", r"震撼登场", r"无与伦比", r"年度机皇", r"绝绝子",
    r"买它就对了", r"前所未有", r"极致体验", r"顶级奢华", r"颜值担当",
    r"神仙颜值", r"闭眼入", r"天花板", r"爆款必入", r"吐血推荐",
]

# 通用售后与交易口号 (非商品自身客观技术属性)
MARKETING_SLOGANS = {
    "官方正品", "正品保障", "全国包邮", "假一赔十", "破损包赔",
    "7天无理由退货", "顺丰包邮", "极速发货", "官方直营", "假一赔四",
    "退货包运费", "假一赔三", "售后无忧", "现货速发", "买贵退差",
}

# 常见知名品牌列表 (防止纯品牌词误入声明)
KNOWN_BRAND_NAMES: Set[str] = {
    "弱水时砂", "声学极客", "极能", "幻影", "御盾", "苹果", "华为", "小米",
    "索尼", "漫步者", "森海塞尔", "铁三角", "博士", "JBL", "水月雨", "飞傲",
    "联想", "戴尔", "华硕", "绿联", "安克", "倍思", "ROSE TECHNICS", "APPLE",
    "HUAWEI", "XIAOMI", "SONY", "EDIFIER", "SENNHEISER", "BOSE", "ANKER",
}

# 常见纯字段名 (无具体陈述或只有字段标题)
PURE_FIELD_TITLES: Set[str] = {
    "商品编号", "商品名称", "品牌", "型号", "规格", "参数", "详情页", "主图",
    "店铺", "包装清单", "好评率", "售后服务", "商品介绍", "基本信息", "核心参数",
    "规格参数", "核心功能", "实测性能", "用户体验", "产品特色", "产品参数",
    "商品详情", "产品信息", "卖点介绍", "图文详情",
}


class ClaimQualityFilter:
    """宣传声明质量过滤器与评分器"""

    @staticmethod
    def is_invalid_placeholder(text: str) -> Tuple[bool, str]:
        """检查是否属于系统占位符、OCR提示或空模板变量"""
        stripped = text.strip()
        if not stripped:
            return True, "属于空字符串"

        # 1. 截图占位符 (如【截图1提取内容】、【截图2提取内容】)
        if re.search(r"【?截图\s*\d+\s*提取内容】?", stripped):
            return True, "属于截图占位符，不属于宣传声明"

        # 2. OCR 占位符
        if re.search(r"【?(?:OCR识别内容|截图提取结果|本地OCR提取|识别结果)】?", stripped):
            return True, "属于OCR系统占位符，不属于宣传声明"

        # 3. 未知或暂无占位符
        if re.match(r"^(?:未知内容|未知|暂无|未提供|空|无|N/A|null|none)$", stripped, re.IGNORECASE):
            return True, "属于占位符或未知内容，缺少具体事实"

        # 4. 未替换的模板变量 (如 {brand}, {model}, <param>)
        if re.search(r"\{[a-zA-Z0-9_\u4e00-\u9fa5]+\}", stripped) or re.search(r"<[a-zA-Z0-9_\u4e00-\u9fa5]+>", stripped):
            return True, "包含未替换的模板变量，缺少具体事实"

        # 5. 提示性占位符
        if re.search(r"【提示】.*(?:未就绪|建议在输入框直接粘贴)", stripped):
            return True, "属于系统提示文本，不属于商品宣传声明"

        return False, ""

    @staticmethod
    def is_brand_or_model(
        text: str,
        target_product: Optional[ProductIdentity] = None,
    ) -> Tuple[bool, str]:
        """检查是否属于纯品牌名、纯型号名或显式品牌字段"""
        stripped = text.strip(" ：:，,。")

        # 显式品牌字段 (如 "品牌：弱水时砂" 或 "品牌: SoundGeek")
        if re.match(r"^(?:品牌名称|品牌|Brand)[:：\s]*[^\s:：]+$", stripped, re.IGNORECASE):
            return True, "属于商品品牌标识，已收录于商品身份，不属于宣传声明"

        # 显式型号字段 (如 "型号：PB-20065" 或 "Model: SoundPro X1")
        if re.match(r"^(?:商品型号|产品型号|型号|机型|Model)[:：\s]*[^\s:：]+$", stripped, re.IGNORECASE):
            return True, "属于商品型号标识，已收录于商品身份，不属于宣传声明"

        # 纯品牌词检查 (如单独一行 "弱水时砂" 或 "声学极客")
        if stripped in KNOWN_BRAND_NAMES or (target_product and stripped == target_product.brand):
            return True, "属于商品品牌标识，已收录于商品身份，不属于宣传声明"

        # 纯型号检查
        if target_product and target_product.model and stripped == target_product.model:
            return True, "属于商品型号标识，已收录于商品身份，不属于宣传声明"

        return False, ""

    @staticmethod
    def is_field_title_or_empty_value(text: str) -> Tuple[bool, str]:
        """检查是否属于纯字段标签、标题或无值的字段"""
        stripped = text.strip()

        # 商品编号及编号行 (如 "商品编号" 或 "商品编号：1008695271")
        if re.match(r"^(?:商品编号|商品编码|货号|SKU|Item ID)[:：\s]*[A-Za-z0-9\-]*$", stripped, re.IGNORECASE):
            if re.search(r"\d+", stripped):
                return True, "属于商品编号/货号元数据，已收录于商品身份，不属于宣传声明"
            return True, "属于字段标签/标题，缺少具体声明内容"

        # 纯字段标题 (如 "规格", "参数", "详情页", "包装清单")
        clean_title = re.sub(r"[:：\s]+$", "", stripped)
        if clean_title in PURE_FIELD_TITLES:
            return True, "属于字段标签/标题，缺少具体声明内容"

        # 仅有字段名称、无字段值的内容 (如 "续航：" 或 "充电功率:")
        if re.match(r"^[^\s:：]{2,10}[:：]\s*$", stripped):
            return True, "仅为字段名称，缺少具体参数或事实陈述"

        # 常见营销口号
        if stripped in MARKETING_SLOGANS:
            return True, "属于售后保障或营销标语，不属于客观技术宣传声明"

        return False, ""


def evaluate_claim_quality_and_category(clean_text: str) -> Tuple[float, bool, str, str]:
    """计算声明质量得分 (0.0~1.0)，可验证性及 7 大限定类别

    返回: (claim_quality_score, is_verifiable, category, verification_target)
    """
    text = clean_text.strip()
    score = 0.50  # 基础分

    # 1. 检测数值与物理单位 (+0.25)
    # 支持: dB, W, mAh, Wh, Hz, kHz, MHz, GHz, GB, TB, MB, mm, cm, m, g, kg, ms, s, 小时, h, min, 分钟, V, A, 口, 档
    has_unit_metric = bool(
        re.search(
            r"\d+(\.\d+)?\s*(dB|W|mAh|Wh|Hz|kHz|MHz|GHz|GB|TB|MB|mm|cm|m|g|kg|ms|s|小时|h|min|分钟|V|A|口|档)",
            text,
            re.IGNORECASE,
        )
    )
    if has_unit_metric:
        score += 0.25

    # 2. 检测行业技术标准 / 协议 / 芯片 / 认证与核心技术架构/硬件功能/材质规范 (+0.20)
    has_tech_standard = bool(
        re.search(
            r"(Hi-Res|金标|LDAC|LHDC|aptX|AAC|SBC|Qi|PD\s*\d?|QC\s*\d?|PPS|IPX\d|IP\d{2}|蓝牙\s*\d\.\d|Bluetooth|ANC|ENC|主动降噪|降噪深度|双动圈|动铁|石墨烯|高保真|钛晶|微米|纳米|氮化镓|GaN|智能温控|恒温|快速干发|速干|负离子|护发|自适应|低延迟|超低延迟|星闪|双设备|入耳检测|无线充电|佩戴检测|触控|通透模式|铝合金|硅胶|陶瓷|镀金|钛合金|编织|Android|iOS|Windows|Mac|快充|闪充)",
            text,
            re.IGNORECASE,
        )
    )
    if has_tech_standard:
        score += 0.20

    # 3. 表达清晰的独立条件句 (+0.15)
    has_condition = bool(
        re.search(
            r"(在.+条件下|配合.+|搭配.+|开启.+下|关闭.+下|需.+|需要.+|满足.+|实验室测试|特定环境|专用App|配套App|原装)",
            text,
        )
    )
    if has_condition:
        score += 0.15

    # 3.1 明确的客观功能/材料动作短句 (如“支持...”、“采用...”、“兼容...”) (+0.15)
    if not has_tech_standard and not has_unit_metric:
        if re.search(r"^(?:支持|采用|兼容|适配)[^\s]{4,}", text):
            score += 0.15

    # 4. 包含主观夸张形容词 (-0.25)
    has_fluff = False
    for pat in SUBJECTIVE_FLUFF_PATTERNS:
        if re.search(pat, text):
            has_fluff = True
            break
    if has_fluff:
        score -= 0.25

    # 5. 过短无实义 (-0.30)
    if len(text) < 5 and not re.search(r"\d", text):
        score -= 0.30

    # 分数限制在 [0.0, 1.0]
    final_score = round(max(0.0, min(1.0, score)), 2)

    # -------------------------------------------------------------------------
    # 类别判定 (必须严格落在 7 个限定类别之中)
    # -------------------------------------------------------------------------
    # 类别 1: 性能 (实测数值、降噪深度、续航时间、充电时间、传输速率、延迟)
    if re.search(r"(降噪|续航|充满|充至|跑分|衰减|衰减率|降噪深度|传输速率|低延迟|延迟|音质|频响|失真度|干发|速干|温控)", text):
        category = "性能"
        target = "实测性能指标与持续表现"

    # 类别 2: 参数 (规格尺寸、重量、容量、接口、喇叭单元尺寸、功率)
    elif re.search(r"(\d+(\.\d+)?\s*(W|mAh|Wh|Hz|GHz|GB|TB|mm|g|kg|口|V|A))|单元|动圈|动铁|电池容量|净重|尺寸", text, re.IGNORECASE):
        category = "参数"
        target = "硬件规格与标称物理参数"

    # 类别 3: 兼容性 (操作系统、协议、认证、接口兼容、设备互联)
    elif re.search(r"(兼容|适配|认证|Hi-Res|金标|协议|LHDC|LDAC|aptX|AAC|SBC|Qi|PD|QC|MFi|雷电|Thunderbolt|iOS|Android|Windows|Mac)", text, re.IGNORECASE):
        category = "兼容性"
        target = "行业认证与协议兼容支持"

    # 类别 4: 材料 (材质、腔体工艺、涂层、亲肤、线材材质)
    elif re.search(r"(材质|材料|铝合金|硅胶|陶瓷|石墨烯|镀金|纳米|亲肤|钛合金|皮革|玻璃|编织)", text):
        category = "材料"
        target = "用料材质与物理做工工艺"

    # 类别 5: 使用条件 (特定环境、前置依赖、配套App、原装配件)
    elif re.search(r"(需搭配|需要搭配|仅在|前提|使用原装|必须开启|配套App|特定条件|实验室环境)", text):
        category = "使用条件"
        target = "功能生效前置环境与操作约束"

    # 类别 6: 明确体验承诺 (防护等级IPX、抗风噪、防汗、佩戴舒适度承诺)
    elif re.search(r"(IPX\d|IP\d{2}|防水|防尘|防汗|抗风噪|零感佩戴|通话降噪|隔音)", text, re.IGNORECASE):
        category = "明确体验承诺"
        target = "明确防护等级与体验承诺"

    # 类别 7: 功能 (其他具体功能开关、交互模式、无线充)
    elif re.search(r"(支持|具备|拥有|双设备|入耳检测|无线充电|触控|通透模式|佩戴检测|弹窗|智能)", text):
        category = "功能"
        target = "功能特性具备性与操作响应"

    else:
        # 兜底规范为“参数”或“明确体验承诺”
        category = "参数" if re.search(r"\d", text) else "明确体验承诺"
        target = "客观参数或体验承诺"

    # -------------------------------------------------------------------------
    # 可验证性判定 (is_verifiable)
    # -------------------------------------------------------------------------
    # 有具体单位数值、具体技术协议/认证、明确功能动词、具体材质或标准防护等级的判定为可验证
    is_verifiable = bool(
        has_unit_metric
        or has_tech_standard
        or re.search(r"(支持|兼容|采用|具备|防水|续航|降噪|充至|重量|容量|单元|频响|接口|温控|干发|护发)", text)
    )

    # 纯口号或无指标主观废话不可验证
    if has_fluff and not has_unit_metric and not has_tech_standard:
        is_verifiable = False

    return final_score, is_verifiable, category, target


class ClaimDecomposer:
    """宣传声明拆解与过滤引擎"""

    def __init__(self, max_claims: int = 5, quality_threshold: float = 0.65):
        self.max_claims = max_claims
        self.quality_threshold = quality_threshold
        self.filter = ClaimQualityFilter()

    def decompose(
        self,
        marketing_text: str,
        target_product: Optional[ProductIdentity] = None,
    ) -> List[ClaimItem]:
        """向后兼容接口：仅返回合格的原子声明列表 (最多 max_claims 条，绝不硬凑)"""
        valid_claims, _ = self.decompose_with_details(marketing_text, target_product)
        return valid_claims

    def decompose_with_details(
        self,
        marketing_text: str,
        target_product: Optional[ProductIdentity] = None,
    ) -> Tuple[List[ClaimItem], List[FilteredCandidate]]:
        """执行全套拆解、过滤与评分流程
        
        返回: (valid_claims, rejected_candidates)
        - valid_claims: 满足 quality_score >= threshold 且 is_verifiable == True 的有效声明 (最多 5 条)
        - rejected_candidates: 记录所有被剔除候选的原文与具体未采用原因
        """
        if not marketing_text or not marketing_text.strip():
            return [], []

        # 1. 按换行、句号、分号、逗号及连接词切分子句候选
        raw_lines = marketing_text.strip().splitlines()
        candidate_phrases: List[str] = []

        for line in raw_lines:
            line_str = line.strip(" •·-*#\t")
            if not line_str:
                continue

            # 若一行内含有逗号、分号或复合事实连接词（如“，并”、“且”、“同时”、“以及”），进一步切分
            sub_phrases = re.split(r"(?:，并|且|同时|配合|支持并且|以及|[，,；;。!！\n]+)", line_str)
            for sp in sub_phrases:
                sp_clean = sp.strip(" ，,。；;！!•·-*#\t")
                if sp_clean:
                    candidate_phrases.append(sp_clean)
                if sp_clean:
                    candidate_phrases.append(sp_clean)

        # 2. 逐项审核、过滤与评分
        valid_claims: List[ClaimItem] = []
        rejected_candidates: List[FilteredCandidate] = []
        seen_statements: Set[str] = set()

        for idx, phrase in enumerate(candidate_phrases, 1):
            cand_id = f"CAND-{idx:02d}"

            # 2.1 占位符拦截
            is_ph, ph_reason = self.filter.is_invalid_placeholder(phrase)
            if is_ph:
                rejected_candidates.append(
                    FilteredCandidate(
                        candidate_id=cand_id,
                        original_text=phrase,
                        rejection_reason=ph_reason,
                        score=0.0,
                        category="占位符/无效文本",
                        is_verifiable=False,
                    )
                )
                continue

            # 2.2 品牌与型号拦截 (归属商品身份元数据)
            is_bm, bm_reason = self.filter.is_brand_or_model(phrase, target_product)
            if is_bm:
                rejected_candidates.append(
                    FilteredCandidate(
                        candidate_id=cand_id,
                        original_text=phrase,
                        rejection_reason=bm_reason,
                        score=0.1,
                        category="商品身份信息",
                        is_verifiable=False,
                    )
                )
                continue

            # 2.3 字段标题与空值拦截
            is_ft, ft_reason = self.filter.is_field_title_or_empty_value(phrase)
            if is_ft:
                rejected_candidates.append(
                    FilteredCandidate(
                        candidate_id=cand_id,
                        original_text=phrase,
                        rejection_reason=ft_reason,
                        score=0.1,
                        category="字段标题/营销标语",
                        is_verifiable=False,
                    )
                )
                continue

            # 2.4 清洗主观夸张情绪词后评估长度
            cleaned_phrase = phrase
            for fluff in SUBJECTIVE_FLUFF_PATTERNS:
                cleaned_phrase = re.sub(fluff, "", cleaned_phrase)
            cleaned_phrase = cleaned_phrase.strip(" ，,。；;！!•·-*#\t")

            if len(cleaned_phrase) < 4 and not re.search(r"\d", cleaned_phrase):
                rejected_candidates.append(
                    FilteredCandidate(
                        candidate_id=cand_id,
                        original_text=phrase,
                        rejection_reason="剔除营销赞美后文本过短，缺乏具体可核验内容",
                        score=0.2,
                        category="主观废话",
                        is_verifiable=False,
                    )
                )
                continue

            # 2.5 质量评分与类别计算
            score, is_verifiable, category, target = evaluate_claim_quality_and_category(cleaned_phrase)

            # 严格核验门禁：is_verifiable == True 且 score >= 0.65
            if not is_verifiable:
                rejected_candidates.append(
                    FilteredCandidate(
                        candidate_id=cand_id,
                        original_text=phrase,
                        rejection_reason="属于主观感受或营销描述，缺乏可独立核验的客观衡量标准",
                        score=score,
                        category=category,
                        is_verifiable=False,
                    )
                )
                continue

            if score < self.quality_threshold:
                rejected_candidates.append(
                    FilteredCandidate(
                        candidate_id=cand_id,
                        original_text=phrase,
                        rejection_reason=f"声明质量评分 ({score:.2f}) 低于准入门槛 ({self.quality_threshold:.2f})",
                        score=score,
                        category=category,
                        is_verifiable=True,
                    )
                )
                continue

            # 2.6 去重检查
            if cleaned_phrase in seen_statements:
                rejected_candidates.append(
                    FilteredCandidate(
                        candidate_id=cand_id,
                        original_text=phrase,
                        rejection_reason="与已入选的宣传声明重复",
                        score=score,
                        category=category,
                        is_verifiable=True,
                    )
                )
                continue

            # 2.7 录入合格声明 (最多 5 条)
            if len(valid_claims) < self.max_claims:
                seen_statements.add(cleaned_phrase)
                claim = ClaimItem(
                    claim_id=len(valid_claims) + 1,
                    original_text=phrase,
                    atomic_statement=cleaned_phrase,
                    single_verifiable_fact=cleaned_phrase,
                    category=category,
                    verification_target=target,
                    normalized_claim=cleaned_phrase,
                    extracted_from="text",
                    claim_quality_score=score,
                    is_verifiable=True,
                )
                valid_claims.append(claim)
            else:
                rejected_candidates.append(
                    FilteredCandidate(
                        candidate_id=cand_id,
                        original_text=phrase,
                        rejection_reason=f"已达到单次核验声明上限 (最多 {self.max_claims} 条)",
                        score=score,
                        category=category,
                        is_verifiable=True,
                    )
                )

        return valid_claims, rejected_candidates


# 全局单例
claim_decomposer = ClaimDecomposer(max_claims=5, quality_threshold=0.65)
