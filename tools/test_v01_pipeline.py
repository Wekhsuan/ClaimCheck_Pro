"""ClaimCheck Pro V0.1 单元与集成测试脚本

验证 Mock 案例数据完整性、四级结论覆盖率、报告生成及工作区路径约束
"""

import sys
from pathlib import Path

# 确保 UTF-8 打印输出
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 将根目录加入路径
BASE_DIR = Path(r"D:\ClaimCheck_Pro").resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pytest
from streamlit_app.config import MOCK_DATA_DIR, OUTPUT_DIR
from streamlit_app.mock_provider import mock_provider
from streamlit_app.report import ReportGenerator
from streamlit_app.schemas import VerificationConclusionEnum, VerificationReport


def test_mock_cases_exist():
    """验证4个预置案例全部存在且正确加载"""
    cases = mock_provider.list_cases()
    assert len(cases) >= 4, f"预置案例数量不足4个，当前仅有 {len(cases)} 个"
    case_ids = [c["case_id"] for c in cases]
    assert "case_01_supported" in case_ids
    assert "case_02_partially_supported" in case_ids
    assert "case_03_conflict" in case_ids
    assert "case_04_insufficient" in case_ids
    print(f"✅ 预置案例检查通过：已加载 {len(cases)} 个案例: {case_ids}")


def test_four_conclusions_coverage():
    """验证四级结论（支持、部分支持、冲突、证据不足）均有真实案例覆盖"""
    covered_conclusions = set()
    for case_info in mock_provider.list_cases():
        cid = case_info["case_id"]
        report = mock_provider.generate_report_from_case(cid)
        assert isinstance(report, VerificationReport)
        assert report.is_mock is True
        assert len(report.claims_results) <= 5, "声明数量不能超过5条"
        for cr in report.claims_results:
            covered_conclusions.add(cr.conclusion.value)

    assert VerificationConclusionEnum.SUPPORTED.value in covered_conclusions
    assert VerificationConclusionEnum.PARTIALLY_SUPPORTED.value in covered_conclusions
    assert VerificationConclusionEnum.CONFLICT.value in covered_conclusions
    assert VerificationConclusionEnum.INSUFFICIENT_EVIDENCE.value in covered_conclusions
    print(f"✅ 四级结论全覆盖检查通过：{covered_conclusions}")


def test_report_generation_and_mock_watermark():
    """验证报告生成器输出及必显Mock标记"""
    report = mock_provider.generate_report_from_case("case_01_supported")
    md = ReportGenerator.generate_markdown(report)
    txt = ReportGenerator.generate_text(report)

    # 必须包含 Mock 标记
    assert "当前为Mock演示数据，未执行实时网络核验" in md
    assert "当前为Mock演示数据，未执行实时网络核验" in txt
    # 必须包含商品身份
    assert report.product.brand in md
    assert report.product.model in md
    # 必须包含免责声明
    assert "免责声明" in md

    # 保存测试
    saved_file = ReportGenerator.save_report_to_disk(report)
    assert saved_file.exists()
    assert saved_file.parent == OUTPUT_DIR
    print(f"✅ 报告生成与Mock标记检查通过，生成文件: {saved_file}")


def test_insufficient_evidence_rule():
    """验证重要业务规则：不得将证据不足断言为虚假宣传"""
    report = mock_provider.generate_report_from_case("case_04_insufficient")
    for cr in report.claims_results:
        # 不能出现将“证据不足”判定为冲突或虚假
        assert cr.conclusion == VerificationConclusionEnum.INSUFFICIENT_EVIDENCE
        assert "虚假" not in cr.conclusion.value
    print(f"✅ 规则验证通过：没有检索到证据时不误判为虚假，正确归入证据不足。")


if __name__ == "__main__":
    test_mock_cases_exist()
    test_four_conclusions_coverage()
    test_report_generation_and_mock_watermark()
    test_insufficient_evidence_rule()
    print("\n🎉 全部单元与规则测试通过！")
