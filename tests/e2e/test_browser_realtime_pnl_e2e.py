import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / 'web_interface'
FRONTEND_URL = 'http://127.0.0.1:3000'
WS_URL = 'ws://127.0.0.1:8765'
TICK_TARGET = 120

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import TradingSystem  # noqa: E402


def _http_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


async def wait_frontend_ready(timeout_seconds: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if await asyncio.to_thread(_http_ready, FRONTEND_URL):
            return
        await asyncio.sleep(0.5)
    raise AssertionError(f'Frontend did not become ready: {FRONTEND_URL}')


async def main() -> None:
    print('=== Browser Realtime PnL E2E verification START ===')

    env = os.environ.copy()
    env['BROWSER'] = 'none'
    env['REACT_APP_WS_URL'] = WS_URL

    npm_command = 'npm.cmd' if os.name == 'nt' else 'npm'
    frontend = subprocess.Popen(
        [npm_command, 'start'],
        cwd=str(WEB_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    system = TradingSystem({
        'broker_mode': 'PAPER',
        'initial_capital': 50_000_000.0,
    })

    try:
        await system.initialize()
        await system.ui_ws.start()
        print('Backend WebSocket server started.')

        await wait_frontend_ready()
        print('Frontend React server is ready.')

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()

            browser_console_errors = []
            page.on(
                'console',
                lambda msg: browser_console_errors.append(msg.text)
                if msg.type == 'error'
                else None
            )
            page.on(
                'pageerror',
                lambda exc: browser_console_errors.append(str(exc))
            )

            await page.goto(
                FRONTEND_URL,
                wait_until='domcontentloaded'
            )

            # 브라우저 UI의 연결 상태 배지('● CONNECTED') 확인
            await page.locator('span', has_text='● CONNECTED').wait_for(timeout=30_000)

            # 백엔드 허브에 브라우저 클라이언트가 실제로 등록될 때까지 확인
            connect_deadline = time.monotonic() + 10.0
            while len(system.ui_ws.clients) == 0 and time.monotonic() < connect_deadline:
                await asyncio.sleep(0.1)

            assert len(system.ui_ws.clients) > 0, 'Browser client was not registered on backend WebSocket hub.'

            debug_ready = await page.evaluate(
                "() => Boolean(window.__KOSPI200_UI_DEBUG__ && "
                "window.__KOSPI200_UI_DEBUG__.getState)"
            )
            assert debug_ready, 'Browser Zustand debug bridge was not initialized.'

            print(f'Browser successfully connected to {WS_URL} (Registered clients: {len(system.ui_ws.clients)})')

            # 시장 시뮬레이션 틱 스트림 실행 (120 틱)
            print(f'Running TradingSystem loop for {TICK_TARGET} ticks...')
            
            # 틱 처리 시 브라우저가 패킷을 소화할 수 있도록 틱 사이에 약간의 간격(예: 10ms)을 주어 실시간 스트림 시뮬레이션
            for tick in system.vms.generate_tick_stream(total_days=1, ticks_per_day=TICK_TARGET):
                system.last_tick = tick
                system.vssf.process_market_data(tick)
                system.op_runtime.update_account_summary(system.vssf.get_account_snapshot())
                commands = system.op_runtime.process_tick(tick)
                for cmd in commands:
                    system.orders_routed += 1
                    report = system.broker.send_order(cmd)
                    if report is not None:
                        system.executions_handled += 1
                        system.op_runtime.consume_execution_report(report)
                system.ticks_processed += 1
                await system.ui_ws.broadcast()
                await asyncio.sleep(0.01) # 10ms 간격으로 실시간 공급

            print(f'TradingSystem loop finished. Ticks processed: {system.ticks_processed}')

            # 브라우저 상태 실시간 진단
            diag = await page.evaluate(
                "() => ({ "
                "wsDebug: window.__KOSPI200_UI_WS_DEBUG__, "
                "coordsLen: window.__KOSPI200_UI_DEBUG__ ? window.__KOSPI200_UI_DEBUG__.getState().coords.length : -1, "
                "seqId: window.__KOSPI200_UI_DEBUG__ ? (window.__KOSPI200_UI_DEBUG__.getState().market ? window.__KOSPI200_UI_DEBUG__.getState().market.seq_id : -1) : -1 "
                "})"
            )
            print(f'Browser diagnostic after stream: {diag}')

            # 브라우저에서 틱 데이터가 누적 수신될 때까지 대기
            await page.wait_for_function(
                "target => Boolean(window.__KOSPI200_UI_DEBUG__ && "
                "window.__KOSPI200_UI_DEBUG__.getState().coords && "
                "window.__KOSPI200_UI_DEBUG__.getState().coords.length >= target)",
                arg=TICK_TARGET,
                timeout=10_000,
            )

            await page.wait_for_timeout(500)

            # 브라우저 런타임 실측 상태 수집
            browser_state = await page.evaluate(
                """() => {
                    const state = window.__KOSPI200_UI_DEBUG__.getState();
                    const wsDebug = window.__KOSPI200_UI_WS_DEBUG__ || {};
                    const coords = state.coords || [];

                    const pnlSections = Array.from(
                        document.querySelectorAll('section')
                    ).filter(
                        section => section.textContent.includes('Realtime PnL')
                    );

                    return {
                        connected: Boolean(state.broker && state.broker.connected),
                        wsReceivedCount: wsDebug.receivedCount || 0,
                        tickSeq: state.market ? state.market.seq_id : null,
                        coordsCount: coords.length,
                        firstCoord: coords[0] || null,
                        lastCoord: coords[coords.length - 1] || null,
                        allCoords: coords,
                        realtimePnlVisible: pnlSections.length > 0,
                        realtimePnlSvgCount: pnlSections.reduce(
                            (count, section) => count + section.querySelectorAll('svg').length,
                            0
                        ),
                    };
                }"""
            )

            # 검증 조건 단언
            expected_total_coords = TICK_TARGET + 1  # 초기 스냅샷(seq 0) + 120 틱(seq 1..120)
            assert system.ticks_processed == TICK_TARGET, f'Runtime ticks {system.ticks_processed} != {TICK_TARGET}'
            assert browser_state['coordsCount'] == expected_total_coords, (
                f"Browser rootStore.coords count {browser_state['coordsCount']} != {expected_total_coords}"
            )
            assert browser_state['tickSeq'] == TICK_TARGET, (
                f"Browser rootStore market.seq_id {browser_state['tickSeq']} != {TICK_TARGET}"
            )
            assert browser_state['firstCoord'] is not None, 'Browser rootStore has no first coord.'
            assert browser_state['lastCoord'] is not None, 'Browser rootStore has no last coord.'
            assert browser_state['firstCoord']['x'] == 0, f"First coord.x {browser_state['firstCoord']['x']} != 0 (초기 스냅샷)"
            assert browser_state['lastCoord']['x'] == TICK_TARGET, (
                f"Last coord.x {browser_state['lastCoord']['x']} != {TICK_TARGET}"
            )
            assert isinstance(browser_state['firstCoord']['y'], (int, float)), 'firstCoord.y is not numeric'
            assert isinstance(browser_state['lastCoord']['y'], (int, float)), 'lastCoord.y is not numeric'

            # 연속성 검사 (0..120 빈틈 없는지)
            seqs = [c['x'] for c in browser_state['allCoords']]
            expected_seqs = list(range(0, TICK_TARGET + 1))
            assert seqs == expected_seqs, f'Browser coord.x sequence mismatch: missing={[s for s in expected_seqs if s not in seqs]}'

            assert browser_state['realtimePnlVisible'], 'Realtime PnL section is not rendered in browser DOM.'
            assert browser_state['realtimePnlSvgCount'] > 0, 'Realtime PnL chart SVG was not rendered in browser DOM.'
            assert not browser_console_errors, f'Browser console/page errors: {browser_console_errors}'

            print('=== Browser E2E RESULT ===')
            print(
                json.dumps(
                    {
                        'ticks_processed': system.ticks_processed,
                        'browser_ws_received_count': browser_state['wsReceivedCount'],
                        'browser_market_seq_id': browser_state['tickSeq'],
                        'browser_rootStore_coords': browser_state['coordsCount'],
                        'browser_first_coord': browser_state['firstCoord'],
                        'browser_last_coord': browser_state['lastCoord'],
                        'realtime_pnl_visible': browser_state['realtimePnlVisible'],
                        'realtime_pnl_svg_count': browser_state['realtimePnlSvgCount'],
                        'browser_errors': browser_console_errors,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )

            await browser.close()

        print('=== Browser Realtime PnL E2E verification PASS ===')

    finally:
        try:
            await system.ui_ws.stop()
        except Exception:
            pass

        try:
            await system.shutdown()
        except Exception:
            pass

        frontend.terminate()
        try:
            frontend.wait(timeout=10)
        except subprocess.TimeoutExpired:
            frontend.kill()
            frontend.wait(timeout=5)


if __name__ == '__main__':
    asyncio.run(main())