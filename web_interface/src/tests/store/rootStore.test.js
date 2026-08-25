import { act } from '@testing-library/react';
import { useStore } from '../../store/rootStore';

describe('Zustand rootStore 코어 로직 검증', () => {
  beforeEach(() => {
    // 매 테스트마다 스토어 상태 초기화
    act(() => {
      useStore.setState({
        market: {},
        marketCondition: { regime: 'NEUTRAL' },
        broker: { mode: 'PAPER', connected: true, account: {} },
        optionProgram: { strategy_metrics: {}, enabled_strategies: {} },
        risk: {},
        executions: [],
        orders: [],
        positions: {},
        payoff: [],
        coords: [],
        replay: {},
        data: {},
      });
    });
  });

  test('[상태 무결성]: updateData 호출 시 기존 좌표 및 국면 정보가 유실되지 않는가?', () => {
    act(() => {
      useStore.getState().updateData({
        marketCondition: { regime: 'BULL' },
        coord: { x: 10, y: 15.5 },
      });
    });

    expect(useStore.getState().marketCondition.regime).toBe('BULL');
    expect(useStore.getState().coords).toEqual([{ x: 10, y: 15.5 }]);

    // 추가 델타 데이터 업데이트 (새 좌표 추가 및 국면 유지)
    act(() => {
      useStore.getState().updateData({
        coord: { x: 11, y: 16.0 },
      });
    });

    expect(useStore.getState().marketCondition.regime).toBe('BULL'); // 기존 국면 유지됨
    expect(useStore.getState().coords).toEqual([
      { x: 10, y: 15.5 },
      { x: 11, y: 16.0 },
    ]);
  });

  test('[윈도우 제한]: 데이터 포인트가 1000개를 초과할 때 가장 오래된 데이터가 탈락(FIFO)하는가?', () => {
    // 1005개의 데이터를 순차 주입 (현재 rootStore는 실시간 PnL 차트 관측을 위해 slice(-1000) 윈도우 유지)
    act(() => {
      for (let i = 1; i <= 1005; i++) {
        useStore.getState().updateData({
          coord: { x: i, y: i * 2 },
        });
      }
    });

    const finalCoords = useStore.getState().coords;

    // 최대 길이는 엄격히 1000개여야 함
    expect(finalCoords.length).toBe(1000);

    // 가장 오래된 1~5번 데이터가 탈락하고 6번부터 1005번까지 존재해야 함
    expect(finalCoords[0]).toEqual({ x: 6, y: 12 });
    expect(finalCoords[999]).toEqual({ x: 1005, y: 2010 });
  });

  test('[상태 무결성]: null/비객체/비정상 패킷 주입 시 기존 상태를 훼손하지 않는가?', () => {
    act(() => {
      useStore.getState().updateData({
        marketCondition: { regime: 'BEAR' },
        coord: { x: 5, y: -5 },
      });
    });

    // 비정상 데이터 주입 시도
    act(() => {
      useStore.getState().updateData(null);
      useStore.getState().updateData(undefined);
      useStore.getState().updateData('invalid_string');
    });

    expect(useStore.getState().marketCondition.regime).toBe('BEAR');
    expect(useStore.getState().coords).toEqual([{ x: 5, y: -5 }]);
  });
});
