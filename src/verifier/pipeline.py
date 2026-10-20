"""ClaimCheck Pro 核心核验流水线引擎 (Verification Pipeline)

负责端到端核验流程编排：
1. 严格隔离 Mock 模式与真实模式 (BYOK / Local)；
2. 计算输入特征指纹 (input_fingerprint)；
3. 执行多阶段处理：商品解析 -> 身份抽取 -> 声明拆解 -> 证据检索适配 -> 交叉比对与二次自检；
4. 明确分离 LLM Provider 与 Search Provider；未配置搜索时显式标明 not_configured；
5. 生成包含全量溯源追踪字段的 VerificationReport；
6. 严禁在真实模式下调用 MockProvider 或返回内置 Mock 数据；
7. 严禁任何形式的静默异常回退。
"""

import hashlib
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from src.crawlers.url_extractor import (
    AccessRestrictedError,
    ExtractedProductData,
    InsufficientProductInfoError,
    extract_product_from_url,
)
from src.parsers.text_parser import clean_product_detail_text
from src.providers import (
    AIProvider,
    LocalModelProvider,
    MockAIProvider,
    OpenAICompatibleProvider,
)
from src.verifier.claim_decomposer import ClaimDecomposer
from src.verifier.cross_verifier import CrossVerifier
from src.verifier.identity_extractor import (
    ProductIdentityResult,
    extract_product_identity,
)
from streamlit_app.mock_provider import mock_provider
from streamlit_app.schemas import (
    ClaimItem,
    ClaimVerificationResult,
    EvidenceItem,
    ProductIdentity,
    SourceLevelEnum,
    StepStatusEnum,
    StructuredError,
    VerificationConclusionEnum,
    VerificationReport,
)

logger = logging.getLogger("claimcheck.pipeline")


class DataModeMismatchError(Exception):
    """数据模式不一致异常：真实模式下检测到 Mock 数据注入"""
    pass


class CandidateConfirmationNeeded(Exception):
    """多候选型号待确认异常：中断流水线提示用户指定目标型号"""
    def __init__(self, identity_res: ProductIdentityResult):
        super().__init__(f"检测到 {len(identity_res.candidates)} 个相似候选型号，需人工确认")
        self.identity_res = identity_res


class NoVerifiableClaimsError(Exception):
    """未提取到可验证宣传声明异常：终止后续核验并友好提示用户"""
    def __init__(
        self,
        message: str = "暂未从当前资料中提取到可验证的宣传声明。请上传或粘贴包含具体参数、功能或卖点的资料，例如续航时间、降噪等级、防水等级、功率、材料或兼容性说明。",
        filtered_candidates: Optional[List[Any]] = None,
    ):
        super().__init__(message)
        self.user_message = message
        self.filtered_candidates = filtered_candidates or []


def calculate_input_fingerprint(
    input_type: str,
    content: str,
    service_mode: str,
    provider_name: str,
    model_name: str,
    confirmed_model: str = "",
) -> str:
    """计算输入指纹 (SHA-256)，用于精准检测输入变更与防止展示过期结果"""
    norm_content = (content or "").strip()
    norm_type = (input_type or "").strip().lower()
    norm_mode = (service_mode or "").strip().lower()
    norm_provider = (provider_name or "").strip().lower()
    norm_model = (model_name or "").strip().lower()
    norm_confirmed = (confirmed_model or "").strip()

    raw_str = f"{norm_type}|{norm_content}|{norm_mode}|{norm_provider}|{norm_model}|{norm_confirmed}"
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]


class VerificationPipeline:
    """核验流水线调度器"""

    def __init__(self):
        self.decomposer = ClaimDecomposer(max_claims=5)
        self.cross_verifier = CrossVerifier()

    def create_provider(
        self,
        service_mode: str,
        byok_config: Optional[Dict[str, Any]] = None,
        local_config: Optional[Dict[str, Any]] = None,
    ) -> AIProvider:
        """根据服务模式构建对应的 Provider 实例，严格隔离 Mock 与真实模式"""
        byok_config = byok_config or {}
        local_config = local_config or {}

        if service_mode == "mock":
            return MockAIProvider()

        elif service_mode == "byok":
            base_url = byok_config.get("base_url", "")
            api_key = byok_config.get("api_key", "")
            model_name = byok_config.get("model_name", "gpt-4o-mini")
            timeout = byok_config.get("timeout", 30)
            temperature = byok_config.get("temperature", 0.3)
            max_tokens = byok_config.get("max_tokens", 2048)

            if not api_key:
                raise ValueError("用户 API Key 不能为空。本项目不提供默认开发者密钥，请在界面填写您的有效密钥。")

            return OpenAICompatibleProvider(
                base_url=base_url,
                api_key=api_key,
                model_name=model_name,
                timeout=timeout,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        elif service_mode == "local":
            base_url = local_config.get("base_url", "http://127.0.0.1:11434/v1")
            model_name = local_config.get("model_name", "qwen2.5:7b")
            timeout = local_config.get("timeout", 45)
            temperature = local_config.get("temperature", 0.2)
            max_tokens = local_config.get("max_tokens", 2048)

            return LocalModelProvider(
                base_url=base_url,
                model_name=model_name,
                timeout=timeout,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        else:
            raise ValueError(f"未知的服务模式: {service_mode}")

    def run_mock_pipeline(
        self,
        case_id: str,
        input_type: str = "url",
        source_input: str = "",
    ) -> Tuple[VerificationReport, Dict[str, StepStatusEnum]]:
        """执行纯 Mock 模式流水线 (仅在明确选择 mock 时调用)"""
        progress_state = {
            "fetch_info": StepStatusEnum.SUCCESS,
            "confirm_identity": StepStatusEnum.SUCCESS,
            "decompose_claims": StepStatusEnum.SUCCESS,
            "search_evidence": StepStatusEnum.SUCCESS,
            "cross_verify": StepStatusEnum.SUCCESS,
            "generate_report": StepStatusEnum.SUCCESS,
        }

        # 调用预置 mock_provider 加载标准案例
        report = mock_provider.generate_report_from_case(case_id, service_mode="mock")
        
        # 补全元数据字段
        fingerprint = calculate_input_fingerprint(
            input_type=input_type,
            content=source_input or case_id,
            service_mode="mock",
            provider_name="MockAIProvider",
            model_name="offline-mock-v1",
            confirmed_model=report.product.model if report.product else "",
        )
        report.run_id = f"RUN-MOCK-{uuid.uuid4().hex[:8]}"
        report.provider_name = "MockAIProvider"
        report.model_name = "offline-mock-v1"
        report.input_type = input_type
        report.input_fingerprint = fingerprint
        report.source_url = source_input if input_type == "url" else None
        report.page_fetch_status = "success"
        report.search_status = "mock_preset"
        report.evidence_scope = "预置离线知识库与标准案例"
        report.is_mock = True
        report.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return report, progress_state

    def run_real_pipeline(
        self,
        service_mode: str,
        input_type: str,
        source_input: str,
        provider: AIProvider,
        confirmed_identity: Optional[ProductIdentityResult] = None,
        confirmed_claims: Optional[List[ClaimItem]] = None,
        manual_evidence_links: str = "",
        manual_evidence_materials: str = "",
        overridden_source_url: Optional[str] = None,
        overridden_page_fetch_status: Optional[str] = None,
        search_provider_name: str = "none",
        search_queries: Optional[List[Any]] = None,
        structured_evidences: Optional[List[EvidenceItem]] = None,
        candidate_webpages: Optional[List[Any]] = None,
        extracted_webpages: Optional[List[Any]] = None,
    ) -> Tuple[VerificationReport, Dict[str, StepStatusEnum]]:
        """执行真实核验流水线 (BYOK 或 Local)，严格隔离 Mock 逻辑"""
        if service_mode == "mock":
            raise ValueError("真实流水线严禁在 mock 模式下被调用")

        run_id = f"RUN-REAL-{uuid.uuid4().hex[:8]}"
        progress_state = {
            "fetch_info": StepStatusEnum.PENDING,
            "confirm_identity": StepStatusEnum.PENDING,
            "decompose_claims": StepStatusEnum.PENDING,
            "search_evidence": StepStatusEnum.NOT_CONFIGURED,
            "cross_verify": StepStatusEnum.PENDING,
            "generate_report": StepStatusEnum.PENDING,
        }

        raw_marketing_text = ""
        source_url = overridden_source_url
        page_fetch_status = overridden_page_fetch_status or "not_executed"

        # ---------------------------------------------------------------------
        # 步骤 1：读取商品信息
        # ---------------------------------------------------------------------
        progress_state["fetch_info"] = StepStatusEnum.RUNNING
        if input_type == "url":
            source_url = source_input.strip()
            try:
                ext_data: ExtractedProductData = extract_product_from_url(source_url)
                raw_marketing_text = (
                    f"{ext_data.name}\n"
                    f"{ext_data.description}\n"
                    + "\n".join(ext_data.specs_list)
                )
                page_fetch_status = "success"
                progress_state["fetch_info"] = StepStatusEnum.SUCCESS
            except (AccessRestrictedError, InsufficientProductInfoError) as e:
                page_fetch_status = "failed"
                progress_state["fetch_info"] = StepStatusEnum.FAILED
                # 严格禁止回退到 Mock 案例，直接抛出供前端结构化渲染
                raise e
            except Exception as e:
                page_fetch_status = "failed"
                progress_state["fetch_info"] = StepStatusEnum.FAILED
                raise RuntimeError(f"网页读取异常: {str(e)}")

        elif input_type == "text":
            clean_res = clean_product_detail_text(source_input)
            raw_marketing_text = clean_res.cleaned_text
            if not overridden_page_fetch_status:
                page_fetch_status = "success"
            progress_state["fetch_info"] = StepStatusEnum.SUCCESS

        elif input_type == "image":
            # 文本已由前端 OCR 提取存入
            raw_marketing_text = source_input.strip()
            if not overridden_page_fetch_status:
                page_fetch_status = "success"
            progress_state["fetch_info"] = StepStatusEnum.SUCCESS
        else:
            raise ValueError(f"不支持的输入类型: {input_type}")

        if not raw_marketing_text.strip():
            progress_state["fetch_info"] = StepStatusEnum.INSUFFICIENT_DATA
            raise ValueError("未能提取到有效商品文本，请补充商品文案或规格后再试。")

        # ---------------------------------------------------------------------
        # 步骤 2：确认商品身份
        # ---------------------------------------------------------------------
        progress_state["confirm_identity"] = StepStatusEnum.RUNNING
        identity_res = confirmed_identity
        if not identity_res:
            identity_res = extract_product_identity(raw_marketing_text)

        if identity_res.has_multiple_candidates and not identity_res.user_confirmed:
            progress_state["confirm_identity"] = StepStatusEnum.NEEDS_CONFIRMATION
            # 中断流水线，需用户前台交互指定型号
            raise CandidateConfirmationNeeded(identity_res)

        product = ProductIdentity(
            brand=identity_res.brand or "通用品牌",
            model=identity_res.model or "通用型号",
            version=identity_res.variant or "标准规格",
            specs=identity_res.identity_evidence or raw_marketing_text[:120],
            sales_region=identity_res.region or "中国大陆",
            product_id=getattr(identity_res, "product_id", "") or "",
            confidence=identity_res.identity_confidence,
        )
        progress_state["confirm_identity"] = StepStatusEnum.SUCCESS

        # ---------------------------------------------------------------------
        # 步骤 3：拆解宣传声明并执行质量过滤 (最多 5 条原子事实，不足时不强凑)
        # ---------------------------------------------------------------------
        progress_state["decompose_claims"] = StepStatusEnum.RUNNING
        filtered_candidates = []
        if confirmed_claims and len(confirmed_claims) > 0:
            claims = confirmed_claims[:5]
        else:
            # 兼容性调用：首先调用 self.decomposer.decompose，以便单元测试中的 mock/patch 正常生效
            claims = self.decomposer.decompose(raw_marketing_text, target_product=product)
            if hasattr(self.decomposer, "decompose_with_details"):
                _, filtered_candidates = self.decomposer.decompose_with_details(
                    raw_marketing_text, target_product=product
                )

        if not claims:
            progress_state["decompose_claims"] = StepStatusEnum.INSUFFICIENT_DATA
            raise NoVerifiableClaimsError(
                "暂未从当前资料中提取到可验证的宣传声明。请上传或粘贴包含具体参数、功能或卖点的资料，例如续航时间、降噪等级、防水等级、功率、材料或兼容性说明。",
                filtered_candidates=filtered_candidates,
            )

        claims = claims[:5]
        progress_state["decompose_claims"] = StepStatusEnum.SUCCESS

        # ---------------------------------------------------------------------
        # 步骤 4：检索公开证据 (模型与搜索严格分离)
        # ---------------------------------------------------------------------
        # 规则 7: 模型 Provider 与 Search Provider 必须完全分开
        search_status = "not_configured"
        all_evidences: List[EvidenceItem] = []

        # 1) 若传入了阶段 3 真实结构化提取的证据，载入证据池
        if structured_evidences:
            all_evidences.extend(structured_evidences)
            search_status = "executed"

        # 2) 若用户提供了手动参考材料与链接，组装为高可信 A/B 级证据
        if manual_evidence_links.strip() or manual_evidence_materials.strip():
            if search_status == "not_configured":
                search_status = "manual_only"
            if manual_evidence_materials.strip():
                all_evidences.append(
                    EvidenceItem(
                        evidence_id="MANUAL-SPEC-01",
                        title=f"{product.brand} {product.model} 用户提供技术说明书/规格材料",
                        url=manual_evidence_links.strip().splitlines()[0] if manual_evidence_links.strip() else "",
                        source_type="用户提供官方技术材料",
                        source_level="A级 (官方资料/说明书/国标质检)",
                        model_match="exact",
                        excerpt=manual_evidence_materials.strip()[:400],
                        evidence_direction="support",
                        published_at=datetime.now().strftime("%Y-%m"),
                        is_valid_evidence=True,
                        is_independent_source=True,
                    )
                )

        if search_status == "not_configured":
            progress_state["search_evidence"] = StepStatusEnum.NOT_CONFIGURED
            evidence_scope = "仅用户提供的文本与截图（未配置网络搜索服务，未执行全网检索）"
        elif search_status == "manual_only":
            progress_state["search_evidence"] = StepStatusEnum.SUCCESS
            evidence_scope = "基于用户提供材料与手动证据进行比对"
        else:
            progress_state["search_evidence"] = StepStatusEnum.SUCCESS
            if input_type == "image":
                evidence_scope = "基于图片文字与商品特征的联网检索，使用独立网络搜索服务与候选网页安全提取正文进行多源交叉核验"
            else:
                evidence_scope = "基于独立网络搜索服务与候选网页安全提取正文进行多源交叉核验"

        # ---------------------------------------------------------------------
        # 步骤 5：多源交叉验证与事实自检
        # ---------------------------------------------------------------------
        progress_state["cross_verify"] = StepStatusEnum.RUNNING
        target_prod_dict = {
            "brand": product.brand,
            "model": product.model,
            "variant": product.version,
            "region": product.sales_region,
        }

        claims_results: List[ClaimVerificationResult] = []
        for claim in claims:
            # 无论是否有外部证据，均统一交由 cross_verifier 判定
            c_res = self.cross_verifier.verify_single_claim(
                claim=claim,
                evidences=all_evidences,
                target_product=target_prod_dict,
                search_status=search_status,
            )
            claims_results.append(c_res)

        progress_state["cross_verify"] = StepStatusEnum.SUCCESS

        # ---------------------------------------------------------------------
        # 步骤 6：生成最终全套核验报告 (包含阶段 4 强化溯源字段)
        # ---------------------------------------------------------------------
        progress_state["generate_report"] = StepStatusEnum.RUNNING

        fingerprint = calculate_input_fingerprint(
            input_type=input_type,
            content=source_input,
            service_mode=service_mode,
            provider_name=provider.get_name(),
            model_name=provider.model_name,
            confirmed_model=product.model,
        )

        report = self.cross_verifier.generate_full_report(
            product=product,
            claims_results=claims_results,
            service_mode=service_mode,
            is_mock=False,  # 真实模式严禁为 True
            search_status=search_status,
            ai_provider_name=provider.get_name(),
            ai_model_name=provider.model_name,
            search_provider_name=search_provider_name,
            search_query_count=len(search_queries) if search_queries else 0,
            candidate_webpage_count=len(candidate_webpages) if candidate_webpages else 0,
            extracted_webpage_count=len(extracted_webpages) if extracted_webpages else 0,
            run_id=run_id,
        )

        report.report_id = f"REP-{service_mode.upper()}-{int(time.time())}"
        report.run_id = run_id
        report.input_type = input_type
        report.input_fingerprint = fingerprint
        report.source_url = source_url
        report.page_fetch_status = page_fetch_status
        report.evidence_scope = evidence_scope
        report.filtered_candidates = filtered_candidates
        report.provider_name = provider.get_name()
        report.model_name = provider.model_name

        # 强安全门禁校验：真实模式下绝不允许 is_mock=True
        if report.is_mock is True and service_mode != "mock":
            raise DataModeMismatchError(
                "检测到数据模式不一致：当前为真实服务模式，但结果来自Mock数据。已阻断展示，请核查流水线调用。"
            )

        progress_state["generate_report"] = StepStatusEnum.SUCCESS
        return report, progress_state


# 全局单例
verification_pipeline = VerificationPipeline()
