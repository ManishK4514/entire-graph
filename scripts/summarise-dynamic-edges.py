"""Summarise the CALLS relations that touch the dynamic fixture.

Reads the grep-filtered NDJSON edge stream on stdin. Used by
capture-graph-evidence.sh section 11; kept as a file rather than inlined so the
shell script stays readable and the quoting stays sane.
"""
import collections
import json
import sys

TARGET = "late_payment_charge"

rows, resolutions = [], collections.Counter()
for line in sys.stdin:
    record = json.loads(line)
    if record.get("record_type") != "relation":
        continue
    rows.append(record)
    resolutions[record["resolution"]] += 1

print(f"  {len(rows)} CALLS relations touch the dynamic fixture. "
      f"By resolution: {dict(resolutions)}")
print()

callers = [r for r in rows
           if "lending-platform-dynamic" in r["to_id"]
           and r["to_id"].endswith(":" + TARGET)]
print(f"  CALLS whose CALLEE is the dynamic fixture's {TARGET}: {len(callers)}")
for record in callers:
    evidence = (record.get("evidence") or [{}])[0]
    caller = record["from_id"].split(":")[-1]
    print(f"    {caller:22} resolution={record['resolution']:12} "
          f"at {evidence.get('file_path', '?')}:{evidence.get('start_line')}")
if not callers:
    print("    (none — which is the whole point: it is reached only through the")
    print("     CHARGE_RULES registry, and no static walk can follow that)")
