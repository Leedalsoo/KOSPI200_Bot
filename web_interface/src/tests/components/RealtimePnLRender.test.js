import React from 'react';
import { render, screen } from '@testing-library/react';
import OptionProgramPanel from '../../OptionProgramPanel';

jest.mock('recharts', () => {
  const React = require('react');
  return {
    ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
    LineChart: ({ children, data }) => <div data-testid="line-chart" data-points={data ? data.length : 0}>{children}</div>,
    Line: () => <div data-testid="line" />,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    CartesianGrid: () => null,
    ScatterChart: ({ children }) => <div data-testid="scatter-chart">{children}</div>,
    Scatter: () => null,
    ReferenceLine: () => null,
  };
});

describe('OptionProgramPanel Realtime PnL 렌더링 및 coords 갱신 검증', () => {
  test('rootStore coords 데이터가 OptionProgramPanel의 Realtime PnL 차트에 정상 바인딩되는가?', () => {
    const mockCoords = [
      { x: 1, y: -5000 },
      { x: 2, y: -87500 },
      { x: 3, y: -127500 },
    ];

    const state = {
      market: { price: 350.0, bid: 349.9, ask: 350.1, spread: 0.2, volume: 1000 },
      marketCondition: { regime: 'NORMAL', regime_confidence: 0.95 },
      broker: { account: { balance: 50000000, realized_pnl: 0, unrealized_pnl: -127500, used_margin: 87530000, free_margin: 0 } },
      optionProgram: { strategy_metrics: {}, enabled_strategies: {} },
      risk: { is_vol_spike: false },
      executions: [],
      orders: [],
      positions: {},
      payoff: [],
      coords: mockCoords,
      replay: { ticks_processed: 3 },
    };

    const { container } = render(
      <OptionProgramPanel state={state} isConnected={true} sendCommand={() => {}} />
    );

    // 1. Realtime PnL 카드 제목 렌더링 확인
    expect(screen.getByText('Realtime PnL')).toBeInTheDocument();

    // 2. Recharts LineChart 컨테이너 존재 및 data-points 바인딩 확인
    const lineChart = container.querySelector('[data-testid="line-chart"]');
    expect(lineChart).toBeInTheDocument();
    expect(lineChart.getAttribute('data-points')).toBe('3');
  });
});
