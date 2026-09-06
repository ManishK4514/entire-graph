"""Codified RBI obligations, matched against code surfaces.

This is the layer a generic impact tool does not have. It turns "this change
touches a lot of code" into "this change alters a regulated disclosure".
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

from blastradius.core.evidence import Provenance, Source

DEFAULT_RULES = os.path.join(os.path.dirname(__file__), "..", "rules", "rbi_surfaces.yaml")


@dataclass
class Surface:
    id: str
    modules: list
    symbols: list
    obligation: str
    citation: str
    severity: str
    confidence: str = "high"
    verify_note: str = ""

    def matches(self, symbol: str) -> bool:
        """A symbol is on this surface if its module is listed, or it is named."""
        module, _, name = symbol.rpartition(".")
        if any(module == m or module.startswith(m + ".") for m in self.modules):
            return not self.symbols or name in self.symbols
        return name in self.symbols and not self.modules


@dataclass
class ScheduledConsumer:
    module: str
    name: str
    schedule: str


@dataclass
class RuleBook:
    surfaces: list = field(default_factory=list)
    consumers: list = field(default_factory=list)
    path: str = ""

    @classmethod
    def load(cls, path: str = None) -> "RuleBook":
        path = os.path.abspath(path or DEFAULT_RULES)
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        surfaces = [
            Surface(
                id=s["id"],
                modules=s.get("match", {}).get("modules", []),
                symbols=s.get("match", {}).get("symbols", []),
                obligation=" ".join(s["obligation"].split()),
                citation=s.get("citation", ""),
                severity=s.get("severity", "medium"),
                confidence=s.get("confidence", "high"),
                verify_note=s.get("verify", ""),
            )
            for s in raw.get("surfaces", [])
        ]
        consumers = [ScheduledConsumer(**c) for c in raw.get("scheduled_consumers", [])]
        return cls(surfaces=surfaces, consumers=consumers, path=path)

    def surfaces_for(self, symbol: str) -> list:
        return [s for s in self.surfaces if s.matches(symbol)]

    def consumer_for(self, symbol: str):
        module = symbol.rpartition(".")[0]
        for c in self.consumers:
            if module == c.module:
                return c
        return None

    def provenance(self, surface: Surface) -> Provenance:
        return Provenance(
            source=Source.RULES,
            file=os.path.relpath(self.path, os.getcwd()),
            detail=f"rule {surface.id}",
        )
