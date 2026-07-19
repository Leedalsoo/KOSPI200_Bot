# -*- coding: utf-8 -*-
import asyncio
import logging
import sys
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


def _decimal_constructor(loader: yaml.BaseLoader, node: yaml.ScalarNode) -> Decimal:
    """YAML float/int 스칼라를 Decimal로 직접 변환하는 커스텀 컨스트럭터"""
    value = loader.construct_scalar(node)
    try:
        return Decimal(str(value))
    except InvalidOperation:
        logger.critical("YAML Decimal 변환 실패: '%s' — 프로세스를 즉사시킵니다.", value)
        sys.exit(1)


def _int_constructor(loader: yaml.BaseLoader, node: yaml.ScalarNode) -> int:
    """YAML int 스칼라를 int로 강제 변환하는 커스텀 컨스트럭터"""
    return int(loader.construct_scalar(node))

# 🛡️ [타입 캐스팅 엄격화] YAML float/int 태그를 가로채어 Decimal/int로 강제 변환
_SAFE_LOADER = yaml.SafeLoader
_SAFE_LOADER.add_constructor("tag:yaml.org,2002:float", _decimal_constructor)
_SAFE_LOADER.add_constructor("tag:yaml.org,2002:int", _int_constructor)


class ConfigAgent:
    """YAML 설정 로드 및 무결성 검증 엔진 (진실의 원천)"""

    def __init__(self, config_path: str) -> None:
        self.config_path: str = config_path
        self.settings: Dict[str, Any] = {}
        # 🛡️ [핫 리로딩 락] 매매 로직 동작 중 설정 불일치 방지를 위한 비동기 락
        self._lock: asyncio.Lock = asyncio.Lock()

    def load_configuration(self) -> None:
        """[목표 A, C] YAML 로드 및 필수 필드 존재/타입 검증 (KeyError 방어, Fail-Fast)"""
        try:
            with open(self.config_path, encoding="utf-8") as fh:
                raw: Any = yaml.load(fh, Loader=_SAFE_LOADER)  # noqa: S506
        except FileNotFoundError:
            # 🛡️ [부팅 즉사 방어] 파일 부재 시 기동 즉시 exit(1)
            logger.critical(
                "ConfigAgent: 설정 파일을 찾을 수 없습니다: '%s' — 프로세스를 즉사시킵니다.",
                self.config_path,
            )
            sys.exit(1)
        except yaml.YAMLError as exc:
            # 🛡️ [부팅 즉사 방어] YAML 파싱 오류 시 기동 즉시 exit(1)
            logger.critical(
                "ConfigAgent: YAML 파싱 오류 (%s) — 프로세스를 즉사시킵니다.", exc
            )
            sys.exit(1)

        if not isinstance(raw, dict):
            logger.critical(
                "ConfigAgent: 설정 파일 최상위 노드가 dict가 아닙니다 — 프로세스를 즉사시킵니다."
            )
            sys.exit(1)

        # 🛡️ [설정값 오염 방지] 전체 dict를 교체하지 않고 내부 값을 update하여 동시성 안전
        self.settings.clear()
        self.settings.update(raw)
        logger.info("ConfigAgent: 설정 로드 완료 (%s)", self.config_path)

    async def reload_configuration(self) -> None:
        """[목표 B] 핫 리로딩 — asyncio.Lock으로 동기화하여 매매 로직과의 불일치 방지"""
        async with self._lock:
            self.load_configuration()
            logger.info("ConfigAgent: 핫 리로딩 완료 — 설정이 안전하게 갱신되었습니다.")

    def get_nested(self, keys: List[str], default: Any = None) -> Any:
        """[목표 A] KeyError 없는 안전한 깊은 체이닝 접근 (nested_get)"""
        node: Any = self.settings
        for key in keys:
            if not isinstance(node, dict):
                # 중간 경로가 dict가 아닌 경우 → default 반환
                logger.debug(
                    "ConfigAgent.get_nested: 경로 '%s' 에서 '%s'가 dict가 아닙니다 — default 반환",
                    keys,
                    key,
                )
                return default
            node = node.get(key)
            if node is None:
                return default
        return node

    def require_nested(self, keys: List[str]) -> Any:
        """[목표 A] 필수 필드 접근 — 존재하지 않으면 즉시 Abort (Fail-Fast)"""
        value = self.get_nested(keys)
        if value is None:
            key_path = ".".join(keys)
            logger.critical(
                "ConfigAgent: 필수 설정 키 '%s' 가 누락되었습니다 — 프로세스를 즉사시킵니다.",
                key_path,
            )
            sys.exit(1)
        return value

    def get_decimal(self, keys: List[str], default: Optional[Decimal] = None) -> Optional[Decimal]:
        """[목표 C] 설정값을 Decimal로 강제 변환하여 반환 (float 오염 방지)"""
        value = self.get_nested(keys)
        if value is None:
            return default
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except InvalidOperation:
            logger.error(
                "ConfigAgent.get_decimal: '%s' 를 Decimal로 변환할 수 없습니다: %s",
                ".".join(keys),
                value,
            )
            return default

    def get_int(self, keys: List[str], default: Optional[int] = None) -> Optional[int]:
        """[목표 C] 설정값을 int로 강제 변환하여 반환"""
        value = self.get_nested(keys)
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.error(
                "ConfigAgent.get_int: '%s' 를 int로 변환할 수 없습니다: %s",
                ".".join(keys),
                value,
            )
            return default
