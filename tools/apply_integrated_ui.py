from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web_interface"
SRC = WEB / "src"

APP = SRC / "App.js"
OPTION = SRC / "OptionProgramPanel.js"
BROKER = SRC / "components" / "VirtualBrokerPanel.js"
EXCHANGE = SRC / "components" / "VirtualExchangePanel.js"
WS = SRC / "hooks" / "useWebSocket.js"
STORE = SRC / "store" / "rootStore.js"

APP_SHELL = r'''import React, { useState } from 'react';
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

export default App;'''

BROKER_CODE = r'''import React from 'react';
const money = (v) => `₩${Number(v || 0).toLocaleString('ko-KR', { maximumFractionDigits: 0 })}`;
function Card({ title, children, wide = false }) { return <section style={{ ...styles.card, gridColumn: wide ? '1 / -1' : undefined }}><div style={styles.cardTitle}>{title}</div>{children}</section>; }
function Metric({ label, value, danger = false }) { return <div style={styles.metric}><span style={styles.label}>{label}</span><strong style={{ color: danger ? '#F87171' : '#F8FAFC' }}>{value}</strong></div>; }
function Button({ children, onClick, danger = false }) { return <button type="button" onClick={onClick} style={{ ...styles.button, ...(danger ? styles.danger : {}) }}>{children}</button>; }
export default function VirtualBrokerPanel({ state, sendCommand }) {
  const account = state.broker?.account || {};
  const broker = state.broker || {};
  const risk = state.risk || {};
  const positions = state.positions || {};
  const orders = state.orders || [];
  const executions = state.executions || [];
  const command = (action, payload = {}) => sendCommand({ action, ...payload });
  return <div style={styles.grid}>
    <Card title="Broker Status"><div style={styles.metrics}><Metric label="Mode" value={broker.mode || 'PAPER'} /><Metric label="Connection" value={broker.connected === false ? 'DISCONNECTED' : 'CONNECTED'} danger={broker.connected === false} /><Metric label="Order State" value={broker.order_state || 'NORMAL'} /><Metric label="Execution State" value={broker.execution_state || 'NORMAL'} /></div></Card>
    <Card title="Account / Margin"><div style={styles.metrics}><Metric label="Balance" value={money(account.balance)} /><Metric label="Realized PnL" value={money(account.realized_pnl)} /><Metric label="Unrealized PnL" value={money(account.unrealized_pnl)} /><Metric label="Used Margin" value={money(account.used_margin)} /><Metric label="Free Margin" value={money(account.free_margin)} /><Metric label="Margin Ratio" value={`${Number(account.margin_ratio || 0).toFixed(1)}%`} danger={Number(account.margin_ratio || 100) < 30} /></div></Card>
    <Card title="Margin Control"><div style={styles.controlRow}><Button onClick={() => command('set_margin_mode', { mode: 'NORMAL' })}>정상</Button><Button onClick={() => command('set_margin_mode', { mode: 'TIGHT' })}>증거금 강화</Button><Button danger onClick={() => command('inject_margin_call')}>Margin Call</Button><Button danger onClick={() => command('inject_margin_shortage')}>증거금 부족</Button></div><div style={styles.controlRow}><Button onClick={() => command('set_leverage', { leverage: 1 })}>1x</Button><Button onClick={() => command('set_leverage', { leverage: 2 })}>2x</Button><Button onClick={() => command('set_leverage', { leverage: 5 })}>5x</Button><Button onClick={() => command('set_leverage', { leverage: 10 })}>10x</Button></div></Card>
    <Card title="Communication / Execution Control"><div style={styles.controlRow}><Button onClick={() => command('set_broker_connection', { connected: true })}>통신 정상</Button><Button danger onClick={() => command('set_broker_connection', { connected: false })}>통신 두절</Button><Button onClick={() => command('set_broker_latency', { latency_ms: 500 })}>500ms 지연</Button><Button onClick={() => command('set_broker_latency', { latency_ms: 0 })}>지연 해제</Button></div><div style={styles.controlRow}><Button onClick={() => command('set_execution_behavior', { mode: 'NORMAL' })}>정상 체결</Button><Button onClick={() => command('set_execution_behavior', { mode: 'DELAYED' })}>체결 지연</Button><Button danger onClick={() => command('set_execution_behavior', { mode: 'REJECT' })}>주문 거부</Button></div></Card>
    <Card title="Positions">{Object.keys(positions).length ? <div style={styles.list}>{Object.entries(positions).map(([key, value]) => <div key={key} style={styles.row}><span>{key}</span><strong>{JSON.stringify(value)}</strong></div>)}</div> : <div style={styles.muted}>포지션 없음</div>}</Card>
    <Card title="Orders / Executions"><div style={styles.sectionLabel}>Orders</div><div style={styles.list}>{orders.slice(-8).map((o, i) => <div key={i} style={styles.row}><span>{o.track_id || o.client_order_id || '-'}</span><span>{o.side || ''} {o.qty || ''}</span></div>)}{!orders.length && <div style={styles.muted}>주문 없음</div>}</div><div style={{ ...styles.sectionLabel, marginTop: 12 }}>Executions</div><div style={styles.list}>{executions.slice(-8).map((e, i) => <div key={i} style={styles.row}><span>{e.track_id || e.exec_id || '-'}</span><span>{e.executed_price || '-'} × {e.executed_qty || 0}</span></div>)}{!executions.length && <div style={styles.muted}>체결 없음</div>}</div></Card>
    <Card title="Risk Snapshot" wide><div style={styles.metrics}><Metric label="Vol Spike" value={risk.is_vol_spike ? 'YES' : 'NO'} danger={risk.is_vol_spike} /><Metric label="Crisis" value={risk.is_crisis_regime ? 'YES' : 'NO'} danger={risk.is_crisis_regime} /><Metric label="Margin Diet" value={risk.is_margin_diet_required ? 'YES' : 'NO'} danger={risk.is_margin_diet_required} /><Metric label="Reason" value={risk.reason || 'NORMAL'} /></div></Card>
  </div>;
}
const styles = {
  grid: { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 14 }, card: { background: '#111827', border: '1px solid #334155', borderRadius: 14, padding: 16, minWidth: 0 }, cardTitle: { color: '#CBD5E1', fontSize: 12, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 14 }, metrics: { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }, metric: { display: 'flex', flexDirection: 'column', gap: 3, padding: 10, background: '#0F172A', borderRadius: 9 }, label: { color: '#64748B', fontSize: 10 }, controlRow: { display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }, button: { border: '1px solid #475569', background: '#1E293B', color: '#E2E8F0', borderRadius: 8, padding: '8px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 700 }, danger: { borderColor: '#7F1D1D', color: '#FCA5A5' }, list: { display: 'flex', flexDirection: 'column', gap: 5 }, row: { display: 'flex', justifyContent: 'space-between', gap: 10, padding: '7px 8px', background: '#0F172A', borderRadius: 7, fontSize: 10, color: '#CBD5E1' }, sectionLabel: { color: '#64748B', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.1em' }, muted: { color: '#64748B', fontSize: 12 }, '@media (max-width: 800px)': { grid: { gridTemplateColumns: '1fr' }, metrics: { gridTemplateColumns: '1fr' } },
};'''

EXCHANGE_CODE = r'''import React, { useState } from 'react';
function Card({ title, children, wide = false }) { return <section style={{ ...styles.card, gridColumn: wide ? '1 / -1' : undefined }}><div style={styles.cardTitle}>{title}</div>{children}</section>; }
function Metric({ label, value, danger = false }) { return <div style={styles.metric}><span style={styles.label}>{label}</span><strong style={{ color: danger ? '#F87171' : '#F8FAFC' }}>{value}</strong></div>; }
function Button({ children, onClick, danger = false }) { return <button type="button" onClick={onClick} style={{ ...styles.button, ...(danger ? styles.danger : {}) }}>{children}</button>; }
export default function VirtualExchangePanel({ state, sendCommand }) {
  const market = state.market || {};
  const condition = state.marketCondition || {};
  const [price, setPrice] = useState(Number(market.price || 350));
  const [volatility, setVolatility] = useState(Number(condition.volatility_ratio || 1));
  const [spread, setSpread] = useState(Number(market.spread || 0.05));
  const [volume, setVolume] = useState(Number(market.volume || 1000));
  const command = (action, payload = {}) => sendCommand({ action, ...payload });
  const applyGenerator = () => command('set_market_generator', { base_price: Number(price), volatility_ratio: Number(volatility), spread: Number(spread), volume: Number(volume) });
  return <div style={styles.grid}>
    <Card title="Virtual Exchange Status"><div style={styles.metrics}><Metric label="KOSPI200" value={Number(market.price || 0).toFixed(2)} /><Metric label="Bid" value={Number(market.bid || 0).toFixed(2)} /><Metric label="Ask" value={Number(market.ask || 0).toFixed(2)} /><Metric label="Spread" value={Number(market.spread || 0).toFixed(4)} /><Metric label="Volume" value={Number(market.volume || 0).toLocaleString('ko-KR')} /><Metric label="Tick" value={market.seq_id || 0} /></div></Card>
    <Card title="Market Regime"><div style={styles.controlRow}>{['NORMAL', 'BULL', 'BEAR', 'SIDEWAYS', 'VOLATILE', 'CRISIS'].map((regime) => <Button key={regime} danger={regime === 'CRISIS'} onClick={() => command('set_market_regime', { regime })}>{regime}</Button>)}</div><div style={styles.metrics}><Metric label="Current Regime" value={condition.regime || 'NEUTRAL'} danger={String(condition.regime).includes('CRISIS')} /><Metric label="Confidence" value={`${(Number(condition.regime_confidence || 0) * 100).toFixed(1)}%`} /><Metric label="Liquidity" value={condition.liquidity_level || 'NORMAL'} /><Metric label="Stress" value={`${(Number(condition.stress_level || 0) * 100).toFixed(1)}%`} danger={Number(condition.stress_level || 0) >= 0.7} /></div></Card>
    <Card title="Price / Data Generator" wide><div style={styles.formGrid}><label style={styles.field}>Base Price<input style={styles.input} type="number" value={price} onChange={(e) => setPrice(e.target.value)} /></label><label style={styles.field}>Volatility Ratio<input style={styles.input} type="number" step="0.1" value={volatility} onChange={(e) => setVolatility(e.target.value)} /></label><label style={styles.field}>Spread<input style={styles.input} type="number" step="0.01" value={spread} onChange={(e) => setSpread(e.target.value)} /></label><label style={styles.field}>Volume<input style={styles.input} type="number" value={volume} onChange={(e) => setVolume(e.target.value)} /></label></div><div style={styles.controlRow}><Button onClick={applyGenerator}>가격 생성조건 적용</Button><Button onClick={() => command('set_simulation_runtime', { running: true })}>START</Button><Button onClick={() => command('set_simulation_runtime', { running: false })}>PAUSE</Button><Button onClick={() => command('reset_market_simulation')}>RESET</Button></div></Card>
    <Card title="Market Stress Injection"><div style={styles.controlRow}><Button onClick={() => command('inject_market_stress', { type: 'VOL_SPIKE' })}>Vol Spike</Button><Button onClick={() => command('inject_market_stress', { type: 'LIQUIDITY_DROP' })}>Liquidity 감소</Button><Button onClick={() => command('inject_market_stress', { type: 'GAP' })}>Gap</Button><Button danger onClick={() => command('inject_market_stress', { type: 'CRASH' })}>Crash</Button><Button danger onClick={() => command('inject_market_stress', { type: 'FLASH_MOVE' })}>Flash Move</Button><Button onClick={() => command('clear_market_stress')}>Stress 해제</Button></div></Card>
    <Card title="Data Stream Control"><div style={styles.controlRow}><Button onClick={() => command('set_tick_speed', { speed: 'SLOW' })}>SLOW</Button><Button onClick={() => command('set_tick_speed', { speed: 'NORMAL' })}>NORMAL</Button><Button onClick={() => command('set_tick_speed', { speed: 'FAST' })}>FAST</Button></div><div style={styles.metrics}><Metric label="Stress Flags" value={(condition.stress_flags || []).length} /><Metric label="Timestamp" value={condition.timestamp || market.timestamp || '-'} /></div></Card>
  </div>;
}
const styles = {
  grid: { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 14 }, card: { background: '#111827', border: '1px solid #334155', borderRadius: 14, padding: 16, minWidth: 0 }, cardTitle: { color: '#CBD5E1', fontSize: 12, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 14 }, metrics: { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }, metric: { display: 'flex', flexDirection: 'column', gap: 3, padding: 10, background: '#0F172A', borderRadius: 9 }, label: { color: '#64748B', fontSize: 10 }, controlRow: { display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }, button: { border: '1px solid #475569', background: '#1E293B', color: '#E2E8F0', borderRadius: 8, padding: '8px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 700 }, danger: { borderColor: '#7F1D1D', color: '#FCA5A5' }, formGrid: { display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10, marginBottom: 12 }, field: { display: 'flex', flexDirection: 'column', gap: 5, color: '#94A3B8', fontSize: 10 }, input: { background: '#0F172A', color: '#F8FAFC', border: '1px solid #334155', borderRadius: 8, padding: 8 }, '@media (max-width: 800px)': { grid: { gridTemplateColumns: '1fr' }, formGrid: { gridTemplateColumns: '1fr 1fr' }, metrics: { gridTemplateColumns: '1fr' } },
};'''

WS_CODE = r'''import { useEffect, useState, useCallback, useRef } from 'react';
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
    if (reconnectTimerRef.current) { clearTimeout(reconnectTimerRef.current); reconnectTimerRef.current = null; }
    if (wsRef.current) { try { wsRef.current.onclose = null; wsRef.current.close(); } catch (e) { /* no-op */ } wsRef.current = null; }
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => { setIsConnected(true); reconnectCount.current = 0; };
    ws.onmessage = (event) => {
      try {
        if (!event.data) return;
        const parsedData = JSON.parse(event.data);
        if (!parsedData || typeof parsedData !== 'object') return;
        const immutablePayload = Object.freeze({ ...parsedData });
        updateData(immutablePayload);
        pendingDataRef.current = immutablePayload;
        if (!throttleTimerRef.current) {
          throttleTimerRef.current = setTimeout(() => {
            if (pendingDataRef.current) { setLastData(pendingDataRef.current); pendingDataRef.current = null; }
            throttleTimerRef.current = null;
          }, 200);
        }
      } catch (err) { console.error('Packet Parsing Error:', err); }
    };
    ws.onclose = () => {
      setIsConnected(false);
      if (wsRef.current === ws) wsRef.current = null;
      const delay = Math.min(1000 * Math.pow(2, reconnectCount.current), 30000);
      reconnectCount.current += 1;
      reconnectTimerRef.current = setTimeout(connect, delay);
    };
    ws.onerror = () => { try { ws.close(); } catch (e) { /* no-op */ } };
    return ws;
  }, [url, updateData]);
  useEffect(() => {
    const ws = connect();
    return () => {
      if (wsRef.current) { wsRef.current.onclose = null; wsRef.current.close(); }
      else if (ws) { ws.onclose = null; ws.close(); }
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
};'''

STORE_CODE = r'''import { create } from 'zustand';
const emptyState = {
  market: {}, marketCondition: {}, broker: { mode: 'PAPER', connected: true, account: {} },
  optionProgram: { strategy_metrics: {}, enabled_strategies: {} }, risk: {}, executions: [], orders: [], positions: {}, payoff: [], coords: [], replay: {},
};
export const useStore = create((set) => ({
  ...emptyState, data: {},
  updateData: (newData) => set((state) => {
    if (!newData || typeof newData !== 'object') return state;
    const incoming = newData.data && typeof newData.data === 'object' ? newData.data : newData;
    const market = { ...state.market, ...(incoming.market || {}) };
    const marketCondition = { ...state.marketCondition, ...(incoming.marketCondition || incoming.condition || {}) };
    const broker = { ...state.broker, ...(incoming.broker || {}), account: { ...state.broker.account, ...(incoming.broker?.account || incoming.account || {}) } };
    const optionProgram = {
      ...state.optionProgram, ...(incoming.optionProgram || {}),
      strategy_metrics: { ...state.optionProgram.strategy_metrics, ...(incoming.optionProgram?.strategy_metrics || incoming.strategy_metrics || {}) },
      enabled_strategies: { ...state.optionProgram.enabled_strategies, ...(incoming.optionProgram?.enabled_strategies || incoming.enabled_strategies || {}) },
    };
    const nextCoords = incoming.coord ? [...state.coords, incoming.coord].slice(-1000) : incoming.coords || state.coords;
    return {
      ...state, data: { ...state.data, ...incoming }, market, marketCondition, broker, optionProgram,
      risk: { ...state.risk, ...(incoming.risk || {}) }, executions: incoming.executions || state.executions,
      orders: incoming.orders || state.orders, positions: incoming.positions || state.positions,
      payoff: incoming.payoff || incoming.payoffCoords || state.payoff, coords: nextCoords,
      replay: { ...state.replay, ...(incoming.replay || {}) },
    };
  }),
}));'''

def backup(path):
    backup_path = path.with_suffix(path.suffix + ".before_integrated_ui.bak")
    if path.exists() and not backup_path.exists():
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    backup(path)
    path.write_text(content, encoding="utf-8")
    print(f"[WRITE] {path}")

def build_option_panel():
    if not APP.exists():
        raise FileNotFoundError(f"현재 App.js를 찾을 수 없습니다: {APP}")
    original = APP.read_text(encoding="utf-8")
    if "function App()" not in original or "export default App;" not in original:
        raise RuntimeError("현재 App.js가 예상된 기존 HFT Control Panel 구조가 아닙니다.")
    option = original.replace("import { useStore } from './store/rootStore';\n", "").replace("import { useWebSocket } from './hooks/useWebSocket';\n", "")
    option = option.replace("function App() {", "function OptionProgramPanel({ state, isConnected, sendCommand }) {", 1)
    option = option.replace("""  const state = useStore();
  const { isConnected, sendCommand } = useWebSocket(
    process.env.REACT_APP_WS_URL || 'ws://localhost:8765'
  );

""", "", 1)
    option = option.replace("export default App;", "export default OptionProgramPanel;", 1)
    write(OPTION, option)

write(APP, APP_SHELL)
build_option_panel()
write(BROKER, BROKER_CODE)
write(EXCHANGE, EXCHANGE_CODE)
write(WS, WS_CODE)
write(STORE, STORE_CODE)

print("[DONE] Integrated Control Panel 구조 적용 완료")
