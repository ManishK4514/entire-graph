"""The orchestrator: changed symbols in, a verifiable decision out.

Since the Noon Curveball the decision has two parts, and they are kept apart on
purpose: WHAT the analysis found (score, band, findings) and WHETHER the
analysis could see everything (completeness). A blast radius is a lower bound.
When something was unresolvable, the score derived from it is a FLOOR, and this
module says so rather than letting a small number speak for itself.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict

from blastradius.core import risk as risk_model
from blastradius.core import tests_select
from blastradius.core.evidence import (
    Completeness, Finding, Provenance, Source, Tier, Verification,
)
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
    completeness: str = Completeness.COMPLETE.value
    blind_spots: list = field(default_factory=list)
    reconciled_blind_spots: list = field(default_factory=list)
    evidence_tiers: dict = field(default_factory=dict)
    verification_path: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)



def reconcile_blind_spots(graph: SymbolGraph, spots) -> tuple:
    """Split spots into (still blind, resolved by another source).

    A call site only ONE resolver is blind to is not a blind spot -- it is the
    reason there are two resolvers. Our local `ast` resolver cannot follow
    `loan.net_disbursal()` through an untyped receiver; Entire Graph can, and
    reports it `type_inferred`. Keeping that as a blind spot would be crying
    wolf, and a blind-spot list nobody reads protects nobody.

    Three rules make the match defensible rather than merely convenient:

      same owner  the covering edge must leave the SAME enclosing symbol
      same file   its evidence must sit in the same file as the unresolved site
      other source  our own resolver cannot vouch for its own blind spot

    Matching on the attribute name alone -- which is what this did first -- would
    let any same-named method on any unrelated type silence a real hole. That is
    exactly the bare-name matching the rest of the product refuses to trust.

    Both halves are returned. A dismissal is a decision the tool made about what
    NOT to tell you, so it is recorded in the report rather than discarded: the
    reader can see which sites were silenced and by which edge.

    Note what can never be reconciled. A `receiver-method` site has a NAME, so
    another source can be checked for it. `dynamic-dispatch` and `reflection` do
    not: the target is chosen at runtime and is unbounded, so no source can have
    covered it. Absence of an edge is only informative when the thing that would
    have produced it was capable of seeing it.
    """
    kept, resolved = [], []
    for spot in spots:
        if spot.routes_anywhere or not spot.target:
            kept.append(spot)
            continue
        attr = spot.target.rpartition(".")[2]
        spot_file = os.path.basename(spot.provenance.file or "")
        covering = None
        for edge in graph.callees_of(spot.symbol):
            if edge.provenance.source == Source.LOCAL_AST:
                continue                      # cannot vouch for its own blind spot
            if edge.callee.rpartition(".")[2] != attr:
                continue
            if spot_file and os.path.basename(edge.provenance.file or "") != spot_file:
                continue
            covering = edge
            break
        if covering is None:
            kept.append(spot)
        else:
            spot.covered_by = (
                f"{covering.provenance.source.value} resolved {covering.callee} "
                f"({covering.provenance.resolution or 'unspecified'})"
            )
            resolved.append(spot)
    return kept, resolved


def scope_blind_spots(spots, reachable: dict, changed: list) -> list:
    """Which unresolved sites can actually affect THIS radius.

    The radius is a REVERSE walk: it holds everything that transitively CALLS the
    changed symbol. So for a missing edge `owner -> target`, the question is
    whether TARGET is in the radius -- if it is, OWNER should have been pulled in
    as a caller and was not.

    An earlier version of this function keyed on the OWNER being in the radius.
    That is backwards, and it is the kind of backwards that fails silently: an
    owner already in the radius cannot be added to it again, so the rule kept
    exactly the spots that could not change the answer and discarded exactly the
    ones that could. Three independent reviewers caught it before it shipped;
    `test_a_localised_spot_is_scoped_by_its_TARGET_not_its_owner` pins it now.

    `routes_anywhere` spots -- dispatch and reflection -- skip the question
    entirely. Their target is chosen at runtime and is unbounded, so the hidden
    edge can land anywhere, including inside this radius.

    The target test is a NAME match over the radius, deliberately loose. We do
    not know what the unresolved call resolves to; that is what makes it a blind
    spot. An over-approximation errs toward reporting a hole that may not exist,
    which is the safe direction for this product -- the unsafe direction is the
    one that lets an incomplete radius look complete.
    """
    in_radius = set(reachable) | set(changed)
    radius_names = {s.rpartition(".")[2] for s in in_radius}
    kept = []
    for spot in spots:
        if spot.routes_anywhere:
            kept.append(spot)
            continue
        attr = (spot.target or "").rpartition(".")[2]
        if attr and attr in radius_names:
            kept.append(spot)
    return kept


def _dedupe_spots(spots) -> list:
    """Two call sites on one line are one hole, not two."""
    seen, out = set(), []
    for s in spots:
        key = (s.kind, s.symbol, s.provenance.file, s.provenance.line, s.target)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def analyse(graph: SymbolGraph, rulebook, changed: list, max_hops: int = 8,
            blind_spots=()) -> ImpactReport:
    reachable = graph.reachable_from(changed, max_hops=max_hops)
    still_blind, reconciled = reconcile_blind_spots(
        graph, _dedupe_spots(list(blind_spots or ())))
    scoped_spots = scope_blind_spots(still_blind, reachable, changed)

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
        blind_spots=scoped_spots,
    )

    # Every reached symbol carries the FULL path back to the root, so an edge
    # near the root appears in every path that runs through it. Counting those
    # occurrences would report far more evidence items than there are edges --
    # 78 for a 24-symbol radius. Dedupe by the graph's own edge identity.
    all_edges, _seen_keys = [], set()
    for _, path in reachable.values():
        for edge in path:
            if edge.key() in _seen_keys:
                continue
            _seen_keys.add(edge.key())
            all_edges.append(edge)
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

    tiers = {t.value: 0 for t in Tier}
    for edge in all_edges:
        tiers[edge.tier().value] += 1
    for finding in findings:
        tiers[finding.tier().value] += 1
    tiers[Tier.NEEDS_VERIFICATION.value] += len(scoped_spots)

    # Read it off the risk result rather than recomputing. The same fact derived
    # in two places is the same fact until someone edits one of them.
    completeness = result.completeness

    # The "safe fallback or verification path": for every claim the tool will
    # not stand behind, the concrete next action. A caveat without an action is
    # just a disclaimer, and disclaimers are what people learn to skip.
    verification_path = [
        {"why": f"{s.kind} at {s.location()}", "do": s.verify, "tier": s.tier().value}
        for s in scoped_spots
    ]
    verification_path += [
        {"why": f"unverified regulatory claim: {f.title}",
         "do": f.needs_verification_note, "tier": f.tier().value}
        for f in findings if f.needs_verification_note
    ]
    if scoped_spots:
        verification_path.append({
            "why": "the blast radius is a lower bound while blind spots remain",
            "do": f"run the selected tests -- {selection['command']} -- and treat a pass "
                  f"as evidence about the resolved paths only",
            "tier": Tier.NEEDS_VERIFICATION.value,
        })

    return ImpactReport(
        completeness=completeness,
        blind_spots=[dict(asdict(s), tier=s.tier().value) for s in scoped_spots],
        reconciled_blind_spots=[dict(asdict(s), tier=s.tier().value) for s in reconciled],
        evidence_tiers=tiers,
        verification_path=verification_path,
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
