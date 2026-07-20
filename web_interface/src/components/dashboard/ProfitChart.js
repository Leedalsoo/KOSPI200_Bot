import React, { memo } from 'react';
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, CartesianGrid, Tooltip } from 'recharts';
import { useStore } from '../../store/rootStore';

/**
 * @typedef {Object} Coordinate
 * @property {number} x - X축 좌표 (시간 또는 틱)
 * @property {number} y - Y축 좌표 (수익률 또는 지수)
 */

/**
 * 실시간 KOSPI200 HFT 시스템의 누적 수익률 곡선을 시각화하는 고성능 차트 컴포넌트.
 * 렌더링 부하 최소화를 위해 React.memo와 Recharts 비애니메이션 모드를 사용합니다.
 * 
 * @component
 * @returns {React.ReactElement} ProfitChart 컴포넌트
 */
const ProfitChart = memo(() => {
  // 🛡️ [Zustand 스토어 상태 구독] coords 배열 직접 변이 엄금 (원칙 3)
  const coords = useStore((state) => state.coords);

  return (
    <div style={{ width: '100%', height: '300px', position: 'relative' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart 
          data={coords}
          margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#2D3748" opacity={0.3} />
          
          <XAxis 
            dataKey="x" 
            hide 
          />
          
          <YAxis 
            domain={['auto', 'auto']}
            stroke="#A0AEC0"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fill: '#A0AEC0' }}
          />

          <Tooltip 
            contentStyle={{ backgroundColor: '#1A202C', borderColor: '#4A5568', color: '#FFF' }}
            labelStyle={{ color: '#A0AEC0' }}
            itemStyle={{ color: '#8884d8' }}
          />
          
          {/* 🛡️ [성능 극대화] 실시간 폭주 대응을 위한 애니메이션 비활성화 (원칙 1) */}
          <Line 
            type="monotone" 
            dataKey="y" 
            stroke="#8884d8" 
            strokeWidth={2}
            dot={false} 
            isAnimationActive={false} 
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
});

ProfitChart.displayName = 'ProfitChart';
export default ProfitChart;
