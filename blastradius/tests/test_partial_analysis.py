"""Incomplete analysis must never render as a complete one.

The Noon Curveball invalidated a single assumption: that a clean parse means a
complete blast radius. These tests pin the correction from both ends -- the new
behaviour when the graph is blind, and the OLD behaviour when it is not, because
a fix that quietly changes the answer for fully resolved code is not a fix.
"""
import os

from types import SimpleNamespace

from blastradius.adapters.local_ast import LocalAstResolver
from blastradius.core.evidence import (
    BlindSpot, Completeness, Edge, Provenance, Source, Tier, Verification,
)
from blastradius.core.graph_model import SymbolGraph
from blastradius.core.impact import reconcile_blind_spots, scope_blind_spots
from blastradius.core.risk import score_change

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESOLVED = os.path.join(REPO, "fixtures", "lending-platform")
DYNAMIC = os.path.join(REPO, "fixtures", "lending-platform-dynamic")


def spots_for(root):
    resolver = LocalAstResolver(root)
    resolver.edges()
    return resolver


def spot(kind="dynamic-dispatch", symbol="m.f", target="", routes_anywhere=True):
    return BlindSpot(
        kind=kind, symbol=symbol,
        provenance=Provenance(Source.LOCAL_AST, "m.py", 3, resolution="unresolved"),
        detail="d", verify="do the thing", routes_anywhere=routes_anywhere, target=target,
    )


# ---- the fixture's premise ------------------------------------------------

def test_the_dynamic_fixture_hides_a_regulated_route_from_static_analysis():
    """The whole reason the fixture exists.

    `late_payment_charge` feeds the Key Fact Statement through a runtime registry.
    If a static CALLS walk ever DOES find that edge, this fixture has stopped
    demonstrating anything and the test says so rather than passing quietly.
    """
    resolver = spots_for(DYNAMIC)
    callers = [e.caller for e in resolver.edges()
               if e.callee.endswith("late_payment_charge")]
    assert callers == [], f"expected no static caller, got {callers}"


def test_the_three_runtime_patterns_are_each_detected():
    kinds = {s.kind for s in spots_for(DYNAMIC).blind_spots}
    assert {"dynamic-dispatch", "reflection", "missing-module"} <= kinds


def test_every_blind_spot_carries_provenance_and_an_action():
    """Invariant 1 applies to 'we could not see' exactly as it does to a finding."""
    for s in spots_for(DYNAMIC).blind_spots:
        assert s.provenance.file and s.provenance.line
        assert s.verify, f"{s.kind} at {s.location()} has no verification action"
        assert s.tier() is Tier.NEEDS_VERIFICATION


# ---- precision: a detector that cries wolf gets switched off ---------------

def test_the_fully_resolved_fixture_reports_no_unreconciled_blind_spots():
    """Existing behaviour. The two receiver-method sites here are resolved by
    Entire Graph (`type_inferred`), so reconciliation must clear them."""
    resolver = spots_for(RESOLVED)
    graph = SymbolGraph()
    for s in resolver.blind_spots:                    # what the graph saw instead
        graph.add(Edge("disclosure.kfs.generate_kfs", "core.loan.Loan.net_disbursal",
                       Provenance(Source.ENTIRE_GRAPH, "kfs.py", 33,
                                  resolution="type_inferred")))
        graph.add(Edge("pricing.interest.effective_apr", "core.loan.Loan.net_disbursal",
                       Provenance(Source.ENTIRE_GRAPH, "interest.py", 21,
                                  resolution="type_inferred")))
        break
    kept, resolved = reconcile_blind_spots(graph, resolver.blind_spots)
    assert kept == []
    assert len(resolved) == 2 and all(s.covered_by for s in resolved)


def test_container_builtins_are_not_blind_spots():
    """`rows.append(...)` names nothing first-party, so there is no edge to miss."""
    locations = {s.location() for s in spots_for(RESOLVED).blind_spots}
    assert not any("schedule.py:30" in loc for loc in locations)
    assert spots_for(RESOLVED).dropped_external > 0   # counted, not silently ignored


def test_getattr_with_a_literal_attribute_is_not_reflection(tmp_path):
    """`getattr(loan, "emi")` is statically knowable; flagging it would be noise."""
    (tmp_path / "m.py").write_text(
        "def f(loan):\n"
        "    a = getattr(loan, 'emi')\n"
        "    b = getattr(loan, field)\n"
        "    return a, b\n"
    )
    spots = spots_for(str(tmp_path)).blind_spots
    lines = [s.provenance.line for s in spots if s.kind == "reflection"]
    assert lines == [3], f"expected only the non-literal getattr, got {lines}"


def scan(tmp_path, **files):
    for name, body in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    return spots_for(str(tmp_path))


def kinds_at(resolver):
    return {(s.kind, s.provenance.line) for s in resolver.blind_spots}


def test_a_callable_held_in_a_variable_is_detected(tmp_path):
    """The commonest dynamic-dispatch shape in Python. The first version did not
    merely miss it -- it counted it under `dropped_external`, actively
    mislabelling a hole as builtin/stdlib noise."""
    r = scan(tmp_path, **{"m.py": (
        "def target(loan):\n    return loan\n\n"
        "TABLE = {'a': target}\n\n"
        "def run(loan, code, callback):\n"
        "    handler = TABLE[code]\n"
        "    handler(loan)\n"
        "    callback(loan)\n"
        "    return len(loan)\n"
    )})
    assert ("dynamic-dispatch", 8) in kinds_at(r)   # handler(loan)
    assert ("dynamic-dispatch", 9) in kinds_at(r)   # callback(loan)
    assert not any(s.provenance.line == 10 for s in r.blind_spots)  # len() is a builtin


def test_a_chained_or_super_call_on_a_first_party_name_is_detected(tmp_path):
    r = scan(tmp_path, **{"m.py": (
        "class Base:\n    def charge(self, loan):\n        return 1\n\n"
        "class Child(Base):\n"
        "    def charge(self, loan):\n"
        "        return super().charge(loan)\n"
    )})
    assert ("dynamic-dispatch", 7) in kinds_at(r)


def test_a_chained_call_on_a_stdlib_object_is_not_flagged(tmp_path):
    """`Decimal(v).quantize(...)` has no first-party edge to miss. Flagging every
    method chain would bury the holes that matter."""
    r = scan(tmp_path, **{"m.py": (
        "from decimal import Decimal\n\n"
        "def to_money(v):\n"
        "    return Decimal(v).quantize(Decimal('0.01'))\n"
    )})
    assert r.blind_spots == []


def test_all_four_ways_to_import_a_generated_module_are_covered(tmp_path):
    r = scan(tmp_path, **{
        "generated/__init__.py": "",
        "pkg/__init__.py": "",
        "a.py": "import generated.cadence\n",
        "b.py": "from generated import cadence\n",
        "c.py": "from generated.cadence import SCHEDULE\n",
    })
    files = {s.provenance.file for s in r.blind_spots if s.kind == "missing-module"}
    assert files == {"a.py", "b.py", "c.py"}, files


def test_an_existing_first_party_module_is_not_reported_missing(tmp_path):
    r = scan(tmp_path, **{
        "pkg/__init__.py": "",
        "pkg/real.py": "def f():\n    return 1\n",
        "a.py": "from pkg.real import f\nfrom pkg import real\n",
    })
    assert [s for s in r.blind_spots if s.kind == "missing-module"] == []


def test_reflection_is_detected_through_an_import_alias(tmp_path):
    """`from importlib import import_module` spells the same entry point."""
    r = scan(tmp_path, **{"m.py": (
        "from importlib import import_module\n\n"
        "def load(name):\n"
        "    return import_module(name)\n"
    )})
    assert ("reflection", 4) in kinds_at(r)


def test_a_knowable_self_call_is_not_flagged(tmp_path):
    """`self.foo()` inside a class whose `foo` we can see is statically knowable."""
    r = scan(tmp_path, **{"m.py": (
        "class Loan:\n"
        "    def emi(self):\n        return 1\n"
        "    def total(self):\n        return self.emi() * 12\n"
    )})
    assert r.blind_spots == []


def test_vars_is_not_reflection(tmp_path):
    """`vars(obj)` returns __dict__ and dispatches to nothing."""
    r = scan(tmp_path, **{"m.py": "def f(o):\n    return vars(o)\n"})
    assert [s for s in r.blind_spots if s.kind == "reflection"] == []


# ---- reconciliation: one-eyed is not blind --------------------------------

def test_a_site_the_graph_resolved_is_not_a_blind_spot():
    graph = SymbolGraph()
    graph.add(Edge("m.f", "core.loan.Loan.emi",
                   Provenance(Source.ENTIRE_GRAPH, "m.py", 3, resolution="type_inferred")))
    kept, resolved = reconcile_blind_spots(
        graph, [spot(kind="receiver-method", symbol="m.f",
                     target="loan.emi", routes_anywhere=False)])
    assert kept == []
    assert "entire-graph resolved core.loan.Loan.emi" in resolved[0].covered_by


def test_reconciliation_requires_the_same_file_not_just_the_same_name():
    """Matching on the attribute name alone would let any same-named method on
    any unrelated type silence a real hole — the bare-name matching this product
    refuses to trust everywhere else."""
    graph = SymbolGraph()
    graph.add(Edge("m.f", "somewhere.else.Other.emi",
                   Provenance(Source.ENTIRE_GRAPH, "other.py", 3, resolution="exact")))
    kept, resolved = reconcile_blind_spots(
        graph, [spot(kind="receiver-method", symbol="m.f",
                     target="loan.emi", routes_anywhere=False)])
    assert len(kept) == 1 and resolved == []


def test_a_dismissed_blind_spot_is_recorded_not_discarded():
    """A decision about what NOT to tell you is still a decision."""
    graph = SymbolGraph()
    graph.add(Edge("m.f", "core.loan.Loan.emi",
                   Provenance(Source.ENTIRE_GRAPH, "m.py", 3, resolution="type_inferred")))
    _, resolved = reconcile_blind_spots(
        graph, [spot(kind="receiver-method", symbol="m.f",
                     target="loan.emi", routes_anywhere=False)])
    assert resolved and resolved[0].covered_by


def test_our_own_source_cannot_reconcile_its_own_blind_spot():
    """Self-corroboration is not verification, and it is not sight either."""
    graph = SymbolGraph()
    graph.add(Edge("m.f", "core.loan.Loan.emi",
                   Provenance(Source.LOCAL_AST, "m.py", 3, resolution="ast_import_resolved")))
    kept, resolved = reconcile_blind_spots(
        graph, [spot(kind="receiver-method", symbol="m.f",
                     target="loan.emi", routes_anywhere=False)])
    assert len(kept) == 1 and resolved == []


def test_runtime_dispatch_can_never_be_reconciled_away():
    """No source can have 'seen' an unbounded target, so no edge clears it."""
    graph = SymbolGraph()
    graph.add(Edge("m.f", "anything", Provenance(Source.ENTIRE_GRAPH, "m.py", 3)))
    kept, _ = reconcile_blind_spots(graph, [spot(routes_anywhere=True)])
    assert len(kept) == 1


# ---- scoping: a caveat not scoped to the answer is unactionable -----------

def test_a_localised_spot_is_scoped_by_its_TARGET_not_its_owner():
    """REGRESSION. The radius is a REVERSE walk — it holds transitive CALLERS of
    the changed symbol. For a missing edge owner->target, the spot matters when
    TARGET is in the radius (the owner should have been pulled in and was not).

    The first version of scope_blind_spots keyed on the OWNER instead. That kept
    exactly the spots that could not change the answer and dropped exactly the
    ones that could — a silent under-report, which is the one failure this
    product cannot have. Caught in review before it shipped.
    """
    radius = {"pricing.fees.penal_charge": (1, [])}

    # owner in the radius, target NOT: the missing edge cannot enlarge the radius
    owner_only = scope_blind_spots(
        [spot(kind="receiver-method", symbol="pricing.fees.penal_charge",
              target="cfg.unrelated_thing", routes_anywhere=False)],
        reachable=radius, changed=["the.change"])
    assert owner_only == []

    # target in the radius, owner NOT: the missing edge WOULD have enlarged it
    target_in = scope_blind_spots(
        [spot(kind="receiver-method", symbol="somewhere.far.away",
              target="obj.penal_charge", routes_anywhere=False)],
        reachable=radius, changed=["the.change"])
    assert len(target_in) == 1, "the spot that could change the answer was dropped"


def test_a_localised_spot_touching_nothing_in_the_radius_is_out_of_scope():
    kept = scope_blind_spots(
        [spot(kind="receiver-method", symbol="far.away",
              target="obj.nothing_like_this", routes_anywhere=False)],
        reachable={"in.radius": (1, [])}, changed=["the.change"])
    assert kept == []


def test_duplicate_sites_on_one_line_collapse_into_one_hole():
    from blastradius.core.impact import _dedupe_spots
    assert len(_dedupe_spots([spot(), spot()])) == 1


def test_a_dispatch_spot_is_always_in_scope_wherever_it_lives():
    kept = scope_blind_spots(
        [spot(symbol="far.away", routes_anywhere=True)],
        reachable={"in.radius": (1, [])}, changed=["the.change"])
    assert len(kept) == 1


# ---- the score stays a pure function --------------------------------------

def base(**kw):
    args = dict(critical_surfaces=[], high_surfaces=[], scheduled_jobs=[],
                hop1_symbols=[], deeper_symbols=[],
                changed_symbols_without_tests=[], all_surfaces_have_tests=False)
    args.update(kw)
    return score_change(**args)


def test_blind_spots_do_not_change_the_number():
    """Invariant 2. An unresolved site is not evidence of risk, and inventing
    points for it would be the inflated-radius mistake in the other direction."""
    surfaces = [SimpleNamespace(id="kfs-generator", severity="critical")]
    without = base(critical_surfaces=surfaces)
    with_spots = base(critical_surfaces=surfaces, blind_spots=[spot(), spot()])
    assert with_spots.score == without.score
    assert with_spots.band == without.band


def test_blind_spots_make_the_score_a_floor_and_say_so_in_the_terms():
    result = base(blind_spots=[spot()])
    assert result.score_is_floor is True
    assert result.completeness == Completeness.PARTIAL.value
    assert result.headline().endswith("(PARTIAL ANALYSIS)")
    term = next(t for t in result.terms if t.name == "analysis-incomplete")
    assert term.contribution == 0 and "FLOOR" in term.because


def test_a_complete_analysis_is_unchanged_in_every_field():
    result = base(hop1_symbols=["a"])
    assert result.score_is_floor is False
    assert result.completeness == Completeness.COMPLETE.value
    assert result.headline() == result.band
    assert [t.name for t in result.terms] == ["direct-callers"]


# ---- the three tiers a reader must be able to tell apart ------------------

def test_a_corroborated_structural_edge_is_confirmed():
    """Built the way SymbolGraph.add builds it: a second source, and the
    resolution that second source used."""
    g = SymbolGraph()
    g.add(Edge("a", "b", Provenance(Source.ENTIRE_GRAPH, "a.py", 1, resolution="exact")))
    g.add(Edge("a", "b", Provenance(Source.LOCAL_AST, "a.py", 1,
                                    resolution="ast_import_resolved")))
    assert g.edges[0].verification is Verification.VERIFIED
    assert g.edges[0].tier() is Tier.CONFIRMED


def test_a_structural_edge_corroborated_only_by_a_name_guess_is_not_confirmed():
    """One good derivation plus one guess is not two independent confirmations.
    The corroborator's OWN resolution has to be checked, or 'two name-guessers
    agreeing is two guesses' is a claim the code does not actually enforce."""
    g = SymbolGraph()
    g.add(Edge("a", "b", Provenance(Source.ENTIRE_GRAPH, "a.py", 1, resolution="exact")))
    g.add(Edge("a", "b", Provenance(Source.LOCAL_AST, "a.py", 1,
                                    resolution="ast_name_only")))
    assert g.edges[0].verification is Verification.VERIFIED   # two sources, yes
    assert g.edges[0].tier() is Tier.HEURISTIC                # two derivations, no


def test_an_unrecognised_resolution_fails_closed_to_heuristic():
    """The one function whose job is conservatism must not default to optimism.
    A provider that adds a new resolution string tomorrow must not silently
    start producing CONFIRMED claims."""
    g = SymbolGraph()
    g.add(Edge("a", "b", Provenance(Source.ENTIRE_GRAPH, "a.py", 1,
                                    resolution="some_future_resolution")))
    g.add(Edge("a", "b", Provenance(Source.LOCAL_AST, "a.py", 1,
                                    resolution="ast_import_resolved")))
    assert g.edges[0].tier() is Tier.HEURISTIC


def test_a_single_sourced_edge_is_heuristic():
    e = Edge("a", "b", Provenance(Source.ENTIRE_GRAPH, "a.py", 1, resolution="exact"))
    assert e.tier() is Tier.HEURISTIC


def test_a_blind_spots_standing_survives_serialisation():
    """Invariant 1: every claim carries {source, file, line, confidence,
    resolution, verified}. A blind spot is a claim."""
    from dataclasses import asdict
    s = spot()
    d = dict(asdict(s), tier=s.tier().value)
    assert d["provenance"]["source"] and d["provenance"]["file"] and d["provenance"]["line"]
    assert d["tier"] == "needs-verification"
    assert "verification" in d


def test_a_name_only_edge_stays_heuristic_even_when_corroborated():
    """Both our sources have a bare-name fallback, so two name-guessers agreeing
    is two guesses. The provider says `name_only` (0.68); we believe it."""
    g = SymbolGraph()
    g.add(Edge("a", "b", Provenance(Source.ENTIRE_GRAPH, "a.py", 1,
                                    resolution="name_only")))
    g.add(Edge("a", "b", Provenance(Source.LOCAL_AST, "a.py", 1,
                                    resolution="ast_import_resolved")))
    assert g.edges[0].tier() is Tier.HEURISTIC


def test_a_conflict_needs_verification():
    e = Edge("a", "b", Provenance(Source.ENTIRE_GRAPH, "a.py", 1, resolution="exact"),
             verification=Verification.CONFLICT)
    assert e.tier() is Tier.NEEDS_VERIFICATION


# ---- end to end: what the report and the gate actually do -----------------

def test_the_report_separates_completeness_from_the_score():
    from blastradius.adapters.rules import RuleBook
    from blastradius.core.impact import analyse

    graph = SymbolGraph()
    graph.add(Edge("disclosure.kfs.generate_kfs", "pricing.fees.penal_charge",
                   Provenance(Source.ENTIRE_GRAPH, "kfs.py", 10, resolution="exact"),
                   verification=Verification.VERIFIED))
    report = analyse(graph, RuleBook.load(), ["pricing.fees.penal_charge"],
                     blind_spots=[spot()]).to_dict()

    assert report["completeness"] == "partial"
    assert report["score"] > 0                      # the score still says what it found
    assert len(report["blind_spots"]) == 1
    assert report["evidence_tiers"]["needs-verification"] >= 1
    assert any("do the thing" == step["do"] for step in report["verification_path"])


def test_a_resolved_analysis_reports_complete_and_carries_no_blind_spots():
    from blastradius.adapters.rules import RuleBook
    from blastradius.core.impact import analyse

    graph = SymbolGraph()
    graph.add(Edge("disclosure.kfs.generate_kfs", "pricing.fees.penal_charge",
                   Provenance(Source.ENTIRE_GRAPH, "kfs.py", 10, resolution="exact"),
                   verification=Verification.VERIFIED))
    report = analyse(graph, RuleBook.load(), ["pricing.fees.penal_charge"]).to_dict()

    assert report["completeness"] == "complete"
    assert report["blind_spots"] == []
    assert report["verification_path"] == [] or all(
        s["why"].startswith("unverified regulatory claim")
        for s in report["verification_path"])


def test_the_gate_does_not_pass_an_analysis_that_could_not_see(capsys):
    """LOW over an incomplete radius is an UNKNOWN, not a pass. Exit 2 says so."""
    from blastradius.cli import main
    argv = ["impact", "--symbol", "pricing.fees.late_payment_charge",
            "--source-root", "fixtures/lending-platform-dynamic",
            "--offline", "--fail-on-critical", "--json"]
    assert main(argv) == 2
    assert main(argv + ["--allow-partial"]) == 0


def test_an_analysis_missing_an_entire_source_is_never_reported_complete(capsys):
    """`--offline` used to print `completeness: complete` three lines above
    `single_sourced: true` — two fields telling opposite stories, reassuring one
    first. An absent evidence source is a blind spot like any other."""
    import json as _json
    from blastradius.cli import main
    main(["impact", "--symbol", "pricing.fees.penal_charge", "--offline", "--json"])
    report = _json.loads(capsys.readouterr().out)
    assert report["completeness"] == "partial"
    assert report["provenance"]["single_sourced"] is True
    kinds = [s["kind"] for s in report["blind_spots"]]
    assert "provider-unavailable" in kinds
    assert any("--offline" in s["verify"] or "provider" in s["verify"]
               for s in report["blind_spots"])


def test_an_incomplete_analysis_never_confirms_a_stated_intent(capsys):
    """The worst failure this product could have: agreeing with the developer
    because it failed to look."""
    import json as _json
    from blastradius.cli import main
    main(["impact", "--symbol", "pricing.fees.late_payment_charge",
          "--source-root", "fixtures/lending-platform-dynamic", "--offline", "--json",
          "--intent", "nothing downstream"])
    report = _json.loads(capsys.readouterr().out)
    assert report["intent"]["mismatch"] == ""          # nothing was found...
    assert "CANNOT be confirmed" in report["intent"]["cannot_confirm"]   # ...and we say so


# ---- a refusal is not an empty answer -------------------------------------

def test_an_ambiguous_symbol_raises_instead_of_reporting_no_callers(monkeypatch):
    """Found by adding the second fixture, which made `penal_charge` ambiguous.

    The provider answered `disambiguation_required` with `callers.entries: null`
    and the adapter read it as "nothing depends on this". Same bug class as the
    curveball itself: a non-answer treated as an answer of zero.
    """
    from blastradius.adapters import entire_graph as eg

    adapter = eg.EntireGraphAdapter.__new__(eg.EntireGraphAdapter)
    adapter.source_root = "fixtures/lending-platform"
    monkeypatch.setattr(adapter, "impact", lambda *a, **k: {
        "disambiguation_required": True,
        "definitions": [
            {"file_path": "fixtures/lending-platform/pricing/fees.py"},
            {"file_path": "fixtures/other/pricing/fees.py"},
            {"file_path": "fixtures/third/pricing/fees.py"},
        ],
        "callers": {"total": 0, "entries": None},
    }, raising=False)
    # Two candidates outside the root, one inside -> narrows cleanly is tested
    # below; here the root itself is ambiguous, so it must refuse.
    adapter.source_root = "fixtures"
    try:
        adapter.impact_callers("penal_charge")
    except eg.EntireGraphAmbiguousSymbol as exc:
        assert "NOT an empty result" in str(exc)
    else:
        raise AssertionError("silently returned a result for an ambiguous symbol")


def test_an_ambiguous_symbol_is_narrowed_by_source_root(monkeypatch):
    from blastradius.adapters import entire_graph as eg

    adapter = eg.EntireGraphAdapter.__new__(eg.EntireGraphAdapter)
    adapter.source_root = "fixtures/lending-platform"
    calls = []

    def fake_impact(symbol, depth=2, limit=50, file=None):
        calls.append(file)
        if file is None:
            return {
                "disambiguation_required": True,
                "definitions": [
                    {"file_path": "fixtures/lending-platform/pricing/fees.py"},
                    {"file_path": "fixtures/lending-platform-dynamic/pricing/fees.py"},
                ],
                "callers": {"total": 0, "entries": None},
            }
        return {"callers": {"total": 1, "entries": [
            {"endpoint": {"file_path": "fixtures/lending-platform/disclosure/kfs.py",
                          "qualified_name": "generate_kfs"}, "depth": 1}]}}

    monkeypatch.setattr(adapter, "impact", fake_impact, raising=False)
    result = adapter.impact_callers("penal_charge")
    assert calls == [None, "fixtures/lending-platform/pricing/fees.py"]
    assert result == {"disclosure.kfs.generate_kfs": 1}


def test_impact_callers_never_leaks_a_symbol_from_outside_the_source_root(monkeypatch):
    """The second opinion must not corroborate against the wrong function.

    `impact` is keyed by symbol NAME, so wherever two directories define the same
    name it can return callers belonging to the other one. Source-root scoping in
    `_module_of` is what keeps those out, and a corroboration drawn from the wrong
    function would be worse than no corroboration at all -- so it gets a test of
    its own rather than relying on the two fixtures happening not to collide.
    """
    from blastradius.adapters import entire_graph as eg

    adapter = eg.EntireGraphAdapter.__new__(eg.EntireGraphAdapter)
    adapter.source_root = "fixtures/lending-platform-dynamic"
    monkeypatch.setattr(adapter, "impact", lambda *a, **k: {"callers": {"entries": [
        {"endpoint": {"file_path": "fixtures/lending-platform/pricing/schedule.py",
                      "qualified_name": "overdue_projection"}, "depth": 1},
        {"endpoint": {"file_path": "fixtures/lending-platform/recovery/dunning.py",
                      "qualified_name": "compute_overdue"}, "depth": 1},
    ]}}, raising=False)
    assert adapter.impact_callers("penal_charge") == {}
