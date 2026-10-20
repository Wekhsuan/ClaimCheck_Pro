"""扫描工作区内所有源码、报告、配置中是否存在真实泄露的 API Key、Token、密码
"""
import os
import re

PATTERNS = [
    r'sk-[a-zA-Z0-9]{20,}',
    r'ghp_[a-zA-Z0-9]{20,}',
    r'(?:api_key|secret|password|passwd|token)\s*[:=]\s*["\'][a-zA-Z0-9_\-\.]{12,}["\']',
]

IGNORE_DIRS = {'.venv', '.git', '.cache', '__pycache__', 'edge_profile_stage4', 'edge_profile_stage5', '.pytest_cache', 'scratch'}
EXCLUDE_WORDS = {'example', 'dummy', 'mock', 'placeholder', 'none', 'your_key', 'test_key', 'invalid_key', 'sk-proj-testkey', 'sk-test-1234567890abcdef', 'sk-mock-key-for-test-only', '占位', '测试', 'sk-test-', 'sk-invalid', 'sk-noquota', 'sk-validkey', 'tvly-'}

def scan():
    findings = []
    root_dir = r"D:\ClaimCheck_Pro"
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            if f.endswith(('.py', '.json', '.md', '.txt', '.env.example', '.yaml', '.yml', '.html')):
                fp = os.path.join(root, f)
                try:
                    with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                        for l_idx, line in enumerate(fh, 1):
                            for pat in PATTERNS:
                                m = re.search(pat, line, re.IGNORECASE)
                                if m:
                                    matched_str = m.group(0).lower()
                                    if not any(ex in matched_str for ex in EXCLUDE_WORDS):
                                        findings.append((fp, l_idx, line.strip()))
                except Exception as e:
                    pass
    return findings

if __name__ == "__main__":
    res = scan()
    print(f"Total potential secrets found: {len(res)}")
    for fp, line_no, content in res:
        print(f"[{fp}:{line_no}] {content}")
