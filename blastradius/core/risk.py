"""Deterministic risk scoring.

The whole trust argument rests on this file: the model never scores anything.
The graph supplies structure, the rulebook supplies regulation, and the number
is a pure function of both. Same input, same score, every run — which is why it
can sit in a merge gate.

Every term is recorded with its contribution so the report can show its work.
"""
from __future__ import annotations

from dataclasses import dataclass, field

BANDS = [(75, "CRITICAL"), (50, "HIGH"), (20, "MEDIUM"), (0, "LOW")]

W_CRITICAL_SURFACE = 40
W_HIGH_SURFACE = 20
W_SCHEDULED_JOB = 12
W_HOP1_SYMBOL = 3
W_DEEP_SYMBOL = 1
W_NO_TEST_ON_CHANGE = 15
W_ALL_COVERED = -10


@dataclass
class Term:
    name: str
    contribution: int
    because: str
    evidence: list = field(default_factory=list)


@dataclass
class RiskResult:
    score: int
    band: str
    terms: list = field(default_factory=list)

    def explain(self) -> list:
        return [(t.name, t.contribution, t.because) for t in self.terms]


def band_for(score: int) -> str:
    for threshold, name in BANDS:
        if score >= threshold:
            return name
    return "LOW"


def score_change(
    *,
    critical_surfaces: list,
    high_surfaces: list,
    scheduled_jobs: list,
    hop1_symbols: list,
    deeper_symbols: list,
    changed_symbols_without_tests: list,
    all_surfaces_have_tests: bool,
) -> RiskResult:
    terms = []

    if critical_surfaces:
        terms.append(Term(
            "regulated-surface-critical", W_CRITICAL_SURFACE,
            f"reaches {len(critical_surfaces)} critical regulated surface(s)",
            [s.id for s in critical_surfaces],
        ))
    if high_surfaces:
        terms.append(Term(
            "regulated-surface-high", W_HIGH_SURFACE,
            f"reaches {len(high_surfaces)} high-severity regulated surface(s)",
            [s.id for s in high_surfaces],
        ))
    if scheduled_jobs:
        terms.append(Term(
            "scheduled-consumers", W_SCHEDULED_JOB * len(scheduled_jobs),
            f"{len(scheduled_jobs)} scheduled job(s) ship this change unattended",
            [j.name for j in scheduled_jobs],
        ))
    if hop1_symbols:
        terms.append(Term(
            "direct-callers", W_HOP1_SYMBOL * len(hop1_symbols),
            f"{len(hop1_symbols)} direct caller(s)", list(hop1_symbols)[:8],
        ))
    if deeper_symbols:
        terms.append(Term(
            "transitive-callers", W_DEEP_SYMBOL * len(deeper_symbols),
            f"{len(deeper_symbols)} transitive caller(s)", list(deeper_symbols)[:8],
        ))
    if changed_symbols_without_tests:
        terms.append(Term(
            "untested-change", W_NO_TEST_ON_CHANGE,
            f"{len(changed_symbols_without_tests)} changed symbol(s) have no direct test",
            list(changed_symbols_without_tests),
        ))
    if all_surfaces_have_tests and (critical_surfaces or high_surfaces):
        terms.append(Term(
            "surfaces-covered", W_ALL_COVERED,
            "every reached regulated surface has test coverage", [],
        ))

    raw = sum(t.contribution for t in terms)
    score = max(0, min(100, raw))
    return RiskResult(score=score, band=band_for(score), terms=terms)
