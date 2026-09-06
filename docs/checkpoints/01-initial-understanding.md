# Checkpoint 1 — Initial understanding and intended architecture

## What we are building and for whom

Blast Radius: impact-aware change review for regulated Indian consumer-lending code.
The user is the engineer or coding agent about to merge a change to a shared lending
codebase, who cannot see past the diff. A `git diff` of `pricing/fees.py` shows six changed
lines; it does not show that those lines are five hops upstream of the Key Fact Statement,
the sanction letter, the bureau submission and the RBI supervisory return — three of which
ship on unattended cron jobs.

Track 2. Entire Graph is the evidence layer, not a tracking sidecar.

## The architecture we intend, and why

Four invariants, chosen now so they can be checked against later:

1. **Evidence-first.** No claim exists without `{source, file, line, confidence,
   resolution, verified}`. Enforced in the type (`core/evidence.py`), not in the renderer's
   good manners, because the guide warns twice against presenting uncertain graph output as
   fact and a renderer-level rule is one refactor away from being lost.
2. **The score is a pure function in our code**, never model output. Same input, same
   score. Reproducibility is the only reason a risk score can sit in a merge gate.
3. **Verification means two independent derivations.** Entire Graph is primary; a local
   `ast` resolver derives every edge again. Agree → VERIFIED. One only → UNVERIFIED,
   rendered greyed, never asserted. Self-corroboration from one source is explicitly not
   verification.
4. **JSON first, renderers on top.** One report object; CLI is a view. This is also
   deliberate Curveball insurance: a CI check or PR comment becomes a small addition.

## Decisions made, with the alternatives we rejected

- **Rejected: "LoanLens", a borrower-facing loan-document analyser.** It solves an
  end-user problem rather than a developer problem and uses no graph evidence, so it fails
  the qualification rule ("adding Entire only for tracking … will not qualify"). What
  survived from it is the domain, the RBI rulebook, and the principle that the model
  extracts while the code computes the verdict.
- **Rejected: using `entire graph impact` alone as the engine.** It is the obvious choice
  and it is bounded at depth ≤ 2 by design. The regulated chain in our fixture is five
  hops. We will stream the full relation set with `entire graph edges` and run our own
  reverse BFS, using `impact` as an independent second opinion where the two overlap.
- **Rejected: a generic "this change is big" risk score.** Structural reach alone cannot
  distinguish renaming a private SMS formatter from changing the number a borrower is
  legally entitled to see. The RBI rule layer is what makes the score mean something.
- **Chosen: degrade loudly, never silently.** If the graph is unavailable the report says
  on its face that findings are single-sourced. A partial blast radius presented as a
  complete one reads exactly like "safe to merge", which is the most dangerous possible
  failure for this product.

## Assumptions we are making

- That Entire Graph performs **semantic** (not inventory-only) analysis of Python. If it
  did not, our fixture would be invisible and every finding fiction. **This is the first
  thing to verify.**
- That the provider exposes per-relation provenance we can cite. If it only returned symbol
  names without call sites, the "click through to the evidence" claim collapses.
- That a synthetic fixture is acceptable and preferable. There is real employer lending
  code on this machine; it is confidential, the guide bars it, and it will not be opened,
  copied or referenced.

## Open risks at this point

1. **The adapter is uncalibrated.** It was written before the Entire CLI was available; the
   subcommands and JSON keys are guessed. Until it is calibrated, Entire is a passenger and
   the project arguably does not qualify. This is the highest-value task on the board.
2. Language support for Python is unverified (see assumptions).
3. The rulebook matches on module and symbol names; a rename silently stops matching.

## Disclosure

Implementation began after the 09:00 kickoff. Part of this scaffold — the risk model, the
evidence types, the synthetic fixture and the RBI rulebook — was authored **outside this
clone**, before the fork existed, and moved in afterwards. Nothing is backdated. This is
recorded here rather than smoothed over.
