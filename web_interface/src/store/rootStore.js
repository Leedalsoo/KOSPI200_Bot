import { create } from 'zustand';
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
}));