# lending-platform-dynamic — a fixture that static analysis cannot fully resolve

Synthetic, like `fixtures/lending-platform/`. No real, customer or employer code.

This one exists to reproduce the Noon Curveball condition: a repository where the
call graph is genuinely incomplete, not because anything failed to parse — every
file here parses cleanly — but because the relationships are formed at runtime.

Three patterns, each in a place a real lending codebase actually puts them:

| Pattern | Where | Why a real codebase does this |
| --- | --- | --- |
| registry dispatch | `disclosure/kfs.py` — `CHARGE_RULES[code](loan)` | which charges appear on a KFS is product configuration, not code |
| reflection | `jobs/daily_kfs_batch.py` — `importlib.import_module` + `getattr` | the batch renderer is named in a job config |
| generated module | `reporting/rbi_return.py` — `from generated.cadence import ...` | filing cadence is emitted from the regulator's published calendar |

**The point of the fixture.** `pricing.fees.late_payment_charge` has **no static caller
whatsoever** here. A reverse-dependency walk over `CALLS` finds nothing, scores it
LOW, and a merge gate that trusts the radius lets it through. In fact it feeds the
Key Fact Statement on every loan, through `CHARGE_RULES`, and ships nightly through
a job that resolves its renderer by name.

That is the whole curveball in one symbol: the graph is not wrong, and the answer
is still dangerous, because the question "what calls this?" was answered completely
and the question the reviewer needed answered was "what could reach this?"
