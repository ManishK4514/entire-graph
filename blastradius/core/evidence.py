"""Evidence model.

The single invariant of this product: **no claim exists without provenance.**
Every edge, every finding, every number carries where it came from, which line
of source proves it, and whether we were able to verify it independently.

The guide is explicit that graph results are evidence, not an oracle, and that
uncertain output must never be presented as fact. That rule is enforced here,
in the type, rather than remembered in the renderer.
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
    conflict_note: str = ""

    def key(self) -> tuple:
        return (self.caller, self.callee)


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


def to_dict(obj) -> dict:
    """JSON-ready. The report object is the single source of truth; the CLI and
    HTML renderers are views over this."""
    return asdict(obj)
