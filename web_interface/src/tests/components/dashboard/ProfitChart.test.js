import React from 'react';
import { render, act } from '@testing-library/react';
import ProfitChart from '../../../components/dashboard/ProfitChart';
import { useStore } from '../../../store/rootStore';

// Recharts ResponsiveContainer의 가로/세로 측정 기능 모킹
jest.mock('recharts', () => {
  const OriginalRecharts = jest.requireActual('recharts');
  return {
    ...OriginalRecharts,
    ResponsiveContainer: ({ children }) => (
      <div style={{ width: 800, height: 300 }}>{children}</div>
    ),
  };
});

describe('ProfitChart 컴포넌트 렌더링 및 반응성 검증', () => {
  beforeEach(() => {
    act(() => {
      useStore.setState({
        coords: []
      });
    });
  });

  test('[반응성]: 스토어에 데이터가 누적될 때 정상적으로 렌더링되는가?', () => {
    const { container } = render(<ProfitChart />);

    // 초기 상태에는 데이터 포인트가 없음
    let path = container.querySelector('.recharts-line-curve');
    expect(path).toBeNull();

    // 10개의 데이터 포인트 주입
    act(() => {
      const newCoords = [];
      for (let i = 0; i < 10; i++) {
        newCoords.push({ x: i, y: i * 1.5 });
      }
      useStore.setState({ coords: newCoords });
    });

    // 상태 업데이트 후 Recharts LineCurve가 그려졌는지 확인
    path = container.querySelector('.recharts-line-curve');
    expect(path).toBeInTheDocument();
  });

  test('[렌더링 성능]: 100개의 데이터가 고속으로 적재될 때 부하 테스트', () => {
    const startTime = performance.now();

    render(<ProfitChart />);

    act(() => {
      const largeCoords = [];
      for (let i = 0; i < 100; i++) {
        largeCoords.push({ x: i, y: Math.sin(i) * 10 });
      }
      useStore.setState({ coords: largeCoords });
    });

    const endTime = performance.now();
    const duration = endTime - startTime;

    console.log(`ProfitChart 100 points render duration: ${duration}ms`);
    expect(duration).toBeLessThan(100);
  });
});
