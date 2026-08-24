#!/usr/bin/env python3
"""
Notion UI code applier for KOSPI200_Bot.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTION_VERSION = "2026-03-11"
PAGES = [
    ("3c65f4f6-eaa1-81a9-bc96-d51ce6974858", "CREATE", "option_program/market_analysis/market_condition_models.py"),
    ("3c65f4f6-eaa1-81f3-8888-d606c78ff12d", "CREATE", "option_program/market_analysis/market_condition_analyzer.py"),
    ("3c65f4f6-eaa1-81b6-acf6-e0f9b2c4dc7a", "REPLACE", "virtual_market_simulator/runtime/simulator_runtime.py"),
    ("3c65f4f6-eaa1-8162-88b4-dbd67bd78b7a", "REPLACE", "option_program/runtime/program_runtime.py"),
    ("3c65f4f6-eaa1-81e0-95d8-d59a644a0ea2", "REPLACE", "web_interface/server.py"),
    ("3c65f4f6-eaa1-8165-a7bd-e81738f1e1f5", "REPLACE", "main.py"),
    ("3c65f4f6-eaa1-8190-9687-d55516d4cb64", "REPLACE", "web_interface/src/store/rootStore.js"),
    ("3c65f4f6-eaa1-81db-a899-f54d55cf56d1", "REPLACE", "web_interface/src/hooks/useWebSocket.js"),
    ("3c65f4f6-eaa1-814f-98bd-d7c70e282b91", "CREATE", "web_interface/src/index.js"),
    ("3c65f4f6-eaa1-812e-8559-f8443e476570", "CREATE", "web_interface/src/App.js"),
    ("3c65f4f6-eaa1-816c-b8c8-c04cb64f9619", "CREATE", "web_interface/public/index.html"),
]

def run_git(*args):
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    ).stdout.strip()

def notion_markdown(page_id):
    token = os.environ.get("NOTION_API_TOKEN")
    if not token:
        raise RuntimeError("NOTION_API_TOKEN 환경변수가 없습니다.")

    req = urllib.request.Request(
        f"https://api.notion.com/v1/pages/{page_id}/markdown",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Notion API 오류 {exc.code}: {body}") from exc

    if payload.get("truncated"):
        raise RuntimeError(f"Notion 페이지가 truncated 상태입니다: {page_id}")
    return payload.get("markdown", "")

def extract_code(markdown):
    fence = chr(96) * 3
    pattern = re.escape(fence) + r"[A-Za-z0-9_+.#/-]*\n(.*?)\n" + re.escape(fence)
    match = re.search(pattern, markdown, re.DOTALL)
    if not match:
        raise RuntimeError("Notion 페이지에서 fenced code block을 찾지 못했습니다.")
    return match.group(1) + "\n"

def safe_path(relative_path):
    target = (REPO_ROOT / relative_path).resolve()
    if REPO_ROOT not in target.parents and target != REPO_ROOT:
        raise RuntimeError(f"허용되지 않은 경로: {relative_path}")
    return target

def main():
    branch = run_git("branch", "--show-current")
    if branch != "Experiment_UI":
        raise RuntimeError(
            f"현재 브랜치가 Experiment_UI가 아닙니다: {branch}\n"
            "먼저 Experiment_UI를 checkout/pull 하십시오."
        )

    status = run_git("status", "--porcelain")
    if status:
        raise RuntimeError(
            "작업폴더에 기존 변경사항이 있습니다.\n"
            "덮어쓰기를 방지하기 위해 중단합니다.\n\n" + status
        )

    print(f"[OK] branch = {branch}")
    print("[OK] clean working tree")

    fetched = []
    for page_id, action, relative_path in PAGES:
        markdown = notion_markdown(page_id)
        code = extract_code(markdown)
        fetched.append((action, relative_path, code))

    backup_root = REPO_ROOT.parent / f"{REPO_ROOT.name}_ui_patch_backup" / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root.mkdir(parents=True, exist_ok=True)

    for action, relative_path, code in fetched:
        path = safe_path(relative_path)

        if action in {"REPLACE", "CREATE"}:
            if path.exists():
                dst = backup_root / relative_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dst)

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code, encoding="utf-8", newline="\n")
            print(f"[WRITE] {relative_path}")

        elif action == "DELETE":
            if path.exists():
                dst = backup_root / relative_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dst)
                path.unlink()
                print(f"[DELETE] {relative_path}")

        else:
            raise RuntimeError(f"알 수 없는 ACTION: {action}")

    print()
    print("[VERIFY] Python syntax")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "main.py",
            "option_program",
            "virtual_market_simulator",
            "web_interface",
        ],
        cwd=REPO_ROOT,
        check=True,
    )

    print("[VERIFY] Git diff summary")
    print(run_git("status", "--short"))
    print(run_git("diff", "--stat"))

    print()
    print("[DONE]")
    print("코드 적용과 Python syntax 검증이 완료되었습니다.")
    print("commit/push는 수행하지 않았습니다.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[STOP] {exc}", file=sys.stderr)
        sys.exit(1)
