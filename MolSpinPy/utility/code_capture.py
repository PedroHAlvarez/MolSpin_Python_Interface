"""Capture the code a custom action function depends on, so it can be rebuilt from metadata.

Each dependency is a dict ``{"name", "kind", "source"}`` where kind is one of
``import``, ``function``, ``class`` or ``constant``. Dependencies are ordered so that
everything a snippet needs appears before it.

Any importable module may be used by an action. Modules outside ``ALLOWED_MODULES`` are
"external": they are listed in the metadata (``function_external_modules``), a warning is
raised when the action is created, and loading refuses them unless they are permitted.

A module can be permitted for one load (``ProjectLoader(..., allow_modules=[...])``) and
that choice is remembered in a per-installation list, ``permitted_modules.json`` inside the
installed MolSpinPy package (override the location with the ``MOLSPINPY_PERMITTED_MODULES``
environment variable). Remembered modules extend ``ALLOWED_MODULES`` on that machine only;
the list is never written into project metadata. Manage it with ``list_permitted_modules``,
``permit_modules`` and ``revoke_modules``.
"""
import ast
import builtins
import hashlib
import importlib
import inspect
import json
import os
import sys
import textwrap
import types
import warnings
from pathlib import Path

import numpy as np

ALLOWED_MODULES = (
    "numpy", "math", "cmath", "scipy", "itertools", "functools", "operator",
    "random", "statistics", "collections", "fractions", "MolSpinPy",
)

PERMITTED_MODULES_ENV = "MOLSPINPY_PERMITTED_MODULES"

# Limits on how far dependency capture follows helpers, so runaway chains fail loudly.
MAX_DEPENDENCY_DEPTH = 10
MAX_DEPENDENCIES = 200


def permitted_modules_path():
    override = os.environ.get(PERMITTED_MODULES_ENV)
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "resources" / "permitted_modules.json"


def list_permitted_modules():
    """Modules this installation has previously permitted (beyond ``ALLOWED_MODULES``)."""
    path = permitted_modules_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        modules = data.get("permitted_modules", []) if isinstance(data, dict) else []
        return sorted({m for m in modules if isinstance(m, str) and m})
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        warnings.warn(f"Ignoring unreadable permitted-modules list '{path}': {exc}", RuntimeWarning, stacklevel=2)
        return []


def _save_permitted_modules(modules):
    path = permitted_modules_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"permitted_modules": sorted(set(modules))}, handle, indent=2)
        return True
    except OSError as exc:
        warnings.warn(
            f"Could not save the permitted-modules list to '{path}' ({exc}); the permission applies to this load only. "
            f"Set {PERMITTED_MODULES_ENV} to a writable file to keep it.",
            RuntimeWarning, stacklevel=3,
        )
        return False


def permit_modules(modules):
    """Remember modules as permitted on this installation. Returns the full stored list."""
    tops = {m.split(".")[0] for m in modules if m}
    current = set(list_permitted_modules())
    new = {m for m in tops if m not in ALLOWED_MODULES} - current
    if new:
        _save_permitted_modules(current | new)
    return sorted(current | new)


def revoke_modules(modules):
    """Stop trusting previously permitted modules. Returns the remaining stored list."""
    drop = {m.split(".")[0] for m in modules}
    remaining = [m for m in list_permitted_modules() if m not in drop]
    _save_permitted_modules(remaining)
    return remaining


def module_allowed(module_name, extra=(), use_stored=True):
    """True for built-in allow-listed modules, modules remembered on this installation, or modules
    the caller explicitly permitted (``extra=True`` permits all)."""
    if not module_name:
        return False
    if extra is True:
        return True
    top = module_name.split(".")[0]
    if top in ALLOWED_MODULES or top in {m.split(".")[0] for m in extra}:
        return True
    return use_stored and top in list_permitted_modules()


def imported_modules(source):
    """Top-level module names imported anywhere in a piece of source, including inside function bodies."""
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(("." * node.level + (node.module or "")).split(".")[0] or ".")
    return modules


def external_modules(function_source, dependencies, use_stored=False):
    """Sorted modules used by an action that are not built-in allowed.

    By default the machine-local permitted list is ignored so the result is portable
    (it is what gets written to the metadata). Pass ``use_stored=True`` to exclude those too.
    """
    modules = imported_modules(function_source) if function_source else set()
    for dep in dependencies or []:
        modules |= imported_modules(dep["source"])
    return sorted(m for m in modules if not module_allowed(m, use_stored=use_stored))


def check_modules_permitted(function_source, dependencies, permitted, label="action"):
    """Raise PermissionError naming every external module that is not permitted."""
    missing = [m for m in external_modules(function_source, dependencies, use_stored=True)
               if not module_allowed(m, permitted)]
    if missing:
        raise PermissionError(
            f"The {label} imports modules outside the built-in allow-list: {', '.join(missing)}. "
            f"Review them, then permit them explicitly, e.g. allow_modules={missing!r} "
            "(permitted modules are remembered on this installation; allow_modules=True permits any module once)."
        )


def dependencies_digest(dependencies):
    payload = json.dumps(dependencies, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def literal_source(value):
    """Return a python literal for value, or None when it cannot be reproduced exactly."""
    if isinstance(value, np.generic):
        value = value.item()
    try:
        text = repr(value)
        if ast.literal_eval(text) == value and type(ast.literal_eval(text)) is type(value):
            return text
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        pass
    return None


def _referenced_names(tree, root_name):
    """Names read by the code that are not bound inside it, in order of first use."""
    bound = {root_name}
    for node in ast.walk(tree):
        if isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node is not tree.body[0]:
            bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    names = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in bound:
            names.setdefault(node.id, None)
    return list(names)


class _Collector:
    def __init__(self, max_depth=None, max_dependencies=None):
        self.dependencies = []
        self._objects = {}
        self._active = set()
        self._chain = []
        self.root_module = None
        self.max_depth = MAX_DEPENDENCY_DEPTH if max_depth is None else max_depth
        self.max_dependencies = MAX_DEPENDENCIES if max_dependencies is None else max_dependencies

    def collect_code(self, obj):
        """Add everything referenced by a function or class defined in user code."""
        if id(obj) in self._active:
            return
        label = getattr(obj, "__name__", repr(obj))
        if len(self._chain) >= self.max_depth:
            raise ValueError(
                f"Dependency chain is deeper than the limit of {self.max_depth} "
                f"({' -> '.join(self._chain + [label])}). Simplify the helpers, or raise "
                "code_capture.MAX_DEPENDENCY_DEPTH if this nesting is intended."
            )
        self._active.add(id(obj))
        self._chain.append(label)
        try:
            self._collect(obj)
        finally:
            self._chain.pop()
            self._active.discard(id(obj))

    def _collect(self, obj):
        try:
            source = textwrap.dedent(inspect.getsource(obj))
        except (OSError, TypeError) as exc:
            raise ValueError(f"Cannot capture source of '{getattr(obj, '__name__', obj)}': {exc}") from exc
        tree = ast.parse(source)
        if inspect.isfunction(obj):
            global_ns = obj.__globals__
            closure = inspect.getclosurevars(obj).nonlocals
        else:
            global_ns = vars(sys.modules[obj.__module__])
            closure = {}
        for name in _referenced_names(tree, obj.__name__):
            if name in closure:
                self.add(name, closure[name], obj)
            elif name in global_ns:
                self.add(name, global_ns[name], obj)
            elif not hasattr(builtins, name):
                continue  # unresolved here; it fails at run time exactly as it would originally

    def add(self, name, value, owner):
        if name in self._objects:
            known = self._objects[name]
            same = known is value or (_comparable(value) and _comparable(known) and type(known) is type(value) and known == value)
            if not same:
                raise ValueError(f"'{name}' refers to different objects in the action's dependencies")
            return

        if isinstance(value, types.ModuleType):
            self._add_import(name, value.__name__, None, value)
            return

        is_code = inspect.isfunction(value) or inspect.isclass(value)
        if is_code and value.__module__ == "builtins":
            return
        if is_code and self._importable(value):
            self._add_import(name, value.__module__, value.__qualname__, value)
            return
        if is_code:
            if value.__name__ != name:
                raise ValueError(f"Cannot capture '{name}': it is an alias of '{value.__name__}'")
            self.collect_code(value)
            if name in self._objects:  # already recorded while resolving a mutually recursive helper
                return
            source = textwrap.dedent(inspect.getsource(value))
            tree = ast.parse(source)
            if tree.body[0].decorator_list:
                decorators = ", ".join(ast.unparse(d) for d in tree.body[0].decorator_list)
                raise ValueError(
                    f"Cannot capture '{name}' used by the action: it is decorated with @{decorators}. "
                    "Rebuilding it would drop the decorator and change its behaviour. "
                    "Use the undecorated helper, or apply the decorator's effect inside the function."
                )
            self._record(name, "class" if inspect.isclass(value) else "function", source.rstrip() + "\n", value)
            return

        if callable(value) and not isinstance(value, np.ndarray):
            for module_name in (getattr(value, "__module__", None), "numpy", "math"):
                if not module_name:
                    continue
                attr = getattr(value, "__qualname__", getattr(value, "__name__", None))
                try:
                    module = importlib.import_module(module_name)
                    if attr and getattr(module, attr, None) is value:
                        self._add_import(name, module_name, attr, value)
                        return
                except ImportError:
                    continue
            raise ValueError(f"Cannot capture '{name}' used by the action: callable {value!r} cannot be imported by name")

        if isinstance(value, np.ndarray):
            data = literal_source(value.tolist())
            if data is None:
                raise ValueError(f"Cannot capture array '{name}' used by the action")
            self._record(name, "constant", f"{name} = numpy.array({data}, dtype={str(value.dtype)!r})\n", value)
            return

        text = literal_source(value)
        if text is None:
            raise ValueError(
                f"Cannot capture '{name}' used by the action: a {type(value).__name__} is not a plain constant. "
                "Pass it as an action parameter or define it inside the function."
            )
        self._record(name, "constant", f"{name} = {text}\n", value)

    def _importable(self, value):
        """True when a function/class lives in another importable module and can be imported by name."""
        module_name = value.__module__
        if not module_name or module_name in ("__main__", self.root_module) or "<locals>" in value.__qualname__:
            return False
        try:
            target = importlib.import_module(module_name)
            for part in value.__qualname__.split("."):
                target = getattr(target, part)
            return target is value
        except (ImportError, AttributeError):
            return False

    def _add_import(self, name, module_name, attr, value):
        if attr is None:
            source = f"import {module_name}\n" if name == module_name else f"import {module_name} as {name}\n"
        else:
            source = f"from {module_name} import {attr}" + ("" if attr == name else f" as {name}") + "\n"
        self._record(name, "import", source, value)

    def _record(self, name, kind, source, value):
        if len(self.dependencies) >= self.max_dependencies:
            raise ValueError(
                f"The action depends on more than {self.max_dependencies} items, which is the limit. "
                "Reduce what it pulls in, or raise code_capture.MAX_DEPENDENCIES if this is intended."
            )
        self._objects[name] = value
        self.dependencies.append({"name": name, "kind": kind, "source": source})


def _comparable(value):
    return isinstance(value, (int, float, complex, str, bytes, bool, tuple, list, dict, set, type(None)))


def capture_dependencies(func, max_depth=None, max_dependencies=None):
    """Return the ordered dependency snippets a custom action function needs.

    Helpers are followed at most ``max_depth`` levels deep (the action itself is level 1) and
    at most ``max_dependencies`` items are collected; exceeding either raises ValueError.
    Defaults are ``MAX_DEPENDENCY_DEPTH`` and ``MAX_DEPENDENCIES``.

    Modules outside the allow-list are accepted, but a warning names them; they are also
    recorded in the metadata and must be permitted explicitly when the metadata is loaded.
    """
    original = inspect.unwrap(func)
    collector = _Collector(max_depth, max_dependencies)
    collector.root_module = getattr(original, "__module__", None)
    collector.collect_code(original)
    dependencies = [d for d in collector.dependencies if d["name"] != original.__name__]
    try:
        external = external_modules(textwrap.dedent(inspect.getsource(original)), dependencies, use_stored=True)
    except (OSError, TypeError):
        external = []
    if external:
        warnings.warn(
            f"Action function '{original.__name__}' uses modules outside the built-in allow-list: "
            f"{', '.join(external)}. They are recorded in the project metadata, and anyone loading it "
            f"must permit them explicitly (ProjectLoader(..., allow_modules={external!r})).",
            category=UserWarning,
            stacklevel=2,
        )
    return dependencies


def execute_dependencies(namespace, dependencies, permitted=()):
    """Execute stored dependency snippets after checking each one is of its declared, permitted shape.

    ``permitted`` names extra modules (beyond ALLOWED_MODULES) imports may use; ``True`` permits any.
    """
    for dep in dependencies:
        kind, name = dep["kind"], dep["name"]
        tree = ast.parse(dep["source"])
        if kind == "import":
            if len(tree.body) != 1 or not isinstance(tree.body[0], (ast.Import, ast.ImportFrom)):
                raise ValueError(f"Dependency '{name}' is not a single import")
            node = tree.body[0]
            modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if isinstance(node, ast.ImportFrom) and node.level:
                raise PermissionError(f"Relative import in dependency '{name}' is not allowed")
            for module_name in modules:
                if not module_allowed(module_name, permitted):
                    raise PermissionError(f"Import of '{module_name}' has not been permitted (see allow_modules)")
        elif kind == "constant":
            if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign):
                raise ValueError(f"Dependency '{name}' is not a single assignment")
            if not _is_safe_constant(tree.body[0].value):
                raise PermissionError(f"Dependency '{name}' is not a plain constant")
        elif kind in ("function", "class"):
            if len(tree.body) != 1 or not isinstance(tree.body[0], (ast.FunctionDef, ast.ClassDef)):
                raise ValueError(f"Dependency '{name}' is not a single definition")
        else:
            raise ValueError(f"Unknown dependency kind '{kind}'")
        exec(compile(tree, "<molspin metadata>", "exec"), namespace)


def _is_safe_constant(node):
    try:
        ast.literal_eval(node)
        return True
    except ValueError:
        pass
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr == "array"
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "numpy"
        and len(node.args) == 1 and _is_literal(node.args[0])
        and all(k.arg == "dtype" and _is_literal(k.value) for k in node.keywords)
    )


def _is_literal(node):
    try:
        ast.literal_eval(node)
        return True
    except ValueError:
        return False
