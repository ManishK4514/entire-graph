# Blast Radius

**Git tells you what changed. Blast Radius tells you what breaks.**

## One-sentence summary

Blast Radius turns Entire Graph's structural evidence into a merge-gate decision for
regulated lending code: it walks reverse dependencies to find every symbol a change can
reach, overlays a codified RBI rulebook to mark which of those are regulated disclosure
surfaces, scores the risk with a deterministic function, selects the exact tests to run,
and pins every single claim to a `file:line` the developer can open.

## Problem, intended user and why it matters

**User:** the engineer or coding agent about to merge a change to a shared consumer-lending
codebase, who cannot see past the diff.

In Indian consumer lending, the penal-charge calculation is not just arithmetic. It feeds
the Key Fact Statement, the sanction letter, the all-inclusive APR, the credit-bureau
submission and the RBI supervisory return. Three of those ship on unattended cron jobs.

A `git diff` of `pricing/fees.py` shows six changed lines. It does not show that those six
lines are five hops upstream of a document the borrower is legally entitled to receive.
Nobody finds out until a customer complains or a regulator asks.

Blast Radius is the review step that closes that gap. On the demo change it reports:

```
BLAST RADIUS: CRITICAL    score 100/100
changed
  pricing.fees.penal_charge  body_changed function
           fixtures/lending-platform/pricing/fees.py:12
  (entire graph diff --base main --head HEAD: 1 entity change(s))

intent check
  stated:  make penal charge non-compounding; contained to pricing.fees
  ACTUAL:  change reaches 4 regulated surface(s) and 3 scheduled job(s) beyond that scope
```

## Selected Entire track and why Entire is essential

**Track 2 — Build with Graph Intelligence.**

Entire Graph is not a logging sidecar here; it is the evidence layer the product is built
on. Remove it and there is no product.

| What the product needs | Which Entire Graph surface supplies it |
| --- | --- |
| Every resolved call relationship in the repo | `entire graph edges --relation CALLS` (NDJSON stream) |
| A per-edge confidence and resolution quality | the `confidence` / `resolution` fields on each relation record |
| The call site that proves each edge | the `evidence[]` array — `{file_path, start_line, end_line}` |
| An independent second opinion on our traversal | `entire graph impact --symbol X` |
| The symbols a real commit changed | `entire graph diff --base A --head B --json` |
| Whether the answer can be trusted | `capabilities`, plus `partial_failures` in the summary record |

The decisive one is `edges`. `impact` is bounded at depth ≤ 2 by design; the regulated
chain in this codebase is **five hops** deep, so the one-shot command cannot see the end of
it. Streaming the full relation set and running our own reverse BFS over it is what makes
the product possible — and it is only possible because the provider will hand over the
whole resolved graph with evidence attached.

## Architecture and main workflow

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
scripts/capture-graph-evidence.sh
docs/graph-evidence/         raw provider output, teed verbatim
```

**Workflow:** semantic diff (or a named symbol) → reverse-dependency closure over the
graph's CALLS relations → RBI rule overlay → deterministic score → test selection →
report. JSON is the single source of truth; the terminal view is a renderer over it, which
is why a CI/PR-comment output is a small addition rather than a rewrite.

### Four invariants

1. **Evidence-first.** No claim exists without `{source, file, line, confidence, resolution,
   verified}`. The guide warns twice against presenting uncertain graph output as fact, so
   that rule lives in the type, not in the renderer's good manners.
2. **The score is a pure function in our code**, never model output. Same input, same
   score. That reproducibility is the only reason it can sit in a merge gate.
3. **Verification means two independent derivations.** Entire Graph is primary; a local
   `ast` resolver derives every edge again. Both agree → `VERIFIED`. One only →
   `UNVERIFIED`, rendered greyed and never asserted. Self-corroboration from the same
   source is explicitly *not* verification — `test_the_same_source_twice_is_not_verification`
   pins that.
4. **JSON first, renderers on top.**

### The risk model (`blastradius/core/risk.py`)

```
+40  reaches a critical regulated surface
+20  reaches a high-severity regulated surface
+12  per scheduled job that ships the change unattended
 +3  per direct caller          +1  per transitive caller
+15  changed symbol has no test anywhere in its blast radius
-10  every reached regulated surface has test coverage
bands: <20 LOW · 20-49 MEDIUM · 50-74 HIGH · >=75 CRITICAL, clamped 0-100
```

Every term prints with its contribution and the evidence that triggered it.

Three bands, one tool, one codebase — all real output:

| Change | Result |
| --- | --- |
| `recovery.dunning._format_sms_text` | **LOW 3/100** — 3 symbols, 0 surfaces, 0 jobs |
| `core.money.annualise_monthly` | **HIGH 52/100** — 16 symbols, 3 surfaces, 1 job |
| `pricing.fees.penal_charge` | **CRITICAL 100/100** — 24 symbols, 4 surfaces, 3 jobs |

The middle row is the argument. Its structural terms alone come to 22 — a generic impact
tool would call it moderate. The RBI overlay takes it to 52, because `annualise_monthly` is
what turns "3% per month" into the annual figure a borrower must be shown.

## Entire Graph findings and verification

Raw provider output is committed under `docs/graph-evidence/`, captured by
`scripts/capture-graph-evidence.sh`. Nothing there is hand-edited.

| File | What it is |
| --- | --- |
| `00-capabilities.json` | provider capability registry — confirms Python is `semantic`, not inventory-only |
| `01-search-penal-charge.txt` | ranked search (recorded **with** its LOW CONFIDENCE banner — see below) |
| `02-def-penal-charge.txt` | definition lookup with the source span |
| `03-impact-pre-change.{txt,json}` | **impact analysis before the high-risk change** |
| `03b-neighbors-callers.txt` | precise two-hop caller relationships |
| `04-edges-calls.ndjson` | the CALLS relation stream Blast Radius actually walks |
| `05-edges-dataflows.ndjson` | the DATA_FLOWS stream behind the orientation finding below |
| `06-final-semantic-diff.json` | **final semantic diff analysis of the submitted implementation** |
| `07-blast-radius-report.txt` | the decision that evidence produced |

### Finding 1 — the graph's DATA_FLOWS relation carries two opposite orientations

Including `DATA_FLOWS` alongside `CALLS` looked like a free improvement to recall. It put
**48 symbols** in `penal_charge`'s blast radius, including `to_money` at hop 1 — which
`penal_charge` *calls*. A callee is not a dependent.

The cause is in the provider's own `reason` field:

```
to_money -> penal_charge          "callee return value flows into caller return value"
overdue_projection -> penal_charge "caller parameter forwarded into callee argument"
```

The first is **reversed** relative to CALLS; the second is not. We caught it by
cross-checking against `entire graph impact`, which labels the same edges `<-` in and `->`
out. `_orient()` in `adapters/entire_graph.py` now normalises both forms, and four unit
tests pin the behaviour — including one asserting that an *unrecognised* reason keeps the
stated direction rather than guessing.

`DATA_FLOWS` is nevertheless **off by default** (`--include-data-flows` opts in). An
inflated blast radius that is not real is worse for this product than a smaller one that
is. With CALLS only, the radius is 24 symbols and every one of them is corroborated.

### Finding 2 — completeness has to be scoped to the analysed subtree, not just reported

Entire Graph reports parse completeness for the **whole repository**. This fork is a
polyglot Go codebase of ~690 files with vendored tree-sitter grammars; the lending fixture
is a 25-file Python subtree. A repository-wide "degraded" verdict therefore says almost
nothing about whether *this* blast radius is trustworthy.

During development, against a provider built from this fork's `cmd/entire-graph` at HEAD,
the snapshot did come back degraded — 684/686 files, with `E_PARSE_ERROR` on vendored C++
grammar headers and `E_MINIFIED` on our own single-line JSON evidence captures. Hiding that
would be dishonest; letting it discredit every finding would be useless. So the report
scopes it, via `GraphRun.failures_in()` and `scope_note()`:

```
scope:    5 diagnostic(s) elsewhere in the repository, 0 inside
          fixtures/lending-platform; Python is analysed semantic
```

`neighbors` corroborates this in the provider's own words: *"0 of 69 Python files failed to
parse … plus 5 diagnostics in other languages (C++ 5), which cannot affect this answer."*

**On the released provider actually used for this submission (`entire graph` v0.4.0) the
repository parses clean**, and the same line reports what is true:

```
provider: entire-graph v0.4.0 (schema 1.1)
parsed:   681/681 files
scope:    no parse failures; Python is analysed semantic
```

Two fixes contributed to that: `docs/graph-evidence/` was added to `.graphignore`, because
captured provider output is not source and indexing it made the tool feed on its own
exhaust; and v0.4.0 handles the vendored grammar headers that the source build did not.

The scoping code stays regardless. When a parse failure *does* land inside the analysed
subtree, the same line turns red and states that the blast radius is incomplete — which is
the only honest thing to print at that point.

### Finding 3 — ranked search over a polyglot fork is honest about not knowing

`search --query "penal charge calculation"` does **not** rank the fixture first; it returns
a `LOW CONFIDENCE … the ranking did not choose` banner. That is correct behaviour — the
fork is a 686-file Go codebase and the fixture is a small Python subtree. We kept the
banner in the evidence rather than swapping in a query that flattered the tool, and the
product relies on `def` / `neighbors` / `edges` for the lookups that must be precise.

### Verification, end to end

- **Two independent derivations.** All **24** reached symbols on the CRITICAL demo are
  derived by both Entire Graph and the local `ast` resolver. `evidence: entire-graph,
  local-ast` and `unverified_count: 0`.
- **Against the provider's own second opinion.** `test_our_traversal_agrees_with_the_
  providers_own_impact_command` asserts our depth-1 callers intersect `entire graph impact`'s.
- **Against tests, not just source.** Blast Radius selected
  `tests/test_fees.py::test_penal_charge_compounds_across_months`. Running it on the
  changed code **fails** — and it fails because it was asserting the compounding behaviour
  the RBI circular prohibits. The graph pointed at the test; the test proved the change was
  real.
- **Two RBI rules are deliberately left unverified.** `foreclosure-charges` and
  `regulatory-return` carry `confidence: medium` and a `verify:` note, and render as
  `UNVERIFIED` with the reason attached. This is not an oversight. The scope of the
  foreclosure-charge bar has been widened over time and we have not confirmed the current
  applicable entity classes, so the product declines to assert it.

## Noon Curveball: what changed and how we adapted

> _To be completed after 12:00. The constraint has not been received at the time of
> writing; nothing here is pre-written._
>
> Planned protocol: freeze and commit at 11:45 · pre-noon checkpoint · close the agent
> session · read the card and write down "the smallest complete response is…" · start a
> **fresh** session and make it reconstruct from the checkpoint before editing · run
> `entire graph impact` on the affected area **before** changing it, teed to
> `docs/graph-evidence/` · implement the smallest complete response · add a test that fails
> on the old commit and passes on the new · checkpoint the response.

## Checkpoint links and what each checkpoint proves

> _"Link" is the wrong word for what Entire CLI 0.10.5 offers and this section does not
> pretend otherwise: there is no `open`, `browse` or `url` verb, and `origin` is an
> `entire://` transport a browser cannot resolve. A checkpoint reference here is a command
> run against an ID. Milestones 3 and 4 are commitments, not findings — the Curveball card
> arrives at 12:00._

**Why a checkpoint ID is evidence and not a self-report.** Entire's git hooks write it, not
this document: a commit made while an agent session is bound to this worktree carries an
`Entire-Checkpoint:` trailer, and `entire checkpoint explain <id>` resolves that ID to the
session's prompts, token counts and touched files (flags per `entire checkpoint explain
--help`; we report its documented surface, not its internals). Nothing edited into this file
can back-write one, which is the only reason the IDs are worth citing.

**Disclosed before a judge finds it: the first four submission commits carry no trailer.**
The hooks were installed at 11:17 and those commits were made at 11:21, before this
document's session existed, so none was stamped — command 3 below prints empty brackets for
all four. Separately, `git log --all` in this fork carries **208** git-parsed
`Entire-Checkpoint:` trailers (277 by raw line-grep, which also counts trailers quoted
inside upstream merge messages). **Every one of them is inherited `entireio` history and
none is ours.** They are genuine checkpoints — `entire graph checkpoint f08be4bb1d35 --json`
resolves one from git alone, no account needed, which is a fair demonstration of the
provider — but citing one as Blast Radius evidence would be a false claim.

| # | Milestone | Status | What it proves |
| --- | --- | --- | --- |
| 1 | Initial understanding and intended architecture | written | the four invariants were chosen up front, not rationalised afterwards |
| 2 | Last stable state before the Noon Curveball | written | a runnable product existed before the constraint arrived |
| 3 | Response to the Noon Curveball | not yet | a fresh session reconstructed the project from checkpoint context and changed a real decision |
| 4 | Final implementation and verification | not yet | what shipped, what was verified, and what remains unverified |

**What backs each row.** The written body is an ordinary file in the repo — no CLI, no
account and no network needed to read it. The ID column is filled only from
`entire checkpoint list --json`; none is ever typed by hand.

| # | Written body | Commit | Entire checkpoint ID |
| --- | --- | --- | --- |
| 1 | `docs/checkpoints/01-initial-understanding.md` | `8d48561`, tagged `demo-before` | none — predates the session |
| 2 | `docs/checkpoints/02-pre-curveball-stable.md` | `dc5b070`, on `origin/blast-radius` | none — predates the session |
| 3 | not written — the card arrives at 12:00 | pending | pending |
| 4 | not written — depends on milestone 3 | pending | pending |

`origin/main` is still the upstream fork point `3a2a715`: the branch is protected and the
push was refused, so the submission lives on `origin/blast-radius` (`dc5b070`) with the demo
change on `origin/demo/penal-charge-fix` (`aa8f3b6`, tagged `demo-after`). A judge who
clones and stays on `main` sees none of this work. The three tags are lightweight, so
`--follow-tags` does not carry them; they were pushed by explicit ref.

### How to verify these yourself

```bash
# 1. live checkpoint count for the current branch — branch-scoped, so read the branch line
entire checkpoint list
entire checkpoint list --json

# 2. resolve a record, by ID or via the commit carrying the trailer
entire checkpoint explain <id>                    # exits 1 if the ID is unknown
entire checkpoint explain --commit HEAD --short   # exits 0 even when no trailer is present

# 3. our own disclosure: which submission commits carry a trailer
git log 3a2a715..main 3a2a715..demo/penal-charge-fix \
  --format='%h %s [%(trailers:key=Entire-Checkpoint,valueonly)]'

# 4. entity-level diff for any checkpoint ID, from git alone — no account, works today
entire graph checkpoint f08be4bb1d35 --json

# 5. the milestone bodies, which need nothing installed at all
ls docs/checkpoints/
```

Read the output of these rather than their exit status: `entire checkpoint explain --commit
HEAD --short` exits `0` while printing `✗ No associated Entire checkpoint`. If command 1
reports checkpoints that this section's ID column does not list, the column is stale and
this section is the thing to distrust.

## Setup, run and test instructions

```bash
./setup.sh                 # creates .venv (PEP 668 safe) and installs deps

# Entire Graph provider. The adapter prefers the official plugin and falls back
# to a locally built one only if the Entire CLI is absent.
entire plugin install graph && entire graph version      # official plugin (v0.4.0)
make graph-bin                     # fallback: build from this fork (Go 1.26+)

make test                  # 31 product tests + 21 fixture tests
make demo                  # the three bands, green -> amber -> red
make demo-diff             # review a committed change from its semantic diff
make gate                  # merge gate: exits non-zero on HIGH/CRITICAL
make evidence              # re-capture docs/graph-evidence/ from the live provider
```

Single change, ad hoc:

```bash
./.venv/bin/python -m blastradius.cli impact --symbol pricing.fees.penal_charge
./.venv/bin/python -m blastradius.cli impact --base main --json
```

## Databricks use, data sources and limitations

Not opted in. No Databricks resources are used.

**Data provenance:** `fixtures/lending-platform/` is **synthetic**, written for this
project. It contains no personal data, no customer data and no company code. The RBI
obligations in `blastradius/rules/rbi_surfaces.yaml` are paraphrased from public circulars
and each carries its citation and a confidence level; two are explicitly marked as needing
verification and render as such.

## Known limitations and next steps

**Limitations, stated plainly:**

- The rulebook maps obligations to **module and symbol names**. Rename `disclosure/kfs.py`
  without updating the YAML and the surface silently stops matching. A rule that matches
  nothing should be a hard error; today it is not.
- `DATA_FLOWS` orientation is derived from the provider's free-text `reason` field. It is
  normalised and tested, but a wording change upstream would need the constant updated —
  which is why the relation is opt-in rather than default.
- The local `ast` verifier cannot resolve method calls through a receiver (`loan.emi()`),
  so edges the graph finds there stay `UNVERIFIED` rather than `VERIFIED`. That is the
  honest outcome, but it understates coverage.
- Reverse BFS is capped at 8 hops (`--max-hops`), and the risk weights are constants in
  `risk.py` rather than a config file.
- Ranked `search` over a large polyglot fork does not surface a small embedded fixture; see
  Finding 3.
- Two RBI citations are unverified by design (see above).

**Next steps toward production readiness:**

1. Fail the run when a rule matches zero symbols — a silently dead rule is worse than no rule.
2. Emit a PR comment / SARIF from the same report object, so the gate explains itself where
   the decision is actually made.
3. Move the risk weights into `config.yaml` so a team can tune them without editing code,
   and record the weights used in the report for auditability.
4. Widen the verifier to resolve receiver method calls, closing the `UNVERIFIED` gap.
5. Point it at a real repository with a real rulebook rather than a synthetic fixture.

## Honesty notes

- Implementation began after the 09:00 kickoff. Part of the scaffold (the risk model, the
  evidence types, the fixture and the rulebook) was written **outside** this clone, before
  the fork existed, and moved in afterwards. Nothing is backdated. Everything that makes
  Entire load-bearing — the calibrated adapter, the traversal over the relation stream, the
  semantic-diff entry point, the completeness scoping and the graph evidence — was written
  inside the clone against the live provider.
- Early calibration was done against a provider built from this fork's own
  `cmd/entire-graph` (`make graph-bin`, version string `dev`), because the Entire CLI was
  not yet installed. **Everything recorded in this submission was then re-run against the
  official plugin, `entire graph` v0.4.0**, in the Entire mirror clone. The adapter's
  `resolve_invocation()` prefers `entire graph` whenever the CLI is present and falls back
  to a locally built provider only when it is not; the schema major and minor (1.1) are
  identical across both, which is why the calibration carried over unchanged.
- You remain accountable for agent-written code: the demo owner should be able to walk
  through `blastradius/core/risk.py` and `_orient()` in `adapters/entire_graph.py` line by
  line, because those two are where the product's trust claims actually live.
