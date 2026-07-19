# -*- coding: utf-8 -*-
import os
import orjson
import asyncio
import logging
from decimal import Decimal
from uuid import UUID
from datetime import datetime
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

def wal_default(obj: Any) -> Any:
    """[목표 B] HFT 커스텀 데이터 타입(Decimal, UUID, datetime) 직렬화 지원"""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} is not JSON serializable")

class WalStore:
    """Zero-Blocking 초고속 JSONL WAL 엔진"""
    
    def __init__(self, log_path: str) -> None:
        self.log_path: str = log_path
        # 동시성 충돌 방지 및 순차적 쓰기를 보장하기 위해 단일 워커 사용
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)

    def _sync_save(self, payload: bytes) -> None:
        """[목표 A] 동기 방식 파일 I/O 및 fsync (스레드풀에서만 실행됨)"""
        with open(self.log_path, "ab") as f:
            f.write(payload)
            f.flush()
            # 🛡️ [fsync 은닉 금지] OS 커널의 쓰기 지연 캐시 강제 동기화
            os.fsync(f.fileno())

    async def save_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """[목표 A, B] 이벤트를 JSONL로 직렬화 후 비동기적으로 스레드풀에 기록 요청"""
        # orjson.OPT_APPEND_NEWLINE을 통한 개행 문자 포함 직렬화
        payload = orjson.dumps(
            {"event_type": event_type, "data": data},
            default=wal_default,
            option=orjson.OPT_APPEND_NEWLINE
        )
        
        # 🛡️ [루프 블로킹 즉사 방어] run_in_executor 활용 비동기 처리
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._sync_save, payload)

    async def load_history(self) -> List[Dict[str, Any]]:
        """[목표 C] 파일 순회 파싱 및 오염된 라인(Corrupted Data) 회복 로직"""
        if not os.path.exists(self.log_path):
            return []

        history: List[Dict[str, Any]] = []
        with open(self.log_path, "rb") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    parsed = orjson.loads(line)
                    if isinstance(parsed, dict):
                        # mypy strict 만족을 위해 명시적으로 타입 캐스팅 처리
                        typed_dict: Dict[str, Any] = parsed
                        history.append(typed_dict)
                except orjson.JSONDecodeError as e:
                    # 🛡️ [예외 은폐 경계] 경고 로그 생성
                    logger.warning(
                        f"Skipping corrupted WAL line: {line.decode('utf-8', errors='replace').strip()} - Error: {e}"
                    )
                    continue
        return history
