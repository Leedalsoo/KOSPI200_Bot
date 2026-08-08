# -*- coding: utf-8 -*-
"""
[5년 장기 복합장 인터랙티브 Chart.js 웹 대시보드 변환기]
- 기존 전략 및 시스템 코드는 100% 그대로 보존합니다.
- 5년(2021~2025년) 실적 데이터를 세계 표준 Chart.js 시각화 엔진 기반의 선명한 5년 누적 막대그래프, 도넛 차트로 자동 생성합니다.
"""
import os
import sys
import webbrowser

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            getattr(sys.stdout, "reconfigure")(encoding="utf-8")
    except Exception:
        pass

def convert_md_to_html_and_open():
    md_file = "annual_hybrid_simulation_result.md"
    html_file = "annual_hybrid_simulation_result.html"

    if not os.path.exists(md_file):
        print(f"[ERROR] {md_file} 파일이 존재하지 않습니다.")
        return

    with open(md_file, "r", encoding="utf-8") as f:
        md_text = f.read()

    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 5년 장기 복합장(2021~2025) 인터랙티브 웹 대시보드 리포트</title>
    <!-- Chart.js 4.4.1 & Marked CDN (소스맵 404 경고 제거 안정화 버젼) -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: #151c2c;
            --card-border: #2a364f;
            --text-color: #f1f5f9;
            --accent-cyan: #38bdf8;
            --accent-purple: #c084fc;
            --accent-green: #4ade80;
            --accent-orange: #fb923c;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
            margin: 0;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            margin-bottom: 40px;
            padding: 30px;
            background: var(--card-bg);
            border-radius: 16px;
            border: 1px solid var(--card-border);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
        }}
        .header h1 {{
            color: var(--accent-cyan);
            margin: 0 0 10px 0;
            font-size: 2.2rem;
        }}
        .grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
            margin-bottom: 30px;
        }}
        @media (max-width: 900px) {{
            .grid-2 {{ grid-template-columns: 1fr; }}
        }}
        .chart-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.3);
        }}
        .chart-card h3 {{
            margin-top: 0;
            color: var(--accent-cyan);
            font-size: 1.25rem;
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .chart-container {{
            position: relative;
            height: 320px;
            width: 100%;
        }}
        .markdown-section {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 35px;
            margin-top: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.4);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: rgba(11, 15, 25, 0.6);
            border-radius: 8px;
            overflow: hidden;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid var(--card-border);
        }}
        th {{
            background-color: #2a364f;
            color: #f1f5f9;
        }}
        tr:hover {{
            background-color: rgba(56, 189, 248, 0.1);
        }}
        blockquote {{
            background: rgba(56, 189, 248, 0.1);
            border-left: 4px solid var(--accent-cyan);
            margin: 20px 0;
            padding: 15px 20px;
            border-radius: 0 8px 8px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌀 5년 장기 복합장 (2021년~2025년) 인터랙티브 웹 대시보드 리포트</h1>
            <p style="color: #94a3b8; margin: 0;">5년 1,250영업일 (약 62.5만 틱) 1000배속 무인 시뮬레이션 성과 시각화 (Chart.js 4.4.1 기반)</p>
        </div>

        <!-- 4종 인터랙티브 막대 & 파이 차트 섹션 -->
        <div class="grid-2">
            <!-- 차트 1: 5년 누적 순손익 추이 막대그래프 -->
            <div class="chart-card">
                <h3>📈 [차트 1] 5년(2021~2025) 연간 누적 순손익 추이 막대그래프</h3>
                <div class="chart-container">
                    <canvas id="monthlyCumulativeChart"></canvas>
                </div>
            </div>

            <!-- 차트 2: 전략별(Track 1~9) 5년 알파 기여도 막대그래프 -->
            <div class="chart-card">
                <h3>📊 [차트 2] 전략별(Track 1~9) 5년 알파 기여도 막대그래프</h3>
                <div class="chart-container">
                    <canvas id="strategyPnlChart"></canvas>
                </div>
            </div>
        </div>

        <div class="grid-2">
            <!-- 차트 3: 5년간 시간대별(T1~T5) 손익 비중 도넛 차트 -->
            <div class="chart-card">
                <h3>🍩 [차트 3] 5년간 장중 5개 시간대별(`T1`~`T5`) 순손익 비중 도넛 차트</h3>
                <div class="chart-container">
                    <canvas id="timeBucketChart"></canvas>
                </div>
            </div>

            <!-- 차트 4: 5년간 만기 4일전(D-4) vs 당일(D-0) 청산 비교 막대그래프 -->
            <div class="chart-card">
                <h3>🎯 [차트 4] 5년간 만기 4일전 (D-4) vs 만기 당일 (D-0) 청산 비교</h3>
                <div class="chart-container">
                    <canvas id="expiryComparisonChart"></canvas>
                </div>
            </div>
        </div>

        <!-- 마크다운 상세 표 및 보고서 본문 -->
        <div class="markdown-section">
            <div id="markdownContent"></div>
        </div>
    </div>

    <script>
        // 1. Chart.js 막대 & 도넛 시각화 차트 생성
        window.addEventListener('DOMContentLoaded', () => {{
            // [차트 1] 5년 연간 누적 순손익 (Bar)
            new Chart(document.getElementById('monthlyCumulativeChart'), {{
                type: 'bar',
                data: {{
                    labels: ['2021년(강세장)', '2022년(약세장)', '2023년(횡보장)', '2024년(폭락장)', '2025년(갭쇼크장)'],
                    datasets: [{{
                        label: '5년 누적 Net PnL (백만 원)',
                        data: [377.0, 742.0, 1109.0, 1492.0, 1885.0],
                        backgroundColor: 'rgba(56, 189, 248, 0.75)',
                        borderColor: '#38bdf8',
                        borderWidth: 2,
                        borderRadius: 6
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ labels: {{ color: '#f1f5f9' }} }} }},
                    scales: {{
                        x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }},
                        y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }}
                    }}
                }}
            }});

            // [차트 2] 전략별 5년 알파 기여도 막대그래프
            new Chart(document.getElementById('strategyPnlChart'), {{
                type: 'bar',
                data: {{
                    labels: ['Track1', 'Track2', 'Track3', 'Track4', 'Track5', 'Track6', 'Track7', 'Track8', 'Track9'],
                    datasets: [{{
                        label: '5년 누적 순손익 (백만 원)',
                        data: [360.0, 226.2, 436.2, 147.5, 212.5, 128.7, 158.7, 115.0, 100.0],
                        backgroundColor: [
                            '#38bdf8', '#818cf8', '#c084fc', '#f472b6', 
                            '#4ade80', '#facc15', '#fb923c', '#f87171', '#a7f3d0'
                        ],
                        borderRadius: 6
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }},
                        y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }}
                    }}
                }}
            }});

            // [차트 3] 5년간 시간대별 손익 비중 도넛 차트
            new Chart(document.getElementById('timeBucketChart'), {{
                type: 'doughnut',
                data: {{
                    labels: ['T1 (갭시초가)', 'T2 (오전추세)', 'T3 (점심횡보)', 'T4 (오후수렴)', 'T5 (장마감컷)'],
                    datasets: [{{
                        data: [312.5, 586.0, 583.5, 287.5, 115.0],
                        backgroundColor: ['#38bdf8', '#4ade80', '#c084fc', '#fb923c', '#f87171'],
                        borderWidth: 2,
                        borderColor: '#151c2c'
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ position: 'right', labels: {{ color: '#f1f5f9' }} }} }}
                }}
            }});

            // [차트 4] 5년간 만기 4일전(D-4) vs 당일(D-0) 청산 비교 막대그래프
            new Chart(document.getElementById('expiryComparisonChart'), {{
                type: 'bar',
                data: {{
                    labels: ['5년 전체 총 순손익', 'Track 7 (위클리)', 'Track 8 (월간)'],
                    datasets: [
                        {{
                            label: '만기 4일전 청산 (D-4)',
                            data: [1627.0, 112.0, 91.0],
                            backgroundColor: 'rgba(148, 163, 184, 0.7)',
                            borderRadius: 6
                        }},
                        {{
                            label: '만기 당일 청산 (D-0)',
                            data: [1885.0, 158.7, 115.0],
                            backgroundColor: 'rgba(74, 222, 128, 0.85)',
                            borderRadius: 6
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ labels: {{ color: '#f1f5f9' }} }} }},
                    scales: {{
                        x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }},
                        y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }}
                    }}
                }}
            }});

            // 2. 마크다운 본문 파싱
            const rawMarkdown = {repr(md_text)};
            document.getElementById('markdownContent').innerHTML = marked.parse(rawMarkdown);
        }});
    </script>
</body>
</html>
"""

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    abs_path = os.path.abspath(html_file)
    print(f"[OK] 5년 Chart.js 웹 대시보드 HTML 파일 저장 완료: {abs_path}")
    print("[OK] 시스템 기본 웹 브라우저로 리포트를 엽니다...")
    webbrowser.open(f"file:///{abs_path}")

if __name__ == "__main__":
    convert_md_to_html_and_open()
