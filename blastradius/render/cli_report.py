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

    partial = report.get("completeness") == "partial"

    out.append("")
    headline = _c(f"  BLAST RADIUS: {band}  ", style) + _c(f"  score {report['score']}/100", BOLD)
    if partial:
        # The qualifier rides on the SAME line as the number. A reader who takes
        # away one line must not take away a number that reads as settled.
        headline += _c("  PARTIAL ANALYSIS — score is a FLOOR", "31")
    out.append(headline)
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

    if report.get("blind_spots"):
        out.append("")
        out.append(_c("analysis blind spots (static analysis could not resolve these)", BOLD))
        for spot in report["blind_spots"]:
            out.append(_c(f"  ?? {spot['kind']}  in {spot['symbol']}", "31"))
            out.append(_c(f"     {spot['detail']}", DIM))
            out.append(_c(f"     at: {spot['provenance']['file']}:{spot['provenance']['line']}", DIM))
            out.append(_c(f"     VERIFY: {spot['verify']}", "33"))

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

    if report.get("verification_path"):
        out.append("")
        out.append(_c("verification path (what would settle what we cannot assert)", BOLD))
        for step in report["verification_path"]:
            out.append(f"  - {step['why']}")
            out.append(_c(f"    -> {step['do']}", DIM))

    out.append("")
    out.append(_c("evidence", BOLD))
    prov = report.get("provenance", {})
    sources = ", ".join(report["evidence_sources"]) or "none"
    out.append(_c(f"  sources:  {sources}", DIM))

    # The three things a reader -- human or agent -- has to be able to tell
    # apart, counted rather than described.
    tiers = report.get("evidence_tiers") or {}
    if tiers:
        out.append(_c(f"  confirmed:          {tiers.get('confirmed', 0):>3}  "
                      f"corroborated by two sources and structurally resolved", DIM))
        out.append(_c(f"  heuristic:          {tiers.get('heuristic', 0):>3}  "
                      f"single-sourced, or inferred by its source (name/type match)", "33"))
        out.append(_c(f"  needs verification: {tiers.get('needs-verification', 0):>3}  "
                      f"must be settled against source or a test", "33"))
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
        # This line reports PARSE completeness. Printing it unqualified next to a
        # partial analysis is what the curveball caught us doing: "no parse
        # failures" is true and is not an answer to "is this radius complete?".
        out.append(_c(f"  scope:    {note}", DIM))
        if partial:
            out.append(_c("            (parse completeness — NOT relation "
                          "completeness; see blind spots above)", "33"))
    if prov.get("single_sourced"):
        out.append(_c("  ! Entire Graph did not run. These findings are SINGLE-SOURCED "
                      "and are not a complete blast radius.", "31"))
    if report["unverified_count"]:
        out.append(_c(
            f"  {report['unverified_count']} edge(s) single-sourced, shown as unverified; "
            f"nothing is asserted that we could not corroborate.", "33"))
    elif report["reached"]:
        # Deliberately narrower wording than before. This sentence used to read
        # "all N reached symbol(s) independently derived by both sources", which
        # a reader hears as completeness. It is a statement about the edges we
        # FOUND, and it now says only that.
        out.append(_c(f"  every one of the {len(report['reached'])} reached symbol(s) was "
                      f"derived independently by both sources", DIM))
    if partial:
        out.append(_c(
            f"  ! {len(report['blind_spots'])} unresolved call site(s) in scope. Symbols "
            f"reachable only through them are NOT in this radius: it is a lower bound, "
            f"not a complete set.", "31"))
    elif report.get("reconciled_blind_spots"):
        # Say only what the report can back. An earlier version read this off a
        # raw count of everything the local resolver produced, which conflated
        # "another source resolved it" with "it was scoped out of this radius" --
        # an affirmative claim about a second source with no provenance behind
        # it, computed by the view rather than read off the report.
        out.append(_c(f"  {len(report['reconciled_blind_spots'])} unresolved call site(s) "
                      f"were resolved by another source and dismissed:", DIM))
        for spot in report["reconciled_blind_spots"][:4]:
            out.append(_c(f"      {spot['provenance']['file']}:{spot['provenance']['line']}"
                          f" — {spot['covered_by']}", DIM))
    for conflict in report.get("conflicts", []):
        out.append(_c(f"  CONFLICT {conflict['caller']} -> {conflict['callee']}", "31"))

    if report.get("intent"):
        out.append("")
        out.append(_c("intent check", BOLD))
        out.append(f"  stated:  {report['intent'].get('stated', '-')}")
        if report["intent"].get("mismatch"):
            out.append(_c(f"  ACTUAL:  {report['intent']['mismatch']}", "31"))
        if report["intent"].get("cannot_confirm"):
            out.append(_c(f"  UNKNOWN: {report['intent']['cannot_confirm']}", "31"))

    out.append("")
    return "\n".join(out)
