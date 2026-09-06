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
BASE="${1:-HEAD~1}"

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

echo "== 02 definition lookup =="
"${G[@]}" def --repo . --symbol penal_charge > "$OUT/02-def-penal-charge.txt" 2>&1

echo "== 03 impact BEFORE the high-risk change =="
"${G[@]}" impact --repo . --worktree --symbol penal_charge --depth 2 --format text \
  > "$OUT/03-impact-pre-change.txt" 2>&1
"${G[@]}" impact --repo . --worktree --symbol penal_charge --depth 2 --format json \
  > "$OUT/03-impact-pre-change.json" 2>&1

echo "== 03b neighbors: the precise relationship lookup =="
"${G[@]}" neighbors --repo . --worktree --symbol penal_charge \
  --relation CALLS --direction in --depth 2 --format text \
  > "$OUT/03b-neighbors-callers.txt" 2>&1

echo "== 04 the relation stream Blast Radius actually walks =="
"${G[@]}" edges --repo . --worktree --relation CALLS \
  | grep -F "$SR" > "$OUT/04-edges-calls.ndjson"

echo "== 05 DATA_FLOWS, the orientation finding =="
"${G[@]}" edges --repo . --worktree --relation DATA_FLOWS \
  | grep -F "$SR" > "$OUT/05-edges-dataflows.ndjson"

echo "== 06 final semantic diff of the submitted implementation =="
"${G[@]}" diff --repo . --base "$BASE" --head HEAD --json \
  > "$OUT/06-final-semantic-diff.json" 2>&1

echo "== 07 the decision the evidence produced =="
./.venv/bin/python -m blastradius.cli impact --symbol pricing.fees.penal_charge \
  --intent "refactor penal charge rounding only, no downstream change" \
  > "$OUT/07-blast-radius-report.txt" 2>&1

wc -l "$OUT"/* | sed 's|docs/graph-evidence/||'
