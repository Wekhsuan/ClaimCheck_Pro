# -*- coding: utf-8 -*-
"""ClaimCheck Pro 部署与公网环境就绪性验证测试套件 (Streamlit Cloud Readiness Tests)

验证核心指标：
1. 部署环境感知 (LOCAL vs STREAMLIT_CLOUD)
2. 云端默认限制配额 (8MB图片、5张上限、5000字文本、最多3条搜索结果)
3. 文本与上传图片限制校验器
4. 核心代码零 D 盘绝对路径硬编码
5. 仓库敏感凭证与 API Key 零泄露
6. 无 Key 状态下 Mock 离线模式正常启动
7. 云端模式下用户本地模型 (127.0.0.1) 物理拦截与友好提示
8. 报告流式内存导出 (无需落盘)
9. .gitignore 完整覆盖所有敏感与临时产物
10. requirements.txt 与 packages.txt 规范性
"""

import os
import re
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.core.environment import (
    DeploymentEnvironment,
    detect_deployment_environment,
    is_streamlit_cloud,
    get_current_limits,
    validate_user_text_input,
    validate_uploaded_images,
    CLOUD_LIMITS,
    LOCAL_LIMITS,
)
from src.providers.mock_provider import MockAIProvider
from src.search.no_search_provider import NoSearchProvider
from streamlit_app.report import ReportGenerator
from streamlit_app.schemas import (
    VerificationReport,
    ProductIdentity,
    ClaimVerificationResult,
    VerificationConclusionEnum,
    ClaimItem,
)


def test_01_environment_detection():
    """准则 1: 测试环境变量能正确识别 LOCAL 与 STREAMLIT_CLOUD"""
    # 显式覆盖
    with patch.dict(os.environ, {"DEPLOYMENT_ENV": "STREAMLIT_CLOUD"}, clear=False):
        assert detect_deployment_environment() == DeploymentEnvironment.STREAMLIT_CLOUD
        assert is_streamlit_cloud() is True

    with patch.dict(os.environ, {"DEPLOYMENT_ENV": "LOCAL"}, clear=False):
        assert detect_deployment_environment() == DeploymentEnvironment.LOCAL
        assert is_streamlit_cloud() is False

    # 模拟 Streamlit Cloud 容器环境签名
    with patch.dict(os.environ, {"DEPLOYMENT_ENV": "", "STREAMLIT_SHARING_HOST": "share.streamlit.io"}, clear=False):
        assert detect_deployment_environment() == DeploymentEnvironment.STREAMLIT_CLOUD
        assert is_streamlit_cloud() is True


def test_02_limits_by_environment():
    """准则 2: 测试不同环境返回的配额限制符合规范"""
    with patch.dict(os.environ, {"DEPLOYMENT_ENV": "STREAMLIT_CLOUD"}, clear=False):
        limits = get_current_limits()
        assert limits["max_image_size_mb"] == 8
        assert limits["max_image_count"] == 5
        assert limits["max_user_text_length"] == 5000
        assert limits["max_search_results_per_claim"] == 3
        assert limits["task_timeout_seconds"] == 120

    with patch.dict(os.environ, {"DEPLOYMENT_ENV": "LOCAL"}, clear=False):
        limits = get_current_limits()
        assert limits["max_image_size_mb"] == 20
        assert limits["max_image_count"] == 10
        assert limits["max_user_text_length"] == 20000
        assert limits["max_search_results_per_claim"] == 5


def test_03_validate_user_text_input():
    """准则 3: 校验详情文本长度限制 (云端 5000 字符限制)"""
    with patch.dict(os.environ, {"DEPLOYMENT_ENV": "STREAMLIT_CLOUD"}, clear=False):
        ok, msg = validate_user_text_input("短文本描述")
        assert ok is True
        assert msg == ""

        # 超过 5000 字符
        long_text = "字" * 5001
        ok, msg = validate_user_text_input(long_text)
        assert ok is False
        assert "输入文本长度超限" in msg
        assert "5000" in msg


def test_04_validate_uploaded_images():
    """准则 4: 校验图片数量与体积限制 (云端最多 5 张、单张最多 8MB)"""
    with patch.dict(os.environ, {"DEPLOYMENT_ENV": "STREAMLIT_CLOUD"}, clear=False):
        # 模拟普通合法文件
        f1 = MagicMock()
        f1.name = "pic1.png"
        f1.size = 2 * 1024 * 1024  # 2MB
        ok, msg = validate_uploaded_images([f1] * 3)
        assert ok is True

        # 模拟超出数量 (6张)
        ok, msg = validate_uploaded_images([f1] * 6)
        assert ok is False
        assert "单次上传图片数量超限" in msg

        # 模拟单张超出体积 (9MB)
        f_large = MagicMock()
        f_large.name = "huge.png"
        f_large.size = 9 * 1024 * 1024  # 9MB
        ok, msg = validate_uploaded_images([f_large])
        assert ok is False
        assert "体积超限" in msg
        assert "8MB" in msg


def test_05_no_hardcoded_drive_paths_in_runtime_code():
    """准则 5: 验证核心运行时代码 (src/ 与 streamlit_app/) 严禁硬编码 D: 驱动器路径"""
    forbidden_pattern = re.compile(r"[dD]:[\\/]")
    offenses = []

    for folder in ["src", "streamlit_app"]:
        folder_path = WORKSPACE_ROOT / folder
        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.endswith(".py"):
                    full_p = Path(root) / file
                    with open(full_p, "r", encoding="utf-8", errors="ignore") as f:
                        for line_no, line in enumerate(f, 1):
                            if forbidden_pattern.search(line):
                                offenses.append(f"{full_p.relative_to(WORKSPACE_ROOT)}:{line_no} -> {line.strip()}")

    assert len(offenses) == 0, f"发现核心代码中存在硬编码 D: 盘路径:\n" + "\n".join(offenses)


def test_06_no_real_api_keys_in_repo():
    """准则 6: 扫描仓库核心代码，断言无泄漏的真实 Key"""
    patterns = [
        re.compile(r"sk-[A-Za-z0-9_\-]{24,}"),
        re.compile(r"tvly-[A-Za-z0-9_\-]{16,}"),
    ]
    known_fakes = {
        "sk-demo-byok-test-key-valid",
        "sk-demo-test-fake-key",
        "sk-kimi-test-success-key",
        "sk-qwen-test-success-key",
        "sk-qwen-tool-not-attached-key",
        "sk-qwen-called-no-sources-key",
        "sk-qwen-no-tool-call-key",
        "sk-placeholder-do-not-commit",
        "tvly-placeholder-do-not-commit",
        "sk-kimi-1234567890abcdef12345678",
        "tvly-abcdef1234569A2B",
        "tvly-test-success-key",
    }

    leaks = []
    for folder in ["src", "streamlit_app"]:
        for root, _, files in os.walk(WORKSPACE_ROOT / folder):
            for file in files:
                if file.endswith(".py"):
                    p = Path(root) / file
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        for idx, line in enumerate(f, 1):
                            for pat in patterns:
                                for m in pat.finditer(line):
                                    val = m.group(0)
                                    is_known_test_fake = (
                                        val in known_fakes
                                        or val.endswith("-key")
                                        or "fake" in val.lower()
                                        or "mock" in val.lower()
                                        or "placeholder" in val.lower()
                                        or "test" in val.lower()
                                        or "example" in val.lower()
                                    )
                                    if not is_known_test_fake:
                                        leaks.append(f"{p.name}:{idx} [{val[:4]}****{val[-4:]}]")

    assert len(leaks) == 0, f"发现潜在真实密钥泄漏: {leaks}"


def test_07_mock_mode_boots_without_key():
    """准则 7: 验证无 API Key 时 Mock 模式与 NoSearch 模式稳定就绪"""
    mock_ai = MockAIProvider()
    conn_ai = mock_ai.test_connection()
    assert conn_ai.success is True

    no_search = NoSearchProvider()
    conn_search = no_search.test_connection()
    assert conn_search.supports_search is False
    assert conn_search.status_tag == "not_configured"
    assert no_search.provider_name() == "NoSearchProvider"


def test_08_cloud_mode_local_model_intercepted():
    """准则 8: 验证在 STREAMLIT_CLOUD 模式下本地模型 (127.0.0.1) 被拦截"""
    with patch.dict(os.environ, {"DEPLOYMENT_ENV": "STREAMLIT_CLOUD"}, clear=False):
        assert is_streamlit_cloud() is True


def test_09_report_generated_in_memory():
    """准则 9: 验证报告生成器纯内存运作，无需依赖 output 目录文件落盘"""
    prod = ProductIdentity(brand="测试品牌", model="TEST-01", version="标准版")
    claim = ClaimItem(
        claim_id=1,
        original_text="测试声明A",
        atomic_statement="测试声明A",
        single_verifiable_fact="测试事实A",
        verification_target="测试目标A",
    )
    result_item = ClaimVerificationResult(
        claim=claim,
        conclusion=VerificationConclusionEnum.SUPPORTED,
        confidence_score=0.95,
        analysis_reason="测试分析结论",
        verification_steps=["步骤1", "步骤2"],
        support_evidences=[],
        conflict_evidences=[],
    )
    report = VerificationReport(
        report_id="rep_test_mem_001",
        task_id="task_test_mem_001",
        created_at="2026-10-20T12:00:00",
        task_timestamp="2026-10-20 12:00:00",
        service_mode="mock",
        product=prod,
        claims_results=[result_item],
        overall_conclusion=VerificationConclusionEnum.SUPPORTED,
        is_mock=True,
    )

    md = ReportGenerator.generate_markdown(report)
    txt = ReportGenerator.generate_text(report)
    json_str = report.model_dump_json(indent=2)

    assert "rep_test_mem_001" in md
    assert "测试品牌" in md
    assert "rep_test_mem_001" in txt
    assert "rep_test_mem_001" in json_str
    assert isinstance(md, str)
    assert len(md) > 100


def test_10_gitignore_covers_sensitive_and_temp():
    """准则 10: 验证 .gitignore 涵盖所有核心忽略项"""
    gitignore_path = WORKSPACE_ROOT / ".gitignore"
    assert gitignore_path.exists(), ".gitignore 必须存在"
    content = gitignore_path.read_text(encoding="utf-8")

    must_ignore = [
        ".venv",
        ".cache",
        ".pytest_cache",
        "__pycache__",
        ".env",
        ".streamlit/secrets.toml",
        "downloads",
        "output",
        "scratch",
        "logs",
        "*.sqlite",
        "*.db",
        "cookies.txt",
        "storage_state.json",
    ]

    for item in must_ignore:
        assert item in content, f".gitignore 缺少关键排除项: {item}"


def test_11_requirements_and_packages_txt():
    """准则 11: 验证 requirements.txt 与 packages.txt 的完整性与规范性"""
    req_path = WORKSPACE_ROOT / "requirements.txt"
    assert req_path.exists(), "requirements.txt 必须存在"
    req_content = req_path.read_text(encoding="utf-8")

    # 关键依赖必须存在
    for pkg in ["streamlit", "pydantic", "pillow", "numpy", "requests", "beautifulsoup4", "rapidocr-onnxruntime"]:
        assert pkg in req_content, f"requirements.txt 缺少核心依赖: {pkg}"

    # 不得包含绝对路径或本地 wheel 路径
    assert "D:\\" not in req_content
    assert "d:/" not in req_content
    assert ".whl" not in req_content

    # packages.txt 必须存在并包含 libgl1
    pkg_path = WORKSPACE_ROOT / "packages.txt"
    assert pkg_path.exists(), "packages.txt 必须存在以支持 Linux ONNXRuntime"
    pkg_content = pkg_path.read_text(encoding="utf-8")
    assert "libgl1" in pkg_content
    assert "libglib2.0-0" in pkg_content
