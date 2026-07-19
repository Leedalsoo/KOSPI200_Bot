# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from pathlib import Path

from config.settings import ConfigAgent



def test_safe_config_retrieval(tmp_path: Path) -> None:
    """[목표 A 검증] 필수 필드 누락 시 크래시 방어 및 안전한 설정값 호출 증명"""
    f = tmp_path / "limits.yaml"
    f.write_text("limits:\n  mdd: 0.15\n")

    agent = ConfigAgent(str(f))
    agent.load_configuration()

    # get_nested로 안전하게 로드 — YAML float가 Decimal로 변환되어야 함
    assert agent.get_nested(["limits", "mdd"]) == Decimal("0.15")
    # 없는 키 로드 시 default 값 반환
    assert agent.get_nested(["limits", "non_existent"], default=0.10) == 0.10


def test_strict_type_enforcement(tmp_path: Path) -> None:
    """[목표 C 검증] YAML float/int가 Decimal/int로 강제 변환됨을 증명"""
    f = tmp_path / "risk.yaml"
    f.write_text(
        "risk:\n"
        "  max_loss: 500000.50\n"
        "  max_qty: 100\n"
    )
    agent = ConfigAgent(str(f))
    agent.load_configuration()

    # float → Decimal 강제 변환 단언
    max_loss = agent.get_decimal(["risk", "max_loss"])
    assert isinstance(max_loss, Decimal)
    assert max_loss == Decimal("500000.50")

    # int → int 강제 변환 단언
    max_qty = agent.get_int(["risk", "max_qty"])
    assert isinstance(max_qty, int)
    assert max_qty == 100


def test_fail_fast_on_missing_file(tmp_path: Path) -> None:
    """[목표 A 방어 지령 검증] 파일 없을 시 sys.exit(1) Fail-Fast 즉사 증명"""
    agent = ConfigAgent(str(tmp_path / "nonexistent.yaml"))
    with pytest.raises(SystemExit) as exc_info:
        agent.load_configuration()
    assert exc_info.value.code == 1


def test_fail_fast_on_invalid_yaml(tmp_path: Path) -> None:
    """[목표 A 방어 지령 검증] YAML 파싱 오류 시 sys.exit(1) 즉사 증명"""
    f = tmp_path / "broken.yaml"
    f.write_text("key: [unclosed")
    agent = ConfigAgent(str(f))
    with pytest.raises(SystemExit) as exc_info:
        agent.load_configuration()
    assert exc_info.value.code == 1


def test_nested_missing_key_returns_default(tmp_path: Path) -> None:
    """[목표 A 검증] 다단 중첩 경로 중 누락 키가 있어도 default를 반환하고 KeyError 없음을 증명"""
    f = tmp_path / "sparse.yaml"
    f.write_text("a:\n  b: 1\n")
    agent = ConfigAgent(str(f))
    agent.load_configuration()

    # 존재하지 않는 3단계 경로 → default 반환
    result = agent.get_nested(["a", "b", "c"], default="fallback")
    assert result == "fallback"

    # 완전히 없는 최상위 키 → default 반환
    result2 = agent.get_nested(["x", "y"], default=42)
    assert result2 == 42


@pytest.mark.asyncio
async def test_hot_reload_lock(tmp_path: Path) -> None:
    """[목표 B 검증] asyncio.Lock 기반 핫 리로딩이 설정을 안전하게 갱신함을 증명"""
    f = tmp_path / "hot.yaml"
    f.write_text("version: 1\n")
    agent = ConfigAgent(str(f))
    agent.load_configuration()
    assert agent.get_int(["version"]) == 1

    # 파일 내용 변경 후 핫 리로딩
    f.write_text("version: 2\n")
    await agent.reload_configuration()
    assert agent.get_int(["version"]) == 2
