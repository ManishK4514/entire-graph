# Checkpoint 2 — Last stable state before the Noon Curveball

## Current intent (unchanged from Checkpoint 1)

Blast Radius: impact-aware change review for regulated lending code. Entire Graph supplies
the structural evidence; a codified RBI rulebook supplies the meaning; a deterministic
function in our code supplies the verdict; every claim points at a `file:line`.

## What is completed and working

End-to-end and runnable from a clean checkout. **52 tests pass** — 31 product, 21 fixture.

- `blast impact --symbol S` and `blast impact --base REF` both work. The second reads the
  changed symbols out of `entire graph diff --base A --head B --json`, so the tool works on
  a real commit rather than only on a hand-named symbol.
- Three distinct bands from one tool on one codebase, all real output:
  `recovery.dunning._format_sms_text` → **LOW 3/100**;
  `core.money.annualise_monthly` → **HIGH 52/100** (structural terms alone are 22 — the RBI
  overlay is what takes it to 52); `pricing.fees.penal_charge` → **CRITICAL 100/100**
  (24 symbols, 4 regulated surfaces, 3 unattended jobs).
- `make gate` exits non-zero on HIGH/CRITICAL. `make evidence` re-captures raw provider
  output into `docs/graph-evidence/`.
- The intent overlay fires: stated *"contained to pricing.fees"* against ACTUAL *"reaches 4
  regulated surface(s) and 3 scheduled job(s) beyond that scope"*.

## The evidence that changed our approach

**Assumption 1 from Checkpoint 1 is confirmed.** `capabilities --json` reports Python in
`semantic_languages`. The fixture is visible; no rewrite needed.

**The adapter is calibrated** against the live provider (schema 1.1) — the top risk from
Checkpoint 1 is closed. Commands, flags and JSON keys were read off real output, which is
committed verbatim under `docs/graph-evidence/`.

**A finding that changed the design: `DATA_FLOWS` carries two opposite orientations.**
Adding it alongside `CALLS` looked like free recall. It put 48 symbols in `penal_charge`'s
blast radius — including `to_money`, which `penal_charge` *calls*. A callee is not a
dependent. The provider's own `reason` field distinguishes them: *"callee return value
flows into caller return value"* is reversed relative to CALLS, *"caller parameter
forwarded into callee argument"* is not. We caught it by cross-checking against
`entire graph impact`, which labels the same edges in/out. `_orient()` now normalises both,
four unit tests pin it, and **DATA_FLOWS is off by default** — an inflated blast radius
that is not real is worse for this product than a smaller one that is. With CALLS only the
radius is 24 symbols and all 24 are corroborated by both sources.

**A second finding: degradation must be scoped, not just reported.** The provider calls
this fork DEGRADED (684/686 files). Hiding that is dishonest; letting it discredit every
finding is useless. The report now scopes it: *"5 diagnostic(s) elsewhere in the
repository, 0 inside fixtures/lending-platform; Python is analysed semantic."* When a
failure does land inside the analysed subtree, the same line turns red and says the radius
is incomplete.

**Verification is real, not decorative.** All 24 reached symbols on the CRITICAL demo are
derived independently by Entire Graph and by a local `ast` resolver. Blast Radius selected
`tests/test_fees.py::test_penal_charge_compounds_across_months`; running it against the
demo change **fails**, and it fails because it was asserting the compounding behaviour the
RBI circular prohibits. The graph pointed at the test; the test proved the change was real.

## What is deliberately unfinished

- Two RBI rules (`foreclosure-charges`, `regulatory-return`) carry `confidence: medium` and
  render as UNVERIFIED with the reason attached. **This is the product refusing to assert
  what it cannot stand behind, not a gap to be closed.**
- No HTML renderer yet. JSON-first means it is a view, not a rewrite.
- The local `ast` verifier cannot resolve receiver method calls (`loan.emi()`), so edges the
  graph finds there stay UNVERIFIED. Honest, but it understates coverage.

## Open technical risks

1. `DATA_FLOWS` orientation is derived from the provider's free-text `reason`. Normalised
   and tested, but an upstream wording change would need the constant updated — which is
   the reason the relation is opt-in rather than default.
2. A rulebook entry that matches zero symbols is silently dead. It should be a hard error.
3. Risk weights are constants in `risk.py`, not configuration.
4. The graph provider used for recorded evidence was built from this fork's own
   `cmd/entire-graph` (`make graph-bin`, version `dev`) because the Entire CLI was not
   installed on the build machine. Same code the plugin ships; `resolve_invocation()`
   prefers `entire graph` whenever the CLI is present.

## Where the seams are, if the Curveball hits the architecture

`adapters/entire_graph.py` is the only caller of the provider. `render/` is a view over one
report dict. `core/` is pure functions with unit tests. Reach for a seam before a rewrite.
