import React, { useState } from 'react';
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

export default App;