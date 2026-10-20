"""ClaimCheck Pro Mock 数据提供层 (MockProvider)

负责加载预置离线案例，组装标准数据模式，确保无网、无Key下依然可完整演示
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from streamlit_app.config import MOCK_DATA_DIR
from streamlit_app.schemas import (
    ClaimItem,
    ClaimVerificationResult,
    EvidenceItem,
    ProductIdentity,
    SourceLevelEnum,
    VerificationConclusionEnum,
    VerificationReport,
)

logger = logging.getLogger("claimcheck.mock_provider")


class MockProvider:
    """Mock 数据提供者"""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or MOCK_DATA_DIR
        self._cases: Dict[str, dict] = {}
        self._load_cases()

    def _load_cases(self):
        """扫描并加载 mock_data 目录下的所有 json 文件"""
        if not self.data_dir.exists():
            return
        for file_path in self.data_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    case_data = json.load(f)
                    case_id = case_data.get("case_id") or file_path.stem
                    self._cases[case_id] = case_data
            except Exception as e:
                logger.error(f"加载Mock案例文件失败 {file_path}: {e}")

    def list_cases(self) -> List[Dict[str, str]]:
        """获取所有可用 Mock 案例简要列表"""
        return [
            {
                "case_id": cid,
                "case_name": data.get("case_name", cid),
                "input_type": data.get("input_type", "text"),
                "input_sample": data.get("input_sample", ""),
            }
            for cid, data in self._cases.items()
        ]

    def get_case_raw(self, case_id: str) -> Optional[dict]:
        """获取原始案例字典"""
        return self._cases.get(case_id)

    def generate_report_from_case(self, case_id: str, service_mode: str = "mock") -> VerificationReport:
        """从预置案例生成严格校验的 VerificationReport 模型"""
        case_data = self._cases.get(case_id)
        if not case_data:
            # 默认使用第一个案例
            if self._cases:
                case_id = list(self._cases.keys())[0]
                case_data = self._cases[case_id]
            else:
                raise ValueError("未找到任何可用的Mock案例数据")

        # 1. 抽取商品身份
        prod_data = case_data.get("product", {})
        product = ProductIdentity(
            brand=prod_data.get("brand", "未知品牌"),
            model=prod_data.get("model", "未知型号"),
            version=prod_data.get("version", "标准版"),
            specs=prod_data.get("specs", ""),
            sales_region=prod_data.get("sales_region", "中国大陆"),
            confidence=prod_data.get("confidence", 0.95),
        )

        # 2. 抽取声明项映射
        claims_map = {}
        for c in case_data.get("claims", []):
            cid = c.get("claim_id")
            claims_map[cid] = ClaimItem(
                claim_id=cid,
                original_text=c.get("original_text", ""),
                atomic_statement=c.get("atomic_statement", ""),
                category=c.get("category", "核心功能"),
                verification_target=c.get("verification_target", "技术指标"),
            )

        # 3. 组装核验结果列表 (最多5条)
        results: List[ClaimVerificationResult] = []
        for v in case_data.get("verification_results", [])[:5]:
            cid = v.get("claim_id")
            claim = claims_map.get(cid)
            if not claim:
                continue

            # 组装证据项
            evidences: List[EvidenceItem] = []
            for e in v.get("evidences", []):
                # 匹配或转换来源等级枚举
                lvl_str = e.get("source_level", "")
                level_enum = SourceLevelEnum.LEVEL_A
                for enum_val in SourceLevelEnum:
                    if enum_val.value.startswith(lvl_str[:2]) or lvl_str.startswith(enum_val.value[:2]):
                        level_enum = enum_val
                        break

                evidences.append(
                    EvidenceItem(
                        evidence_id=e.get("evidence_id", "EVID-00"),
                        source_title=e.get("source_title", "公开参考来源"),
                        source_url=e.get("source_url", ""),
                        source_level=level_enum,
                        model_matched=e.get("model_matched", True),
                        snippet=e.get("snippet", ""),
                        published_date=e.get("published_date", ""),
                    )
                )

            # 匹配结论枚举
            conclusion_str = v.get("conclusion", "证据不足")
            conclusion_enum = VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
            for c_enum in VerificationConclusionEnum:
                if c_enum.value == conclusion_str:
                    conclusion_enum = c_enum
                    break

            results.append(
                ClaimVerificationResult(
                    claim=claim,
                    conclusion=conclusion_enum,
                    evidences=evidences,
                    analysis_reason=v.get("analysis_reason", "经比对公开资料形成核验分析。"),
                    confidence=v.get("confidence", 0.9),
                    self_check_passed=v.get("self_check_passed", True),
                    self_check_notes=v.get("self_check_notes", "通过自检"),
                )
            )

        # 4. 统计四级结论分布
        summary = {
            VerificationConclusionEnum.SUPPORTED.value: 0,
            VerificationConclusionEnum.PARTIALLY_SUPPORTED.value: 0,
            VerificationConclusionEnum.CONFLICT.value: 0,
            VerificationConclusionEnum.INSUFFICIENT_EVIDENCE.value: 0,
        }
        for r in results:
            summary[r.conclusion.value] = summary.get(r.conclusion.value, 0) + 1

        # 5. 组装总体摘要与决策建议
        total_claims = len(results)
        s_cnt = summary.get(VerificationConclusionEnum.SUPPORTED.value, 0)
        p_cnt = summary.get(VerificationConclusionEnum.PARTIALLY_SUPPORTED.value, 0)
        c_cnt = summary.get(VerificationConclusionEnum.CONFLICT.value, 0)
        i_cnt = summary.get(VerificationConclusionEnum.INSUFFICIENT_EVIDENCE.value, 0)

        summary_text = (
            f"本次针对【{product.brand} {product.model} ({product.version})】共核验 {total_claims} 项核心宣传声明。"
            f"核验结果统计：有证据支持 {s_cnt} 条，部分支持 {p_cnt} 条，存在冲突 {c_cnt} 条，证据不足 {i_cnt} 条。"
        )
        if c_cnt > 0:
            summary_text += " ⚠️ 经检索官方技术手册与权威实测，部分标称参数与实际规格存在冲突，建议重点关注并核实批次。"
        elif p_cnt > 0:
            summary_text += " 💡 核心功能基本属实，但宣传文案省略了必要的使用前提条件（如线材、协议或特定环境限制）。"
        elif s_cnt == total_claims and total_claims > 0:
            summary_text += " ✅ 各项宣传均获得同型号A级官方规格书与专业实测的充分支持，结论确凿。"

        human_items = case_data.get("human_verification_notes", []) or [
            f"核实机身铭牌标准型号是否与宣传 '{product.model}' 完全一致，谨防同系列低配混淆。",
            "优先在品牌官方服务支持页面输入序列号核验三包凭证与质检信息。"
        ]

        advice_items = case_data.get("pre_purchase_advice", []) or [
            "建议优先通过官方直营或授权专卖店选购，索取正规发票以保障售后权益。",
            "若商品宣称快充或高清传输协议，请提前确认自身配套设备（手机/充电头/线材）是否具备兼容能力。",
            "收货开箱时先行通电试机，核对机身固件显示的技术代号后再撕除保护膜确认收货。"
        ]

        # 6. 组装完整报告
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_id = f"REP-{case_id.upper()}-{int(datetime.now().timestamp())}"

        return VerificationReport(
            report_id=report_id,
            task_timestamp=now_str,
            service_mode=service_mode,
            is_mock=True,
            product=product,
            claims_results=results,
            conclusion_summary=summary,
            overall_summary=case_data.get("overall_summary", summary_text),
            human_verification_items=human_items,
            human_verification_notes=human_items,
            pre_purchase_advice=advice_items,
        )


# 单例实例
mock_provider = MockProvider()
