"""Deterministic risk scoring.

The whole trust argument rests on this file: the model never scores anything.
The graph supplies structure, the rulebook supplies regulation, and the number
is a pure function of both. Same input, same score, every run — which is why it
can sit in a merge gate.

Every term is recorded with its contribution so the report can show its work.

The Noon Curveball did NOT change the arithmetic, and that is a deliberate
choice rather than an omission. An unresolved dispatch site is not evidence of
risk -- inventing points for it would be the same sin as the inflated
DATA_FLOWS radius we rejected in Checkpoint 2, just in the other direction.
What it changes is the STANDING of the number: every term here counts something
FOUND, so anything unfound can only push the score down. A score computed over
an incomplete radius is therefore a FLOOR, and the result says so on a separate
field. Same inputs, same score, still a pure function -- now with an honest
statement of what it is a score OF.
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
    completeness: str = "complete"
    score_is_floor: bool = False

    def explain(self) -> list:
        return [(t.name, t.contribution, t.because) for t in self.terms]

    def headline(self) -> str:
        """What may be printed next to the number, never the number alone."""
        return f"{self.band} (PARTIAL ANALYSIS)" if self.score_is_floor else self.band


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
    blind_spots: list = (),
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

    # Contribution ZERO, and recorded as a term anyway. It appears in "why this
    # score" precisely because it is the one line there that explains what the
    # score cannot account for -- and a reader who scans the terms is exactly
    # the reader who must not miss it.
    if blind_spots:
        kinds = sorted({s.kind for s in blind_spots})
        terms.append(Term(
            "analysis-incomplete", 0,
            f"{len(blind_spots)} unresolved site(s) in scope ({', '.join(kinds)}) — "
            f"every term above counts something FOUND, so this score is a FLOOR",
            [f"{s.symbol} @ {s.provenance.location()}" for s in blind_spots][:8],
        ))

    raw = sum(t.contribution for t in terms)
    score = max(0, min(100, raw))
    return RiskResult(
        score=score,
        band=band_for(score),
        terms=terms,
        completeness="partial" if blind_spots else "complete",
        score_is_floor=bool(blind_spots),
    )
