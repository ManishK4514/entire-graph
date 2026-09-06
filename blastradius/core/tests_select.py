"""Which tests to actually run.

A blast radius that does not end in a command the developer can paste is a
diagram, not a decision.
"""
from __future__ import annotations


def is_test_symbol(symbol: str) -> bool:
    module = symbol.rpartition(".")[0]
    leaf = symbol.rpartition(".")[2]
    return module.startswith("tests.") or module == "tests" or leaf.startswith("test_")


def select(reachable: dict, changed: list) -> dict:
    """Split the blast radius into tests and production symbols, and turn the
    tests into runnable node ids."""
    tests, production = [], []
    for symbol in list(reachable) + list(changed):
        (tests if is_test_symbol(symbol) else production).append(symbol)

    node_ids = []
    for t in sorted(set(tests)):
        module, _, name = t.rpartition(".")
        path = module.replace(".", "/") + ".py"
        node_ids.append(f"{path}::{name}" if name.startswith("test_") else path)

    return {
        "test_symbols": sorted(set(tests)),
        "production_symbols": sorted(set(production)),
        "node_ids": node_ids,
        "command": "pytest " + " ".join(node_ids) if node_ids else "pytest",
    }


def symbols_without_tests(changed: list, reachable: dict) -> list:
    """A changed symbol with no test anywhere in its blast radius."""
    covered = {s for s in reachable if is_test_symbol(s)}
    return [] if covered else [c for c in changed if not is_test_symbol(c)]
