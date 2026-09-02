# -*- coding: utf-8 -*-
"""Option Contract Master & Expiry Lookup Interface.

Defines the contract for looking up option expiration dates by instrument symbol.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional


class IOptionContractMaster(ABC):
    """[추상 인터페이스] 옵션 종목 심볼 기반 만기일 조회 계약."""

    @abstractmethod
    def get_expiry(self, symbol: str) -> Optional[str]:
        """주어진 옵션 종목코드(symbol)의 만기일(YYYY-MM-DD)을 반환.

        종목코드가 존재하지 않거나 만기일이 정의되지 않은 경우 None 반환.
        """
        pass

    @abstractmethod
    def register_contract(self, symbol: str, expiry: str) -> None:
        """옵션 종목코드와 만기일을 마스터 테이블에 등록."""
        pass


class InMemoryOptionContractMaster(IOptionContractMaster):
    """[기본 구현체] 메모리 기반 옵션 종목 마스터 테이블."""

    def __init__(self, contracts: Optional[Dict[str, str]] = None) -> None:
        # {symbol: expiry_date_str (YYYY-MM-DD)}
        self._contracts: Dict[str, str] = dict(contracts or {})

    def get_expiry(self, symbol: str) -> Optional[str]:
        if not symbol:
            return None
        return self._contracts.get(symbol.strip())

    def register_contract(self, symbol: str, expiry: str) -> None:
        if symbol and expiry:
            self._contracts[symbol.strip()] = expiry.strip()
