"""ClaimCheck Pro 数据模式规范 (Schemas)

定义商品身份、原子声明、分级证据、四级核验结论及完整报告结构
严格对齐阶段 5 规范：
1. 单次最多 5 条宣传声明
2. 每条声明单一可验证事实
3. A/B/C/D 四级证据来源分级
4. 证据 8 项记录规范 (title, url, source_type, source_level, published_at, model_match, excerpt, evidence_direction)
5. 四级核验结论与二次事实自检
6. 总体摘要、人工确认项与购买前建议
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator


class VerificationConclusionEnum(str, Enum):
    """四级核验结论枚举"""
    SUPPORTED = "有证据支持"
    PARTIALLY_SUPPORTED = "部分支持"
    CONFLICT = "存在冲突"
    INSUFFICIENT_EVIDENCE = "证据不足"


class SourceLevelEnum(str, Enum):
    """证据来源A/B/C/D分级体系"""
    LEVEL_A = "A级 (官方资料/说明书/国标质检)"
    LEVEL_B = "B级 (权威实验室/科技媒体评测)"
    LEVEL_C = "C级 (垂直自媒体/论坛体验)"
    LEVEL_D = "D级 (电商买家评价/社交线索)"


class TaskStateEnum(str, Enum):
    """端到端统一任务状态机"""
    DRAFT = "draft"                                            # 草稿状态：等待商品输入
    IDENTITY_PENDING = "identity_pending"                      # 商品身份待确认
    CLAIMS_PENDING = "claims_pending"                          # 宣传声明待确认
    SEARCH_CONFIRMATION_PENDING = "search_confirmation_pending"# 搜索预算与策略待确认
    SEARCHING = "searching"                                    # 正在检索公开网页与正文
    EVIDENCE_READY = "evidence_ready"                          # 结构化证据准备就绪
    VERIFYING = "verifying"                                    # 正在执行多源交叉核验
    COMPLETED = "completed"                                    # 核验完成，生成专业报告
    FAILED = "failed"                                          # 执行失败/遇到阻断异常
    CANCELLED = "cancelled"                                    # 用户取消分析


# 7 个严格允许的宣传声明类别
ALLOWED_CLAIM_CATEGORIES = [
    "参数",
    "功能",
    "性能",
    "材料",
    "兼容性",
    "使用条件",
    "明确体验承诺",
]

# 旧版类别向 7 个标准类别的兼容映射表
CATEGORY_LEGACY_MAP = {
    "规格参数": "参数",
    "核心功能": "功能",
    "实测性能": "性能",
    "用户体验": "明确体验承诺",
}


class ProductIdentity(BaseModel):
    """商品身份抽取结果"""
    brand: str = Field(..., description="品牌名称")
    model: str = Field(..., description="标准型号")
    version: Optional[str] = Field(default="标准版", description="规格/版本")
    specs: Optional[str] = Field(default="", description="关键参数简述")
    sales_region: Optional[str] = Field(default="中国大陆", description="销售地区/网络制式")
    product_id: Optional[str] = Field(default="", description="商品编号/货号/SKU")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="身份抽取置信度")


class FilteredCandidate(BaseModel):
    """未采用/被过滤的候选声明条目"""
    candidate_id: str = Field(default="", description="候选标识")
    original_text: str = Field(..., description="候选原文")
    rejection_reason: str = Field(..., description="未采用具体原因")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="质量评分")
    category: Optional[str] = Field(default="未知", description="推断类别")
    is_verifiable: bool = Field(default=False, description="是否可验证")


class ClaimItem(BaseModel):
    """原子宣传声明 (每条声明只能包含一个可验证事实)"""
    claim_id: int = Field(..., description="声明序号 (1~5)")
    original_text: str = Field(..., description="宣传原文摘录")
    atomic_statement: str = Field(..., description="原子化提炼声明")
    single_verifiable_fact: str = Field(default="", description="单一可验证事实核心描述")
    category: str = Field(default="参数", description="类别：参数/功能/性能/材料/兼容性/使用条件/明确体验承诺")
    verification_target: str = Field(..., description="核验目标与可测量指标")

    # 扩展字段：质量评分、可验证性、规范化文本及溯源信息
    normalized_claim: Optional[str] = Field(default=None, description="标准化声明陈述")
    extracted_from: Optional[str] = Field(default="text", description="提取来源: text / ocr / url / manual")
    claim_quality_score: float = Field(default=0.8, ge=0.0, le=1.0, description="声明质量评分 (0.0~1.0)")
    is_verifiable: bool = Field(default=True, description="是否属于可独立核验的客观事实")
    rejection_reason: Optional[str] = Field(default=None, description="若未采用的剔除原因说明")
    search_keywords: List[str] = Field(default_factory=list, description="推荐检索关键词列表")

    @model_validator(mode="before")
    @classmethod
    def populate_and_normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 核心事实字段对齐
            if not data.get("single_verifiable_fact"):
                data["single_verifiable_fact"] = data.get("atomic_statement", "")
            if not data.get("normalized_claim"):
                data["normalized_claim"] = data.get("atomic_statement", "")
            # 类别对齐与映射 (确保属于 7 个允许类别)
            cat = data.get("category", "参数")
            if cat in CATEGORY_LEGACY_MAP:
                data["category"] = CATEGORY_LEGACY_MAP[cat]
            elif cat not in ALLOWED_CLAIM_CATEGORIES:
                # 若不在 7 大类中，按核心特征归一化
                if "参数" in cat or "规格" in cat:
                    data["category"] = "参数"
                elif "功能" in cat:
                    data["category"] = "功能"
                elif "性能" in cat or "续航" in cat:
                    data["category"] = "性能"
                elif "材料" in cat or "材质" in cat:
                    data["category"] = "材料"
                elif "兼容" in cat or "协议" in cat:
                    data["category"] = "兼容性"
                elif "条件" in cat or "环境" in cat:
                    data["category"] = "使用条件"
                else:
                    data["category"] = "明确体验承诺"
        return data


class EvidenceItem(BaseModel):
    """证据条目 (严格满足 8 项记录规范及阶段 4 有效性与去重字段)"""
    evidence_id: str = Field(default="", description="证据唯一标识")
    title: str = Field(default="", description="证据标题或出处")
    url: str = Field(default="", description="来源链接")
    source_type: str = Field(default="官方规格", description="来源类型：官方白皮书/用户手册/检测报告/媒体横评/论坛用户/电商评价等")
    source_level: str = Field(default="A级", description="证据来源等级：A级/B级/C级/D级")
    published_at: str = Field(default="", description="发布时间或版本日期")
    model_match: str = Field(default="exact", description="型号匹配状态：exact(严格对齐)/probable(高度疑似)/series_only(仅同系列)/mismatch(型号不符)/unknown(未知)")
    excerpt: str = Field(default="", description="核心证据原文摘录")
    evidence_direction: str = Field(default="support", description="证据倾向：support(支持)/contradict(冲突)/partial(部分支持)/neutral(中立)")

    # 阶段 4 新增字段：证据有效性、质量强度与去重独立性
    is_valid_evidence: bool = Field(default=True, description="是否为有效证据(通过10项有效性校验)")
    validity_score: float = Field(default=1.0, ge=0.0, le=1.0, description="有效性得分(0.0~1.0)")
    validity_reason: str = Field(default="符合证据有效性规范", description="有效性判定理由")
    exclusion_reason: Optional[str] = Field(default=None, description="若未采用/排除的具体原因")
    claim_relevance_score: float = Field(default=1.0, ge=0.0, le=1.0, description="与当前声明的相关度得分")
    evidence_strength: str = Field(default="strong", description="证据强度：strong / medium / weak / unusable")
    content_fingerprint: str = Field(default="", description="正文内容指纹，用于识别重复转载")
    source_cluster_id: str = Field(default="", description="来源聚类簇标识")
    is_independent_source: bool = Field(default=True, description="是否属于独立证据源(排除无出处转载与重复搬运)")
    duplicate_of_evidence_id: Optional[str] = Field(default=None, description="若是重复内容，指向的首发证据ID")

    # 兼容字段映射 (确保旧版 mock 案例数据无缝兼容)
    source_title: Optional[str] = None
    source_url: Optional[str] = None
    snippet: Optional[str] = None
    published_date: Optional[str] = None
    model_matched: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def unify_field_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 标题对齐
            if not data.get("title") and data.get("source_title"):
                data["title"] = data["source_title"]
            if not data.get("source_title") and data.get("title"):
                data["source_title"] = data["title"]
            # 链接对齐
            if not data.get("url") and data.get("source_url"):
                data["url"] = data["source_url"]
            if not data.get("source_url") and data.get("url"):
                data["source_url"] = data["url"]
            # 摘录对齐
            if not data.get("excerpt") and data.get("snippet"):
                data["excerpt"] = data["snippet"]
            if not data.get("snippet") and data.get("excerpt"):
                data["snippet"] = data["excerpt"]
            # 发布日期对齐
            if not data.get("published_at") and data.get("published_date"):
                data["published_at"] = data["published_date"]
            if not data.get("published_date") and data.get("published_at"):
                data["published_date"] = data["published_at"]
            # 型号匹配对齐 (5个标准值: exact, probable, series_only, mismatch, unknown)
            mm = data.get("model_match")
            if not mm:
                matched_bool = data.get("model_matched", True)
                data["model_match"] = "exact" if matched_bool else "mismatch"
            elif mm == "compatible":
                # 兼容旧代码 compatible 映射为 probable
                data["model_match"] = "probable"
            
            # 同步更新布尔标志 model_matched
            if data.get("model_matched") is None:
                data["model_matched"] = (data.get("model_match") in ["exact", "probable", "compatible"])

            # 等级规范对齐 (如 "A级 (官方资料...)" 简化或兼容)
            level_raw = str(data.get("source_level", "A级"))
            if level_raw.startswith("A"):
                data["source_level"] = "A级 (官方资料/说明书/国标质检)"
            elif level_raw.startswith("B"):
                data["source_level"] = "B级 (权威实验室/科技媒体评测)"
            elif level_raw.startswith("C"):
                data["source_level"] = "C级 (垂直自媒体/论坛体验)"
            elif level_raw.startswith("D"):
                data["source_level"] = "D级 (电商买家评价/社交线索)"

            # 来源类型推断
            if not data.get("source_type"):
                level_raw = str(data.get("source_level", ""))
                if level_raw.startswith("A"):
                    data["source_type"] = "官方规格/技术手册"
                elif level_raw.startswith("B"):
                    data["source_type"] = "第三方实验室/专业评测"
                elif level_raw.startswith("C"):
                    data["source_type"] = "社区论坛/用户真实长评"
                else:
                    data["source_type"] = "电商买家评价/自媒体"

            # 证据倾向推断
            if not data.get("evidence_direction"):
                snippet_text = data.get("excerpt") or data.get("snippet") or ""
                if any(w in snippet_text for w in ["不支持", "无法", "不具备", "仅为", "相左", "矛盾", "不一致", "差异", "非满血"]):
                    data["evidence_direction"] = "contradict"
                elif any(w in snippet_text for w in ["仅在", "特定条件", "前提", "受限", "需要搭配", "局部", "降级"]):
                    data["evidence_direction"] = "partial"
                else:
                    data["evidence_direction"] = "support"
        return data


class StepStatusEnum(str, Enum):
    """步骤进度状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_CONFIGURED = "not_configured"
    NEEDS_CONFIRMATION = "needs_confirmation"
    INSUFFICIENT_DATA = "insufficient_data"


class StructuredError(BaseModel):
    """结构化错误信息定义"""
    error_code: str = Field(..., description="错误编码，如 ERR_PAGE_RESTRICTED, ERR_PROVIDER_AUTH")
    error_stage: str = Field(..., description="错误阶段，如 page_fetch, identity_extraction, claim_decomp, model_infer")
    user_message: str = Field(..., description="面向用户的友好说明")
    technical_message: str = Field(..., description="脱敏后的技术错误明细 (严禁包含明文API Key)")
    suggested_action: str = Field(..., description="给用户的明确下一步操作建议")
    retryable: bool = Field(default=False, description="是否支持重试")


class ClaimVerificationResult(BaseModel):
    """单条声明核验结果 (阶段 4 强化规范)"""
    claim: ClaimItem
    conclusion: VerificationConclusionEnum
    evidences: List[EvidenceItem] = Field(default_factory=list)
    analysis_reason: str = Field(..., description="核验分析理由与依据说明")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="结论置信度 (0.0~1.0 兼容字段)")
    self_check_passed: bool = Field(default=True, description="二次事实自检是否通过")
    self_check_notes: Optional[str] = Field(default="通过自检：证据链与推论逻辑严密一致，未发现幻觉或矛盾断言。")
    self_check_rules_evaluated: List[str] = Field(default_factory=list, description="自检评估命中的规则列表")
    pre_purchase_tips: List[str] = Field(default_factory=list, description="针对本声明的购买前核验小贴士")

    # 阶段 4 扩展字段：显式四级核验结论、置信度分级、多源溯源与自检结构
    claim_id: int = Field(default=1, description="声明序号")
    original_claim: str = Field(default="", description="宣传原文摘录")
    normalized_claim: str = Field(default="", description="标准化声明陈述")
    claim_category: str = Field(default="参数", description="声明类别")
    verdict: str = Field(default="有证据支持", description="四级核验结论文本: 有证据支持/部分支持/存在冲突/证据不足")
    confidence_level: str = Field(default="高", description="置信度等级: 高(80~100)/中高(65~79)/中(45~64)/低(0~44)")
    confidence_score: float = Field(default=90.0, ge=0.0, le=100.0, description="量化置信度分值 (0~100)")
    evidence_count: int = Field(default=0, description="候选证据总数量")
    valid_evidence_count: int = Field(default=0, description="有效证据数量")
    independent_source_count: int = Field(default=0, description="独立证据源数量(排除重复转载)")
    highest_source_level: str = Field(default="无", description="最高证据来源等级(A级/B级/C级/D级/无)")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="支持证据ID列表")
    contradicting_evidence_ids: List[str] = Field(default_factory=list, description="冲突证据ID列表")
    partial_evidence_ids: List[str] = Field(default_factory=list, description="部分支持证据ID列表")
    excluded_evidences: List[Dict[str, Any]] = Field(default_factory=list, description="未采用/排除证据及其原因")
    limitations: str = Field(default="", description="结论局限性与前提条件")
    user_advice: str = Field(default="", description="用户购买与使用核验建议")
    needs_manual_review: bool = Field(default=False, description="是否需要人工复核")
    review_reason: str = Field(default="", description="触发人工复核的具体原因")
    self_check_status: str = Field(default="passed", description="自检状态: passed / corrected / failed / needs_manual_review")
    self_check_issues: List[str] = Field(default_factory=list, description="自检发现并纠偏的问题列表")
    confidence_components: Dict[str, float] = Field(default_factory=dict, description="置信度评分组成细项")
    confidence_reason: str = Field(default="", description="置信度量化打分说明")

    @model_validator(mode="before")
    @classmethod
    def populate_phase4_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 同步 claim 属性
            claim_obj = data.get("claim")
            if claim_obj:
                c_id = getattr(claim_obj, "claim_id", None) or (claim_obj.get("claim_id") if isinstance(claim_obj, dict) else 1)
                c_orig = getattr(claim_obj, "original_text", "") or (claim_obj.get("original_text", "") if isinstance(claim_obj, dict) else "")
                c_norm = getattr(claim_obj, "normalized_claim", "") or (claim_obj.get("normalized_claim", "") if isinstance(claim_obj, dict) else "") or c_orig
                c_cat = getattr(claim_obj, "category", "") or (claim_obj.get("category", "") if isinstance(claim_obj, dict) else "参数")
                if not data.get("claim_id"):
                    data["claim_id"] = c_id
                if not data.get("original_claim"):
                    data["original_claim"] = c_orig
                if not data.get("normalized_claim"):
                    data["normalized_claim"] = c_norm
                if not data.get("claim_category"):
                    data["claim_category"] = c_cat

            # 同步 verdict 与 conclusion
            concl = data.get("conclusion")
            if concl:
                concl_str = concl.value if hasattr(concl, "value") else str(concl)
                if not data.get("verdict"):
                    data["verdict"] = concl_str

            # 同步 confidence_score 与 confidence
            c_score = data.get("confidence_score")
            c_float = data.get("confidence")
            if c_score is None and c_float is not None:
                # 0.0~1.0 转为 0~100
                data["confidence_score"] = round(c_float * 100.0, 1)
            elif c_score is not None and c_float is None:
                data["confidence"] = round(c_score / 100.0, 3)
            elif c_score is not None and c_float is not None:
                # 若两者都有，保证一致
                if c_score <= 1.0 and c_float <= 1.0:
                    data["confidence_score"] = round(c_score * 100.0, 1)

            final_score = data.get("confidence_score", 90.0)
            if not data.get("confidence_level"):
                if final_score >= 80.0:
                    data["confidence_level"] = "高"
                elif final_score >= 65.0:
                    data["confidence_level"] = "中高"
                elif final_score >= 45.0:
                    data["confidence_level"] = "中"
                else:
                    data["confidence_level"] = "低"

            # 统计证据
            ev_list = data.get("evidences", [])
            data["evidence_count"] = len(ev_list)
            valid_evs = [e for e in ev_list if getattr(e, "is_valid_evidence", True) if not (isinstance(e, dict) and not e.get("is_valid_evidence", True))]
            data["valid_evidence_count"] = len(valid_evs)
            indep_evs = [e for e in valid_evs if getattr(e, "is_independent_source", True) if not (isinstance(e, dict) and not e.get("is_independent_source", True))]
            data["independent_source_count"] = len(indep_evs)

            # 最高来源等级
            if not data.get("highest_source_level"):
                highest = "无"
                for ev in valid_evs:
                    lvl = getattr(ev, "source_level", "") if not isinstance(ev, dict) else ev.get("source_level", "")
                    if "A级" in lvl or lvl.startswith("A"):
                        highest = "A级"
                        break
                    elif ("B级" in lvl or lvl.startswith("B")) and highest in ["无", "C级", "D级"]:
                        highest = "B级"
                    elif ("C级" in lvl or lvl.startswith("C")) and highest in ["无", "D级"]:
                        highest = "C级"
                    elif ("D级" in lvl or lvl.startswith("D")) and highest == "无":
                        highest = "D级"
                data["highest_source_level"] = highest

            # 划分支持、冲突与部分支持证据列表
            if not data.get("supporting_evidence_ids"):
                supp_ids = []
                conf_ids = []
                part_ids = []
                for ev in ev_list:
                    e_id = getattr(ev, "evidence_id", "") if not isinstance(ev, dict) else ev.get("evidence_id", "")
                    e_dir = getattr(ev, "evidence_direction", "") if not isinstance(ev, dict) else ev.get("evidence_direction", "")
                    if e_dir == "support" and e_id:
                        supp_ids.append(e_id)
                    elif e_dir == "contradict" and e_id:
                        conf_ids.append(e_id)
                    elif e_dir == "partial" and e_id:
                        part_ids.append(e_id)
                data["supporting_evidence_ids"] = supp_ids
                data["contradicting_evidence_ids"] = conf_ids
                data["partial_evidence_ids"] = part_ids

        return data


class VerificationReport(BaseModel):
    """全套核验报告结构 (阶段 4 强化规范)"""
    report_id: str
    task_timestamp: str
    service_mode: str = Field(..., description="执行模式：mock / byok / local")
    is_mock: bool = Field(default=True, description="是否为Mock演示数据")
    
    # 追踪溯源字段
    run_id: str = Field(default="", description="单次核验唯一运行流水号")
    provider_name: str = Field(default="mock", description="实际调用的Provider名称")
    model_name: str = Field(default="offline-mock-v1", description="实际调用的模型名称")
    input_type: str = Field(default="url", description="输入类型：url / text / image")
    input_fingerprint: str = Field(default="", description="输入特征指纹哈希")
    source_url: Optional[str] = Field(default=None, description="来源URL")
    page_fetch_status: str = Field(default="not_executed", description="网页读取状态：success / failed / insufficient_data / not_executed")
    search_status: str = Field(default="not_configured", description="搜索服务状态：not_configured / executed / failed / manual_only / mock_preset")
    evidence_scope: str = Field(default="user_material_only", description="证据边界说明")
    generated_at: str = Field(default="", description="报告生成时间戳")

    # 阶段 4 新增溯源与量化统计字段
    ai_provider_name: str = Field(default="", description="AI Provider 名称")
    ai_model_name: str = Field(default="", description="AI 模型名称")
    search_provider_name: str = Field(default="", description="Search Provider 名称")
    search_query_count: int = Field(default=0, description="分层检索词总数")
    candidate_webpage_count: int = Field(default=0, description="候选网页总数")
    extracted_webpage_count: int = Field(default=0, description="正文提取成功网页数")
    candidate_evidence_count: int = Field(default=0, description="候选证据条数")
    valid_evidence_count: int = Field(default=0, description="有效证据条数")
    independent_source_count: int = Field(default=0, description="独立来源总数")
    manual_review_count: int = Field(default=0, description="需人工复核声明数")
    highest_risk_claim: str = Field(default="", description="风险最高宣传声明")
    most_supported_claim: str = Field(default="", description="证据最充分宣传声明")
    main_limitations: str = Field(default="", description="报告主要局限与边界")
    pre_purchase_checklist: List[str] = Field(default_factory=list, description="购买前核实要点清单")

    product: ProductIdentity
    claims_results: List[ClaimVerificationResult] = Field(default_factory=list)
    filtered_candidates: List[FilteredCandidate] = Field(default_factory=list, description="未采用候选声明列表")
    
    # 四级统计
    conclusion_summary: Dict[str, int] = Field(default_factory=dict)
    
    # 总体摘要与决策建议
    overall_summary: str = Field(default="", description="全篇总体核验综合摘要")
    human_verification_items: List[str] = Field(default_factory=list, description="人工确认项列表")
    human_verification_notes: Optional[List[str]] = Field(default_factory=list, description="人工复核建议(旧字段兼容)")
    pre_purchase_advice: List[str] = Field(default_factory=list, description="消费者购买前操作建议")
    
    # 法律免责声明 (非行政鉴定、非商业欺诈认定)
    disclaimer: str = Field(
        default="免责声明：本报告由 ClaimCheck Pro 基于公开可查证资料与多源交叉验证算法生成，旨在为消费者与运营人员提供客观参考。报告结论仅代表当前检索范围的事实比对，不构成任何司法鉴定、行政质检结论或商业欺诈定性。商品具体性能受个体使用环境、批次变更及固件升级影响，购买与使用请以品牌官方最新公告为准。"
    )

    @model_validator(mode="before")
    @classmethod
    def unify_report_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("human_verification_items") and data.get("human_verification_notes"):
                data["human_verification_items"] = data["human_verification_notes"]
            if not data.get("human_verification_notes") and data.get("human_verification_items"):
                data["human_verification_notes"] = data["human_verification_items"]
            if not data.get("generated_at") and data.get("task_timestamp"):
                data["generated_at"] = data["task_timestamp"]
        return data

