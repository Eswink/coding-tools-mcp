"""Run every authorization-harness contract against real tracked test sources."""
from pathlib import Path
import os
import re
import subprocess
import sys

TESTS = (
    "Windows非提升回归v12.py", "Windows宿主回归v13.py", "跨平台原生回归v8.py",
    "聊天授权原生回归v6.py", "聊天授权证据回归v16.py", "Windows启动回归v17.py",
    "聊天授权门禁回归v18.py", "标准用户回归v22.py", "标准账户路径回归v23.py", "Windows令牌参数回归v25.py",
)
if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    total = 0
    for name in TESTS:
        result = subprocess.run([sys.executable, str(root / name)], cwd=root.parent,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, encoding="utf-8", timeout=90)
        print(name, flush=True)
        print(result.stdout, end="", flush=True)
        print(result.stderr, end="", flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)
        match = re.search(r"Ran (\d+) tests?", result.stderr)
        if not match or re.search(r"skipped=|expected failures=", result.stderr):
            raise RuntimeError("incomplete contract execution")
        total += int(match.group(1))
    print(f"辅助回归：{total} 项通过；不代表真实原生或发布验收。", flush=True)
