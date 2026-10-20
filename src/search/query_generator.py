"""ClaimCheck Pro 分层检索词生成器 (Layered Search Query Generator)

严格遵循：
1. 每条有效核验声明依据商品身份 (brand, product_name, model, variant, region, claim, category) 生成分层查询；
2. 三层分层逻辑：
   - 第一层：官方资料 (Official) -> 官方规格、说明书、支持、核心关键词、datasheet、manual；
   - 第二层：专业评测 (Review) -> 专业评测、实测、关键词+评测、review、test；
   - 第三层：用户体验 (Experience) -> 用户反馈、常见问题、实际体验 (仅当用户开启时)；
3. 限制规则：
   - 每条声明最多生成 4 至 6 个查询；
   - 优先官方资料，官方资料不足才执行专业评测；
   - 用户体验查询默认关闭；
   - 删除重复查询；
   - 绝不生成缺少品牌和型号的过度宽泛查询；
   - 严禁使用占位符、字段名或无效声明；
   - 查询词记录 query_id, claim_id, query_text, query_type, priority, generated_at, execution_status。
"""

from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Set, Union
from pydantic import BaseModel, Field

from streamlit_app.schemas import ClaimItem


class SearchQueryItem(BaseModel):
    """单条搜索查询结构 (用于审计与分层执行)"""
    query_id: str = Field(..., description="查询唯一标识，如 q_1_1")
    claim_id: int = Field(..., description="关联的声明序号")
    query_text: str = Field(..., description="最终生成的检索关键词文本")
    query_type: str = Field(..., description="查询类型：official(官方资料) / review(专业评测) / experience(用户反馈)")
    priority: int = Field(default=1, description="优先级：1为最高(官方)，2为次高(评测)，3为辅助(体验)")
    generated_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"), description="生成时间")
    execution_status: str = Field(default="pending", description="执行状态：pending(待执行) / executed(已执行) / skipped(已跳过)")


class LayeredQueryGenerator:
    """分层检索词生成引擎"""

    # 常见占位符与垃圾标记（严禁进入查询）
    INVALID_PLACEHOLDERS = [
        "【截图", "截图提取", "ocr识别", "商品编号", "商品名称",
        "未知", "暂无", "null", "none", "{brand}", "{model}",
    ]

    @staticmethod
    def extract_claim_core_keywords(claim_text: str, category: str = "") -> str:
        """从宣传声明原文中提取最具辨识度的核心参数或功能词"""
        if not claim_text:
            return ""

        text = claim_text.strip()
        # 1. 优先提取带数值与单位的硬核参数 (如 48dB, 40小时, 65W, 5000mAh, IPX5, 4.5g)
        num_unit_match = re.search(
            r"([0-9]+(?:\.[0-9]+)?\s*(?:db|w|mah|wh|hz|ghz|gb|mb|mm|cm|g|kg|小时|min|分钟|级防水|级防尘))",
            text,
            re.IGNORECASE,
        )
        if num_unit_match:
            unit_val = num_unit_match.group(1).replace(" ", "")
            # 结合参数类别上下文
            if "降噪" in text and "db" in unit_val.lower():
                return f"{unit_val}降噪"
            if "续航" in text:
                return f"续航{unit_val}"
            if "快充" in text or "功率" in text or "w" in unit_val.lower():
                return f"{unit_val}快充"
            if "防水" in text:
                return unit_val
            return unit_val

        # 2. 提取行业技术协议、标准或材质 (如 LHDC 5.0, LDAC, Hi-Res, 蓝牙5.3, 钛合金)
        tech_match = re.search(
            r"(lhdc\s*[\d\.]*|ldac|hi-res|aptx|anc|enc|qi|pd\s*[\d\.]*|蓝牙\s*[\d\.]*|航空铝|钛合金|氮化镓|双设备连接|空间音频)",
            text,
            re.IGNORECASE,
        )
        if tech_match:
            return tech_match.group(1).strip()

        # 3. 兜底清洗：剔除无用动词与助词后保留最长名词短语
        cleaned = re.sub(r"^(支持|采用|配备|具有|提供|拥有|最高|达到|高达|全系|官方标称)", "", text)
        cleaned = re.sub(r"[，。！？；、“”\"']", " ", cleaned).strip()
        words = [w for w in cleaned.split() if len(w) >= 2 and w not in ["能够", "可以", "以及", "并且"]]
        return words[0] if words else cleaned[:12]

    def generate_queries_for_claim(
        self,
        identity: Dict[str, Any],
        claim: Union[ClaimItem, Dict[str, Any]],
        include_user_reviews: bool = False,
        max_queries: int = 5,
    ) -> List[SearchQueryItem]:
        """为单条声明生成符合规范的分层查询词列表
        
        参数:
            identity: 商品身份字典 (brand, model, product_name, variant, region)
            claim: ClaimItem 对象或字典
            include_user_reviews: 是否开启第三层“用户体验与反馈”查询 (默认 False)
            max_queries: 每条声明最大生成查询数 (4 至 6 条，默认 5)
        """
        # 1. 提取身份信息
        brand = str(identity.get("brand", "") or "").strip()
        model = str(identity.get("model", "") or "").strip()
        product_name = str(identity.get("name", identity.get("product_name", "")) or "").strip()

        # 强保护：绝不生成缺少品牌和型号的过度宽泛查询
        if (not brand or brand in ["通用品牌", "未知品牌"]) and (not model or model in ["未知型号", "未知"]):
            return []

        # 确定检索主体 (品牌 + 型号，或 品牌 + 精确品名)
        if brand and model and model != "未知型号":
            base_subject = f"{brand} {model}"
        elif model and model != "未知型号":
            base_subject = model
        else:
            base_subject = f"{brand} {product_name[:15]}".strip()

        # 2. 提取声明原文与核心词
        if isinstance(claim, ClaimItem):
            claim_id = claim.claim_id
            claim_text = claim.single_verifiable_fact or claim.atomic_statement or claim.original_text
            category = claim.category
        else:
            claim_id = int(claim.get("claim_id", 1))
            claim_text = str(claim.get("single_verifiable_fact") or claim.get("atomic_statement") or claim.get("original_text") or "")
            category = str(claim.get("category", "参数"))

        # 强保护：严禁使用占位符、字段名或无效声明生成查询
        for ph in self.INVALID_PLACEHOLDERS:
            if ph.lower() in claim_text.lower():
                return []
        if len(claim_text.strip()) < 3:
            return []

        keyword = self.extract_claim_core_keywords(claim_text, category)

        # 3. 分层构建候选查询
        generated_candidates: List[Dict[str, Any]] = []

        if include_user_reviews:
            # 开启用户反馈时：按 2 官方 + 2 评测 + 1~2 体验 均衡构建
            generated_candidates.append({
                "text": f"{base_subject} 官方规格",
                "type": "official",
                "priority": 1,
            })
            if keyword:
                generated_candidates.append({
                    "text": f"{base_subject} {keyword}",
                    "type": "official",
                    "priority": 1,
                })
            else:
                generated_candidates.append({
                    "text": f"{base_subject} 官方说明书",
                    "type": "official",
                    "priority": 1,
                })

            generated_candidates.append({
                "text": f"{base_subject} 专业评测",
                "type": "review",
                "priority": 2,
            })
            if keyword:
                generated_candidates.append({
                    "text": f"{base_subject} {keyword} 评测",
                    "type": "review",
                    "priority": 2,
                })
            else:
                generated_candidates.append({
                    "text": f"{base_subject} 实测",
                    "type": "review",
                    "priority": 2,
                })

            generated_candidates.append({
                "text": f"{base_subject} 用户反馈",
                "type": "experience",
                "priority": 3,
            })
            generated_candidates.append({
                "text": f"{base_subject} 常见问题",
                "type": "experience",
                "priority": 3,
            })
        else:
            # 默认关闭用户反馈时：聚焦官方与专业实测
            generated_candidates.append({
                "text": f"{base_subject} 官方规格",
                "type": "official",
                "priority": 1,
            })
            generated_candidates.append({
                "text": f"{base_subject} 官方说明书",
                "type": "official",
                "priority": 1,
            })
            if keyword:
                generated_candidates.append({
                    "text": f"{base_subject} {keyword}",
                    "type": "official",
                    "priority": 1,
                })
            generated_candidates.append({
                "text": f"{base_subject} 专业评测",
                "type": "review",
                "priority": 2,
            })
            generated_candidates.append({
                "text": f"{base_subject} 实测",
                "type": "review",
                "priority": 2,
            })
            if keyword:
                generated_candidates.append({
                    "text": f"{base_subject} {keyword} 评测",
                    "type": "review",
                    "priority": 2,
                })

        # 4. 去重与数量截断 (保留 4 至 6 个)
        seen_texts: Set[str] = set()
        final_queries: List[SearchQueryItem] = []
        target_limit = min(max(4, max_queries), 6)

        for cand in generated_candidates:
            raw_text = cand["text"].strip()
            # 规范化去重 (忽略空格与大小写)
            norm_key = re.sub(r"\s+", " ", raw_text.lower())
            if norm_key in seen_texts:
                continue
            seen_texts.add(norm_key)

            q_item = SearchQueryItem(
                query_id=f"q_{claim_id}_{len(final_queries) + 1}",
                claim_id=claim_id,
                query_text=raw_text,
                query_type=cand["type"],
                priority=cand["priority"],
            )
            final_queries.append(q_item)
            if len(final_queries) >= target_limit:
                break

        return final_queries

    def generate_all_queries(
        self,
        identity: Dict[str, Any],
        claims: List[ClaimItem],
        include_user_reviews: bool = False,
        max_queries_per_claim: int = 5,
    ) -> Dict[int, List[SearchQueryItem]]:
        """为所有有效声明批量生成分层检索词映射字典 (claim_id -> queries)"""
        query_map: Dict[int, List[SearchQueryItem]] = {}
        for claim in claims:
            queries = self.generate_queries_for_claim(
                identity=identity,
                claim=claim,
                include_user_reviews=include_user_reviews,
                max_queries=max_queries_per_claim,
            )
            query_map[claim.claim_id] = queries
        return query_map
