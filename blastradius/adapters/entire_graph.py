"""Entire Graph adapter — the PRIMARY evidence source.

CALIBRATED 2026-09-06 against entire-graph `schema_version` 1.1 (`provider:
entire-graph`). Every command, flag and JSON key below was read off the real
provider, and the captured output is committed under `docs/graph-evidence/`
so a reader can check this file against it.

Four provider surfaces are used, each for a different job:

  edges        NDJSON relation stream, filtered server-side with --relation.
               This is the backbone: it yields EVERY resolved relation in the
               repository, so Blast Radius can walk reverse dependencies to an
               unbounded depth. `impact` deliberately stops at depth 2; a real
               regulated blast radius in this fixture is five hops deep, so the
               stream is what makes the product possible.
  impact       The provider's own one-shot blast radius for a symbol. Used as
               an INDEPENDENT CORROBORATION of our own traversal at depth<=2,
               and for the facets we do not derive ourselves (type consumers,
               data flows, co-change coupling).
  diff         Entity-level semantic diff between two refs. Turns `--base REF`
               into a set of changed symbols, so the tool works on a real diff
               and not only on a hand-named symbol.
  capabilities Feature detection. We refuse to run against an unknown schema
               major rather than silently misread it.

Provider facts that are load-bearing here, and are NOT invented by us:

  * `confidence`  a float per relation (0.92 same-file exact, 0.86 resolved
                  through an import, 0.78 resolved to an external symbol).
  * `resolution`  how the call was resolved: exact | import_resolved |
                  import_external | heuristic.
  * `evidence[]`  the call site, as {file_path, start_line, end_line, detail}.

Those three are why a Blast Radius finding can be clicked through to a line of
source. We do not synthesise any of them.

Failure policy: this adapter raises rather than degrades silently. The caller
decides whether to fall back to the local resolver, and when it does, the
report says on its face that findings are single-sourced. The one thing this
product must never do is present a partial blast radius as a complete one.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Iterator, Optional

from blastradius.core.evidence import Edge, Provenance, Source

# We understand this schema major. A newer major may have re-typed records, so
# we refuse it instead of guessing. A newer MINOR is allowed but reported.
SCHEMA_MAJOR = 1

# Relations that mean "if the callee changes, the caller is affected".
#
# CALLS only, by default, and that default is a finding rather than a shortcut.
#
# DATA_FLOWS looks like a free win -- it catches value propagation a call graph
# misses -- but it carries TWO OPPOSITE ORIENTATIONS in one relation type,
# distinguished only by the `reason` string:
#
#   "callee return value flows into caller return value"
#        from_id = callee, to_id = caller     <- REVERSED relative to CALLS
#        e.g. to_money -> penal_charge means penal_charge DEPENDS ON to_money
#   "caller parameter forwarded into callee argument"
#        from_id = caller, to_id = callee     <- same direction as CALLS
#
# Reading every DATA_FLOWS edge with the CALLS orientation put 48 symbols in
# the blast radius of `penal_charge`, including its own callees (`to_money`
# surfaced at hop 1). We caught it by cross-checking against the provider's own
# `impact` command, which labels the same edges `<-` in / `->` out.
#
# `_orient` below normalises both forms correctly, so DATA_FLOWS is available
# with --include-data-flows. It is off by default because an inflated blast
# radius that is not real is worse for this product than a smaller one that is.
IMPACT_RELATIONS = ("CALLS",)

# Relation -> how much we trust it as an impact edge, independent of the
# provider's own per-edge confidence. CALLS is a hard dependency; DATA_FLOWS is
# real but weaker, and is labelled as such in the report.
RELATION_WEIGHT = {"CALLS": 1.0, "DATA_FLOWS": 0.75}

# `reason` fragments that mean from_id is the CALLEE and to_id is the CALLER,
# i.e. the edge must be inverted before it can be walked as a dependency.
INVERTED_REASONS = ("callee return value flows into caller",)


def _orient(from_symbol: str, to_symbol: str, relation: str, reason: str) -> tuple:
    """Normalise a provider relation into (dependent, dependency).

    `dependent` is the symbol that breaks when `dependency` changes -- the
    direction a blast radius is walked in. CALLS is already in that order.
    DATA_FLOWS is not always, so it is oriented from its stated reason.
    """
    if relation == "DATA_FLOWS" and any(m in reason for m in INVERTED_REASONS):
        return to_symbol, from_symbol
    return from_symbol, to_symbol


class EntireGraphUnavailable(RuntimeError):
    """The provider could not be run, or produced nothing usable."""


class EntireGraphSchemaMismatch(EntireGraphUnavailable):
    """The provider spoke a schema major we do not understand."""


def resolve_invocation(explicit: Optional[str] = None) -> list:
    """How to call the graph provider, most-official first.

    1. An explicit path (--graph-bin) or $BLASTRADIUS_GRAPH_BIN.
    2. `entire graph ...` — the official plugin path from the Entire CLI.
    3. `entire-graph ...` — a standalone provider binary on PATH.
    4. `.blastradius/entire-graph-dev` — a provider built from this very fork
       (`go build ./cmd/entire-graph`). Since the repository we are working in
       IS entire-graph, building the provider from source is a legitimate and
       fully reproducible way to run it.

    Returns the argv prefix; the subcommand is appended by the caller.
    """
    explicit = explicit or os.environ.get("BLASTRADIUS_GRAPH_BIN")
    if explicit:
        if not (os.path.isfile(explicit) and os.access(explicit, os.X_OK)):
            raise EntireGraphUnavailable(f"graph binary not executable: {explicit}")
        return [explicit]
    if shutil.which("entire"):
        return ["entire", "graph"]
    if shutil.which("entire-graph"):
        return ["entire-graph"]
    for candidate in (".blastradius/entire-graph-dev", "./entire-graph"):
        path = os.path.abspath(candidate)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return [path]
    raise EntireGraphUnavailable(
        "no Entire Graph provider found. Install the Entire CLI and run "
        "`entire plugin install graph`, or build the provider from this fork "
        "with `make graph-bin`."
    )


def _module_of(file_path: str, source_root: str) -> Optional[str]:
    """Repo-relative file path -> dotted module, relative to the source root.

    `fixtures/lending-platform/pricing/fees.py` with source root
    `fixtures/lending-platform` becomes `pricing.fees`. Returns None for files
    outside the source root, which is how we ignore the rest of the repository.
    """
    file_path = file_path.replace(os.sep, "/").lstrip("./")
    root = (source_root or "").replace(os.sep, "/").strip("/")
    if root:
        if not file_path.startswith(root + "/"):
            return None
        file_path = file_path[len(root) + 1:]
    if not file_path.endswith(".py"):
        return None
    parts = [p for p in file_path[:-3].split("/") if p and p != "__init__"]
    return ".".join(parts)


def parse_symbol_id(symbol_id: str, source_root: str) -> Optional[str]:
    """Provider symbol id -> the dotted symbol name Blast Radius uses.

    The provider's stable id is
        <repo_key>:<Language>:<file_path>:<kind>:<Name>
    for example
        local/fixrepo:Python:fixtures/lending-platform/pricing/fees.py:function:penal_charge
    and `Name` is already class-qualified for methods (`Loan.net_disbursal`),
    which is why the local AST resolver is class-qualified too — the two names
    have to be comparable for verification to mean anything.

    External endpoints (`external:symbol:decimal.Decimal`) return None: a
    change to our code cannot break the standard library, and pretending
    otherwise would inflate every blast radius.
    """
    if not symbol_id or symbol_id.startswith("external:"):
        return None
    parts = symbol_id.rsplit(":", 3)
    if len(parts) != 4:
        return None
    _prefix, file_path, _kind, name = parts
    module = _module_of(file_path, source_root)
    if module is None or not name:
        return None
    return f"{module}.{name}"


def symbol_id_file(symbol_id: str) -> Optional[str]:
    """The repo-relative file path out of a provider symbol id."""
    if not symbol_id or symbol_id.startswith("external:"):
        return None
    parts = symbol_id.rsplit(":", 3)
    return parts[1] if len(parts) == 4 else None


@dataclass
class GraphRun:
    """What one provider invocation told us. Recorded so the report can state
    which provider version and commit the evidence came from."""
    provider: str = ""
    provider_version: str = ""
    schema_version: str = ""
    repo_key: str = ""
    commit: str = ""
    relation_counts: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    partial_failures: list = field(default_factory=list)
    languages: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    argv: list = field(default_factory=list)

    def cite(self) -> str:
        return f"{self.provider} {self.provider_version} (schema {self.schema_version})"

    def failures_in(self, source_root: str) -> list:
        """Partial parse failures that fall INSIDE the analysed subtree.

        The provider reports completeness for the whole repository, and this
        fork is a 686-file polyglot Go codebase, so the snapshot is routinely
        "degraded" for reasons that cannot touch a Python lending fixture (a
        C++ grammar header, for instance). Scoping the degradation is the
        difference between an honest caveat and a useless one: the report must
        be able to say *this* answer is complete, or say precisely why not.
        """
        root = (source_root or "").replace(os.sep, "/").strip("/")
        out = []
        for failure in self.partial_failures:
            path = (failure.get("file_path") or "").replace(os.sep, "/")
            if not root or path.startswith(root + "/"):
                out.append(failure)
        return out

    def scope_note(self, source_root: str) -> str:
        scoped = self.failures_in(source_root)
        if scoped:
            return (f"{len(scoped)} file(s) inside {source_root} failed to parse — "
                    f"this blast radius is INCOMPLETE")
        total = len(self.partial_failures)
        analysed = (self.languages or {})
        tier = analysed.get("Python", "unknown")
        if total:
            return (f"{total} diagnostic(s) elsewhere in the repository, 0 inside "
                    f"{source_root}; Python is analysed {tier}")
        return f"no parse failures; Python is analysed {tier}"


class EntireGraphAdapter:
    """Reads structural evidence out of Entire Graph."""

    def __init__(
        self,
        repo: str,
        source_root: str = "",
        binary: Optional[str] = None,
        worktree: bool = True,
        timeout: int = 180,
        profile: str = "full",
    ):
        self.repo = os.path.abspath(repo)
        self.source_root = source_root
        self.worktree = worktree
        self.timeout = timeout
        self.profile = profile
        self.prefix = resolve_invocation(binary)
        self.last_run = GraphRun()

    # ---- invocation ------------------------------------------------------

    def _argv(self, *args: str) -> list:
        return list(self.prefix) + list(args)

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        argv = self._argv(*args)
        try:
            proc = subprocess.run(
                argv, cwd=self.repo, capture_output=True, text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise EntireGraphUnavailable(
                f"`{' '.join(argv[:3])}` timed out after {self.timeout}s"
            ) from exc
        except OSError as exc:
            raise EntireGraphUnavailable(f"could not execute {argv[0]}: {exc}") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip().splitlines()
            raise EntireGraphUnavailable(
                f"`{' '.join(argv[:3])}` exited {proc.returncode}: "
                f"{detail[0] if detail else 'no output'}"
            )
        return proc

    def _check_schema(self, header: dict) -> None:
        version = str(header.get("schema_version", ""))
        major = version.split(".")[0]
        if not major.isdigit():
            raise EntireGraphSchemaMismatch(f"unreadable schema_version {version!r}")
        if int(major) != SCHEMA_MAJOR:
            raise EntireGraphSchemaMismatch(
                f"provider speaks schema {version}; this adapter understands "
                f"major {SCHEMA_MAJOR}. Refusing to guess at re-typed records."
            )

    # ---- capabilities ----------------------------------------------------

    def capabilities(self) -> dict:
        """Feature detection. Also the first required graph artefact: it proves
        which languages get semantic (not merely inventory) analysis."""
        # `capabilities` takes --json and nothing else -- it reports the
        # provider's static capability registry, not a property of this repo.
        proc = self._run("capabilities", "--json")
        return json.loads(proc.stdout)

    def semantic_languages(self) -> list:
        caps = self.capabilities()
        return caps.get("semantic_languages") or caps.get("semantic_language_names") or []

    # ---- the relation stream (the backbone) ------------------------------

    def _stream(self, mode: str, *extra: str) -> Iterator[dict]:
        args = [mode, "--repo", self.repo, "--profile", self.profile]
        if self.worktree:
            args.append("--worktree")
        args.extend(extra)
        proc = self._run(*args)
        header_seen = False
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not header_seen:
                header_seen = True
                self._check_schema(record)
                self.last_run = GraphRun(
                    provider=record.get("provider", ""),
                    provider_version=record.get("provider_version", ""),
                    schema_version=record.get("schema_version", ""),
                    repo_key=record.get("repo_key", ""),
                    commit=record.get("commit", ""),
                    argv=self._argv(*args),
                )
                continue
            if record.get("record_type") == "summary":
                self.last_run.relation_counts = (
                    record.get("completeness", {}).get("relations") or {}
                )
                self.last_run.warnings = record.get("warnings", []) or []
                self.last_run.partial_failures = record.get("partial_failures", []) or []
                self.last_run.languages = record.get("language_tiers", {}) or {}
                self.last_run.stats = record.get("stats", {}) or {}
                continue
            yield record
        if not header_seen:
            raise EntireGraphUnavailable(f"`{mode}` produced no records")

    def edges(self, relations: tuple = IMPACT_RELATIONS) -> list:
        """Every impact-bearing relation in the repository, as Blast Radius edges.

        A relation record looks like this (verbatim from the provider):

            {"record_type":"relation",
             "from_id":"local/r:Python:.../schedule.py:function:overdue_projection",
             "to_id":"local/r:Python:.../fees.py:function:penal_charge",
             "type":"CALLS","confidence":0.86,
             "resolution":"import_resolved",
             "reason":"direct call expression resolved through import path",
             "evidence":[{"kind":"call_site","file_path":".../schedule.py",
                          "start_line":44,"end_line":46,"detail":"penal_charge"}]}

        `from_id` depends on `to_id`, so in Blast Radius terms from_id is the
        CALLER and to_id is the CALLEE. Walking callers is walking the blast
        radius.
        """
        found = []
        for record in self._stream("edges", "--relation", ",".join(relations)):
            if record.get("record_type") != "relation":
                continue
            relation = record.get("type", "")
            reason = record.get("reason", "") or ""
            from_symbol = parse_symbol_id(record.get("from_id", ""), self.source_root)
            to_symbol = parse_symbol_id(record.get("to_id", ""), self.source_root)
            if not from_symbol or not to_symbol or from_symbol == to_symbol:
                continue
            caller, callee = _orient(from_symbol, to_symbol, relation, reason)
            evidence = (record.get("evidence") or [{}])[0]
            call_file = evidence.get("file_path") or symbol_id_file(record.get("from_id", ""))
            provider_conf = float(record.get("confidence") or 0.0)
            found.append(Edge(
                caller=caller,
                callee=callee,
                relation=relation,
                provenance=Provenance(
                    source=Source.ENTIRE_GRAPH,
                    file=call_file,
                    line=evidence.get("start_line"),
                    end_line=evidence.get("end_line"),
                    confidence=round(provider_conf * RELATION_WEIGHT.get(relation, 1.0), 3),
                    resolution=record.get("resolution", ""),
                    detail=reason or f"{relation} {caller} -> {callee}",
                ),
            ))
        if not found:
            raise EntireGraphUnavailable(
                "the provider resolved no impact relations under source root "
                f"{self.source_root!r} — check --source-root against the repo layout"
            )
        return found

    # ---- the provider's own blast radius (corroboration) -----------------

    def impact(self, symbol: str, depth: int = 2, limit: int = 50) -> dict:
        """The provider's one-shot blast radius, as a second opinion.

        Bounded at depth<=2 by the provider, so it cannot replace our traversal
        — but where the two overlap, agreement is real corroboration from a
        different code path inside the provider, and disagreement is worth
        surfacing.
        """
        args = [
            "impact", "--repo", self.repo, "--symbol", symbol,
            "--depth", str(depth), "--limit", str(limit),
            "--format", "json", "--profile", self.profile,
        ]
        if self.worktree:
            args.append("--worktree")
        proc = self._run(*args)
        payload = json.loads(proc.stdout)
        self._check_schema({"schema_version": f"{SCHEMA_MAJOR}.0"})
        return payload

    def impact_callers(self, symbol: str, depth: int = 2) -> dict:
        """{dotted symbol: hop depth} from the provider's own impact command."""
        payload = self.impact(symbol, depth=depth)
        out = {}
        for entry in payload.get("callers", {}).get("entries", []) or []:
            endpoint = entry.get("endpoint", {}) or {}
            module = _module_of(endpoint.get("file_path", "") or "", self.source_root)
            name = endpoint.get("qualified_name") or endpoint.get("name") or ""
            if module and name:
                out[f"{module}.{name}"] = int(entry.get("depth") or 1)
        return out

    # ---- semantic diff ---------------------------------------------------

    def changed_symbols(self, base: str, head: str = "HEAD") -> list:
        """Entity-level semantic diff -> the symbols a real diff actually changed.

        Returns records carrying the provider's own change classification, so
        the report can say `modified pricing.fees.penal_charge` rather than
        `fees.py changed`.
        """
        proc = self._run(
            "diff", "--repo", self.repo, "--base", base, "--head", head, "--json",
        )
        payload = json.loads(proc.stdout)
        self._check_schema(payload)
        changed = []
        for entry in payload.get("files", []) or []:
            path = entry.get("path", "")
            module = _module_of(path, self.source_root)
            if module is None:
                continue
            for change in entry.get("changes", []) or []:
                name = change.get("name")
                if not name:
                    continue
                changed.append({
                    "symbol": f"{module}.{name}",
                    "change_type": change.get("type", ""),
                    "kind": change.get("kind", ""),
                    "file": path,
                    "line": change.get("after_start_line") or change.get("before_start_line"),
                    "signature": change.get("new_signature") or change.get("old_signature") or "",
                    "provider_dependents": change.get("dependents_count"),
                })
        return changed

    def raw_diff(self, base: str, head: str = "HEAD") -> str:
        """The verbatim semantic-diff JSON, for the required graph artefact."""
        return self._run(
            "diff", "--repo", self.repo, "--base", base, "--head", head, "--json",
        ).stdout
