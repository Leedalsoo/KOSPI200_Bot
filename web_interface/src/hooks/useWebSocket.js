import { useEffect, useState, useCallback, useRef } from 'react';
import { useStore } from '../store/rootStore';

/**
 * @typedef {Object} WebSocketHookResult
 * @property {boolean} isConnected - WebSocket 연결 상태 여부
 * @property {Object|null} lastData - 쓰로틀링되어 정제 수신된 가장 최신의 데이터 객체
 */

/**
 * 백엔드 HFT 엔진의 Throttled/Aggregated 데이터를 수신하여 UI 상태를 동기화하는 비동기 브릿지 훅.
 * 백엔드의 100ms 샘플링 틱 폭주에 대응하여 200ms 쓰로틀링 렌더링 제어를 지원합니다.
 * 
 * @param {string} url - WebSocket 서버 주소
 * @returns {WebSocketHookResult}
 */
export const useWebSocket = (url) => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastData, setLastData] = useState(null);
  const updateData = useStore((state) => state.updateData);

  // 🛡️ [Exponential Backoff 및 자원 클린업을 위한 레퍼런스 체인]
  const reconnectCount = useRef(0);
  const reconnectTimerRef = useRef(null);
  const throttleTimerRef = useRef(null);
  const pendingDataRef = useRef(null);
  const wsRef = useRef(null);

  const connect = useCallback(() => {
    // 기존 활성화된 타이머 및 소켓 클린업
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.onclose = null;
        wsRef.current.close();
      } catch (e) {
        // ignore
      }
      wsRef.current = null;
    }

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      reconnectCount.current = 0; // 연결 성공 시 재시도 횟수 초기화
    };

    ws.onmessage = (event) => {
      try {
        // 1. Binary Serialization / orjson 호환 데이터 파싱 및 Null 검증
        if (!event.data) return;
        const parsedData = JSON.parse(event.data);
        
        // 🛡️ [Null 및 타입 방어] 유효하지 않은 패킷은 크래시 없이 패스
        if (!parsedData || typeof parsedData !== 'object') {
          return;
        }

        // 🛡️ [원칙 1: Immutability 준수] 수신 데이터는 절대 직접 변경하지 않는다(Immutable)
        const immutablePayload = Object.freeze({ ...parsedData });

        // 2. Delta Updates 처리: 부분 데이터만 수신된 경우 Store가 즉각 병합 처리
        updateData(immutablePayload);

        // 🛡️ [통신 부하 대응] 100ms 고주파 패킷 유입으로 인한 렌더링 폭탄 방어 (200ms 쓰로틀링)
        pendingDataRef.current = immutablePayload;
        if (!throttleTimerRef.current) {
          throttleTimerRef.current = setTimeout(() => {
            if (pendingDataRef.current) {
              setLastData(pendingDataRef.current);
              pendingDataRef.current = null;
            }
            throttleTimerRef.current = null;
          }, 200);
        }
      } catch (err) {
        console.error("Packet Parsing Error:", err);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      
      // 🛡️ [고아 연결 방어 및 자원 클린업]
      if (wsRef.current === ws) {
        wsRef.current = null;
      }

      // 4. Exponential Backoff (재접속 부하 분산)
      const delay = Math.min(1000 * Math.pow(2, reconnectCount.current), 30000);
      reconnectCount.current += 1;
      
      reconnectTimerRef.current = setTimeout(() => {
        connect();
      }, delay);
    };

    ws.onerror = () => {
      // 에러 시 소켓 닫기를 유도하여 onclose에서 재접속 처리 흐름 통일
      try {
        ws.close();
      } catch (e) {
        // ignore
      }
    };

    return ws;
  }, [url, updateData]);

  useEffect(() => {
    const ws = connect();

    // 🛡️ [메모리 누수 방어] 언마운트 또는 URL 변경 시 모든 소켓 및 타이머 즉시 자원 회수
    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      } else if (ws) {
        ws.onclose = null;
        ws.close();
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (throttleTimerRef.current) {
        clearTimeout(throttleTimerRef.current);
      }
    };
  }, [connect]);

  return { isConnected, lastData };
};
