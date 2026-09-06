"""blast — impact-aware change review for regulated lending code.

    blast impact --symbol pricing.fees.penal_charge
    blast impact --base HEAD~1                 # changed symbols from a real diff
    blast impact --base HEAD~1 --fail-on-critical --json   # merge gate

Git tells you what changed. Blast Radius tells you what breaks.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from blastradius.adapters.entire_graph import IMPACT_RELATIONS
from blastradius.adapters.local_ast import LocalAstResolver
from blastradius.adapters.rules import RuleBook
from blastradius.core.graph_model import SymbolGraph
from blastradius.core.impact import analyse
from blastradius.render import cli_report

DEFAULT_SOURCE_ROOT = "fixtures/lending-platform"


def build_graph(repo: str, source_root: str, use_graph: bool = True,
                graph_bin: str = None, relations: tuple = None) -> tuple:
    """Assemble the symbol graph from two independent derivations.

    Entire Graph is the PRIMARY evidence source: it is a tree-sitter parse with
    real import resolution, and it reports a per-relation confidence and the
    call site that proves each edge. The local AST resolver runs as a SECOND,
    independent derivation of the same relationships.

      both derive the edge  -> VERIFIED
      only one derives it   -> UNVERIFIED (rendered greyed, never asserted)

    Two derivations is the verification story. It is not a fallback dressed up
    as one: when the provider is missing, the report says on its face that its
    findings are single-sourced, because a partial blast radius presented as a
    complete one is the one failure this product cannot have.
    """
    graph = SymbolGraph()
    notes, run = [], None
    src_abs = os.path.join(os.path.abspath(repo), source_root) if source_root else os.path.abspath(repo)

    if use_graph:
        try:
            from blastradius.adapters.entire_graph import EntireGraphAdapter
            adapter = EntireGraphAdapter(repo, source_root=source_root, binary=graph_bin)
            for edge in adapter.edges(relations or IMPACT_RELATIONS):
                graph.add(edge)
            run = adapter.last_run
            counts = ", ".join(f"{k}={v}" for k, v in sorted(run.relation_counts.items())
                               if k in ("CALLS", "DATA_FLOWS"))
            notes.append(f"entire-graph: ok — {run.cite()}, {counts}")
            for warning in run.warnings:
                notes.append(f"entire-graph warning: {warning.get('code', '?')}")
        except Exception as exc:                      # noqa: BLE001 - degrade loudly, never crash
            notes.append(f"entire-graph UNAVAILABLE ({exc}) — findings are SINGLE-SOURCED "
                         f"and must not be treated as a complete blast radius")

    resolver = LocalAstResolver(src_abs)
    resolver.collect_definitions()
    local = resolver.edges()
    for edge in local:
        graph.add(edge)
    notes.append(f"local-ast: ok — {len(local)} call edges independently derived")
    return graph, notes, run


def resolve_changed(args, repo: str, source_root: str) -> tuple:
    """The symbols under review, either named explicitly or read off a real diff."""
    if args.symbol:
        return list(args.symbol), []
    from blastradius.adapters.entire_graph import EntireGraphAdapter
    adapter = EntireGraphAdapter(repo, source_root=source_root, binary=args.graph_bin)
    records = adapter.changed_symbols(args.base, args.head)
    if not records:
        raise SystemExit(
            f"semantic diff {args.base}..{args.head} changed no symbol under {source_root!r}"
        )
    return [r["symbol"] for r in records], records


def cmd_impact(args) -> int:
    repo = os.path.abspath(args.repo)
    source_root = args.source_root

    changed, diff_records = resolve_changed(args, repo, source_root)
    relations = IMPACT_RELATIONS + (("DATA_FLOWS",) if args.include_data_flows else ())
    graph, notes, run = build_graph(repo, source_root, use_graph=not args.offline,
                                    graph_bin=args.graph_bin, relations=relations)
    rulebook = RuleBook.load(args.rules)
    report = analyse(graph, rulebook, changed, max_hops=args.max_hops).to_dict()

    report["provenance"] = {
        "repo": repo,
        "source_root": source_root,
        "graph_provider": run.cite() if run else None,
        "graph_commit": run.commit if run else None,
        "graph_argv": " ".join(run.argv) if run else None,
        "graph_relation_counts": run.relation_counts if run else {},
        "graph_partial_failures_total": len(run.partial_failures) if run else 0,
        "graph_partial_failures_in_scope": run.failures_in(source_root) if run else [],
        "graph_completeness_note": run.scope_note(source_root) if run else
            "Entire Graph did not run; this radius is derived from one source only",
        "graph_files_parsed": (run.stats or {}).get("parsed_files") if run else None,
        "graph_files_total": (run.stats or {}).get("files") if run else None,
        "single_sourced": run is None,
        "notes": notes,
    }
    if diff_records:
        report["semantic_diff"] = {
            "base": args.base, "head": args.head, "changes": diff_records,
        }

    if args.intent:
        surfaces = [f["title"] for f in report["findings"]]
        report["intent"] = {
            "stated": args.intent,
            "mismatch": (
                f"change reaches {len(surfaces)} regulated surface(s) and "
                f"{len(report['scheduled_jobs'])} scheduled job(s) beyond that scope"
                if surfaces or report["scheduled_jobs"] else ""
            ),
        }

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(cli_report.render(report))

    return 1 if args.fail_on_critical and report["band"] in ("CRITICAL", "HIGH") else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="blast", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("impact", help="analyse the blast radius of a change")
    p.add_argument("--repo", default=".", help="git repository root (default: .)")
    p.add_argument("--source-root", default=DEFAULT_SOURCE_ROOT,
                   help=f"subtree to analyse (default: {DEFAULT_SOURCE_ROOT})")
    p.add_argument("--symbol", action="append",
                   help="changed symbol, e.g. pricing.fees.penal_charge (repeatable)")
    p.add_argument("--base", help="derive changed symbols from a semantic diff against this ref")
    p.add_argument("--head", default="HEAD", help="head ref for --base (default: HEAD)")
    p.add_argument("--rules", default=None, help="path to the rules file")
    p.add_argument("--max-hops", type=int, default=8)
    p.add_argument("--graph-bin", default=None, help="explicit Entire Graph provider binary")
    p.add_argument("--json", action="store_true", help="machine-readable report")
    p.add_argument("--include-data-flows", action="store_true",
                   help="also walk DATA_FLOWS edges (orientation-normalised; widens the radius)")
    p.add_argument("--offline", action="store_true",
                   help="skip Entire Graph; findings become single-sourced")
    p.add_argument("--intent", default=None,
                   help="stated intent to check the actual blast radius against")
    p.add_argument("--fail-on-critical", action="store_true",
                   help="exit non-zero on HIGH or CRITICAL (for CI)")
    p.set_defaults(func=cmd_impact)

    args = parser.parse_args(argv)
    if args.command == "impact" and not args.symbol and not args.base:
        parser.error("give --symbol or --base")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
