"""Independent local resolver built on Python's ast module.

This is NOT the primary evidence source — Entire Graph is. This exists so that
every edge can be derived a second time, independently, and cross-checked. When
both agree, the edge is VERIFIED. When only one produces it, the edge is
UNVERIFIED and rendered greyed. When they disagree, that is a CONFLICT and we
say so.

It doubles as the --offline path when the graph is unavailable, in which case
the report states plainly that findings are single-sourced.

It has a second job since the Noon Curveball: it is the BLIND SPOT DETECTOR.
`_resolve()` below has always dropped names it could not tie to a definition --
correctly, because guessing is what produces a blast radius that is not real.
What it did not do was remember. A dropped call site is precisely the place a
dependency can hide, so every unresolvable call form is now recorded as a
`BlindSpot` with a file:line and the action that would settle it.

Doing it HERE rather than in the graph adapter is deliberate. Entire Graph
cannot report the edge it never saw -- absence is not a record it can emit. The
only way to know an edge is missing is to look at the source at the point where
resolution failed, which is the one thing this resolver is already doing.
"""
from __future__ import annotations

import ast
import builtins
import os

from blastradius.core.evidence import BlindSpot, Edge, Provenance, Source

# Builtins that produce a callable or a module the resolver cannot follow.
# `getattr`/`setattr` only count when the attribute name is NOT a literal --
# `getattr(loan, "emi")` is statically knowable and flagging it would be noise,
# and a detector that cries wolf gets switched off.
REFLECTION_BUILTINS = {"getattr", "setattr", "eval", "exec", "__import__"}
REFLECTION_CALLS = {"importlib.import_module", "importlib.reload", "pkgutil.resolve_name"}


class LocalAstResolver:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.definitions = {}   # "module.symbol" -> (file, lineno)
        self.modules = {}       # "module" -> file
        self.blind_spots = []   # [BlindSpot] -- where resolution failed, and why
        self.dropped_external = 0   # unresolved bare names (builtins, stdlib, third party)

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
        self.blind_spots, self.dropped_external = [], 0
        for module, path in self.modules.items():
            try:
                tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
            except (SyntaxError, OSError):
                continue
            aliases = self._import_aliases(tree, module)
            rel = os.path.relpath(path, self.root)
            self._scan_blind_spots(tree, module, rel, aliases)
            for qualname, node in self._defs_in(tree.body, ""):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                caller = f"{module}.{qualname}"
                for called, lineno, resolution in self._calls_in(node, aliases, module):
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
                            resolution=resolution,
                            detail=f"{caller} calls {called}",
                        ),
                    ))
            # Module-level calls. Job entrypoints live here, and a scheduled job
            # that calls straight into a regulated path at import time is
            # exactly the kind of edge a diff hides.
            for node in tree.body:
                if isinstance(node, (ast.Assign, ast.Expr, ast.If)):
                    for called, lineno, _resolution in self._calls_in(node, aliases, module):
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

    # ---- blind spots -----------------------------------------------------

    def _scan_blind_spots(self, tree, module: str, rel: str, aliases: dict) -> None:
        """Record every call site whose target this resolver cannot determine.

        The output is deliberately narrow. A detector that flags every `len()`
        and `Decimal()` teaches the reader to skip the section, which is worse
        than not having it: the whole value of a blind-spot list is that a short
        one gets read. So unresolved bare names -- overwhelmingly builtins and
        stdlib -- are COUNTED (`dropped_external`) and disclosed as a number,
        while only the forms that can genuinely hide a first-party dependency
        are recorded individually.
        """
        spans = self._def_spans(tree, module)

        for node in ast.walk(tree):
            if isinstance(node, (ast.ImportFrom, ast.Import)):
                self._scan_import(node, module, rel, spans)
            elif isinstance(node, ast.Call):
                self._scan_call(node, module, rel, spans, aliases)

    def _def_spans(self, tree, module: str) -> list:
        """(start, end, qualified_name) for each def/class, innermost wins."""
        spans = []
        for qualname, node in self._defs_in(tree.body, ""):
            end = getattr(node, "end_lineno", None) or node.lineno
            spans.append((node.lineno, end, f"{module}.{qualname}"))
        return spans

    @staticmethod
    def _owner_at(spans: list, lineno: int, module: str) -> str:
        best = None
        for start, end, name in spans:
            if start <= lineno <= end and (best is None or start >= best[0]):
                best = (start, name)
        return best[1] if best else f"{module}.<module>"

    def _spot(self, kind, owner, rel, lineno, detail, verify, routes_anywhere,
              target: str = "") -> None:
        self.blind_spots.append(BlindSpot(
            kind=kind,
            symbol=owner,
            provenance=Provenance(
                source=Source.LOCAL_AST,
                file=rel,
                line=lineno,
                confidence=0.0,          # a blind spot asserts nothing; it withholds
                resolution="unresolved",
                detail=detail,
            ),
            detail=detail,
            verify=verify,
            routes_anywhere=routes_anywhere,
            target=target,
        ))

    def _scan_import(self, node, module: str, rel: str, spans: list) -> None:
        owner = self._owner_at(spans, node.lineno, module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                self._maybe_missing_module(alias.name, owner, rel, node.lineno)
            return
        if any(a.name == "*" for a in node.names):
            self._spot(
                "star-import", owner, rel, node.lineno,
                f"`from {node.module or '.'} import *` -- the imported names are not "
                f"enumerable statically, so calls to them resolve to nothing",
                f"replace the star import at {rel}:{node.lineno} with explicit names, "
                f"or confirm the exported set of {node.module or 'the package'}",
                routes_anywhere=True,
            )
            return
        if node.level or not node.module:
            return
        # `from generated.cadence import X` names the module directly; and
        # `from generated import cadence` names it as an imported symbol, which
        # the first version missed entirely because the PACKAGE does exist.
        self._maybe_missing_module(node.module, owner, rel, node.lineno)
        for alias in node.names:
            self._maybe_missing_module(f"{node.module}.{alias.name}", owner, rel,
                                       node.lineno, only_if_package_known=True)

    def _maybe_missing_module(self, target: str, owner: str, rel: str, lineno: int,
                              only_if_package_known: bool = False) -> None:
        """A first-party-looking module that is not on disk: generated at build
        time, or produced by a code generator this analysis never ran."""
        if not target or target in self.modules:
            return
        head = target.split(".")[0]
        first_party = any(m == head or m.startswith(head + ".") for m in self.modules)
        if not first_party:
            return
        if only_if_package_known:
            # `from pkg import name` -- only a missing module if `name` is not a
            # symbol the package actually defines.
            package = target.rpartition(".")[0]
            if any(k.startswith(package + ".") for k in self.definitions):
                return
        if any(s.kind == "missing-module" and s.provenance.line == lineno
               and s.provenance.file == rel for s in self.blind_spots):
            return
        self._spot(
            "missing-module", owner, rel, lineno,
            f"`{target}` is imported from a first-party package but no such module "
            f"exists in the analysed subtree -- generated, or excluded from analysis",
            f"confirm whether {target} is generated at build time; if so, generate it "
            f"and re-run, because nothing downstream of it is in this radius",
            routes_anywhere=True,
        )

    def _scan_call(self, node, module: str, rel: str, spans: list, aliases: dict) -> None:
        owner = self._owner_at(spans, node.lineno, module)
        func = node.func

        # HANDLERS[key](loan) -- the target is chosen from a table at runtime.
        if isinstance(func, ast.Subscript):
            self._spot(
                "dynamic-dispatch", owner, rel, node.lineno,
                "call target is selected from a subscript at runtime; the callee is "
                "whatever the table holds, which static analysis cannot enumerate",
                f"open {rel}:{node.lineno}, enumerate the dispatch table, and re-run "
                f"`blast impact --symbol <target>` for each entry it can hold",
                routes_anywhere=True,
            )
            return

        # factory()(loan), getattr(m, n)(loan) -- callee is another call's result.
        if isinstance(func, ast.Call):
            self._spot(
                "dynamic-dispatch", owner, rel, node.lineno,
                "call target is the return value of another call; the callee is not "
                "a name this resolver can bind to a definition",
                f"open {rel}:{node.lineno} and identify what the inner call returns; "
                f"re-run `blast impact --symbol <target>` for each possibility",
                routes_anywhere=True,
            )
            return

        name = self._call_name(func)
        if not name:
            # super().charge(loan), repo.get_client().charge(loan) -- an attribute
            # chain that does not bottom out in a name. The first version did a
            # bare `return` here: not an edge, not a blind spot, not even counted,
            # which contradicted this scanner's whole contract.
            # Same first-party guard as the receiver-method branch below.
            # `Decimal(v).quantize(...)` is a chained call on a stdlib object:
            # there is no first-party edge there to miss, and flagging every one
            # would bury the holes that matter.
            if (isinstance(func, ast.Attribute)
                    and any(k.endswith("." + func.attr) for k in self.definitions)):
                self._spot(
                    "dynamic-dispatch", owner, rel, node.lineno,
                    f"`{func.attr}` is called on the result of an expression (a chained "
                    f"or super() call), so the receiver -- and therefore the callee -- "
                    f"is not a name this resolver can bind",
                    f"open {rel}:{node.lineno} and confirm the concrete receiver type; "
                    f"the edge exists in the source even though neither resolver has it",
                    routes_anywhere=False,
                    target=func.attr,
                )
            else:
                self.dropped_external += 1
            return

        if self._is_reflection(name, node, aliases):
            self._spot(
                "reflection", owner, rel, node.lineno,
                f"`{name}` resolves its target at runtime from a value, not a name",
                f"open {rel}:{node.lineno}; confirm the reachable targets by reading the "
                f"source or by running the test that covers this path",
                routes_anywhere=True,
            )
            return

        if self._resolve(name, aliases, module)[0]:
            return

        head, _, attr = name.rpartition(".")

        # A callable held in a plain local name: `handler = TABLE[k]` then
        # `handler(loan)`, a callback parameter, a functools.partial result. The
        # commonest dynamic-dispatch shape in Python, and the first version did
        # not merely miss it -- it counted it as "builtin/stdlib dropped as
        # external", actively mislabelling a hole as noise.
        if not head:
            if name in dir(builtins) or name in aliases:
                self.dropped_external += 1
                return
            self._spot(
                "dynamic-dispatch", owner, rel, node.lineno,
                f"`{name}` is a callable held in a local name or parameter; its target "
                f"is whatever was assigned to it at runtime",
                f"open {rel}:{node.lineno} and determine what `{name}` can be bound to; "
                f"re-run `blast impact --symbol <target>` for each possibility",
                routes_anywhere=True,
            )
            return

        # obj.method() where the receiver's type is not statically known. Only
        # when the attribute names something first-party: `rows.append(...)` and
        # `base.update(...)` are container builtins, there is no first-party edge
        # there to miss, and listing them would bury the ones that matter.
        if head in ("self", "cls"):
            # `self.foo()` inside a class whose `foo` we can see is statically
            # knowable, and flagging it would be noise of exactly the kind that
            # gets a detector switched off.
            if any(k.startswith(module + ".") and k.endswith("." + attr)
                   for k in self.definitions):
                return
        if head not in aliases and any(k.endswith("." + attr) for k in self.definitions):
            self._spot(
                "receiver-method", owner, rel, node.lineno,
                f"`{name}` is called through a receiver whose type is not statically "
                f"known, and `{attr}` names a definition in this subtree",
                f"open {rel}:{node.lineno} and confirm the receiver's concrete class; "
                f"if it is first-party, the edge exists in the source and this radius "
                f"is missing it",
                routes_anywhere=False,
                target=name,
            )
            return

        self.dropped_external += 1

    @staticmethod
    def _is_reflection(name: str, node, aliases: dict = None) -> bool:
        """`getattr(loan, "emi")` is statically knowable; `getattr(loan, field)`
        is not. Only the second is a blind spot, and treating them alike would
        bury the real ones."""
        # Follow import aliases: `from importlib import import_module` spells the
        # same reflection entry point as a bare name, and matching on the literal
        # spelling let it through.
        qualified = (aliases or {}).get(name, name)
        if (name in REFLECTION_CALLS or qualified in REFLECTION_CALLS
                or name.endswith(".import_module") or qualified.endswith(".import_module")):
            return True
        if name not in REFLECTION_BUILTINS and qualified not in REFLECTION_BUILTINS:
            return False
        # `vars(obj)` returns __dict__ and dispatches to nothing -- unlike the
        # others it cannot hide a call edge, so it is not reflection for our
        # purposes and flagging it was pure noise.
        if name in ("eval", "exec", "__import__"):
            return True
        second = node.args[1] if len(node.args) > 1 else None
        return not isinstance(second, ast.Constant)

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
            resolved, resolution = self._resolve(name, aliases, module)
            if resolved:
                yield resolved, child.lineno, resolution

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
        """Resolve a call name, and report HOW it was resolved.

        Returns `(symbol, resolution)`, or `(None, "")` when unresolvable. Only
        symbols we actually saw defined are resolved to; an unresolvable name is
        dropped rather than guessed, because guessing is what produces a blast
        radius that is not real.

        The resolution string is returned per CALL SITE rather than remembered
        per symbol. An earlier version recorded name-matched symbols in a set on
        the resolver, which made an edge's resolution depend on the order files
        happened to be walked: the same edge could come back `import_resolved`
        on one run and `name_only` on the next. A tier that is not reproducible
        is worse than no tier, and invariant 2 is reproducibility.
        """
        if name in aliases and aliases[name] in self.definitions:
            return aliases[name], "ast_import_resolved"
        same_module = f"{module}.{name}"
        if same_module in self.definitions:
            return same_module, "ast_import_resolved"
        # A bare name that matches exactly one class-qualified definition in this
        # module (a method called without its receiver spelled out). That is a
        # NAME MATCH, not a resolution, and it is tiered heuristic accordingly.
        suffix = "." + name
        local = [k for k in self.definitions
                 if k.startswith(module + ".") and k.endswith(suffix)]
        if len(local) == 1:
            return local[0], "ast_name_only"
        if "." in name:
            head, _, tail = name.partition(".")
            if head in aliases:
                candidate = f"{aliases[head]}.{tail}"
                if candidate in self.definitions:
                    return candidate, "ast_import_resolved"
        if name in self.definitions:
            return name, "ast_import_resolved"
        return None, ""
