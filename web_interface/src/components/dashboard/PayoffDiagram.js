import React, { memo } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, ResponsiveContainer, ReferenceLine, Tooltip } from 'recharts';
import { useStore } from '../../store/rootStore';

/**
 * @typedef {Object} PayoffCoordinate
 * @property {number} x - 지수 (Index)
 * @property {number} y - 만기 손익 (PnL)
 */

/**
 * 합성 옵션 전략의 지수별 손익 구조(Payoff Profile)를 실시간 시각화하는 다이어그램 컴포넌트.
 * 현재가 기준선(ReferenceLine)의 동적 중심 매핑 및 비애니메이션 최적화를 적용했습니다.
 * 
 * @component
 * @returns {React.ReactElement} PayoffDiagram 컴포넌트
 */
const PayoffDiagram = memo(() => {
  // 🛡️ [Zustand 스토어 상태 구독] 페이오프 곡선 데이터
  const payoffCoords = useStore((state) => state.payoffCoords);
  
  // 🛡️ [원칙 1 준수] X축의 기준이 될 지수 현재가 조회 (기본값 350.00)
  const currentPrice = useStore((state) => 
    state.data.underlyingPrice || state.data.price || 350
  );

  // X축이 항상 지수 현재가를 기준으로 좌우 대칭 중심이 잡히도록 도메인 동적 제어
  const xDomain = [currentPrice - 20, currentPrice + 20];

  return (
    <div style={{ width: '100%', height: '300px', position: 'relative' }}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart
          margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#2D3748" opacity={0.3} />
          
          {/* X축: 지수 현재가 기준 동적 범위 매핑 (원칙 1) */}
          <XAxis 
            type="number" 
            dataKey="x" 
            name="Index" 
            domain={xDomain}
            stroke="#A0AEC0"
            tick={{ fontSize: 11, fill: '#A0AEC0' }}
          />
          
          <YAxis 
            type="number" 
            dataKey="y" 
            name="PnL" 
            domain={['auto', 'auto']}
            stroke="#A0AEC0"
            tick={{ fontSize: 11, fill: '#A0AEC0' }}
          />

          <Tooltip 
            cursor={{ strokeDasharray: '3 3' }}
            contentStyle={{ backgroundColor: '#1A202C', borderColor: '#4A5568', color: '#FFF' }}
            itemStyle={{ color: '#82ca9d' }}
          />

          {/* 🛡️ [성능 극대화] 실시간 차트 폭주 제어를 위한 애니메이션 배제 (원칙 2) */}
          <Scatter 
            data={payoffCoords} 
            fill="#82ca9d" 
            line={{ stroke: '#82ca9d', strokeWidth: 2 }}
            shape={() => null} // 점 마커를 숨기고 라인처럼 깔끔하게 렌더링
            isAnimationActive={false} 
          />

          {/* 0축 손익분기선 기준선 */}
          <ReferenceLine y={0} stroke="#E53E3E" strokeDasharray="3 3" />
          
          {/* 🛡️ 현재가 위치 실시간 세로 마커 (Current Baseline) */}
          <ReferenceLine x={currentPrice} stroke="#3182CE" strokeWidth={2} label={{ value: 'Current', fill: '#3182CE', fontSize: 10, position: 'top' }} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
});

PayoffDiagram.displayName = 'PayoffDiagram';
export default PayoffDiagram;
