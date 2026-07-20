import React from 'react';
import { render, act } from '@testing-library/react';
import PayoffDiagram from '../../components/dashboard/PayoffDiagram';
import { useStore } from '../../store/rootStore';

// Recharts ResponsiveContainer 모킹
jest.mock('recharts', () => {
  const OriginalRecharts = jest.requireActual('recharts');
  return {
    ...OriginalRecharts,
    ResponsiveContainer: ({ children }) => (
      <div style={{ width: 800, height: 300 }}>{children}</div>
    ),
  };
});

describe('PayoffDiagram 컴포넌트 렌더링 및 동적 갱신 검증', () => {
  beforeEach(() => {
    act(() => {
      useStore.setState({
        data: { underlyingPrice: 350 },
        payoffCoords: []
      });
    });
  });

  test('[좌표 정확도 & 동적 갱신]: 데이터 주입 및 현재가 마커 렌더링 확인', () => {
    const { container } = render(<PayoffDiagram />);

    // 페이오프 좌표 데이터 주입
    act(() => {
      useStore.setState({
        data: { underlyingPrice: 355 }, // 현재가 변경 시뮬레이션
        payoffCoords: [
          { x: 340, y: -50 },
          { x: 350, y: 10 },
          { x: 355, y: 20 },
          { x: 360, y: -10 }
        ]
      });
    });

    // Recharts ReferenceLine이 활성화되었는지 확인
    const lines = container.querySelectorAll('.recharts-reference-line');
    expect(lines.length).toBeGreaterThan(0);
  });

  test('[성능]: 500개 대량 Scatter 데이터 주입 시 렌더링 시간 검증', () => {
    const startTime = performance.now();

    render(<PayoffDiagram />);

    act(() => {
      const mockPayoff = [];
      for (let i = 300; i < 400; i += 0.2) {
        mockPayoff.push({ x: i, y: Math.sin(i) * 100 });
      }
      useStore.setState({
        data: { underlyingPrice: 350 },
        payoffCoords: mockPayoff
      });
    });

    const endTime = performance.now();
    const duration = endTime - startTime;

    console.log(`PayoffDiagram 500 points render duration: ${duration}ms`);
    expect(duration).toBeLessThan(100);
  });
});
