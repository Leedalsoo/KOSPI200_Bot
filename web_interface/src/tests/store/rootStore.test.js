import { act } from '@testing-library/react';
import { useStore } from '../../store/rootStore';

describe('Zustand rootStore 코어 로직 검증', () => {
  beforeEach(() => {
    // 매 테스트마다 스토어 상태 초기화
    act(() => {
      useStore.setState({
        data: {},
        regime: 'NEUTRAL',
        coords: [],
        payoffCoords: []
      });
    });
  });

  test('[상태 무결성]: updateData 호출 시 기존 좌표 및 국면 정보가 유실되지 않는가?', () => {
    act(() => {
      useStore.getState().updateData({
        regime: 'BULL',
        coord: { x: 10, y: 15.5 }
      });
    });

    expect(useStore.getState().regime).toBe('BULL');
    expect(useStore.getState().coords).toEqual([{ x: 10, y: 15.5 }]);

    // 추가 델타 데이터 업데이트 (새 좌표 추가 및 국면 유지)
    act(() => {
      useStore.getState().updateData({
        coord: { x: 11, y: 16.0 }
      });
    });

    expect(useStore.getState().regime).toBe('BULL'); // 기존 국면 유지됨
    expect(useStore.getState().coords).toEqual([
      { x: 10, y: 15.5 },
      { x: 11, y: 16.0 }
    ]);
  });

  test('[윈도우 제한]: 데이터 포인트가 100개를 초과할 때 가장 오래된 데이터가 탈락(FIFO)하는가?', () => {
    // 105개의 데이터를 순차 주입
    act(() => {
      for (let i = 1; i <= 105; i++) {
        useStore.getState().updateData({
          coord: { x: i, y: i * 2 }
        });
      }
    });

    const finalCoords = useStore.getState().coords;

    // 최대 길이는 엄격히 100개여야 함
    expect(finalCoords.length).toBe(100);

    // 가장 오래된 1~5번 데이터가 탈락하고 6번부터 105번까지 존재해야 함
    expect(finalCoords[0]).toEqual({ x: 6, y: 12 });
    expect(finalCoords[99]).toEqual({ x: 105, y: 210 });
  });

  test('[상태 무결성]: null/비객체/비정상 패킷 주입 시 기존 상태를 훼손하지 않는가?', () => {
    act(() => {
      useStore.getState().updateData({
        regime: 'BEAR',
        coord: { x: 5, y: -5 }
      });
    });

    // 비정상 데이터 주입 시도
    act(() => {
      useStore.getState().updateData(null);
      useStore.getState().updateData(undefined);
      useStore.getState().updateData("invalid_string");
    });

    expect(useStore.getState().regime).toBe('BEAR');
    expect(useStore.getState().coords).toEqual([{ x: 5, y: -5 }]);
  });
});
