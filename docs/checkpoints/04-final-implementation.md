# Checkpoint 4 — Final implementation and verification

What shipped in response to the Noon Curveball (Track 2, *"Graph is evidence, not an
oracle"*), what was verified and how, and what remains unverified on purpose.

[`03-curveball-response.md`](03-curveball-response.md) holds the reconstruction from
checkpoint context, the graph analysis run **before** any edit, and the invalidated
assumption. This document is the design that came out of it.

---

## The revised design in one sentence

A blast radius is a **lower bound**, so the report now carries a **completeness axis
orthogonal to the score**: the number stays a pure function of what was found, and the tool
states separately — with a `file:line` and an action for every unresolved site — whether
what was found is all there is.

## What changed, by seam

The seam was the one Checkpoint 2 predicted, and the graph confirmed it before any edit:
`edges` has 4 direct callers, `Provenance` has 12, and the consumers sit in `adapters/` and
`core/`. Nothing was rewritten; the traversal, the rulebook, the test selector and the risk
weights are as they were. `graph_model.py` gained one accessor and one retained field.

| File | Change | The intent behind it |
| --- | --- | --- |
| `core/evidence.py` | `BlindSpot`; `Tier` / `Completeness` enums; `tier()` on `Edge` and `Finding`; `STRUCTURAL_RESOLUTIONS` | "we could not see this" is a claim, so it carries provenance like every other claim |
| `adapters/local_ast.py` | records the call sites `_resolve()` drops, in six kinds, each with a `verify` action | the graph cannot report an edge it never saw — absence has to be detected at the source |
| `core/impact.py` | `reconcile_blind_spots()`, `scope_blind_spots()`, deduped evidence, four new report fields | a site only one source is blind to is not a blind spot |
| `core/risk.py` | a **zero-contribution** term, `score_is_floor`, `completeness`; **arithmetic untouched** | every term counts something *found*, so anything unfound can only push the score down |
| `cli.py` | `--allow-partial`; gate exit **2**; intent no longer confirmable by silence; absent provider is a blind spot; `disambiguation_required` honoured | "clear" and "could not see" are different answers and must not share an exit code |
| `render/cli_report.py` | tier counts, blind-spot section, verification path, qualified scope line | a reader has to be able to tell three kinds of claim apart |

## The six blind-spot kinds

| Kind | Trigger | Reconcilable? |
| --- | --- | --- |
| `dynamic-dispatch` | `HANDLERS[k](x)`, `factory()(x)`, a callable held in a variable or parameter, `super().m(x)` | **No** — target unbounded |
| `reflection` | `getattr` with a non-literal name, `importlib.import_module` (including through an alias), `eval` / `exec` | **No** |
| `star-import` | `from m import *` | **No** |
| `missing-module` | first-party package, module absent from disk (generated code) — all four import forms | **No** |
| `provider-unavailable` | Entire Graph did not run (`--offline`, or the provider is missing) | **No** |
| `receiver-method` | `obj.method()`, receiver type unknown, attribute names a real definition | **Yes** — it has a name another source can be checked for |

**Precision was designed in, because a detector that cries wolf gets switched off.**
`getattr(loan, "emi")` with a literal is statically knowable. `rows.append(...)` and
`Decimal(v).quantize(...)` name nothing first-party. `self.emi()` where `emi` is visible in
the same module is knowable. `vars(obj)` dispatches to nothing. None are flagged; each has a
test. Unresolved bare names that are builtins or stdlib — **57** of them in the main fixture
— are counted and disclosed as a number, not listed.

---

## Verification

**95 tests pass** — 72 product (was 31), 21 original fixture, 2 dynamic fixture. `make test`
is green end to end.

### Existing behaviour is preserved — measured, not asserted

| Change | Before the curveball | After |
| --- | --- | --- |
| `recovery.dunning._format_sms_text` | LOW 3/100, 3 symbols | **LOW 3/100, 3 symbols, `complete`** |
| `core.money.annualise_monthly` | HIGH 52/100, 16 symbols | **HIGH 52/100, 16 symbols, `complete`** |
| `pricing.fees.penal_charge` | CRITICAL 100/100, 24 symbols | **CRITICAL 100/100, 24 symbols, `complete`** |

`unverified_count` is **0** on all three, as before. The main fixture's two `receiver-method`
candidates are **reconciled away** — Entire Graph resolves both (`type_inferred`) — and the
report now says which site was dismissed by which edge rather than silently dropping it.

The new tier counts are the one place the report says more than it used to: on the CRITICAL
demo, 25 `confirmed`, 1 `heuristic`, 2 `needs-verification`. The heuristic one is an edge the
provider itself resolved by name; the two needing verification are the RBI rules that have
always carried a `verify` note.

### The new behaviour is demonstrated on a fixture, not described

`fixtures/lending-platform-dynamic/` — synthetic, no real or employer code. Every file parses
cleanly; the relationships form at runtime. `pricing.fees.late_payment_charge` has **no
static caller at all**, verified against the live provider (`docs/graph-evidence/11-*`) and
pinned by a test that fails if a static walk ever does find one — so the fixture cannot
silently stop demonstrating anything.

Before: LOW band, empty radius, gate exit 0.
After: `PARTIAL ANALYSIS — score is a FLOOR`, five sites with `file:line` and an action each,
`UNKNOWN` on the intent check, gate **exit 2**.

---

## What an adversarial review caught before this shipped

Six independent reviewers, one per dimension, each finding sent to three further agents
prompted to **refute** it. It found real defects in the first cut of this change, which is
worth recording — a checkpoint that lists only what went right is not evidence of anything.

**The scoping rule was inverted** (three reviewers, independently). The radius is a
*reverse* walk, so for a missing edge `owner -> target` the question is whether **target** is
in the radius. The first version keyed on **owner** — which kept exactly the spots that could
not change the answer and discarded exactly the ones that could. A hole capable of hiding a
route into the Key Fact Statement would have been dropped as "out of scope" and the report
would have said `complete`. Fixed; both directions pinned by
`test_a_localised_spot_is_scoped_by_its_TARGET_not_its_owner`.

**Reconciliation was silencing holes on a bare name match.** Any same-named method on any
unrelated type could dismiss a real blind spot — the exact bare-name matching the rest of the
product refuses to trust. It now requires the covering edge to leave the same enclosing
symbol *and* carry evidence in the same file. And a dismissal used to be written to an object
that was then discarded; dismissals are now returned, serialised as `reconciled_blind_spots`,
and printed. **A decision about what not to tell you is still a decision.**

**The tier function failed open.** A three-string denylist meant any resolution the provider
added later counted as structural. It is now an allowlist — an unrecognised resolution is
heuristic. And `tier()` checked only the *primary* source's resolution while
`SymbolGraph.add` discarded the corroborator's, so an `exact` edge corroborated **only by our
own bare-name guess** was tiered `confirmed` — precisely what that file's own docstring says
must not happen.

**The detector had four blind spots of its own**: a callable held in a variable (the
commonest dispatch shape in Python — and it was being counted as stdlib noise), chained and
`super()` calls (not an edge, not a spot, not even counted), three of the four ways to import
a generated module, and reflection reached through an import alias. All four are fixed and
tested.

**`--offline` claimed a complete analysis** — printing `completeness: complete` three lines
above `single_sourced: true`, reassuring one first. The absent provider is now a first-class
blind spot.

**Evidence counts were inflated roughly threefold.** `all_edges` flattened the BFS proof
paths, and each reached symbol carries the *full* path to the root, so an edge near the root
was counted once per path through it — 78 evidence items for a 24-symbol radius. Deduping by
edge identity also corrected `unverified_count` and the conflicts list.

### Two bugs the work found outside itself

**In our own adapter.** The provider correctly refused an ambiguous `impact` query —
`disambiguation_required: true`, `callers.entries: null` — and `impact_callers()` read it as
*"nothing depends on this."* The same bug class as the curveball, in our own code: a refusal
treated as an answer of zero. It now honours the flag, narrows with `--file`, and raises
`EntireGraphAmbiguousSymbol` otherwise. Caught by an existing test going red.

**In the evidence capture script.** `grep -F "fixtures/lending-platform"` also matches
`fixtures/lending-platform-dynamic/`, so the second fixture's relations were leaking into the
first fixture's committed evidence stream. Fixed with a trailing slash.

### One regression the new fixture itself caused

Adding a fixture that also defined `penal_charge`, `to_money` and five other names made those
names ambiguous repo-wide. The provider behaved correctly — it downgraded the affected edges
from `import_resolved` to `name_only` — but the **original** demo lost a corroborated caller
and its `unverified_count` went 0 → 1. The fixture's symbols were renamed so the trees no
longer collide; its demonstration does not depend on rulebook matches, because its radius is
empty by design, so this cost nothing.

It is recorded because it is the curveball's thesis once more: **the graph's answer changed
because the repository changed around it, not because the code under review did.**

---

## What remains unverified, stated plainly

- **Two RBI rules** (`foreclosure-charges`, `regulatory-return`) still carry
  `confidence: medium` and render `needs-verification` with the reason attached. Unchanged,
  and still the product declining to assert what it cannot stand behind.
- **The detector is a lower bound on blind spots, not a complete list.** It catches the
  patterns it knows. `completeness: complete` means *"no blind spot was detected"*, which is
  a weaker claim than *"there are none"* — and after this curveball, that distinction is
  exactly the one this product exists to make. Saying it here rather than discovering it on
  stage is the point of this section.
- **Scoping a localised spot uses a NAME match against the radius**, deliberately loose. We
  do not know what an unresolved call resolves to — that is what makes it a blind spot — so
  it errs toward reporting a hole that may not exist. That is the safe direction; the unsafe
  one is letting an incomplete radius look complete.
- **`dropped_external` is a count, not a list** — 57 bare names in the main fixture,
  overwhelmingly builtins and stdlib, disclosed as a number and not individually audited.
- **Reverse BFS remains capped at 8 hops**, and the risk weights remain constants in
  `risk.py` rather than configuration.

## What we would do next

1. Enumerate dispatch tables where they are literal, so the "re-run for each entry" action is
   one command rather than manual work.
2. Use `USES_TYPE` / `REFERENCES` relations to close the `Verification`-style gap — a symbol
   referenced but never called is exactly what `CALLS` alone cannot see.
3. Runtime corroboration: a coverage trace from the selected tests would resolve dispatch
   edges definitively, turning the verification path from an instruction into evidence.
4. Fail the run when a rulebook entry matches zero symbols — a silently dead rule is the same
   bug class this checkpoint is about.
