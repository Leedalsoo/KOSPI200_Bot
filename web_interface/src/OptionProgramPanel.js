import React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ScatterChart,
  Scatter,
  ReferenceLine,
} from 'recharts';

const tracks = [
  ['Track1', 'Tail Defense'],
  ['Track2', 'Asymmetric Trap'],
  ['Track3', 'Stat Arbitrage'],
  ['Track4', 'Gamma Scalping'],
  ['Track5', 'Gap Protocol'],
  ['Track6', 'Daily 0DTE'],
  ['Track7', 'Weekly Insurance'],
  ['Track8', 'Monthly Strangle'],
  ['Track9', 'Insurance'],
];

const fmt = (v) => Number(v || 0).toLocaleString('ko-KR', { maximumFractionDigits: 2 });
const money = (v) => '₩' + fmt(v);

function Card({ title, children, wide = false }) {
  return (
    <section
      className={`dashboard-card ${wide ? 'wide' : ''}`}
      style={{
        ...styles.card,
        gridColumn: wide ? '1 / -1' : undefined,
      }}
    >
      <div style={styles.cardTitle}>{title}</div>
      {children}
    </section>
  );
}

function Metric({ label, value, danger = false }) {
  return (
    <div style={styles.metric}>
      <span style={styles.label}>{label}</span>
      <strong style={{ color: danger ? '#F87171' : '#F8FAFC' }}>{value}</strong>
    </div>
  );
}

export default function OptionProgramPanel({ state, isConnected, sendCommand }) {
  const safeState = state || {};
  const market = safeState.market || {};
  const condition = safeState.marketCondition || {};
  const broker = safeState.broker || {};
  const account = broker.account || {};
  const optionProgram = safeState.optionProgram || {};
  const strategies = optionProgram.strategy_metrics || {};
  const enabled = optionProgram.enabled_strategies || {};
  const risk = safeState.risk || {};
  const executions = safeState.executions || [];
  const orders = safeState.orders || [];
  const positions = safeState.positions || {};
  const payoff = safeState.payoff || [];
  const coords = safeState.coords || [];
  const replay = safeState.replay || {};

  const toggleTrack = (trackId) => {
    if (typeof sendCommand === 'function') {
      sendCommand({
        action: 'set_strategy_enabled',
        track_id: trackId,
        enabled: enabled[trackId] === false,
      });
    }
  };

  return (
    <div className="dashboard-grid" style={styles.grid}>
      <Card title="Virtual Market">
        <div className="dashboard-metrics-grid" style={styles.metrics}>
          <Metric label="KOSPI200" value={fmt(market.price)} />
          <Metric label="Bid" value={fmt(market.bid)} />
          <Metric label="Ask" value={fmt(market.ask)} />
          <Metric label="Spread" value={fmt(market.spread)} />
          <Metric label="Volume" value={fmt(market.volume)} />
          <Metric label="Connection" value={isConnected ? 'CONNECTED' : 'DISCONNECTED'} danger={!isConnected} />
        </div>
      </Card>

      <Card title="Market Condition">
        <div className="dashboard-metrics-grid" style={styles.metrics}>
          <Metric
            label="Regime"
            value={condition.regime || optionProgram.current_regime || 'NEUTRAL'}
            danger={String(condition.regime || optionProgram.current_regime || '').includes('CRISIS')}
          />
          <Metric label="Confidence" value={(Number(condition.regime_confidence || 0) * 100).toFixed(1) + '%'} />
          <Metric label="Volatility Ratio" value={Number(condition.volatility_ratio || 1).toFixed(2) + 'x'} />
          <Metric label="Liquidity" value={condition.liquidity_level || 'NORMAL'} />
          <Metric
            label="Stress"
            value={(Number(condition.stress_level || 0) * 100).toFixed(1) + '%'}
            danger={Number(condition.stress_level || 0) >= 0.7}
          />
        </div>
        <div style={styles.flags}>
          {(condition.stress_flags || []).length
            ? condition.stress_flags.map((f) => (
                <span key={f} style={styles.flag}>
                  {f}
                </span>
              ))
            : <span style={styles.muted}>관측된 경보 없음</span>}
        </div>
      </Card>

      <Card title="Account / Margin">
        <div className="dashboard-metrics-grid" style={styles.metrics}>
          <Metric label="Balance" value={money(account.balance)} />
          <Metric label="Realized PnL" value={money(account.realized_pnl)} />
          <Metric label="Unrealized PnL" value={money(account.unrealized_pnl)} />
          <Metric label="Used Margin" value={money(account.used_margin)} />
          <Metric label="Free Margin" value={money(account.free_margin)} />
        </div>
      </Card>

      <Card title="Risk">
        <div className="dashboard-metrics-grid" style={styles.metrics}>
          <Metric label="Vol Spike" value={risk.is_vol_spike ? 'YES' : 'NO'} danger={risk.is_vol_spike} />
          <Metric label="Crisis" value={risk.is_crisis_regime ? 'YES' : 'NO'} danger={risk.is_crisis_regime} />
          <Metric label="Margin Diet" value={risk.is_margin_diet_required ? 'YES' : 'NO'} danger={risk.is_margin_diet_required} />
          <Metric label="Vol Ratio" value={Number(risk.active_vol_ratio || 1).toFixed(2) + 'x'} />
        </div>
        <div style={styles.reason}>{risk.reason || 'NORMAL'}</div>
      </Card>

      <Card title="Strategy Matrix" wide>
        <div className="dashboard-track-grid" style={styles.trackGrid}>
          {tracks.map(([id, name]) => {
            const m = strategies[id] || {};
            const on = enabled[id] !== false;
            return (
              <div key={id} style={{ ...styles.track, borderColor: on ? '#10B981' : '#334155' }}>
                <div style={styles.trackHead}>
                  <strong>{id}</strong>
                  <button
                    type="button"
                    onClick={() => toggleTrack(id)}
                    style={{ ...styles.toggle, background: on ? '#10B981' : '#475569' }}
                    aria-label={`Toggle ${id}`}
                  >
                    <span style={{ ...styles.toggleSpan, left: on ? 18 : 2 }} />
                  </button>
                </div>
                <div style={styles.trackName}>{name}</div>
                <div style={styles.trackStats}>
                  <span>Ticks {m.ticks_evaluated || 0}</span>
                  <span>Signals {m.signals_generated || 0}</span>
                  <span>Orders {m.orders_created || 0}</span>
                  <span>Errors {m.exceptions || 0}</span>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <Card title="Positions">
        {Object.keys(positions).length === 0 ? (
          <div style={styles.muted}>포지션 없음</div>
        ) : (
          <div className="dashboard-list" style={styles.list}>
            {Object.entries(positions).map(([key, value]) => (
              <div key={key} className="dashboard-row" style={styles.row}>
                <span>{key}</span>
                <strong>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</strong>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Orders / Executions">
        <div style={styles.sectionLabel}>Orders</div>
        <div className="dashboard-list" style={styles.list}>
          {orders.slice(-6).map((o, i) => (
            <div key={i} className="dashboard-row" style={styles.row}>
              <span>{o.track_id || o.client_order_id || '-'}</span>
              <span>{o.side || ''} {o.qty || ''}</span>
            </div>
          ))}
          {!orders.length && <div style={styles.muted}>주문 대기 중</div>}
        </div>
        <div style={{ ...styles.sectionLabel, marginTop: 12 }}>Executions</div>
        <div className="dashboard-list" style={styles.list}>
          {executions.slice(-6).map((e, i) => (
            <div key={i} className="dashboard-row" style={styles.row}>
              <span>{e.track_id || e.exec_id || '-'}</span>
              <span>{fmt(e.executed_price)} × {e.executed_qty || 0}</span>
            </div>
          ))}
          {!executions.length && <div style={styles.muted}>체결 대기 중</div>}
        </div>
      </Card>

      <Card title="Composite Payoff" wide>
        {payoff.length ? (
          <div className="chart-wrapper-responsive" style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
              <ScatterChart>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" dataKey="x" />
                <YAxis type="number" dataKey="y" />
                <Tooltip />
                <ReferenceLine y={0} />
                <Scatter data={payoff} line={{ stroke: '#38BDF8' }} shape={() => null} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div style={styles.muted}>실제 포지션이 생성되면 Payoff가 표시됩니다.</div>
        )}
      </Card>

      <Card title="Realtime PnL" wide>
        <div className="chart-wrapper-responsive" style={{ width: '100%', height: 280 }}>
          <ResponsiveContainer>
            <LineChart data={coords}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="x" />
              <YAxis />
              <Tooltip />
              <Line dataKey="y" stroke="#38BDF8" dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card title="Replay / Runtime">
        <div className="dashboard-metrics-grid" style={styles.metrics}>
          <Metric label="Last Tick" value={replay.timestamp || market.timestamp || condition.timestamp || '-'} />
          <Metric label="Seq" value={condition.seq_id || market.seq_id || 0} />
          <Metric label="Ticks Processed" value={replay.ticks_processed || 0} />
          <Metric label="Orders Routed" value={replay.orders_routed || 0} />
          <Metric label="Executions Handled" value={replay.executions_handled || 0} />
          <Metric label="Stress Flags" value={(condition.stress_flags || []).length} />
        </div>
      </Card>
    </div>
  );
}

const styles = {
  grid: { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 14 },
  card: { background: '#111827', border: '1px solid #334155', borderRadius: 14, padding: 16, minWidth: 0 },
  cardTitle: { color: '#CBD5E1', fontSize: 12, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 14 },
  metrics: { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 },
  metric: { display: 'flex', flexDirection: 'column', gap: 3, padding: 10, background: '#0F172A', borderRadius: 9 },
  label: { color: '#64748B', fontSize: 10 },
  muted: { color: '#64748B', fontSize: 12 },
  flags: { display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 12 },
  flag: { color: '#FBBF24', background: '#422006', border: '1px solid #92400E', padding: '4px 7px', borderRadius: 6, fontSize: 9 },
  reason: { marginTop: 10, color: '#94A3B8', fontFamily: 'monospace', fontSize: 10 },
  trackGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 },
  track: { background: '#0F172A', border: '1px solid', borderRadius: 10, padding: 11 },
  trackHead: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  trackName: { marginTop: 7, fontSize: 12, fontWeight: 700 },
  trackStats: { marginTop: 8, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, color: '#94A3B8', fontSize: 9 },
  toggle: { width: 38, height: 21, border: 0, borderRadius: 12, padding: 2, position: 'relative', cursor: 'pointer' },
  toggleSpan: { position: 'absolute', top: 2, width: 17, height: 17, borderRadius: '50%', background: '#FFF', transition: 'left 0.15s ease' },
  list: { display: 'flex', flexDirection: 'column', gap: 5 },
  row: { display: 'flex', justifyContent: 'space-between', gap: 10, padding: '7px 8px', background: '#0F172A', borderRadius: 7, fontSize: 10, color: '#CBD5E1' },
  sectionLabel: { color: '#64748B', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.1em' },
};