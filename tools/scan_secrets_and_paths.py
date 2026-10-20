#!/usr/bin/env python3
"""
ClaimCheck Pro Repository Secret & Cross-Platform Path Scanner
==============================================================
Scans the repository (excluding .venv, .git, etc.) for:
1. Sensitive patterns (sk-, tvly-, Bearer, Authorization, Cookie, api_key, password)
2. Non-cross-platform paths (D:\, D:/, ClaimCheck_Pro hardcoded paths, Windows user folders)
"""

import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

WORKSPACE = Path(__file__).resolve().parent.parent

IGNORE_DIRS = {
    ".venv", ".git", ".cache", ".pytest_cache", "downloads", "node_modules",
    "__pycache__", "output", ".idea", ".vscode"
}

IGNORE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".docx", ".pdf",
    ".exe", ".dll", ".pyd", ".pyc", ".whl", ".zip"
}

# 1. Secret patterns
SECRET_PATTERNS = {
    "sk-ws-": re.compile(r"sk-ws-[A-Za-z0-9_\-]{6,}"),
    "sk-": re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    "tvly-": re.compile(r"tvly-[A-Za-z0-9_\-]{8,}"),
    "Bearer": re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{16,}"),
    "Authorization": re.compile(r"Authorization[\"']?\s*:\s*[\"']Bearer\s+[^\"']{10,}"),
    "Cookie": re.compile(r"(?:Cookie|Set-Cookie)[\"']?\s*:\s*[\"'][^\"']{10,}"),
    "api_key": re.compile(r"api_key\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}"),
    "password": re.compile(r"password\s*[:=]\s*[\"'][^\"'\s]{6,}"),
}

# Distinguish recognized fake keys / placeholders from real keys
FAKE_KEYWORDS = [
    "placeholder", "example", "demo", "fake", "mock", "test",
    "sk-user-provided", "dummy", "sample", "your-", "your_",
    "sk-kimi-1234567890abcdef", "sk-proj-placeholder"
]


def is_fake_or_placeholder(val: str, line: str) -> bool:
    val_lower = val.lower()
    line_lower = line.lower()
    return any(k in val_lower or k in line_lower for k in FAKE_KEYWORDS)


def mask_secret(val: str) -> str:
    val = val.strip()
    if len(val) <= 8:
        return "****"
    return f"{val[:4]}****{val[-4:]}"


# 2. Hardcoded Windows paths
PATH_PATTERNS = {
    "D_drive_backslash": re.compile(r"[dD]:\\[a-zA-Z0-9_\\]+"),
    "D_drive_forwardslash": re.compile(r"[dD]:/[a-zA-Z0-9_/]+"),
    "windows_user_dir": re.compile(r"[cC]:\\Users\\[a-zA-Z0-9_]+"),
    "claimcheck_pro_hardcoded": re.compile(r"ClaimCheck_Pro[\\/][a-zA-Z0-9_\\/]+"),
}


def scan_repo():
    findings = []
    path_findings = []

    for root, dirs, files in os.walk(WORKSPACE):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            suffix = Path(file).suffix.lower()
            if suffix in IGNORE_EXTENSIONS:
                continue

            p = Path(root) / file
            rel_path = p.relative_to(WORKSPACE).as_posix()

            if rel_path == "tools/scan_secrets_and_paths.py":
                continue

            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for line_no, line in enumerate(f, 1):
                        # 1. Scan secrets
                        for pat_name, pat in SECRET_PATTERNS.items():
                            for m in pat.finditer(line):
                                matched_str = m.group(0)
                                is_fake = is_fake_or_placeholder(matched_str, line)
                                masked = mask_secret(matched_str)
                                findings.append({
                                    "file": rel_path,
                                    "line": line_no,
                                    "pattern": pat_name,
                                    "masked": masked,
                                    "is_fake": is_fake,
                                    "snippet": line.strip()[:80]
                                })

                        # 2. Scan hardcoded paths
                        for pat_name, pat in PATH_PATTERNS.items():
                            for m in pat.finditer(line):
                                matched_str = m.group(0)
                                path_findings.append({
                                    "file": rel_path,
                                    "line": line_no,
                                    "pattern": pat_name,
                                    "matched": matched_str,
                                    "snippet": line.strip()[:80]
                                })
            except Exception as e:
                pass

    return findings, path_findings


if __name__ == "__main__":
    secrets, paths = scan_repo()
    print("=" * 60)
    print(f"  SECRET SCAN REPORT: {len(secrets)} occurrences found")
    print("=" * 60)

    runtime_secrets = [s for s in secrets if s["file"].startswith(("src/", "streamlit_app/"))]
    print(f"Secrets in runtime code (src/, streamlit_app/): {len(runtime_secrets)}")
    for s in runtime_secrets:
        flag = "[FAKE/PLACEHOLDER]" if s["is_fake"] else "[POTENTIAL REAL KEY!]"
        print(f"  {flag} [{s['pattern']}] {s['file']}:{s['line']} -> {s['masked']}")

    non_runtime_real = [s for s in secrets if not s["is_fake"] and not s["file"].startswith(("src/", "streamlit_app/"))]
    print(f"\nNon-runtime potential real keys (tests, docs, etc.): {len(non_runtime_real)}")
    for s in non_runtime_real[:20]:
        print(f"  [{s['pattern']}] {s['file']}:{s['line']} -> {s['masked']} ({s['snippet'][:50]})")
    if len(non_runtime_real) > 20:
        print(f"  ... and {len(non_runtime_real) - 20} more")

    print("\n" + "=" * 60)
    print(f"  HARDCODED PATH SCAN REPORT: {len(paths)} occurrences")
    print("=" * 60)
    runtime_paths = [p for p in paths if p["file"].startswith(("src/", "streamlit_app/"))]
    print(f"Hardcoded paths in runtime code (src/, streamlit_app/): {len(runtime_paths)}")
    for p in runtime_paths:
        print(f"  [{p['pattern']}] {p['file']}:{p['line']} -> {p['matched']}")

    test_paths = [p for p in paths if p["file"].startswith("tests/")]
    print(f"\nHardcoded paths in tests/ (e.g. test fixtures): {len(test_paths)}")
    for p in test_paths[:10]:
        print(f"  [{p['pattern']}] {p['file']}:{p['line']} -> {p['matched']}")
    if len(test_paths) > 10:
        print(f"  ... and {len(test_paths) - 10} more in tests")
