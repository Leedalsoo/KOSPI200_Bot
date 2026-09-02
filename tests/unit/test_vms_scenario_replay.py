import pytest
from main import TradingSystem
from option_program.runtime.program_runtime import OptionProgramRuntime
from shared.contracts.canonical import CanonicalMarketTick
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime


def _tick(seq: int, price: float) -> CanonicalMarketTick:
    return CanonicalMarketTick(
        timestamp=f"2026-08-23 09:00:{seq % 60:02d}.000",
        underlying_price=price,
        strike_price=350.0,
        option_type="CALL",
        bid_price=price - 0.1,
        ask_price=price + 0.1,
        last_price=price,
        volume=10,
        seq_id=seq,
    )


def test_scenario_source_is_default_and_produces_ticks() -> None:
    runtime = VirtualMarketSimulatorRuntime()
    runtime.set_scenario("CALM")
    runtime.set_running(True)
    ticks = list(runtime.generate_tick_stream(total_days=1, ticks_per_day=5))
    assert len(ticks) == 5
    assert all(t.seq_id > 0 for t in ticks)
    assert runtime.get_control_state()["source"] == "SCENARIO"


def test_scenario_selection_is_deterministic_after_reset() -> None:
    runtime_a = VirtualMarketSimulatorRuntime()
    runtime_b = VirtualMarketSimulatorRuntime()
    runtime_a.set_scenario("HIGH_VOLATILITY")
    runtime_b.set_scenario("HIGH_VOLATILITY")
    a = list(runtime_a.generate_tick_stream(total_days=1, ticks_per_day=10))
    b = list(runtime_b.generate_tick_stream(total_days=1, ticks_per_day=10))
    assert [x.underlying_price for x in a] == [x.underlying_price for x in b]


def test_replay_source_overrides_scenario_generation() -> None:
    runtime = VirtualMarketSimulatorRuntime()
    replay = [_tick(101, 401.0), _tick(102, 402.0), _tick(103, 403.0)]
    runtime.load_replay(replay)
    runtime.set_running(True)
    ticks = list(runtime.generate_tick_stream(total_days=1, ticks_per_day=10))
    assert [t.seq_id for t in ticks] == [101, 102, 103]
    assert [t.underlying_price for t in ticks] == [401.0, 402.0, 403.0]
    assert runtime.get_control_state()["source"] == "REPLAY"


def test_replay_reset_restarts_from_first_tick() -> None:
    runtime = VirtualMarketSimulatorRuntime()
    replay = [_tick(1, 401.0), _tick(2, 402.0)]
    runtime.load_replay(replay)
    runtime.set_running(True)
    first = list(runtime.generate_tick_stream(total_days=1, ticks_per_day=2))
    runtime.replay.reset()
    second = list(runtime.generate_tick_stream(total_days=1, ticks_per_day=2))
    assert [t.seq_id for t in first] == [1, 2]
    assert [t.seq_id for t in second] == [1, 2]


def test_reset_clears_replay_and_stops_runtime() -> None:
    runtime = VirtualMarketSimulatorRuntime()
    runtime.load_replay([_tick(1, 401.0)])
    runtime.reset_simulation()
    state = runtime.get_control_state()
    assert state["source"] == "SCENARIO"
    assert state["replay"]["active"] is False
    assert state["running"] is False


def test_replay_round_trip_tick_exact_field_equality() -> None:
    """[10단계-6] Replay 적재 후 산출되는 tick이 원본 입력의 모든 필드 및 순서와 100% 일치함을 검증."""
    input_ticks = [
        CanonicalMarketTick(
            timestamp=f"2026-08-23 09:{i:02d}:00.000",
            underlying_price=350.0 + i * 0.25,
            strike_price=350.0,
            option_type="CALL" if i % 2 == 0 else "PUT",
            bid_price=350.0 + i * 0.25 - 0.05,
            ask_price=350.0 + i * 0.25 + 0.05,
            last_price=350.0 + i * 0.25,
            volume=100 + i * 10,
            seq_id=1000 + i,
        )
        for i in range(1, 21)
    ]

    vms = VirtualMarketSimulatorRuntime()
    vms.load_replay(input_ticks)
    vms.set_running(True)

    replayed_ticks = list(vms.generate_tick_stream(total_days=1, ticks_per_day=len(input_ticks)))

    assert len(replayed_ticks) == len(input_ticks)
    for orig, rep in zip(input_ticks, replayed_ticks):
        assert rep.seq_id == orig.seq_id
        assert rep.timestamp == orig.timestamp
        assert rep.underlying_price == orig.underlying_price
        assert rep.strike_price == orig.strike_price
        assert rep.option_type == orig.option_type
        assert rep.bid_price == orig.bid_price
        assert rep.ask_price == orig.ask_price
        assert rep.last_price == orig.last_price
        assert rep.volume == orig.volume


@pytest.mark.asyncio
async def test_replay_live_pipeline_equivalence_and_determinism() -> None:
    """[10단계-6] 동일 CanonicalMarketTick 입력 시 Replay 공급 경로와 Live Pipeline 간 동등성 및 결정론성 검증."""
    input_ticks = [
        CanonicalMarketTick(
            timestamp=f"2026-08-23 09:00:{i:02d}.000",
            underlying_price=345.0 + (i % 5) * 1.5,
            strike_price=350.0,
            option_type="CALL",
            bid_price=345.0 + (i % 5) * 1.5 - 0.1,
            ask_price=345.0 + (i % 5) * 1.5 + 0.1,
            last_price=345.0 + (i % 5) * 1.5,
            volume=50 + i * 5,
            seq_id=2000 + i,
        )
        for i in range(1, 21)
    ]

    # -------------------------------------------------------------------------
    # 세션 A: Direct Replay / Backtest 경로 (Fresh OptionProgramRuntime에 직접 공급)
    # -------------------------------------------------------------------------
    runtime_direct = OptionProgramRuntime()
    direct_commands = []
    for tick in input_ticks:
        cmds = runtime_direct.process_tick(tick)
        direct_commands.extend(cmds)

    # -------------------------------------------------------------------------
    # 세션 B: Live TradingSystem Pipeline 경로 (VMS Replay 적재 -> run_loop 구동)
    # -------------------------------------------------------------------------
    ts = TradingSystem(config={"mode": "PAPER"})
    await ts.initialize()
    ts.vms.load_replay(input_ticks)

    # Live run_loop 실행 (20틱)
    await ts.run_loop(max_ticks=len(input_ticks))

    # -------------------------------------------------------------------------
    # 동등성(Equivalence) 검증: Direct 공급과 Live Pipeline의 핵심 산출물 비교
    # -------------------------------------------------------------------------
    # 1) Live 파이프라인에서 수신 및 처리된 마지막 틱 일치
    assert ts.last_tick is not None
    assert ts.last_tick.seq_id == input_ticks[-1].seq_id
    assert ts.last_tick.underlying_price == input_ticks[-1].underlying_price

    # 2) 생성된 주문 총 개수 및 순서 일치
    live_history = getattr(ts.op_runtime, "last_orders", [])
    assert len(direct_commands) == len(live_history)
    assert len(direct_commands) > 0

    # 3) 각 주문의 핵심 계약 속성(client_order_id, track_id, side, qty, price) 100% 동등성 검증
    for direct_cmd, live_cmd in zip(direct_commands, live_history):
        assert direct_cmd.client_order_id == live_cmd["client_order_id"]
        assert direct_cmd.track_id == live_cmd["track_id"]
        assert direct_cmd.side.value == live_cmd["side"]
        assert direct_cmd.qty == live_cmd["qty"]
        assert direct_cmd.price == live_cmd["price"]

    # -------------------------------------------------------------------------
    # 결정론성(Determinism) 검증: Fresh Runtime에서 동일 입력 반복 실행 시 100% 동일
    # -------------------------------------------------------------------------
    runtime_repeat = OptionProgramRuntime()
    repeat_commands = []
    for tick in input_ticks:
        cmds = runtime_repeat.process_tick(tick)
        repeat_commands.extend(cmds)

    assert len(repeat_commands) == len(direct_commands)
    for c_orig, c_rep in zip(direct_commands, repeat_commands):
        assert c_orig.client_order_id == c_rep.client_order_id
        assert c_orig.track_id == c_rep.track_id
        assert c_orig.qty == c_rep.qty
        assert c_orig.price == c_rep.price
        assert c_orig.symbol == c_rep.symbol
