import { useEffect, useState, useCallback, useRef } from 'react';
import { useStore } from '../store/rootStore';
export const useWebSocket = (url) => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastData, setLastData] = useState(null);
  const updateData = useStore((state) => state.updateData);
  const reconnectCount = useRef(0);
  const reconnectTimerRef = useRef(null);
  const throttleTimerRef = useRef(null);
  const pendingDataRef = useRef(null);
  const wsRef = useRef(null);
  const connect = useCallback(() => {
    if (reconnectTimerRef.current) { clearTimeout(reconnectTimerRef.current); reconnectTimerRef.current = null; }
    if (wsRef.current) { try { wsRef.current.onclose = null; wsRef.current.close(); } catch (e) { /* no-op */ } wsRef.current = null; }
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => { setIsConnected(true); reconnectCount.current = 0; };
    ws.onmessage = (event) => {
      try {
        if (!event.data) return;
        const parsedData = JSON.parse(event.data);
        if (!parsedData || typeof parsedData !== 'object') return;
        const immutablePayload = Object.freeze({ ...parsedData });
        updateData(immutablePayload);
        pendingDataRef.current = immutablePayload;
        if (!throttleTimerRef.current) {
          throttleTimerRef.current = setTimeout(() => {
            if (pendingDataRef.current) { setLastData(pendingDataRef.current); pendingDataRef.current = null; }
            throttleTimerRef.current = null;
          }, 200);
        }
      } catch (err) { console.error('Packet Parsing Error:', err); }
    };
    ws.onclose = () => {
      setIsConnected(false);
      if (wsRef.current === ws) wsRef.current = null;
      const delay = Math.min(1000 * Math.pow(2, reconnectCount.current), 30000);
      reconnectCount.current += 1;
      reconnectTimerRef.current = setTimeout(connect, delay);
    };
    ws.onerror = () => { try { ws.close(); } catch (e) { /* no-op */ } };
    return ws;
  }, [url, updateData]);
  useEffect(() => {
    const ws = connect();
    return () => {
      if (wsRef.current) { wsRef.current.onclose = null; wsRef.current.close(); }
      else if (ws) { ws.onclose = null; ws.close(); }
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (throttleTimerRef.current) clearTimeout(throttleTimerRef.current);
    };
  }, [connect]);
  const sendCommand = useCallback((command) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(command));
    return true;
  }, []);
  return { isConnected, lastData, sendCommand };
};