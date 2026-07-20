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
  payoffCoords: [], // [{x: 340, y: -100}, {x: 350, y: 0}, ...]
  
  updateData: (newData) => set((state) => {
    // 🛡️ [Null 및 타입 방어]
    if (!newData || typeof newData !== 'object') {
      return state;
    }
    
    // 1. 기존 데이터 객체 병합 (하위 호환성 유지)
    const nextData = {
      ...state.data,
      ...newData,
    };
    
    // 2. RegimeState (현재 국면) 업데이트
    const nextRegime = newData.regime || state.regime;
    
    // 3. SyntheticCoords 업데이트 (원칙 2 준수: MAX_POINTS 제한 및 Immutability 준수)
    let nextCoords = state.coords;
    if (newData.coord && typeof newData.coord === 'object') {
      nextCoords = [...state.coords, newData.coord].slice(-Constants.MAX_POINTS);
    }
    
    // 4. PayoffCoords 업데이트 (새 배열이 들어오면 통째로 교체하여 불변성 확보)
    const nextPayoffCoords = newData.payoffCoords || state.payoffCoords;
    
    return {
      data: nextData,
      regime: nextRegime,
      coords: nextCoords,
      payoffCoords: nextPayoffCoords,
    };
  }),
}));
