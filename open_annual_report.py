# -*- coding: utf-8 -*-
"""
5년 1000배속 가상 시뮬레이션 결과 웹 브라우저 자동 리포트 오픈 스크립트 (open_annual_report.py)
"""
import os
import sys
import io
import webbrowser
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def open_report():
    html_path = os.path.abspath("annual_simulation_report.html")
    if not os.path.exists(html_path):
        print(f"❌ [오류] {html_path} 파일을 찾을 수 없습니다.")
        sys.exit(1)
        
    formatted_path = html_path.replace('\\', '/')
    url = f"file:///{formatted_path}"
    print("=" * 80)
    print("🌐 [웹 브라우저 리포터] KOSPI200 Bot 5년 시뮬레이션 웹 보고서를 여는 중...")
    print("=" * 80)
    print(f"  • 보고서 경로: {html_path}")
    print(f"  • URL: {url}")
    print("=" * 80)
    
    webbrowser.open(url)
    print("✅ 기본 웹 브라우저에서 보고서가 자동으로 열렸습니다.")

if __name__ == "__main__":
    open_report()
