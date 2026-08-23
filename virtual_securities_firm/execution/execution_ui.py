"""Virtual Securities Firm Execution UI Interface."""
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ExecutionUI:
    """[VSSF 체결 모니터링 UI]"""
    def __init__(self):
        self.execution_logs: List[Dict[str, Any]] = []

    def log_execution(self, execution_report_dict: Dict[str, Any]) -> None:
        self.execution_logs.append(execution_report_dict)

    def render_execution_summary(self) -> Dict[str, Any]:
        return {
            "title": "=== VSSF 가상체결 실시간 로그 모니터 ===",
            "total_executions": len(self.execution_logs),
            "latest_executions": self.execution_logs[-10:] if self.execution_logs else []
        }
