"""The orchestrator: changed symbols in, a verifiable decision out."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from blastradius.core import risk as risk_model
from blastradius.core import tests_select
from blastradius.core.evidence import Finding, Provenance, Source, Verification
from blastradius.core.graph_model import SymbolGraph


@dataclass
class ImpactReport:
    changed: list
    band: str
    score: int
    risk_terms: list
    findings: list
    reached: list
    scheduled_jobs: list
    tests: dict
    evidence_sources: list
    unverified_count: int
    conflicts: list = field(default_factory=list)
    intent: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def analyse(graph: SymbolGraph, rulebook, changed: list, max_hops: int = 8) -> ImpactReport:
    reachable = graph.reachable_from(changed, max_hops=max_hops)

    critical, high, findings = [], [], []
    seen_surfaces = set()
    for symbol, (hops, path) in sorted(reachable.items(), key=lambda kv: kv[1][0]):
        for surface in rulebook.surfaces_for(symbol):
            if surface.id in seen_surfaces:
                continue
            seen_surfaces.add(surface.id)
            (critical if surface.severity == "critical" else high).append(surface)
            proof = path[-1] if path else None
            findings.append(Finding(
                title=f"reaches regulated surface: {surface.id}",
                detail=(
                    f"{symbol} is {hops} hop(s) downstream of the change and carries a "
                    f"regulatory obligation. {surface.obligation}"
                ),
                severity=surface.severity,
                provenance=proof.provenance if proof else rulebook.provenance(surface),
                verification=proof.verification if proof else Verification.UNVERIFIED,
                citation=surface.citation,
                needs_verification_note=surface.verify_note,
            ))

    jobs = []
    for symbol in reachable:
        consumer = rulebook.consumer_for(symbol)
        if consumer and consumer not in jobs:
            jobs.append(consumer)

    hop1 = [s for s, (h, _) in reachable.items() if h == 1 and not tests_select.is_test_symbol(s)]
    deeper = [s for s, (h, _) in reachable.items() if h > 1 and not tests_select.is_test_symbol(s)]

    selection = tests_select.select(reachable, changed)
    untested = tests_select.symbols_without_tests(changed, reachable)

    result = risk_model.score_change(
        critical_surfaces=critical,
        high_surfaces=high,
        scheduled_jobs=jobs,
        hop1_symbols=hop1,
        deeper_symbols=deeper,
        changed_symbols_without_tests=untested,
        all_surfaces_have_tests=bool(selection["test_symbols"]) and bool(critical or high),
    )

    all_edges = [e for _, path in reachable.values() for e in path]
    # An edge's sources are its primary source PLUS every source that
    # independently derived it. Reporting only the primary would hide the
    # corroboration that the verification verdict actually rests on.
    sources = sorted({e.provenance.source.value for e in all_edges}
                     | {getattr(s, "value", s) for e in all_edges for s in e.corroborated_by})
    unverified = sum(1 for e in all_edges if e.verification is not Verification.VERIFIED)
    conflicts = [
        {"caller": e.caller, "callee": e.callee, "note": e.conflict_note}
        for e in all_edges if e.verification is Verification.CONFLICT
    ]

    return ImpactReport(
        changed=sorted(changed),
        band=result.band,
        score=result.score,
        risk_terms=[asdict(t) for t in result.terms],
        findings=[asdict(f) for f in findings],
        reached=[
            {
                "symbol": s,
                "hops": h,
                "proof": path[-1].provenance.location() if path else None,
                "verification": (path[-1].verification.value if path else "unverified"),
            }
            for s, (h, path) in sorted(reachable.items(), key=lambda kv: (kv[1][0], kv[0]))
        ],
        scheduled_jobs=[asdict(j) for j in jobs],
        tests=selection,
        evidence_sources=sources,
        unverified_count=unverified,
        conflicts=conflicts,
    )
