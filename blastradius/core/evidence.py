"""Evidence model.

The single invariant of this product: **no claim exists without provenance.**
Every edge, every finding, every number carries where it came from, which line
of source proves it, and whether we were able to verify it independently.

The guide is explicit that graph results are evidence, not an oracle, and that
uncertain output must never be presented as fact. That rule is enforced here,
in the type, rather than remembered in the renderer.

Two axes, deliberately kept apart:

  TIER         how much weight one claim carries  (confirmed / heuristic /
               needs-verification)
  COMPLETENESS whether the set of claims is all there is  (complete / partial)

A claim can be confirmed inside an analysis that is partial. Collapsing the two
is what lets a small blast radius read as a safe one, so they never share a
field.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Source(str, Enum):
    """Where a claim came from. Rendered next to every finding."""
    ENTIRE_GRAPH = "entire-graph"      # primary: Entire Graph structural evidence
    LOCAL_AST = "local-ast"            # independent local parse, used to verify
    RULES = "rbi-rules"                # codified regulation
    GIT = "git"


class Verification(str, Enum):
    VERIFIED = "verified"              # two independent sources agree
    UNVERIFIED = "unverified"          # only one source; shown greyed, never asserted
    CONFLICT = "conflict"              # sources disagree; surfaced loudly


# Resolutions that mean the relationship was RESOLVED structurally, as opposed
# to inferred. Entire Graph reports this itself, per relation: `exact` (0.92) is
# a same-file resolution, `import_resolved` (0.86) followed a real import path.
# Against those, `name_only` (0.68) matched on the identifier alone and
# `type_inferred` (0.83) guessed a receiver type -- the provider telling us it
# was guessing, which we were not listening to.
#
# This is an ALLOWLIST, and deliberately so. The first version listed the
# heuristic strings instead, which meant any resolution the provider added later
# -- or any typo -- silently counted as structural. A function whose entire job
# is conservatism must not fail open: an unrecognised resolution is treated as
# heuristic, which is the safe direction.
STRUCTURAL_RESOLUTIONS = frozenset({"exact", "import_resolved", "ast_import_resolved"})


def is_structural(resolution: str) -> bool:
    return resolution in STRUCTURAL_RESOLUTIONS


class Tier(str, Enum):
    """How much weight a reader -- human or agent -- may put on ONE claim.

    The three values are the three the reader actually has to tell apart:
    something the tool stands behind, something it is guessing at, and something
    it is explicitly handing back for a human or a test to settle.
    """
    CONFIRMED = "confirmed"                    # corroborated AND structurally resolved
    HEURISTIC = "heuristic"                    # single-sourced, or inferred by its source
    NEEDS_VERIFICATION = "needs-verification"  # must be settled against source or a test


class Completeness(str, Enum):
    """Whether the analysis could see everything, not whether it was right.

    PARTIAL does not mean the findings are wrong. It means findings that should
    exist may be missing, so the radius is a LOWER BOUND and the score derived
    from it is a FLOOR.
    """
    COMPLETE = "complete"
    PARTIAL = "partial"


@dataclass(frozen=True)
class Provenance:
    """Where a single claim came from, precisely enough to click through.

    `confidence` and `resolution` are NOT ours. They are reported per relation
    by Entire Graph (0.92 for a same-file exact call, 0.86 resolved through an
    import, 0.78 resolved to an external symbol) and carried through unchanged.
    That distinction matters: the product does not invent a confidence number,
    it repeats one the evidence source stands behind.
    """
    source: Source
    file: Optional[str] = None
    line: Optional[int] = None
    detail: str = ""
    end_line: Optional[int] = None
    confidence: float = 0.0
    resolution: str = ""

    def location(self) -> str:
        if self.file and self.line:
            return f"{self.file}:{self.line}"
        return self.file or "<no location>"


@dataclass
class Edge:
    """A caller -> callee relationship. The atom of a blast radius.

    `relation` is the graph relation type that produced this edge (CALLS,
    DATA_FLOWS). A CALLS edge is a hard dependency; a DATA_FLOWS edge is real
    but weaker, and the report labels it so a reader can discount it.
    """
    caller: str                        # "module.symbol"
    callee: str
    provenance: Provenance
    relation: str = "CALLS"
    verification: Verification = Verification.UNVERIFIED
    corroborated_by: list = field(default_factory=list)
    corroborated_resolutions: list = field(default_factory=list)
    conflict_note: str = ""

    def key(self) -> tuple:
        return (self.caller, self.callee)

    def tier(self) -> "Tier":
        """Verification and resolution are different questions, and an edge is
        CONFIRMED only when BOTH answer well, on BOTH sides.

        Corroboration alone is not enough: our two sources share a bare-name
        fallback, so two name-guessers agreeing is two guesses, not a proof. That
        is `test_the_same_source_twice_is_not_verification` applied to resolution
        quality instead of to source identity.

        Which is why the corroborator's OWN resolution has to be checked too.
        An `exact` edge from Entire Graph, corroborated only by our resolver's
        bare-name match, is one good derivation and one guess -- and reading that
        as CONFIRMED is the very thing the paragraph above forbids.
        """
        if self.verification is Verification.CONFLICT:
            return Tier.NEEDS_VERIFICATION
        if self.verification is not Verification.VERIFIED:
            return Tier.HEURISTIC
        if not is_structural(self.provenance.resolution):
            return Tier.HEURISTIC
        if not any(is_structural(r) for r in self.corroborated_resolutions):
            return Tier.HEURISTIC
        return Tier.CONFIRMED


@dataclass
class Finding:
    """Something the developer needs to know, with the proof attached."""
    title: str
    detail: str
    severity: str                      # low | medium | high | critical
    provenance: Provenance
    verification: Verification = Verification.UNVERIFIED
    citation: str = ""
    needs_verification_note: str = ""

    def is_assertable(self) -> bool:
        """Whether we may state this as fact rather than as a possibility."""
        return (
            self.verification is Verification.VERIFIED
            and not self.needs_verification_note
        )

    def tier(self) -> "Tier":
        if self.needs_verification_note:
            return Tier.NEEDS_VERIFICATION
        if self.verification is Verification.VERIFIED:
            return Tier.CONFIRMED
        return Tier.HEURISTIC


@dataclass
class BlindSpot:
    """A place where the analysis KNOWS it could not see.

    This is the type the curveball forced into existence. Before it, an
    unresolvable call site was dropped -- `_resolve()` in local_ast.py says so
    in as many words: "An unresolvable name is dropped rather than guessed."
    Dropping is right; dropping SILENTLY is what let a blast radius that had
    holes in it render as a complete one.

    A blind spot carries the same provenance contract as every other claim in
    this product, because "we could not resolve this" is itself a claim and has
    to be as clickable as the findings are. It additionally carries `verify`:
    the concrete thing a human or agent should do to settle it. A blind spot the
    tool cannot tell you how to close is a shrug, not a finding.
    """
    kind: str                          # dynamic-dispatch | reflection | star-import |
                                       # receiver-method | missing-module
    symbol: str                        # the enclosing symbol we were resolving inside
    provenance: Provenance
    detail: str = ""
    verify: str = ""                   # the action that would resolve it
    routes_anywhere: bool = False      # True when the unseen target is unbounded
    target: str = ""                   # the syntactic callee, when there was one
    covered_by: str = ""               # set when another source resolved this site
    # Invariant 1 asks every claim to carry a verification standing. Edge and
    # Finding carry one as a FIELD, which survives asdict(); a blind spot needs
    # the same, or a JSON-first consumer sees the only claim type in the product
    # whose standing is implicit.
    verification: Verification = Verification.UNVERIFIED

    def tier(self) -> "Tier":
        """Always. A blind spot is by definition the thing a human must settle."""
        return Tier.NEEDS_VERIFICATION

    def location(self) -> str:
        return self.provenance.location()


def to_dict(obj) -> dict:
    """JSON-ready. The report object is the single source of truth; the CLI and
    HTML renderers are views over this."""
    return asdict(obj)
