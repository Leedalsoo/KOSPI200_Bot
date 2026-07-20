import { renderHook, act } from '@testing-library/react';
import { useWebSocket } from './useWebSocket';
import { useStore } from '../store/rootStore';

// 🛡️ [글로벌 WebSocket 모킹]
class MockWebSocket {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.readyState = 0; // CONNECTING
    MockWebSocket.instances.push(this);

    // 연결 수립 비동기 흉내
    this.openTimeout = setTimeout(() => {
      this.readyState = 1; // OPEN
      if (this.onopen) this.onopen();
    }, 10);
  }

  close() {
    this.readyState = 3; // CLOSED
    if (this.openTimeout) {
      clearTimeout(this.openTimeout);
    }
    // 소켓 close 이벤트 트리거
    setTimeout(() => {
      if (this.onclose) this.onclose();
    }, 10);
  }

  triggerMessage(data) {
    if (this.onmessage) {
      this.onmessage({ data });
    }
  }

  triggerClose() {
    if (this.onclose) {
      this.onclose();
    }
  }
}

global.WebSocket = MockWebSocket;

describe('useWebSocket Hook 검증', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    jest.useFakeTimers();
    // 스토어 데이터 매 테스트 마다 초기화
    act(() => {
      useStore.setState({ data: {} });
    });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('[상태 전파]: 연결 시 isConnected가 정상 활성화되는가?', async () => {
    const { result } = renderHook(() => useWebSocket('ws://localhost:8080'));

    // 초기 상태는 false
    expect(result.current.isConnected).toBe(false);

    // 10ms 지나서 소켓 오픈 트리거
    await act(async () => {
      jest.advanceTimersByTime(10);
    });

    expect(result.current.isConnected).toBe(true);
  });

  test('[데이터 무결성]: 패킷 정상 파싱 및 null 방어 동작 여부', async () => {
    const { result } = renderHook(() => useWebSocket('ws://localhost:8080'));

    await act(async () => {
      jest.advanceTimersByTime(10);
    });

    const mockSocket = MockWebSocket.instances[0];

    // 정상 데이터 발송
    await act(async () => {
      mockSocket.triggerMessage(JSON.stringify({ price: 350.25, qty: 10 }));
    });

    // 쓰로틀 타임(200ms) 대기하여 lastData 수신 확인
    await act(async () => {
      jest.advanceTimersByTime(200);
    });

    expect(result.current.lastData).toEqual({ price: 350.25, qty: 10 });
    expect(useStore.getState().data).toEqual({ price: 350.25, qty: 10 });

    // Null 및 비객체 주입 시 크래시 없는가 검증
    await act(async () => {
      mockSocket.triggerMessage(null);
      mockSocket.triggerMessage('invalid json format string');
      mockSocket.triggerMessage(JSON.stringify(null));
      mockSocket.triggerMessage(JSON.stringify(12345));
    });

    // 쓰로틀 타임 경과
    await act(async () => {
      jest.advanceTimersByTime(200);
    });

    // 크래시 없이 기존 상태가 안전하게 보존됨을 검증
    expect(result.current.lastData).toEqual({ price: 350.25, qty: 10 });
    expect(useStore.getState().data).toEqual({ price: 350.25, qty: 10 });
  });

  test('[연결 강건성]: 서버 끊김 시 지수 백오프(Exponential Backoff)로 3회 이상 정상 재시도하는가?', async () => {
    const { result } = renderHook(() => useWebSocket('ws://localhost:8080'));

    await act(async () => {
      jest.advanceTimersByTime(10);
    });

    expect(result.current.isConnected).toBe(true);
    expect(MockWebSocket.instances.length).toBe(1);

    const firstSocket = MockWebSocket.instances[0];

    // 1차 연결 강제 닫기 -> 1초 뒤 재접속 발생 예상
    await act(async () => {
      firstSocket.triggerClose();
    });
    expect(result.current.isConnected).toBe(false);

    // 1초 경과 대기 (재접속 타이머 1000ms + 소켓 오픈 10ms)
    await act(async () => {
      jest.advanceTimersByTime(1010);
    });
    expect(MockWebSocket.instances.length).toBe(2);

    // 2차 연결 강제 닫기 -> 2초 뒤 재접속 발생 예상
    const secondSocket = MockWebSocket.instances[1];
    await act(async () => {
      secondSocket.triggerClose();
    });

    // 2초 경과 대기 (2000ms + 10ms)
    await act(async () => {
      jest.advanceTimersByTime(2010);
    });
    expect(MockWebSocket.instances.length).toBe(3);

    // 3차 연결 강제 닫기 -> 4초 뒤 재접속 발생 예상
    const thirdSocket = MockWebSocket.instances[2];
    await act(async () => {
      thirdSocket.triggerClose();
    });

    // 4초 경과 대기 (4000ms + 10ms)
    await act(async () => {
      jest.advanceTimersByTime(4010);
    });
    expect(MockWebSocket.instances.length).toBe(4);
  });

  test('[통신 부하 대응]: 100ms 갱신 시 쓰로틀링(200ms)이 정상 작동하여 렌더링 갱신 횟수가 통제되는가?', async () => {
    const { result } = renderHook(() => useWebSocket('ws://localhost:8080'));

    await act(async () => {
      jest.advanceTimersByTime(10);
    });

    const mockSocket = MockWebSocket.instances[0];

    // 100ms 간격으로 5번의 데이터를 주입
    // 0ms, 100ms, 200ms, 300ms, 400ms
    await act(async () => {
      mockSocket.triggerMessage(JSON.stringify({ seq: 1 }));
    });
    
    // 100ms 시점
    await act(async () => {
      jest.advanceTimersByTime(100);
      mockSocket.triggerMessage(JSON.stringify({ seq: 2 }));
    });

    // Zustand 스토어는 부분 델타 업데이트를 즉시 병합 처리하므로 seq 2가 반영됨
    expect(useStore.getState().data.seq).toBe(2);
    // 그러나 lastData 훅 상태는 200ms 쓰로틀링에 의해 아직 갱신되지 않고 null 상태
    expect(result.current.lastData).toBeNull();

    // 200ms 시점 -> 쓰로틀 타이머 만료되어 로컬 lastData 갱신됨 (seq: 2 적용)
    await act(async () => {
      jest.advanceTimersByTime(100);
    });
    expect(result.current.lastData.seq).toBe(2);

    // 300ms 시점
    await act(async () => {
      mockSocket.triggerMessage(JSON.stringify({ seq: 3 }));
      jest.advanceTimersByTime(100);
      mockSocket.triggerMessage(JSON.stringify({ seq: 4 }));
    });

    // 400ms 시점 -> 쓰로틀 타이머 만료로 lastData 갱신 (seq: 4 적용)
    await act(async () => {
      jest.advanceTimersByTime(100);
    });
    expect(result.current.lastData.seq).toBe(4);
  });
});
