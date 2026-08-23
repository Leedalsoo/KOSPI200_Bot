import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class AccountState:
    """자산 및 증거금 상태"""
    initial_capital: float = 25000000.0
    current_capital: float = 25000000.0
    accumulated_reserve: float = 0.0
    total_equity: float = 25000000.0
    daily_hwm: float = 25000000.0
    highest_equity_today: float = 25000000.0
    used_margin: float = 0.0
    margin_ratio: float = 0.0
    calculated_fee: float = 0.0

@dataclass
class PortfolioState:
    """포지션 및 미체결 주문 상태"""
    current_position_qty: int = 0
    options: List[Dict[str, Any]] = field(default_factory=list)
    track5_active_qty: int = 0
    track3_entry_price: float = 0.0
    track3_entry_qty: int = 0
    track3_net_qty: int = 0
    insurance_budget_pool: float = 1000000.0

@dataclass
class RiskMetrics:
    """스트레스 및 3중 방어막 메트릭"""
    guard_trigger_count: int = 0
    emergency_cooldown_ticks: int = 0
    daily_friction_cost: float = 0.0
    daily_friction_lockdown: bool = False
    main_engine_broken: bool = False
    is_stress_active: bool = False

@dataclass
class SystemTelemetry:
    """통계 및 성능 기록"""
    strategy_realized_pnl: Dict[str, float] = field(default_factory=dict)
    strategy_pnl_tracker: Dict[str, float] = field(default_factory=dict)
    strategy_stress_pnl: Dict[str, float] = field(default_factory=dict)
    session_telemetry: List[Dict[str, Any]] = field(default_factory=list)
    event_logs: List[Dict[str, Any]] = field(default_factory=list)
    trading_date_logs: List[str] = field(default_factory=list)
    rollover_event_log: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class SessionContext:
    """매 틱(Tick)마다 시스템 전역에서 전달되는 단일 상태 객체"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    runtime_mode: str = "SIMULATION"
    
    account: AccountState = field(default_factory=AccountState)
    portfolio: PortfolioState = field(default_factory=PortfolioState)
    risk: RiskMetrics = field(default_factory=RiskMetrics)
    telemetry: SystemTelemetry = field(default_factory=SystemTelemetry)
    
    current_price: float = 0.0
    prev_price: float = 0.0
    current_regime: str = "NORMAL"
    simulated_days_to_expiry: float = 30.0
    already_rolled_this_month: bool = False
    
    autobot_active: bool = False
    restart_count: int = 0

    def reset_for_new_session(self, preserve_capital: bool = False):
        self.session_id = str(uuid.uuid4())
        self.already_rolled_this_month = False
        self.portfolio.track3_entry_price = 0.0
        self.portfolio.track3_entry_qty = 0
        self.portfolio.track3_net_qty = 0
        self.restart_count = 0
        self.telemetry.session_telemetry.clear()
        self.telemetry.event_logs.clear()
        
        if not preserve_capital:
            self.account = AccountState()
