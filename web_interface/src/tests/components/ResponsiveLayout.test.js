import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import App from '../../App';
import OptionProgramPanel from '../../OptionProgramPanel';
import VirtualBrokerPanel from '../../components/VirtualBrokerPanel';
import VirtualExchangePanel from '../../components/VirtualExchangePanel';

jest.mock('recharts', () => {
  const React = require('react');
  return {
    ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
    LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
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


describe('React Responsive Layout Test Suite', () => {
  const mockState = {
    market: { price: 350.5, bid: 350.4, ask: 350.6, spread: 0.2, volume: 10000, seq_id: 123 },
    marketCondition: { regime: 'NORMAL', regime_confidence: 0.95, volatility_ratio: 1.1, liquidity_level: 'HIGH', stress_level: 0.1, stress_flags: [] },
    broker: { mode: 'PAPER', connected: true, account: { balance: 50000000, realized_pnl: 100000, unrealized_pnl: -20000, used_margin: 5000000, free_margin: 45000000 } },
    optionProgram: { current_regime: 'NORMAL', enabled_strategies: {}, strategy_metrics: {} },
    positions: {},
    orders: [],
    executions: [],
    payoff: [],
    coords: [],
    replay: { ticks_processed: 100, orders_routed: 10, executions_handled: 10 },
  };

  const viewports = [
    { name: 'Desktop Full HD', width: 1920, height: 1080 },
    { name: 'Desktop Standard', width: 1440, height: 900 },
    { name: 'Tablet Landscape', width: 1024, height: 768 },
    { name: 'Tablet Portrait', width: 768, height: 1024 },
    { name: 'Mobile iPhone 12/13/14', width: 390, height: 844 },
    { name: 'Mobile iPhone SE', width: 375, height: 812 },
  ];

  viewports.forEach(({ name, width, height }) => {
    test(`renders App properly in viewport: ${name} (${width}x${height})`, () => {
      window.innerWidth = width;
      window.innerHeight = height;
      window.dispatchEvent(new Event('resize'));

      const { container } = render(<App />);
      expect(container.querySelector('.dashboard-page')).toBeInTheDocument();
      expect(container.querySelector('.dashboard-header')).toBeInTheDocument();
      expect(container.querySelector('.dashboard-tabs')).toBeInTheDocument();
      expect(screen.getByText('Integrated Control Panel')).toBeInTheDocument();
    });
  });

  test('OptionProgramPanel applies responsive grid and card classes', () => {
    const { container } = render(
      <OptionProgramPanel state={mockState} isConnected={true} sendCommand={() => {}} />
    );
    expect(container.querySelector('.dashboard-grid')).toBeInTheDocument();
    expect(container.querySelectorAll('.dashboard-card').length).toBeGreaterThan(0);
    expect(container.querySelectorAll('.dashboard-metrics-grid').length).toBeGreaterThan(0);
  });

  test('VirtualBrokerPanel applies responsive grid and control classes', () => {
    const { container } = render(
      <VirtualBrokerPanel state={mockState} sendCommand={() => {}} />
    );
    expect(container.querySelector('.dashboard-grid')).toBeInTheDocument();
    expect(container.querySelectorAll('.dashboard-card').length).toBeGreaterThan(0);
    expect(container.querySelectorAll('.dashboard-btn').length).toBeGreaterThan(0);
  });

  test('VirtualExchangePanel applies responsive grid and form classes', () => {
    const { container } = render(
      <VirtualExchangePanel state={mockState} sendCommand={() => {}} />
    );
    expect(container.querySelector('.dashboard-grid')).toBeInTheDocument();
    expect(container.querySelector('.dashboard-form-grid')).toBeInTheDocument();
    expect(container.querySelectorAll('.dashboard-card').length).toBeGreaterThan(0);
  });
});
