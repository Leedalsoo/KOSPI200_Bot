from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

APP_JS = r'''import React, { useState } from 'react';
import { useStore } from './store/rootStore';
import { useWebSocket } from './hooks/useWebSocket';
import OptionProgramPanel from './OptionProgramPanel';
import VirtualBrokerPanel from './components/VirtualBrokerPanel';
import VirtualExchangePanel from './components/VirtualExchangePanel';

function App() {
  const state = useStore();
  const { isConnected, sendCommand } = useWebSocket(
    process.env.REACT_APP_WS_URL || 'ws://localhost:8765'
  );

  if (typeof window !== 'undefined' && process.env.NODE_ENV !== 'production') {
    window.__KOSPI200_UI_DEBUG__ = {
      getState: () => useStore.getState(),
    };
  }

  const [activeTab, setActiveTab] = useState('option');
  const tabs = [
    ['option', '① 옵션 프로그램'],
    ['broker', '② 가상증권사'],
    ['exchange', '③ 가상거래소'],
  ];

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <div>
          <div style={styles.kicker}>KOSPI200 HFT</div>
          <h1 style={styles.title}>Integrated Control Panel</h1>
          <div style={styles.sub}>Virtual Market · Virtual Securities Firm · Option Program</div>
        </div>
        <div style={styles.headerRight}>
          <span style={{ ...styles.connection, ...(isConnected ? styles.connected : styles.disconnected) }}>
            {isConnected ? '● CONNECTED' : '● DISCONNECTED'}
          </span>
          <span style={styles.badge}>{state.broker?.mode || 'PAPER'}</span>
          <span style={styles.badge}>Tick {state.market?.seq_id || 0}</span>
        </div>
      </header>
      <nav style={styles.tabs} aria-label="Integrated Control Panel tabs">
        {tabs.map(([id, label]) => (
          <button key={id} type="button" onClick={() => setActiveTab(id)} style={{ ...styles.tab, ...(activeTab === id ? styles.tabActive : {}) }}>
            {label}
          </button>
        ))}
      </nav>
      <main>
        {activeTab === 'option' && <OptionProgramPanel state={state} isConnected={isConnected} sendCommand={sendCommand} />}
        {activeTab === 'broker' && <VirtualBrokerPanel state={state} sendCommand={sendCommand} />}
        {activeTab === 'exchange' && <VirtualExchangePanel state={state} sendCommand={sendCommand} />}
      </main>
    </div>
  );
}

const styles = {
  page: { minHeight: '100vh', background: '#0F172A', color: '#F8FAFC', padding: 20, fontFamily: 'Inter, system-ui, sans-serif' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, marginBottom: 14, padding: 18, background: '#111827', border: '1px solid #334155', borderRadius: 14 },
  kicker: { color: '#38BDF8', fontSize: 11, fontWeight: 800, letterSpacing: '0.15em' },
  title: { margin: '4px 0', fontSize: 25 },
  sub: { color: '#94A3B8', fontSize: 12 },
  headerRight: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' },
  connection: { padding: '6px 10px', borderRadius: 8, fontSize: 11, fontWeight: 800 },
  connected: { color: '#34D399', background: '#064E3B' },
  disconnected: { color: '#F87171', background: '#450A0A' },
  badge: { padding: '6px 10px', borderRadius: 8, background: '#1E293B', color: '#CBD5E1', fontSize: 11 },
  tabs: { display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8, marginBottom: 14 },
  tab: { border: '1px solid #334155', background: '#111827', color: '#94A3B8', borderRadius: 10, padding: '12px 10px', fontWeight: 800, cursor: 'pointer' },
  tabActive: { background: '#1E293B', color: '#F8FAFC', borderColor: '#38BDF8' },
  '@media (max-width: 800px)': { tabs: { gridTemplateColumns: '1fr' }, header: { flexDirection: 'column', alignItems: 'stretch' } },
};

export default App;
'''

WS_HOOK_JS = r'''import { useEffect, useState, useCallback, useRef } from 'react';
import { useStore } from '../store/rootStore';

export const useWebSocket = (url) => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastData, setLastData] = useState(null);
  const updateData = useStore((state) => state.updateData);
  const reconnectCount = useRef(0);
  const reconnectTimerRef = useRef(null);
  const throttleTimerRef = useRef(null);
  const pendingDataRef = useRef(null);
  const wsRef = useRef(null);

  const connect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.onclose = null;
        wsRef.current.close();
      } catch (e) {
        // no-op
      }
      wsRef.current = null;
    }

    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => {
      setIsConnected(true);
      reconnectCount.current = 0;
    };
    ws.onmessage = (event) => {
      try {
        if (!event.data) return;
        const parsedData = JSON.parse(event.data);
        if (!parsedData || typeof parsedData !== 'object') return;
        const immutablePayload = Object.freeze({ ...parsedData });
        updateData(immutablePayload);

        if (process.env.NODE_ENV !== 'production' && typeof window !== 'undefined') {
          const previous = window.__KOSPI200_UI_WS_DEBUG__ || { receivedCount: 0 };
          window.__KOSPI200_UI_WS_DEBUG__ = {
            receivedCount: previous.receivedCount + 1,
            lastPayload: immutablePayload,
          };
        }

        pendingDataRef.current = immutablePayload;
        if (!throttleTimerRef.current) {
          throttleTimerRef.current = setTimeout(() => {
            if (pendingDataRef.current) {
              setLastData(pendingDataRef.current);
              pendingDataRef.current = null;
            }
            throttleTimerRef.current = null;
          }, 200);
        }
      } catch (err) {
        console.error('Packet Parsing Error:', err);
      }
    };
    ws.onclose = () => {
      setIsConnected(false);
      if (wsRef.current === ws) wsRef.current = null;
      const delay = Math.min(1000 * Math.pow(2, reconnectCount.current), 30000);
      reconnectCount.current += 1;
      reconnectTimerRef.current = setTimeout(connect, delay);
    };
    ws.onerror = () => {
      try {
        ws.close();
      } catch (e) {
        // no-op
      }
    };
    return ws;
  }, [url, updateData]);

  useEffect(() => {
    const ws = connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      } else if (ws) {
        ws.onclose = null;
        ws.close();
      }
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (throttleTimerRef.current) clearTimeout(throttleTimerRef.current);
    };
  }, [connect]);

  const sendCommand = useCallback((command) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(command));
    return true;
  }, []);

  return { isConnected, lastData, sendCommand };
};
'''

TEST_PY = r'''import asyncio
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
EXPECTED_BROWSER_MESSAGES = TICK_TARGET + 1  # initial snapshot + one packet per tick

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import TradingSystem


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
    system = TradingSystem({'broker_mode': 'PAPER', 'initial_capital': 50_000_000.0})

    try:
        await system.initialize()
        await system.ui_ws.start()
        await wait_frontend_ready()

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            browser_errors = []
            page.on('console', lambda msg: browser_errors.append(msg.text) if msg.type == 'error' else None)
            page.on('pageerror', lambda exc: browser_errors.append(str(exc)))

            await page.goto(FRONTEND_URL, wait_until='domcontentloaded')
            await page.get_by_text('CONNECTED', exact=False).wait_for(timeout=30_000)

            debug_ready = await page.evaluate(
                "() => Boolean(window.__KOSPI200_UI_DEBUG__ && window.__KOSPI200_UI_DEBUG__.getState)"
            )
            ws_debug_ready = await page.evaluate(
                "() => Boolean(window.__KOSPI200_UI_WS_DEBUG__ || window.__KOSPI200_UI_DEBUG__)"
            )
            assert debug_ready, 'Browser Zustand debug bridge was not initialized.'
            assert ws_debug_ready, 'Browser WebSocket debug bridge was not initialized.'

            print(f'Browser connected to {WS_URL}')
            await system.run_loop(max_ticks=TICK_TARGET)

            await page.wait_for_function(
                "target => window.__KOSPI200_UI_DEBUG__.getState().coords.length >= target",
                arg=TICK_TARGET,
                timeout=30_000,
            )
            await page.wait_for_function(
                "target => window.__KOSPI200_UI_WS_DEBUG__ && window.__KOSPI200_UI_WS_DEBUG__.receivedCount >= target",
                arg=EXPECTED_BROWSER_MESSAGES,
                timeout=30_000,
            )
            await page.wait_for_timeout(500)

            state = await page.evaluate(
                """() => {
                    const s = window.__KOSPI200_UI_DEBUG__.getState();
                    const ws = window.__KOSPI200_UI_WS_DEBUG__;
                    const coords = s.coords || [];
                    const pnlSections = Array.from(document.querySelectorAll('section')).filter(
                        section => section.textContent.includes('Realtime PnL')
                    );
                    return {
                        wsReceivedCount: ws ? ws.receivedCount : 0,
                        wsLastSeq: ws && ws.lastPayload && ws.lastPayload.market ? ws.lastPayload.market.seq_id : null,
                        wsLastCoord: ws ? ws.lastPayload.coord || null : null,
                        tickSeq: s.market ? s.market.seq_id : null,
                        coordsCount: coords.length,
                        firstCoord: coords[0] || null,
                        lastCoord: coords[coords.length - 1] || null,
                        realtimePnlVisible: pnlSections.length > 0,
                        realtimePnlSvgCount: pnlSections.reduce((n, section) => n + section.querySelectorAll('svg').length, 0),
                    };
                }"""
            )

            assert system.ticks_processed == TICK_TARGET
            assert state['wsReceivedCount'] == EXPECTED_BROWSER_MESSAGES
            assert state['wsLastSeq'] == TICK_TARGET
            assert state['wsLastCoord'] is not None
            assert state['wsLastCoord']['x'] == TICK_TARGET
            assert state['tickSeq'] == TICK_TARGET
            assert state['coordsCount'] == TICK_TARGET
            assert state['lastCoord'] is not None
            assert state['lastCoord']['x'] == TICK_TARGET
            assert state['lastCoord']['y'] == state['wsLastCoord']['y']
            assert state['realtimePnlVisible']
            assert state['realtimePnlSvgCount'] > 0
            assert not browser_errors, f'Browser console/page errors: {browser_errors}'

            print(json.dumps({
                'ticks_processed': system.ticks_processed,
                'browser_ws_received_count': state['wsReceivedCount'],
                'browser_ws_last_seq': state['wsLastSeq'],
                'browser_ws_last_coord': state['wsLastCoord'],
                'browser_market_seq_id': state['tickSeq'],
                'browser_rootStore_coords': state['coordsCount'],
                'browser_last_coord': state['lastCoord'],
                'realtime_pnl_visible': state['realtimePnlVisible'],
                'realtime_pnl_svg_count': state['realtimePnlSvgCount'],
                'browser_errors': browser_errors,
            }, indent=2, ensure_ascii=False))
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
'''

FILES = {
    'web_interface/src/App.js': APP_JS,
    'web_interface/src/hooks/useWebSocket.js': WS_HOOK_JS,
    'tests/e2e/test_browser_realtime_pnl_e2e.py': TEST_PY,
}

for relative_path, content in FILES.items():
    target = ROOT / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8', newline='\n')
    print(f'[WRITE] {target}')

print('[DONE] Browser Realtime PnL E2E files applied.')