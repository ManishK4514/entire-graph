"""The product must never claim verification it does not have."""
from blastradius.core.evidence import Edge, Provenance, Source, Verification
from blastradius.core.graph_model import SymbolGraph


def edge(caller, callee, source, line=1):
    return Edge(caller, callee, Provenance(source, "a.py", line))


def test_a_single_source_edge_stays_unverified():
    g = SymbolGraph()
    g.add(edge("a", "b", Source.LOCAL_AST))
    assert g.edges[0].verification is Verification.UNVERIFIED


def test_the_same_source_twice_is_not_verification():
    """Two call sites found by one parser prove nothing about that parser."""
    g = SymbolGraph()
    g.add(edge("a", "b", Source.LOCAL_AST, line=1))
    g.add(edge("a", "b", Source.LOCAL_AST, line=9))
    assert g.edges[0].verification is Verification.UNVERIFIED
    assert len(g.edges) == 1


def test_two_independent_sources_verify_an_edge():
    g = SymbolGraph()
    g.add(edge("a", "b", Source.LOCAL_AST))
    g.add(edge("a", "b", Source.ENTIRE_GRAPH))
    assert g.edges[0].verification is Verification.VERIFIED
    assert Source.ENTIRE_GRAPH in g.edges[0].corroborated_by


def test_traversal_returns_the_proof_path():
    g = SymbolGraph()
    g.add(edge("mid", "leaf", Source.LOCAL_AST))
    g.add(edge("top", "mid", Source.LOCAL_AST))
    reach = g.reachable_from(["leaf"])
    assert reach["top"][0] == 2
    assert [e.caller for e in reach["top"][1]] == ["mid", "top"]
