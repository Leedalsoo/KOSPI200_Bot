import { create } from 'zustand';

// 🛡️ [Constants 설정] 원칙 2 준수
const Constants = {
  MAX_POINTS: 100
};

// 🛡️ [HFT 대시보드 코어 스토어] 델타 업데이트 및 실시간 좌표 윈도우 지원
export const useStore = create((set) => ({
  data: {},
  regime: 'NEUTRAL',
  coords: [], // [{x: 0, y: 0}, ...]
  
  updateData: (newData) => set((state) => {
    // 🛡️ [Null 및 타입 방어]
    if (!newData || typeof newData !== 'object') {
 