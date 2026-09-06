# Checkpoint 3 — Response to the Noon Curveball

> **Track 2 curveball: "Graph is evidence, not an oracle."**
>
> This document was written in a **fresh agent session** that had no memory of building the
> project. Everything in Part 1 was reconstructed from the Entire checkpoint records
> (`entire checkpoint list`, `entire checkpoint explain c318df27e970`,
> `entire checkpoint explain 92f99349fbfe`) plus `docs/checkpoints/02-pre-curveball-stable.md`
> and `BUILDATHON.md` — **before a single source file was opened**. That ordering is the point:
> if the checkpoints are worth anything, a cold session should be able to pick the project up
> from them alone.

---

## Part 1 — Reconstruction from the pre-curveball checkpoint

### Intent

**Blast Radius: impact-aware change review for regulated Indian consumer-lending code.**

The user is the engineer — or the coding agent — about to merge a change to a shared lending
codebase, who cannot see past the diff. A `git diff` of `pricing/fees.py` shows six changed
lines. It does not show that those lines sit five hops upstream of the Key Fact Statement, the
sanction letter, the all-inclusive APR, the credit-bureau submission and the RBI supervisory
return — three of which ship on unattended cron jobs. Nobody finds out until a customer
complains or a regulator asks.

The division of labour is deliberate and is the whole thesis:

| Layer | Supplies |
| --- | --- |
| Entire Graph | the **structural evidence** — resolved relations with call sites, confidence and resolution |
| `rules/rbi_surfaces.yaml` | the **meaning** — which reached symbols are regulated disclosure surfaces |
| `core/risk.py` | the **verdict** — a deterministic pure function, never model output |
| `render/` | a **view** over a JSON report that is the single source of truth |

Track 2. Entire Graph is load-bearing, not a logging sidecar: remove it and there is no product.

### Architecture

```
blastradius/
  cli.py                     blast impact [--symbol S | --base REF] [--json] [--intent]
                                          [--fail-on-critical] [--offline]
  adapters/
    entire_graph.py          PRIMARY evidence. edges / impact / diff / capabilities.
    local_ast.py             independent second derivation, used to VERIFY
    rules.py                 loads rules/rbi_surfaces.yaml, matches symbols -> obligations
  core/
    evidence.py              Provenance / Edge / Finding. Source + Verification enums.
    graph_model.py           SymbolGraph; reverse BFS returning the proof path
    impact.py                orchestrator -> ImpactReport
    risk.py                  the deterministic pure scoring function
    tests_select.py          affected symbols -> pytest node ids
  render/cli_report.py       terminal view over the report dict
  rules/rbi_surfaces.yaml    8 codified RBI obligations
fixtures/lending-platform/   synthetic demo target: 14 modules, 21 tests
docs/graph-evidence/         raw provider output, teed verbatim
```

**Workflow:** semantic diff (or a named symbol) → reverse-dependency closure over the graph's
`CALLS` relations → RBI rule overlay → deterministic score → test selection → report.

**Why `edges` and not `impact` is the engine.** `entire graph impact` is bounded at depth ≤ 2
by design; the regulated chain in this fixture is **five hops** deep. Streaming the full
relation set and running our own reverse BFS is what makes the product possible — with
`impact` retained as an *independent second opinion* where the two overlap.

### The four invariants

1. **Evidence-first.** No claim exists without `{source, file, line, confidence, resolution,
   verified}`. Enforced in the type (`core/evidence.py`), not in the renderer's good manners.
2. **The score is a pure function in our code**, never model output. Same input, same score.
   Reproducibility is the only reason a risk score may sit in a merge gate.
3. **Verification means two independent derivations.** Entire Graph is primary; a local `ast`
   resolver derives every edge again. Both agree → `VERIFIED`. One only → `UNVERIFIED`,
   rendered greyed and never asserted. Self-corroboration from one source is explicitly *not*
   verification (`test_the_same_source_twice_is_not_verification` pins this).
4. **JSON first, renderers on top.** One report object; the CLI is a view over it.

### What is complete and working

End-to-end and runnable from a clean checkout, **52 tests passing** (31 product, 21 fixture),
against the official plugin `entire graph` v0.4.0 (schema 1.1), 681/681 files parsed.

- `blast impact --symbol S` **and** `blast impact --base REF` both work — the second reads
  changed entities out of `entire graph diff --base A --head B --json`, so the tool reviews a
  real commit, not only a hand-named symbol.
- Three distinct bands from one tool on one codebase, all real output:
  `recovery.dunning._format_sms_text` → **LOW 3/100**; `core.money.annualise_monthly` →
  **HIGH 52/100** (structural terms alone are 22 — the RBI overlay takes it to 52);
  `pricing.fees.penal_charge` → **CRITICAL 100/100** (24 symbols, 4 regulated surfaces, 3
  unattended jobs).
- `make gate` exits non-zero on HIGH/CRITICAL; `make evidence` re-captures raw provider output.
- The intent overlay fires: stated *"contained to pricing.fees"* vs ACTUAL *"reaches 4
  regulated surface(s) and 3 scheduled job(s) beyond that scope"*.
- Two prior graph findings are already banked: `DATA_FLOWS` carries **two opposite
  orientations** (normalised by `_orient()`, four tests, relation off by default); and
  completeness must be **scoped to the analysed subtree** (`GraphRun.failures_in()`,
  `scope_note()`) rather than reported repository-wide.

### Deliberately unfinished, and open risks

- Two RBI rules (`foreclosure-charges`, `regulatory-return`) carry `confidence: medium` and
  render `UNVERIFIED` with the reason attached. **The product refusing to assert what it
  cannot stand behind — not a gap.**
- The local `ast` verifier cannot resolve receiver method calls (`loan.emi()`), so those edges
  stay `UNVERIFIED`. Honest, but it understates coverage.
- `DATA_FLOWS` orientation is derived from the provider's free-text `reason` field; an upstream
  wording change would need the constant updated — hence opt-in.
- A rulebook entry matching zero symbols is silently dead; it should be a hard error.
- Risk weights are constants in `risk.py`, not configuration.
- Reverse BFS capped at 8 hops.

### Where the seams are

Recorded in Checkpoint 2, before the card arrived: *"`adapters/entire_graph.py` is the only
caller of the provider. `render/` is a view over one report dict. `core/` is pure functions
with unit tests. Reach for a seam before a rewrite."*

---

## Part 2 — The assumption the Curveball invalidated

> Written **before** any implementation edit. The graph analysis in Part 3 was run first;
> the eleven raw captures are in `docs/graph-evidence/08-*` and `09-*`.

### The assumption, stated exactly

> **"If every file in the analysed subtree parsed cleanly, the blast radius is complete —
> so the absence of an edge is evidence that no dependency exists."**

It is written into Checkpoint 2 in as many words: *"With CALLS only the radius is 24 symbols
and all 24 are corroborated by both sources"*, and *"no parse failures; Python is analysed
semantic"* is printed on the report as the completeness line. We built a careful mechanism —
`GraphRun.failures_in()` and `scope_note()` — to decide whether the answer could be trusted,
and we pointed that mechanism at **parse failure**.

### Why it is false

Parse completeness and *relation* completeness are different properties. A file can parse
perfectly and still hide dependencies that no static resolver can see:

- dynamic dispatch — `HANDLERS[key](loan)`, `getattr(module, name)()`
- reflection and late binding — `importlib.import_module`, `__import__`, `eval`/`exec`
- registration indirection — decorator registries, plugin entry points, signal/hook tables
- string-keyed configuration — a job name in YAML resolved to a callable at runtime
- generated code — a module that does not exist until build time
- and, demonstrated below, relations that are simply **not of the kind we asked for**

`681/681 files parsed` was true. It was also not an answer to the question we were asking.

### The proof is in our own repository, from our own evidence layer

`docs/graph-evidence/08-curveball-impact-verification.txt`:

```
$ entire graph impact --repo . --symbol Verification --file blastradius/core/evidence.py
IMPACT DEGENERATE: Verification has no callers, callees or type consumers
```

`docs/graph-evidence/09-curveball-degenerate-crosscheck.txt` — the same symbol, by grep:

```
blastradius/core/graph_model.py:37   existing.verification = Verification.VERIFIED
blastradius/core/evidence.py:90      self.verification is Verification.VERIFIED
blastradius/core/impact.py:84        ... if e.verification is not Verification.VERIFIED
                                     (10 references in total)
```

`Verification` is the enum that decides whether Blast Radius may assert a finding at all.
The graph reports it as having **no relations whatsoever**, because an enum attribute
reference is not a `CALLS` edge and the relation we asked for was `CALLS`.

**The provider is not wrong.** It answered the question it was asked, precisely, and its
`impact` command even labelled the answer `DEGENERATE` rather than dressing it up. The error
is entirely ours: we read "no edges returned" as "no dependencies exist". That is the
difference between evidence and an oracle, and the curveball landed it on the one file where
our trust claims live.

### What it costs the product, specifically

This is not a cosmetic honesty problem. Under-reporting is the failure mode this product
cannot have, and it is the one this assumption produces:

1. **A missing edge shrinks the radius, and a small radius scores LOW.** Every structural
   term in `risk.py` counts things *found* — surfaces, jobs, hop-1 callers. Nothing counts
   what could not be resolved. A dispatch site that hides a route into the Key Fact Statement
   does not lower confidence in the score; it silently lowers the score itself. `make gate`
   then exits **0**. Incomplete analysis renders as **"safe to merge"**.

2. **Invariant 3 has an asymmetry we never wrote down.** Two independent derivations can
   confirm an edge that *exists*. They cannot confirm that an edge is *absent* — and our
   second source, the local `ast` resolver, is blind in the same places as the first, by
   construction: `_resolve()` in `adapters/local_ast.py:170` **drops any name it cannot tie
   to a definition it saw**, and drops it silently. Two blind sources agreeing on a blind
   spot is not corroboration.

3. **`unverified_count: 0` was rendered as though it meant the radius was fully verified.**
   It means every edge *we found* was corroborated. It says nothing about edges neither
   source found — and `cli_report.py:109` prints "all N reached symbol(s) independently
   derived by both sources", which a reader will reasonably hear as completeness.

### The correction

> **Absence of evidence is not evidence of absence. A blast radius is a lower bound, not a
> set — and where the analysis is blind, the tool must say where, and must not let a
> confident-looking LOW pass a merge gate.**

Concretely, the report gains a **completeness axis orthogonal to the score**. The score stays
exactly what it is — a pure function of what is known, unchanged for fully resolved code —
and the report states separately whether what is known is all there is. See Part 4.

---

## Part 3 — The graph analysis that was run before editing

`entire graph impact` was run on **every part of the implementation that consumes
relationship, impact or semantic-diff evidence**, before any implementation file was
modified. Raw output is teed verbatim into `docs/graph-evidence/`, one file per consumer.

> **Disclosure about these captures.** The counts in the table below are the readings from
> that pre-implementation run — the ordering the card requires. The `08-*` files on disk are
> **re-captured by `make evidence`** against the finished code, so they stay reproducible
> rather than frozen. Re-running them changes exactly one number: `impact_callers` reports
> **3** callees instead of 2, because this change gave it a third
> (`EntireGraphAmbiguousSymbol`, raised when the provider declines to answer). Everything
> else is identical, including the result that drove the design — `Verification` returning
> `IMPACT DEGENERATE` — because its cause, that an enum reference is not a `CALLS` edge, has
> nothing to do with our code.

| Consumer | Evidence it consumes | Blast radius the graph reported | Capture |
| --- | --- | --- | --- |
| `EntireGraphAdapter.edges` | **relationship** — the `CALLS` stream | 5 callers, 7 callees | `08-curveball-impact-edges.txt` |
| `EntireGraphAdapter.impact_callers` | **impact** — the provider's second opinion | 1 caller, 2 callees *(3 after this change — see the disclosure above)* | `08-curveball-impact-impact-callers.txt` |
| `EntireGraphAdapter.changed_symbols` | **semantic diff** — `graph diff --json` | 2 callers, 4 callees | `08-curveball-impact-changed-symbols.txt` |
| `_orient` | relationship orientation | 10 callers (6 direct, 4 transitive) | `08-curveball-impact-orient.txt` |
| `GraphRun.scope_note` | completeness reporting | 0 callers, 1 callee | `08-curveball-impact-scope-note.txt` |
| `Provenance` | every claim's citation | 12 callers, 2 type consumers | `08-curveball-impact-provenance.txt` |
| `Edge` | the atom of the radius | 11 callers, 2 type consumers | `08-curveball-impact-edge.txt` |
| `Finding` | the assertable claim | 2 callers | `08-curveball-impact-finding.txt` |
| `Verification` | the verdict on every edge | **IMPACT DEGENERATE — no relations at all** | `08-curveball-impact-verification.txt` |
| `build_graph` | assembles both derivations | 1 caller, 9 callees | `08-curveball-impact-build-graph.txt` |

Two things came out of this that changed the implementation rather than decorating it.

**The `Verification` result is the curveball in miniature** and is written up in Part 2. It
is why the fix is a source-level detector rather than more graph queries: the graph cannot
report an edge it never saw, so no amount of asking it will reveal the absence.

**The seam was confirmed, not assumed.** `edges` has 4 direct callers and `Provenance` has
12 — the consumers are concentrated in `adapters/` and `core/`, exactly where Checkpoint 2
predicted. That is what licensed a seam change over a rewrite.

### A third finding, from the provider's own fields

`docs/graph-evidence/04-edges-calls.ndjson`, re-counted by resolution:

```
import_resolved  70 (conf 0.86)     exact  20 (0.92)     import_external 19 (0.78)
name_only         6 (conf 0.68)     type_inferred 2 (0.83)
```

Eight of those edges are the provider telling us **it inferred rather than resolved** —
`name_only` matched on the identifier alone. Blast Radius was carrying `confidence` through
faithfully and then treating all eight identically to an `exact` edge when deciding what to
assert. The provider was more honest about its own uncertainty than we were.

---

## Part 4 — The revised design

> **Read with Checkpoint 4.** This part records the design as first cut. An adversarial
> review then found real defects in it — a scoping rule that was inverted, a reconciliation
> rule that silenced holes on a bare name match, a tier function that failed open, and four
> gaps in the detector. Those corrections, and the numbers as shipped, are in
> [`04-final-implementation.md`](04-final-implementation.md). The passages below are marked
> where the shipped behaviour differs.

The change is at the adapter/renderer seam, as Checkpoint 2 anticipated. `risk.py`'s
arithmetic is untouched; no traversal was rewritten.

### 1. A new evidence type: `BlindSpot` (`core/evidence.py`)

`_resolve()` in `adapters/local_ast.py` has always dropped names it could not tie to a
definition — correctly, because guessing is what produces a radius that is not real. It now
**records** what it drops. A `BlindSpot` carries the same provenance contract as every other
claim, plus `verify`: the concrete action that would settle it. A blind spot the tool cannot
tell you how to close is a shrug, not a finding.

Detected: `dynamic-dispatch` (`HANDLERS[k](loan)`, `factory()(loan)`), `reflection`
(`getattr` with a non-literal name, `importlib.import_module`, `eval`/`exec`), `star-import`,
`missing-module` (a first-party package whose module is not on disk — generated code), and
`receiver-method`.

> **Revised after review.** `dynamic-dispatch` now also covers a callable held in a variable
> or parameter — the commonest shape in Python, and it was being miscounted as stdlib noise —
> and chained/`super()` calls. `missing-module` covers all four import forms rather than one,
> reflection is followed through import aliases, and a sixth kind, `provider-unavailable`,
> reports the case where Entire Graph did not run at all. See Checkpoint 4.

**Precision was designed in, because a detector that cries wolf gets switched off.**
`getattr(loan, "emi")` with a literal is statically knowable and is not flagged.
`rows.append(...)` names nothing first-party, so there is no edge to miss. Unresolved bare
names — builtins and stdlib, 57 of them in the main fixture — are **counted and disclosed as
a number**, not listed.

### 2. Reconciliation: a site only one source is blind to is not a blind spot

The local resolver cannot follow `loan.net_disbursal()` through an untyped receiver. Entire
Graph can, and reports it `type_inferred`. `reconcile_blind_spots()` drops any spot another
source resolved — which is why **the existing fixture reports `completeness: complete`** and
its two candidate spots vanish.

The asymmetry is the point: a `receiver-method` site has a name, so another source can be
checked for it. `dynamic-dispatch` and `reflection` do not — the target is unbounded, so no
source can have covered it and the spot always stands.

### 3. Scoping, and a score that is a floor

`scope_blind_spots()` applies the same discipline as `GraphRun.failures_in()`: dispatch and
reflection are always in scope because the hidden edge can land anywhere; a localised
receiver-method site is scoped by whether it can touch this radius at all.

> **Corrected after review — this was the most serious defect in the first cut.** That last
> clause originally read "in scope only when its *enclosing symbol* is already in the
> radius". The radius is a REVERSE walk, so for a missing edge `owner -> target` the question
> is whether **target** is in it. Keying on the owner kept exactly the spots that could not
> change the answer and dropped exactly the ones that could. Three reviewers caught it
> independently; see Checkpoint 4.

`risk.py` gains **no points and no weights**. Inventing risk for an unresolved site would be
the inflated-`DATA_FLOWS` mistake of Checkpoint 2 in the other direction. Instead: every term
in that file counts something *found*, so anything unfound can only push the score down, and
the result therefore carries `score_is_floor` and a **zero-contribution term** that appears in
"why this score" and says so. The number is unchanged; its standing is stated.

### 4. Three tiers, so a reader can tell claims apart

| Tier | Means |
| --- | --- |
| **confirmed** | corroborated by two sources **and** structurally resolved (`exact` / `import_resolved`) |
| **heuristic** | single-sourced, **or** inferred by its own source (`name_only`, `type_inferred`, `ast_name_only`), **or** corroborated only by another inference |
| **needs verification** | conflicts, RBI rules carrying a `verify` note, and every blind spot |

Corroboration alone is deliberately **not** sufficient for `confirmed`. Both our resolvers
have a bare-name fallback, so two name-guessers agreeing is two guesses. That is
`test_the_same_source_twice_is_not_verification` applied to resolution quality instead of to
source identity.

### 5. The gate stops conflating "clear" with "could not see"

```
exit 0   clear
exit 1   we saw enough, and it is risky        (HIGH / CRITICAL)
exit 2   we could not see enough to clear it   (analysis partial)
```

`--allow-partial` lets a team accept the residual risk **explicitly** rather than by not
being told. And the intent overlay no longer treats silence as agreement: an incomplete
radius can contradict a stated intent but can never corroborate one, so it prints
`UNKNOWN: containment CANNOT be confirmed` instead of quietly validating "nothing downstream".

### 6. A bug this work found in our own adapter

Adding the second fixture made `penal_charge` ambiguous across two files. The provider
correctly refused to answer, returning `disambiguation_required: true` with
`callers.entries: null`. `impact_callers()` read that as **"nothing depends on this."**

Same bug class as the curveball, in our own code: a refusal treated as an answer of zero. It
now honours the flag, narrows with `--file` to the definition inside the source root, and
raises `EntireGraphAmbiguousSymbol` if that still does not identify one. It was caught by an
existing test going red, which is the argument for having had the test.

### Why the new result is safe

- **Fully resolved code is untouched.** The three demo bands reproduce exactly — LOW 3/100
  (3 symbols), HIGH 52/100 (16), CRITICAL 100/100 (24), all `completeness: complete`. The
  main fixture has no dynamic dispatch, so nothing to report and nothing changes.
- **Under-reporting can no longer read as safety.** On the new fixture the radius is
  genuinely **empty** and the band is LOW — and the tool refuses to let that pass: `PARTIAL
  ANALYSIS — score is a FLOOR`, five sites named with `file:line`, an action for each, and
  exit 2.
- **Nothing is asserted that we cannot stand behind.** Every new claim carries provenance;
  every blind spot carries a verification action; the heuristic tier is separated from the
  confirmed one using the provider's own resolution field.
