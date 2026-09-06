# fixtures/lending-platform

A **synthetic** Indian consumer-lending codebase, written for this Buildathon as
the demo target for Blast Radius. It contains no real, proprietary or customer
data and is not derived from any employer's code.

It exists to provide a dependency chain that a `git diff` genuinely cannot
reveal:

```
pricing/fees.penal_charge
  -> pricing/schedule.overdue_projection
     -> disclosure/kfs.penal_illustration        [REGULATED: KFS]
        -> disclosure/kfs.generate_kfs
           -> disclosure/kfs.render_kfs_text
              -> jobs/daily_kfs_batch            [scheduled 02:00]
           -> disclosure/sanction_letter         [REGULATED: sanction disclosure]
  -> recovery/dunning.compute_overdue
     -> reporting/rbi_return.portfolio_row       [REGULATED: supervisory return]
        -> jobs/monthly_rbi_return               [scheduled monthly]
     -> reporting/bureau.bureau_record
        -> jobs/nightly_bureau_push              [scheduled 01:30]
```

## The two demo changes

| | Change | Expected verdict |
|---|---|---|
| **Green** | rename `recovery/dunning._format_sms_text` | LOW — 0 regulated surfaces, 0 jobs, 1 test |
| **Red** | stop `pricing/fees.penal_charge` compounding | CRITICAL — 3 regulated surfaces, 3 scheduled jobs, 6 tests |

The red change is *correct* under RBI's 2023 penal-charges circular, which is
the point: even a compliance fix has a blast radius, and the developer making it
cannot see where it lands.

## Run

```bash
PYTHONPATH=. pytest -q     # 21 tests
```
