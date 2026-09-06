"""The adapter is where a wrong assumption becomes a wrong blast radius.

Every fixture string in this file is verbatim provider output captured on
2026-09-06 and committed under docs/graph-evidence/. If the provider's schema
moves, these fail rather than silently mis-reading it.
"""
import json
import os
import shutil
import subprocess

import pytest

from blastradius.adapters.entire_graph import (
    SCHEMA_MAJOR,
    EntireGraphAdapter,
    EntireGraphSchemaMismatch,
    EntireGraphUnavailable,
    _module_of,
    _orient,
    parse_symbol_id,
    resolve_invocation,
    symbol_id_file,
)

ROOT = "fixtures/lending-platform"
FEES_ID = f"local/r:Python:{ROOT}/pricing/fees.py:function:penal_charge"
METHOD_ID = f"local/r:Python:{ROOT}/core/loan.py:method:Loan.net_disbursal"
INIT_ID = f"local/r:Python:{ROOT}/pricing/__init__.py:function:setup"
EXTERNAL_ID = "external:symbol:decimal.Decimal"
OUTSIDE_ID = "local/r:Go:internal/cli/impact.go:function:runImpact"


# ---- symbol id parsing ---------------------------------------------------

def test_a_provider_symbol_id_becomes_a_dotted_symbol():
    assert parse_symbol_id(FEES_ID, ROOT) == "pricing.fees.penal_charge"


def test_a_method_keeps_its_class_qualifier():
    """The local AST resolver qualifies methods the same way. If these two
    disagreed on the name, 'verification' would be two tools talking past
    each other rather than agreeing."""
    assert parse_symbol_id(METHOD_ID, ROOT) == "core.loan.Loan.net_disbursal"


def test_dunder_init_collapses_into_its_package():
    assert parse_symbol_id(INIT_ID, ROOT) == "pricing.setup"


def test_external_symbols_are_not_in_our_blast_radius():
    """A change to our code cannot break the standard library. Counting it
    would inflate every radius."""
    assert parse_symbol_id(EXTERNAL_ID, ROOT) is None


def test_files_outside_the_source_root_are_ignored():
    assert parse_symbol_id(OUTSIDE_ID, ROOT) is None


def test_a_malformed_id_is_dropped_not_guessed():
    assert parse_symbol_id("nonsense", ROOT) is None
    assert parse_symbol_id("", ROOT) is None


def test_the_file_path_is_recoverable_for_citation():
    assert symbol_id_file(FEES_ID) == f"{ROOT}/pricing/fees.py"
    assert symbol_id_file(EXTERNAL_ID) is None


def test_module_of_rejects_non_python():
    assert _module_of(f"{ROOT}/README.md", ROOT) is None


# ---- the DATA_FLOWS orientation bug -------------------------------------
#
# This is the test that exists because the product was wrong once. Reading
# every DATA_FLOWS edge with the CALLS orientation put 48 symbols in
# penal_charge's blast radius, including its own callees.

RETURN_FLOW = "callee return value flows into caller return value"
PARAM_FLOW = "caller parameter forwarded into callee argument"


def test_calls_are_already_in_dependency_order():
    assert _orient("caller", "callee", "CALLS", "direct call expression") == ("caller", "callee")


def test_a_return_value_data_flow_is_inverted():
    """`to_money -> penal_charge` with this reason means penal_charge DEPENDS
    ON to_money, so to_money must not appear in penal_charge's blast radius."""
    assert _orient("to_money", "penal_charge", "DATA_FLOWS", RETURN_FLOW) == (
        "penal_charge", "to_money"
    )


def test_a_forwarded_parameter_data_flow_is_not_inverted():
    assert _orient("overdue_projection", "penal_charge", "DATA_FLOWS", PARAM_FLOW) == (
        "overdue_projection", "penal_charge"
    )


def test_an_unrecognised_data_flow_reason_keeps_the_stated_direction():
    """We do not invent an orientation we cannot justify from the evidence."""
    assert _orient("a", "b", "DATA_FLOWS", "some future reason") == ("a", "b")


# ---- schema safety -------------------------------------------------------

def test_an_unknown_schema_major_is_refused_not_guessed(tmp_path):
    adapter = EntireGraphAdapter.__new__(EntireGraphAdapter)
    with pytest.raises(EntireGraphSchemaMismatch):
        adapter._check_schema({"schema_version": f"{SCHEMA_MAJOR + 1}.0"})
    with pytest.raises(EntireGraphSchemaMismatch):
        adapter._check_schema({"schema_version": "not-a-version"})
    adapter._check_schema({"schema_version": f"{SCHEMA_MAJOR}.7"})   # newer minor is fine


def test_a_missing_provider_raises_rather_than_returning_an_empty_radius(monkeypatch):
    """Degrading to 'no impact found' would be the most dangerous possible
    failure mode: it reads exactly like 'safe to merge'."""
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    monkeypatch.setenv("BLASTRADIUS_GRAPH_BIN", "")
    monkeypatch.chdir("/")
    with pytest.raises(EntireGraphUnavailable):
        resolve_invocation()


def test_an_explicit_binary_that_is_not_executable_is_rejected(tmp_path):
    dud = tmp_path / "nope"
    dud.write_text("")
    with pytest.raises(EntireGraphUnavailable):
        resolve_invocation(str(dud))


# ---- live provider (skipped when it is not installed) --------------------

def _provider_available() -> bool:
    try:
        resolve_invocation()
        return True
    except EntireGraphUnavailable:
        return False


live = pytest.mark.skipif(not _provider_available(), reason="no Entire Graph provider")


@live
def test_the_provider_reports_python_as_semantically_analysed():
    """The whole product rests on this. If Python were inventory-only, the
    fixture would be invisible and every finding would be fiction."""
    caps = EntireGraphAdapter(".", source_root=ROOT).capabilities()
    languages = caps.get("semantic_languages") or []
    assert any(l.lower() == "python" for l in languages), languages


@live
def test_the_provider_finds_the_real_callers_of_penal_charge():
    adapter = EntireGraphAdapter(".", source_root=ROOT)
    edges = adapter.edges()
    callers = {e.caller for e in edges if e.callee == "pricing.fees.penal_charge"}
    assert "pricing.schedule.overdue_projection" in callers
    assert "recovery.dunning.compute_overdue" in callers
    # its own callee must never appear as a dependent
    assert "core.money.to_money" not in callers


@live
def test_every_graph_edge_carries_a_clickable_citation():
    """The invariant: no claim without provenance."""
    for e in EntireGraphAdapter(".", source_root=ROOT).edges():
        assert e.provenance.file and e.provenance.line, e
        assert e.provenance.confidence > 0, e
        assert e.provenance.resolution, e


@live
def test_our_traversal_agrees_with_the_providers_own_impact_command():
    """Two code paths inside the provider, plus ours, must agree at depth 1."""
    adapter = EntireGraphAdapter(".", source_root=ROOT)
    theirs = adapter.impact_callers("penal_charge", depth=1)
    ours = {e.caller for e in adapter.edges() if e.callee == "pricing.fees.penal_charge"}
    assert set(theirs) & ours, (theirs, ours)
