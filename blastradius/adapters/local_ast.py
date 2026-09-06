"""Independent local resolver built on Python's ast module.

This is NOT the primary evidence source — Entire Graph is. This exists so that
every edge can be derived a second time, independently, and cross-checked. When
both agree, the edge is VERIFIED. When only one produces it, the edge is
UNVERIFIED and rendered greyed. When they disagree, that is a CONFLICT and we
say so.

It doubles as the --offline path when the graph is unavailable, in which case
the report states plainly that findings are single-sourced.
"""
from __future__ import annotations

import ast
import os

from blastradius.core.evidence import Edge, Provenance, Source


class LocalAstResolver:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.definitions = {}   # "module.symbol" -> (file, lineno)
        self.modules = {}       # "module" -> file

    # ---- discovery -------------------------------------------------------

    def _module_name(self, path: str) -> str:
        rel = os.path.relpath(path, self.root)
        rel = rel[:-3] if rel.endswith(".py") else rel
        parts = [p for p in rel.split(os.sep) if p != "__init__"]
        return ".".join(parts)

    def _py_files(self):
        skip = {"__pycache__", ".git", ".venv", "venv", "node_modules", ".pytest_cache"}
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for name in filenames:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)

    def collect_definitions(self) -> dict:
        """Definitions, class-qualified.

        Names are qualified the same way Entire Graph qualifies them
        (`Loan.net_disbursal`, not `net_disbursal`). The two resolvers have to
        agree on what a symbol is CALLED before agreeing on what calls it can
        mean anything -- otherwise "verification" would just be two tools
        talking past each other.
        """
        for path in self._py_files():
            module = self._module_name(path)
            self.modules[module] = path
            try:
                tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
            except (SyntaxError, OSError):
                continue
            for qualname, node in self._defs_in(tree.body, ""):
                self.definitions[f"{module}.{qualname}"] = (path, node.lineno)
        return self.definitions

    def _defs_in(self, body, prefix: str):
        """Yield (qualified_name, node) for every def/class, recursing into
        classes so methods carry their class name."""
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield (prefix + node.name), node
            elif isinstance(node, ast.ClassDef):
                qual = prefix + node.name
                yield qual, node
                yield from self._defs_in(node.body, qual + ".")

    # ---- edges -----------------------------------------------------------

    def edges(self) -> list:
        """Every call this parser can resolve, as an independent derivation.

        Confidence is fixed at 0.6: this resolver is deliberately conservative
        (it drops any name it cannot tie to a definition it actually saw), so
        an edge it produces is trustworthy, but it is a second opinion rather
        than the primary source. It never claims the provider's confidence.
        """
        if not self.definitions:
            self.collect_definitions()
        found = []
        for module, path in self.modules.items():
            try:
                tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
            except (SyntaxError, OSError):
                continue
            aliases = self._import_aliases(tree, module)
            rel = os.path.relpath(path, self.root)
            for qualname, node in self._defs_in(tree.body, ""):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                caller = f"{module}.{qualname}"
                for called, lineno in self._calls_in(node, aliases, module):
                    if called == caller:
                        continue
                    found.append(Edge(
                        caller=caller,
                        callee=called,
                        relation="CALLS",
                        provenance=Provenance(
                            source=Source.LOCAL_AST,
                            file=rel,
                            line=lineno,
                            confidence=0.6,
                            resolution="ast_import_resolved",
                            detail=f"{caller} calls {called}",
                        ),
                    ))
            # Module-level calls. Job entrypoints live here, and a scheduled job
            # that calls straight into a regulated path at import time is
            # exactly the kind of edge a diff hides.
            for node in tree.body:
                if isinstance(node, (ast.Assign, ast.Expr, ast.If)):
                    for called, lineno in self._calls_in(node, aliases, module):
                        found.append(Edge(
                            caller=f"{module}.<module>",
                            callee=called,
                            relation="CALLS",
                            provenance=Provenance(
                                source=Source.LOCAL_AST, file=rel, line=lineno,
                                confidence=0.6, resolution="ast_module_body",
                                detail=f"{module} module body calls {called}",
                            ),
                        ))
        return found

    def _import_aliases(self, tree, module: str) -> dict:
        """local name -> fully qualified symbol, including function-local imports."""
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    local = alias.asname or alias.name
                    aliases[local] = f"{node.module}.{alias.name}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    aliases[alias.asname or alias.name] = alias.name
        return aliases

    def _calls_in(self, node, aliases: dict, module: str):
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            name = self._call_name(child.func)
            if not name:
                continue
            resolved = self._resolve(name, aliases, module)
            if resolved:
                yield resolved, child.lineno

    @staticmethod
    def _call_name(func):
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            parts = []
            cur = func
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
                return ".".join(reversed(parts))
        return None

    def _resolve(self, name: str, aliases: dict, module: str):
        """Only resolve to symbols we actually saw defined. An unresolvable name
        is dropped rather than guessed — guessing is what produces a blast radius
        that is not real."""
        if name in aliases and aliases[name] in self.definitions:
            return aliases[name]
        same_module = f"{module}.{name}"
        if same_module in self.definitions:
            return same_module
        # A bare name that matches exactly one class-qualified definition in
        # this module (a method called without its receiver spelled out).
        suffix = "." + name
        local = [k for k in self.definitions
                 if k.startswith(module + ".") and k.endswith(suffix)]
        if len(local) == 1:
            return local[0]
        if "." in name:
            head, _, tail = name.partition(".")
            if head in aliases:
                candidate = f"{aliases[head]}.{tail}"
                if candidate in self.definitions:
                    return candidate
        if name in self.definitions:
            return name
        return None
