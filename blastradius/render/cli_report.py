"""Terminal renderer. A view over the report object, never a second source."""
from __future__ import annotations

import os
import sys

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


BAND_STYLE = {
    "LOW": ("42;30", "green"),
    "MEDIUM": ("43;30", "yellow"),
    "HIGH": ("45;30", "magenta"),
    "CRITICAL": ("41;97", "red"),
}
DIM, BOLD = "2", "1"


def render(report: dict) -> str:
    out = []
    band = report["band"]
    style = BAND_STYLE.get(band, ("47;30", "white"))[0]

    out.append("")
    out.append(_c(f"  BLAST RADIUS: {band}  ", style) + _c(f"  score {report['score']}/100", BOLD))
    out.append("")
    out.append(_c("changed", BOLD))
    diff = {c["symbol"]: c for c in report.get("semantic_diff", {}).get("changes", [])}
    for symbol in report["changed"]:
        record = diff.get(symbol)
        if record:
            out.append(f"  {symbol}  {_c(record['change_type'] + ' ' + record['kind'], DIM)}")
            out.append(_c(f"           {record['file']}:{record['line']}", DIM))
        else:
            out.append(f"  {symbol}")
    if report.get("semantic_diff"):
        sd = report["semantic_diff"]
        out.append(_c(f"  (entire graph diff --base {sd['base']} --head {sd['head']}: "
                      f"{len(sd['changes'])} entity change(s))", DIM))

    if report["findings"]:
        out.append("")
        out.append(_c("compliance findings", BOLD))
        for f in report["findings"]:
            marker = "!!" if f["severity"] == "critical" else " !"
            out.append(f"  {_c(marker, '31' if f['severity'] == 'critical' else '33')} {f['title']}")
            out.append(_c(f"     {f['detail']}", DIM))
            if f["citation"]:
                out.append(_c(f"     cite: {f['citation']}", DIM))
            out.append(_c(f"     proof: {f['provenance']['file'] or '?'}"
                          f":{f['provenance']['line'] or '?'}", DIM))
            if f["needs_verification_note"]:
                out.append(_c(f"     UNVERIFIED — {f['needs_verification_note']}", "33"))

    if report["scheduled_jobs"]:
        out.append("")
        out.append(_c("scheduled consumers (ship unattended)", BOLD))
        for j in report["scheduled_jobs"]:
            out.append(f"  {j['name']}  {_c(j['schedule'], DIM)}")

    out.append("")
    out.append(_c("why this score", BOLD))
    for term in report["risk_terms"]:
        sign = "+" if term["contribution"] >= 0 else ""
        out.append(f"  {sign}{term['contribution']:>4}  {term['name']}")
        out.append(_c(f"         {term['because']}", DIM))

    out.append("")
    out.append(_c(f"blast radius: {len(report['reached'])} symbols", BOLD))
    for item in report["reached"][:12]:
        mark = "" if item["verification"] == "verified" else _c(" [unverified]", "33")
        out.append(f"  hop {item['hops']}  {item['symbol']}{mark}")
        out.append(_c(f"           {item['proof']}", DIM))
    if len(report["reached"]) > 12:
        out.append(_c(f"  ... {len(report['reached']) - 12} more (--json for all)", DIM))

    out.append("")
    out.append(_c("run these tests", BOLD))
    out.append(f"  {report['tests']['command']}")

    out.append("")
    out.append(_c("evidence", BOLD))
    prov = report.get("provenance", {})
    sources = ", ".join(report["evidence_sources"]) or "none"
    out.append(_c(f"  sources:  {sources}", DIM))
    if prov.get("graph_provider"):
        out.append(_c(f"  provider: {prov['graph_provider']} @ "
                      f"{(prov.get('graph_commit') or '')[:12]}", DIM))
        out.append(_c(f"  command:  {prov.get('graph_argv', '')}", DIM))
        out.append(_c(f"  parsed:   {prov.get('graph_files_parsed')}/"
                      f"{prov.get('graph_files_total')} files", DIM))
    note = prov.get("graph_completeness_note", "")
    if prov.get("graph_partial_failures_in_scope"):
        out.append(_c(f"  ! {note}", "31"))
    elif note:
        out.append(_c(f"  scope:    {note}", DIM))
    if prov.get("single_sourced"):
        out.append(_c("  ! Entire Graph did not run. These findings are SINGLE-SOURCED "
                      "and are not a complete blast radius.", "31"))
    if report["unverified_count"]:
        out.append(_c(
            f"  {report['unverified_count']} edge(s) single-sourced, shown as unverified; "
            f"nothing is asserted that we could not corroborate.", "33"))
    else:
        out.append(_c(f"  all {len(report['reached'])} reached symbol(s) independently "
                      f"derived by both sources", DIM))
    for conflict in report.get("conflicts", []):
        out.append(_c(f"  CONFLICT {conflict['caller']} -> {conflict['callee']}", "31"))

    if report.get("intent"):
        out.append("")
        out.append(_c("intent check", BOLD))
        out.append(f"  stated:  {report['intent'].get('stated', '-')}")
        if report["intent"].get("mismatch"):
            out.append(_c(f"  ACTUAL:  {report['intent']['mismatch']}", "31"))

    out.append("")
    return "\n".join(out)
