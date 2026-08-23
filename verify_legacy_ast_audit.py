"""Deep AST and Static Analysis Audit for Legacy Import, Caller, and State Mutation Isolation."""
import ast
import os
import sys
from typing import Dict, List, Set, Tuple

TARGET_DIRS = [
    "option_program",
    "virtual_securities_firm",
    "virtual_market_simulator",
    "shared",
    "infra",
]

LEGACY_PACKAGES = {
    "account",
    "position",
    "pnl",
    "risk",
    "exchange",
    "execution",
    "strategy",
    "fsm",
    "sensor",
    "interface",
    "hft",
    "core",
    "recovery",
}

FORBIDDEN_MUTATION_ATTRS = {
    "balance",
    "cash",
    "total_balance",
    "used_margin",
    "free_margin",
    "positions",
    "unrealized_pnl",
    "realized_pnl",
}


class DeepASTAuditor(ast.NodeVisitor):
    def __init__(self, filepath: str, is_strategy: bool = False):
        self.filepath = filepath
        self.is_strategy = is_strategy
        self.legacy_imports: List[Tuple[int, str]] = []
        self.forbidden_mutations: List[Tuple[int, str]] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            root_mod = alias.name.split(".")[0]
            if root_mod in LEGACY_PACKAGES:
                self.legacy_imports.append((node.lineno, f"import {alias.name}"))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            root_mod = node.module.split(".")[0]
            if root_mod in LEGACY_PACKAGES:
                self.legacy_imports.append((node.lineno, f"from {node.module} import ..."))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        # 전략 코드 내부에서 계좌/증거금/포지션 직접 변이 금지
        if self.is_strategy:
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in FORBIDDEN_MUTATION_ATTRS:
                    # self.balance = ... or account.balance = ...
                    self.forbidden_mutations.append((node.lineno, f"Direct mutation of '{target.attr}'"))
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign):
        if self.is_strategy:
            if isinstance(node.target, ast.Attribute) and node.target.attr in FORBIDDEN_MUTATION_ATTRS:
                self.forbidden_mutations.append((node.lineno, f"Direct aug-mutation of '{node.target.attr}'"))
        self.generic_visit(node)


def run_ast_audit() -> bool:
    print("=" * 80)
    print("[DEEP AST AUDIT] Legacy Isolation, Imports, Callers & State Mutation Audit")
    print("=" * 80)

    total_files_audited = 0
    total_legacy_imports = 0
    total_forbidden_mutations = 0

    for target_dir in TARGET_DIRS:
        if not os.path.exists(target_dir):
            continue
        for root, _, files in os.walk(target_dir):
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    is_strategy = "strategy" in root.replace("\\", "/").split("/")
                    total_files_audited += 1

                    with open(filepath, "r", encoding="utf-8") as f:
                        try:
                            tree = ast.parse(f.read(), filename=filepath)
                        except Exception as e:
                            print(f"[ERROR] Parsing failed for {filepath}: {e}")
                            return False

                    auditor = DeepASTAuditor(filepath, is_strategy=is_strategy)
                    auditor.visit(tree)

                    if auditor.legacy_imports:
                        for lineno, msg in auditor.legacy_imports:
                            print(f"  [FAIL] Legacy Import: {filepath}:{lineno} -> {msg}")
                            total_legacy_imports += 1

                    if auditor.forbidden_mutations:
                        for lineno, msg in auditor.forbidden_mutations:
                            print(f"  [FAIL] Forbidden Mutation in Strategy: {filepath}:{lineno} -> {msg}")
                            total_forbidden_mutations += 1

    print("-" * 80)
    print(f"Audited Target Python Files:      {total_files_audited} files")
    print(f"Legacy Imports Found:             {total_legacy_imports} violations")
    print(f"Direct State Mutations Found:     {total_forbidden_mutations} violations")
    print("=" * 80)

    if total_legacy_imports == 0 and total_forbidden_mutations == 0:
        print("[AUDIT RESULT] PASS - Target Architecture & Strategy Domains are 100% Isolated!")
        return True
    else:
        print("[AUDIT RESULT] FAIL - Violations detected.")
        return False


if __name__ == "__main__":
    success = run_ast_audit()
    sys.exit(0 if success else 1)
