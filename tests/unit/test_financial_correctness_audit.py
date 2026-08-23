"""Unit test for KRX Financial Correctness Analytical Hand-Calculation Audit."""
from verify_financial_correctness_audit import verify_financial_correctness_audit

def test_financial_correctness_krx_rules_pass() -> None:
    """[Audit] Verify system financial calculations match KRX analytical hand-calculations 100%."""
    is_correct = verify_financial_correctness_audit()
    assert is_correct is True
