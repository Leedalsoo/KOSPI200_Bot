# -*- coding: utf-8 -*-
import pytest
import os
import tempfile
import orjson
import asyncio
from decimal import Decimal
from uuid import uuid4
from datetime import datetime

from infra.wal_store import WalStore, wal_default

def test_wal_default_serialization() -> None:
    """[목표 B 검증] 커스텀 타입 직렬화 정합성 및 예외 차단 증명"""
    test_uuid = uuid4()
    test_dec = Decimal("350.55")
    test_dt = datetime.now()
    
    data = {"u": test_uuid, "d": test_dec, "t": test_dt}
    serialized = orjson.dumps(data, default=wal_default)
    
    parsed = orjson.loads(serialized)
    assert parsed["u"] == str(test_uuid)
    assert parsed["d"] == "350.55"

    # 🛡️ [직렬화 예외 차단 검증] 지원하지 않는 커스텀 객체 인입 시 TypeError 차단 증명
    class UnsupportedClass:
        pass

    with pytest.raises(TypeError):
        orjson.dumps({"unsupported": UnsupportedClass()}, default=wal_default)

@pytest.mark.asyncio
async def test_wal_store_save_and_load() -> None:
    """[목표 A 검증] 스레드풀 기반 비동기 I/O 동시 쓰기 시 순차성(Sequential FIFO) 스트레스 증명"""
    Configuring Web Interface Package
    11:04 AM
    제시된 **[CHECKER PROMPT: WEBSOCKET HOOK INTERFACE VALIDATOR V1]**에 의거하여 web_interface/src/hooks/useWebSocket.js의 구현 사양을 전수 대조 및 검증한 결과 보고서입니다.
    
    1. Object.isFrozen 동결 처리 (Immutable) 검증
    확인 코드 라인 (L63-L64):
    javascript
    // 🛡️ [원칙 1: Immutability 준수] 수신 데이터는 절대 직접 변경하지 않는다(Immutable)
    const immutablePayload = Object.freeze({ ...parsedData });
    검증 결과 (PASS): 수신한 원본 데이터의 얕은 복사본을 생성한 후 Object.freeze를 강제 적용하여 외부 스레드나 UI 레벨에서 데이터가 임의로 직접 변경되는 부작용을 사전에 차단합니다.
    2. 100ms 미만 주기 폭주시 200ms 쓰로틀링 충족 여부 검증
    확인 코드 라인 (L69-L79):
    javascript
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
    검증 결과 (PASS): 100ms 미만 주기로 패킷이 연속 유입되어도, pendingDataRef.current 참조값만 계속 최신화하고 리렌더링을 유발하는 setLastData는 200ms 타이머 만료 시점에 단 1회만 호출됩니다. 이는 CPU/렌더링 오버헤드를 200ms 주기로 일정하게 통제합니다.
    3. 소켓 단절 시 지수 백오프(Exponential Backoff) 승수 지연 검증
    확인 코드 라인 (L93-L100):
    javascript
    // 4. Exponential Backoff (재접속 부하 분산)
    const delay = Math.min(1000 * Math.pow(2, reconnectCount.current), 30000);
    reconnectCount.current += 1;
    reconnectTimerRef.current = setTimeout(() => {
      connect();
    }, delay);
    검증 결과 (PASS):
    1회차 차단 시: $1000 \times 2^0 = 1000\text{ms}$
    2회차 차단 시: $1000 \times 2^1 = 2000\text{ms}$
    3회차 차단 시: $1000 \times 2^2 = 4000\text{ms}$
    최대 $30,000\text{ms}$ (30초)로 상한 한계가 정상 캡핑되어, 백엔드 서버에 서비스 거부(DoS) 상태를 발생시키지 않도록 지수적으로 재시도 간격이 안전하게 확장됩니다.
    4. 패킷 예외 방어 (null, 빈 문자열, 비객체 데이터 크래시 방지) 검증
    확인 코드 라인 (L52-L61):
    javascript
    ws.onmessage = (event) => {
      try {
        // 1. Binary Serialization / orjson 호환 데이터 파싱 및 Null 검증
        if (!event.data) return;
        const parsedData = JSON.parse(event.data);
        
        // 🛡️ [Null 및 타입 방어] 유효하지 않은 패킷은 크래시 없이 패스
        if (!parsedData || typeof parsedData !== 'object') {
          return;
        }
    검증 결과 (PASS):
    event.data가 없는 경우 조기 리턴합니다.
    JSON.parse 파싱 에러는 try-catch 블록이 전역 포획하여 크래시를 방지합니다.
    파싱 성공 후에도 null이거나 객체 타입이 아닐 경우(typeof null === 'object' 예외 방어 포함) 후속 로직 진입 전에 완벽하게 조기 배제됩니다.
    🔍 검증 결론
    
    
    useWebSocket.js
    /KOSPI200_Bot/web_interface/src/hooks/useWebSocket.js) 파일 및 동반된 단위 테스트 파일인 
    
    useWebSocket.test.js
    /KOSPI200_Bot/web_interface/src/hooks/useWebSocket.test.js)은 체커 프롬프트의 4대 검증 규격을 예외 없이 충족하여 실전 무결성 통과(VERIFIED) 상태임을 최종 보고합니다.
    
    11:04 AM
    11:05 AM
    🏛️ [준공 보고서] rootStore.js 구현 및 검증 완료
    백엔드 엔진으로부터 수신된 실시간 좌표 데이터(지수, 수익) 및 알고리즘 국면 상태를 구독할 수 있는 **Zustand 코어 스토어(rootStore.js)**와 이를 검증하는 **단위 테스트(rootStore.test.js)**의 구현을 완료했습니다.
    
    1. 설계 및 구현 세부 사양
    Immutability & FIFO 윈도우 제한 (원칙 2): coords 배열에 신규 실시간 좌표(coord)를 추가할 때 불변성을 유지([...state.coords, newData.coord])하도록 구성했으며, 상수로 선언된 Constants.MAX_POINTS (최대 100개) 한계를 엄격히 준수하여 slice(-MAX_POINTS)로 FIFO(First-In-First-Out) 큐 방식으로 오래된 데이터를 자동 탈락시킵니다.
    순수 상태 관리 (원칙 1): updateData의 set 내부에는 어떠한 외부 비동기 호출이나 API 통신, I/O 작업도 유입되지 않는 순수 함수(Pure Function)로 구축하여 사이드 이펙트와 동기식 병목을 원천 배제했습니다.
    하위 호환성 유지: 기존 통합 패킷 델타 업데이트 필드(data)와 신규 규격인 regime (알고리즘 국면), coords (시각화 좌표 큐) 상태 업데이트를 유기적으로 병합하여 기존 테스트(useWebSocket.test.js)와의 호환성 및 무결성을 백% 보장합니다.
    2. 코드 및 테스트 구축 결과
    생성된 스토어: 
    
    rootStore.js
    /KOSPI200_Bot/web_interface/src/store/rootStore.js)
    생성된 단위 테스트: 
    
    rootStore.test.js
    /KOSPI200_Bot/web_interface/src/store/rootStore.test.js) (상태 무결성, 100개 초과 시의 FIFO 윈도우 한계 제한, null 및 비정상 패킷 방어 검증 로직 완비)
    🚀 다음 컴포넌트(ProfitChart.js) 작업 준비 완료 신호
    중앙 저장소(rootStore.js)와 비동기 브릿지(useWebSocket.js)가 완전히 맞물려 실시간 데이터 파이프라인의 척추가 완성되었습니다. 다음 단계인 실시간 시각화 컴포넌트 **ProfitChart.js**의 개발 및 조립을 진행할 준비가 완료되었습니다. 지시를 주시면 즉시 착수하겠습니다.
    
    11:05 AM
    11:08 AM
    🏛️ [준공 보고서] ProfitChart.js 구현 및 최적화 완료
    실시간 KOSPI200 HFT 대시보드의 전체 수익률 추이를 1Hz 주기로 안전하게 렌더링하는 ProfitChart.js 컴포넌트와 이에 대응하는 **부하 테스트 파일(ProfitChart.test.js)**의 구성을 완료했습니다.
    
    1. 설계 및 최적화 핵심 사양
    애니메이션 비활성화 (원칙 1): 틱 폭주가 일어나는 HFT 환경의 특성상 리렌더링마다 차트 애니메이션을 연산하는 것은 브라우저 메인 스레드에 심각한 병목을 유발하므로, isAnimationActive={false} 설정을 통해 렌더링 성능을 획득하고 CPU 자원 낭비를 차단했습니다.
    데이터 무가공 렌더링 (원칙 2): 컴포넌트 내부에서는 복잡한 매핑이나 변환 로직을 일절 수행하지 않으며, 오직 rootStore의 coords 데이터 배열만을 선형적으로 출력하여 제로 오버헤드 렌더링을 관철했습니다.
    구독 규격 준수 & Immutability: Zustand 스토어의 coords 상태를 읽기 전용으로 슬라이스 구독(useStore((state) => state.coords))하고, 이를 불변 형태 그대로 Recharts 컴포넌트에 공급하도록 구현했습니다.
    2. 코드 및 테스트 파일 연동 정보
    수익률 차트 컴포넌트: 
    
    ProfitChart.js
    /KOSPI200_Bot/web_interface/src/components/dashboard/ProfitChart.js)
    단위 및 성능 부하 테스트: 
    
    ProfitChart.test.js
    /KOSPI200_Bot/web_interface/src/components/dashboard/ProfitChart.test.js) (ResponsiveContainer 모킹 및 100개 포인트 고속 갱신 시 100ms 이내 초고속 렌더링 통과 여부 검증 구조 적용)
    🚀 다음 컴포넌트(PayoffDiagram.js) 조립 준비 완료 신호
    수익률 차트 컴포넌트의 조립이 완료되었습니다. 대시보드의 실시간 파생상품 손익 구조를 시각화할 다음 핵심 UI 컴포넌트인 **PayoffDiagram.js**의 개발 및 조립 신호를 대기하고 있습니다. 지시해 주시면 즉시 착수하겠습니다.
    
    
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        log_path = tmp.name

    try:
        store = WalStore(log_path)
        
        # 🛡️ [동시성 순차성 스트레스 검증] 100개 요청을 일시에 병렬 전송
        # 단일 워커 ThreadPoolExecutor가 FIFO 방식으로 디스크에 정확히 순서대로 밀어 넣는지 입증
        tasks = [store.save_event("SEQ_TEST", {"seq": i}) for i in range(100)]
        await asyncio.gather(*tasks)
        
        history = await store.load_history()
        assert len(history) == 100
        
        # 0부터 99까지 한 치의 순서 오차도 없이 기록되었는지 단언
        for i, event in enumerate(history):
            assert event["event_type"] == "SEQ_TEST"
            assert event["data"]["seq"] == i

    finally:
        try:
            os.remove(log_path)
        except OSError:
            pass

@pytest.mark.asyncio
async def test_wal_store_corrupted_data_recovery() -> None:
    """[목표 C 검증] 정전 시나리오: 반쪽짜리 오염된 JSONL 줄이 있어도 정상 데이터는 파싱됨을 증명"""
    with tempfile.NamedTemporaryFile(delete=False, mode='wb') as tmp:
        # 정상 데이터 기록
        tmp.write(orjson.dumps({"event_type": "VALID", "data": 1}, option=orjson.OPT_APPEND_NEWLINE))
        # 오염된 반쪽 데이터 강제 주입
        tmp.write(b'{"event_type": "CORRUPTED", "da\n')
        # 정상 데이터 기록
        tmp.write(orjson.dumps({"event_type": "VALID2", "data": 2}, option=orjson.OPT_APPEND_NEWLINE))
        log_path = tmp.name

    try:
        store = WalStore(log_path)
        history = await store.load_history()
        # 크래시 없이 정상적인 2개의 라인만 복구되어야 함
        assert len(history) == 2
        assert history[0]["event_type"] == "VALID"
        assert history[1]["event_type"] == "VALID2"
    finally:
        try:
            os.remove(log_path)
        except OSError:
            pass
