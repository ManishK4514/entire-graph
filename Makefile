PY := ./.venv/bin/python
SR := fixtures/lending-platform
SRD := fixtures/lending-platform-dynamic

setup:
	./setup.sh

# Build the Entire Graph provider from this fork. Used when the Entire CLI is
# not installed on the machine; `entire graph` is preferred when it is.
graph-bin:
	go build -o .blastradius/entire-graph-dev ./cmd/entire-graph
	@echo "provider: $$(.blastradius/entire-graph-dev version)"

test:
	$(PY) -m pytest blastradius/tests -q
	cd $(SR) && PYTHONPATH=. ../../.venv/bin/python -m pytest -q
	cd $(SRD) && PYTHONPATH=. ../../.venv/bin/python -m pytest -q

# The three bands, from one tool, on one codebase.
demo-green:
	$(PY) -m blastradius.cli impact --symbol recovery.dunning._format_sms_text

demo-amber:
	$(PY) -m blastradius.cli impact --symbol core.money.annualise_monthly

demo-red:
	$(PY) -m blastradius.cli impact --symbol pricing.fees.penal_charge \
	  --intent "refactor penal charge rounding only, no downstream change"

# The real workflow: a committed change, reviewed from its semantic diff.
demo-diff:
	$(PY) -m blastradius.cli impact --base demo/penal-charge-fix~1 --head demo/penal-charge-fix \
	  --intent "make penal charge non-compounding; contained to pricing.fees"

# The curveball case: a repository static analysis cannot fully resolve. The
# radius is EMPTY and the band is LOW, and the tool refuses to let that read as
# safe -- it names the four unresolved sites and what to do about each.
demo-partial:
	$(PY) -m blastradius.cli impact --symbol pricing.fees.late_payment_charge \
	  --source-root $(SRD) \
	  --intent "adjust penal charge rounding; nothing downstream"

demo: demo-green demo-amber demo-red

# Merge gate. Exits non-zero on HIGH or CRITICAL.
gate:
	$(PY) -m blastradius.cli impact --base demo/penal-charge-fix~1 --head demo/penal-charge-fix --fail-on-critical --json > /dev/null \
	  && echo "gate: PASS" || echo "gate: BLOCKED (exit $$?)"

# Same gate, on the unresolvable repository. Exit 2, not 0: "we could not see
# enough to clear this" is a different answer from "this is clear".
gate-partial:
	$(PY) -m blastradius.cli impact --symbol pricing.fees.late_payment_charge \
	  --source-root $(SRD) --fail-on-critical --json > /dev/null \
	  && echo "gate: PASS" || echo "gate: BLOCKED (exit $$?)"

evidence:
	./scripts/capture-graph-evidence.sh

.PHONY: setup graph-bin test demo demo-green demo-amber demo-red demo-diff \
	demo-partial gate gate-partial evidence
