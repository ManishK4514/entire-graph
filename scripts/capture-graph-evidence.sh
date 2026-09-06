#!/usr/bin/env bash
# Capture the Entire Graph evidence the Buildathon requires, verbatim.
#
#   1. a graph search / definition lookup
#   2. a relationship / impact analysis BEFORE a high-risk change
#   3. a final semantic diff analysis of the submitted implementation
#
# Every file here is raw provider output. Nothing is edited by hand; that is
# the point of teeing it.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=docs/graph-evidence
mkdir -p "$OUT"

# Prefer the official plugin; fall back to a provider built from this fork.
if command -v entire >/dev/null 2>&1; then
  G=(entire graph)
elif [ -x .blastradius/entire-graph-dev ]; then
  G=(./.blastradius/entire-graph-dev)
else
  echo "no Entire Graph provider found; run 'make graph-bin' or install the Entire CLI" >&2
  exit 1
fi
echo "provider: ${G[*]}  ($("${G[@]}" version 2>/dev/null))"

SR=fixtures/lending-platform
# Filters below use "$SR/" with the trailing slash on purpose: plain "$SR" also
# matches fixtures/lending-platform-dynamic/, which would mix the two fixtures'
# relations into one another's evidence files.
# The "submitted implementation" is everything this project added on top of the
# upstream fork point, so that is what the final semantic diff must analyse.
BASE="${1:-upstream-base}"

echo "== 00 capabilities =="
"${G[@]}" capabilities --json > "$OUT/00-capabilities.json"

echo "== 01 search =="
# Recorded verbatim, low confidence and all. The fork is a 686-file Go
# codebase and our regulated fixture is a small Python subtree, so ranked
# search over the whole repo does NOT put the fixture on top -- and the
# provider says so itself with a LOW CONFIDENCE banner. We keep that banner in
# the evidence instead of hiding it, and use def/neighbors/edges (below) for
# the precise lookups the product actually depends on.
"${G[@]}" search --repo . --profile full --format text --top-k 5 \
  --query "penal charge calculation" \
  > "$OUT/01-search-penal-charge.txt" 2>&1

# From here on, penal_charge MUST be qualified with --file. Two fixtures define it
# (the original and the deliberately-unresolvable one added for the Noon Curveball),
# and the provider correctly refuses to answer an ambiguous name -- it returns the
# definition LIST instead of the analysis. Captures 02, 03 and 03b silently became
# definition lists the first time this ran after the second fixture landed, which is
# the same lesson the curveball taught, arriving by post: a confident-looking output
# that does not answer the question you asked.
FEES="fixtures/lending-platform/pricing/fees.py"

echo "== 02 definition lookup =="
"${G[@]}" def --repo . --symbol penal_charge --file "$FEES" \
  > "$OUT/02-def-penal-charge.txt" 2>&1

echo "== 03 impact BEFORE the high-risk change =="
"${G[@]}" impact --repo . --worktree --symbol penal_charge --file "$FEES" \
  --depth 2 --format text > "$OUT/03-impact-pre-change.txt" 2>&1
"${G[@]}" impact --repo . --worktree --symbol penal_charge --file "$FEES" \
  --depth 2 --format json > "$OUT/03-impact-pre-change.json" 2>&1

echo "== 03b neighbors: the precise relationship lookup =="
"${G[@]}" neighbors --repo . --worktree --symbol penal_charge --file "$FEES" \
  --relation CALLS --direction in --depth 2 --format text \
  > "$OUT/03b-neighbors-callers.txt" 2>&1

echo "== 04 the relation stream Blast Radius actually walks =="
"${G[@]}" edges --repo . --worktree --relation CALLS \
  | grep -F "$SR/" > "$OUT/04-edges-calls.ndjson"

echo "== 05 DATA_FLOWS, the orientation finding =="
"${G[@]}" edges --repo . --worktree --relation DATA_FLOWS \
  | grep -F "$SR/" > "$OUT/05-edges-dataflows.ndjson"

echo "== 06 final semantic diff of the submitted implementation =="
"${G[@]}" diff --repo . --base "$BASE" --head HEAD --json \
  > "$OUT/06-final-semantic-diff.json" 2>&1

echo "== 06b semantic diff of the demo change itself =="
"${G[@]}" diff --repo . --base demo-before --head demo-after --json \
  > "$OUT/06b-semantic-diff-demo-change.json" 2>&1

echo "== 07 the decision the evidence produced =="
./.venv/bin/python -m blastradius.cli impact --symbol pricing.fees.penal_charge \
  --intent "refactor penal charge rounding only, no downstream change" \
  > "$OUT/07-blast-radius-report.txt" 2>&1

echo "== 08 impact on every evidence-consuming symbol, the curveball analysis =="
capture_impact() {  # name symbol file
  "${G[@]}" impact --repo . --symbol "$2" --file "$3" --format text \
    > "$OUT/08-curveball-impact-$1.txt" 2>&1
}
capture_impact edges            EntireGraphAdapter.edges           blastradius/adapters/entire_graph.py
capture_impact impact-callers   EntireGraphAdapter.impact_callers  blastradius/adapters/entire_graph.py
capture_impact changed-symbols  EntireGraphAdapter.changed_symbols blastradius/adapters/entire_graph.py
capture_impact orient           _orient                            blastradius/adapters/entire_graph.py
capture_impact scope-note       GraphRun.scope_note                blastradius/adapters/entire_graph.py
capture_impact edge             Edge                               blastradius/core/evidence.py
capture_impact finding          Finding                            blastradius/core/evidence.py
capture_impact provenance       Provenance                         blastradius/core/evidence.py
capture_impact verification     Verification                       blastradius/core/evidence.py
capture_impact build-graph      build_graph                        blastradius/cli.py

echo "== 09 'IMPACT DEGENERATE' is not 'unused' — cross-check against grep =="
{
  echo "# Cross-check: 'IMPACT DEGENERATE' is not 'unused'"
  echo "# captured $(date -u +%Y-%m-%dT%H:%M:%SZ) against $("${G[@]}" version)"
  echo
  echo '$ entire graph impact --repo . --symbol Verification --file blastradius/core/evidence.py'
  cat "$OUT/08-curveball-impact-verification.txt"
  echo
  echo '$ grep -rn "Verification\." blastradius/'
  grep -rn "Verification\." blastradius/
  echo
  echo "# The provider reports 0 callers / 0 callees / 0 type consumers for Verification."
  echo "# grep finds 10 real references, including Finding.is_assertable's decision on line 90"
  echo "# of core/evidence.py. Enum attribute access is not a CALLS edge, so the relation"
  echo "# does not exist in the graph. The graph is not wrong; it answered the question it"
  echo "# was asked. We were asking it a question it does not answer."
} > "$OUT/09-curveball-degenerate-crosscheck.txt"

echo "== 10 the decision on a repository static analysis cannot fully resolve =="
./.venv/bin/python -m blastradius.cli impact --symbol pricing.fees.penal_charge \
  --source-root fixtures/lending-platform-dynamic \
  --intent "adjust penal charge rounding; nothing downstream" \
  > "$OUT/10-curveball-partial-report.txt" 2>&1

echo "== 11 the dynamic fixture as Entire Graph actually sees it =="
{
  echo "# The dynamic fixture, as Entire Graph actually sees it"
  echo "# captured $(date -u +%Y-%m-%dT%H:%M:%SZ) against $("${G[@]}" version)"
  echo "#"
  echo "# METHOD NOTE: this must be captured with --worktree. A first attempt without it"
  echo "# read the COMMITTED tree, where this fixture did not yet exist, and reported zero"
  echo "# relations -- a clean, confident, meaningless answer. That is the same class of"
  echo "# mistake the curveball is about, made while documenting the curveball."
  echo
  echo '$ entire graph edges --repo . --relation CALLS --worktree | grep lending-platform-dynamic'
  "${G[@]}" edges --repo . --relation CALLS --worktree \
    | grep 'lending-platform-dynamic' \
    | python3 "$(dirname "$0")/summarise-dynamic-edges.py"
  echo
  echo "# The claim this file exists to verify: late_payment_charge, the symbol the"
  echo "# demo reviews, has NO caller in the graph. It is reached only through the"
  echo "# CHARGE_RULES registry in disclosure/kfs.py, which no static walk can follow."
  echo "# Blast Radius therefore reports a 0-symbol radius -- correctly -- and refuses"
  echo "# to let that read as safe."
  echo
  echo '$ entire graph impact --repo . --symbol late_payment_charge --file fixtures/lending-platform-dynamic/pricing/fees.py --worktree'
  "${G[@]}" impact --repo . --symbol late_payment_charge \
    --file fixtures/lending-platform-dynamic/pricing/fees.py --worktree --format text 2>&1 | head -14
} > "$OUT/11-curveball-dynamic-graph.txt" 2>&1

wc -l "$OUT"/* | sed 's|docs/graph-evidence/||'
