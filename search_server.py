import sys
sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[union-attr]

keywords = ['EXIT_PENDING', 'pending_exit_orders', 'EXIT FILLED', '_pos_get', 
            'strategy_realized_pnl', 'portfolio_options', '_vob', '_exec_ladder',
            'PositionRecord', 'LimitOrderRecord', '_pos_to_dict', '_recalc_margin',
            'from_legacy_dict', 'RISK COVER', 'ITM']

with open('mock_ws_server.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    for kw in keywords:
        if kw in line:
            print(f"L{i}[{kw}]: {line.rstrip()[:120]}")
            break
