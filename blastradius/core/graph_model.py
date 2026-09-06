"""The symbol graph and reverse-dependency traversal.

Deliberately dumb: it holds edges and walks them. All intelligence about where
edges came from lives in the adapters; all intelligence about what a walk means
lives in impact.py. Keeping this layer boring is what makes the traversal
testable without an Entire installation.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from blastradius.core.evidence import Edge, Verification


@dataclass
class SymbolGraph:
    edges: list = field(default_factory=list)
    _forward: dict = field(default_factory=lambda: defaultdict(list))
    _reverse: dict = field(default_factory=lambda: defaultdict(list))
    _seen: set = field(default_factory=set)

    def add(self, edge: Edge) -> None:
        """Idempotent. A second source asserting the same edge corroborates it
        rather than duplicating it — that is how verification happens."""
        if edge.key() in self._seen:
            existing = self.find(edge.caller, edge.callee)
            if existing is None:
                return
            # Self-corroboration is not verification. An edge is VERIFIED only
            # when a DIFFERENT source derives it independently -- two call sites
            # found by the same parser prove nothing about that parser.
            if edge.provenance.source == existing.provenance.source:
                return
            if edge.provenance.source not in existing.corroborated_by:
                existing.corroborated_by.append(edge.provenance.source)
                # Keep HOW the corroborator resolved it, not just that it did.
                # Discarding this was what let one good derivation plus one
                # bare-name guess read as two independent confirmations.
                existing.corroborated_resolutions.append(edge.provenance.resolution)
                existing.verification = Verification.VERIFIED
            return
        self._seen.add(edge.key())
        self.edges.append(edge)
        self._forward[edge.caller].append(edge)
        self._reverse[edge.callee].append(edge)

    def find(self, caller: str, callee: str):
        for e in self._reverse.get(callee, []):
            if e.caller == caller:
                return e
        return None

    def callers_of(self, symbol: str) -> list:
        return self._reverse.get(symbol, [])

    def callees_of(self, symbol: str) -> list:
        return self._forward.get(symbol, [])

    def symbols(self) -> set:
        return set(self._forward) | set(self._reverse)

    def reachable_from(self, roots, max_hops: int = 6) -> dict:
        """Reverse BFS: everything that transitively DEPENDS ON the roots.

        Returns {symbol: (hop_distance, [Edge path proving it])}. The path is
        what lets the report show its work instead of asserting a conclusion.
        """
        result = {}
        queue = deque((r, 0, []) for r in roots)
        seen = set(roots)
        while queue:
            symbol, hops, path = queue.popleft()
            if hops >= max_hops:
                continue
            for edge in self.callers_of(symbol):
                if edge.caller in seen:
                    continue
                seen.add(edge.caller)
                proof = path + [edge]
                result[edge.caller] = (hops + 1, proof)
                queue.append((edge.caller, hops + 1, proof))
        return result
