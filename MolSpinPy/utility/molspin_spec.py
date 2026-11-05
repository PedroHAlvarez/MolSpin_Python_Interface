"""Spec sheet describing the inputs of MolSpin's general tasks (HSGeneral, SSGeneral, MultiSSGeneral).

MolSpin has no machine readable schema, so the sheet is extracted from the MolSpin C++ sources
(``RunSection/General/<task folder>``) by pattern matching:

* property keys and their aliases come from ``Get("key", target)`` and ``ReadString(p, {"a", "b"}, v)`` calls,
* types and defaults come from the declaration of the target variable,
* choices, requirements and conflicts come from the validation error messages.

When no MolSpin source tree can be found, a bundled (unverified) copy of the sheet is used.
"""
import json
import os
import re
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path

BUNDLED_SPEC = Path(__file__).resolve().parent.parent / "resources" / "molspin_spec.json"

_STRING = r'"((?:[^"\\]|\\.)*)"'
_CPP_TYPES = {
    "bool": "bool", "int": "int", "unsigned": "int", "unsigned int": "int", "long": "int",
    "size_t": "int", "arma::uword": "int", "double": "float", "float": "float", "std::string": "string",
}
_TYPE_PATTERN = "|".join(re.escape(t) for t in sorted(_CPP_TYPES, key=len, reverse=True))

_CONFLICT_CUES = ("conflict", "cannot be combined", "do not combine", "mutually exclusive")
_REQUIRE_CUES = (" requires ",)
_SCOPE_CUES = ("only valid with", "do not apply", "does not apply", "is not used", "not used by")
_RANGE_CUES = ("must be", "at least", "positive", "finite")


@dataclass
class PropertySpec:
    name: str
    aliases: list = field(default_factory=list)
    value_type: str = "unknown"
    default: object = None
    choices: list = field(default_factory=list)
    required: bool = False
    description: str = ""
    source: str = ""

    @property
    def names(self):
        return [self.name, *self.aliases]


@dataclass
class Constraint:
    """``requires``: subject needs the others. ``conflicts``: keys cannot be combined.
    ``scoped``: keys only apply under a condition. ``range``: value limits. The message is the source text."""
    kind: str
    keys: list
    message: str
    source: str = ""


@dataclass
class TaskSpec:
    type: str
    aliases: list = field(default_factory=list)
    properties: dict = field(default_factory=dict)
    constraints: list = field(default_factory=list)

    def resolve_alias(self, key):
        """Return the canonical property name for a key or alias (case-insensitive), or None."""
        key = key.lower()
        for prop in self.properties.values():
            if key in (n.lower() for n in prop.names):
                return prop.name
        return None

    def allowed_keys(self, include_aliases=True):
        keys = []
        for prop in self.properties.values():
            keys.extend(prop.names if include_aliases else [prop.name])
        return keys

    def required_keys(self):
        return [p.name for p in self.properties.values() if p.required]

    def constraints_for(self, key, kind=None):
        name = self.resolve_alias(key)
        return [c for c in self.constraints if name in c.keys and (kind is None or c.kind == kind)]

    def requires_of(self, key):
        """Keys named alongside `key` in 'requires' constraints where `key` is the subject."""
        name = self.resolve_alias(key)
        return sorted({k for c in self.constraints if c.kind == "requires" and c.keys and c.keys[0] == name
                       for k in c.keys[1:]})

    def conflicts_of(self, key):
        name = self.resolve_alias(key)
        return sorted({k for c in self.constraints if c.kind == "conflicts" and name in c.keys
                       for k in c.keys if k != name})


@dataclass
class SpecSheet:
    tasks: dict = field(default_factory=dict)
    verified: bool = False
    source_root: str = ""

    def get(self, task_type):
        """Look up a task by canonical name or any accepted alias (case-insensitive)."""
        wanted = task_type.lower()
        for task in self.tasks.values():
            if wanted in (n.lower() for n in [task.type, *task.aliases]):
                return task
        return None

    def to_dict(self):
        return {"verified": self.verified, "source_root": self.source_root,
                "tasks": {name: asdict(t) for name, t in self.tasks.items()}}

    def to_json(self, path=None):
        text = json.dumps(self.to_dict(), indent=2)
        if path is not None:
            Path(path).write_text(text + "\n", encoding="utf-8")
        return text

    @classmethod
    def from_dict(cls, data):
        tasks = {}
        for name, t in data["tasks"].items():
            tasks[name] = TaskSpec(
                type=t["type"], aliases=t["aliases"],
                properties={k: PropertySpec(**v) for k, v in t["properties"].items()},
                constraints=[Constraint(**c) for c in t["constraints"]])
        return cls(tasks=tasks, verified=data.get("verified", False), source_root=data.get("source_root", ""))

    @classmethod
    def from_json(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def write_typed_dicts(self, path):
        """Write a module of ``TypedDict`` classes, one per task, so editors can complete property names:
        ``def f(**props: Unpack[SSGeneralProperties])``."""
        lines = ['"""Generated by SpecSheet.write_typed_dicts. Do not edit by hand."""',
                 "from typing import TYPE_CHECKING, List, TypedDict", "", ""]
        py_types = {"bool": "bool", "int": "int", "float": "float", "string": "str", "list": "List[str]"}
        for task in self.tasks.values():
            lines.append(f"class {task.type}Properties(TypedDict, total=False):")
            lines.append(f'    """Properties accepted by the MolSpin {task.type} task."""')
            if not task.properties:
                lines.append("    pass")
            for prop in task.properties.values():
                for name in prop.names:
                    if not name.isidentifier():
                        continue
                    lines.append(f"    {name}: {py_types.get(prop.value_type, 'object')}")
                    doc = prop.description or ""
                    if prop.choices:
                        doc = f"{doc} One of: {', '.join(prop.choices)}.".strip()
                    if name != prop.name:
                        doc = f"{doc} Alias of {prop.name}.".strip()
                    if prop.default is not None:
                        doc = f"{doc} Default: {prop.default}.".strip()
                    if doc:
                        lines.append(f'    """{doc.replace(chr(34), chr(39))}"""')
            lines += ["", ""]
        lines += self._task_base_lines()
        Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def task_docstring(self, task):
        """Human readable summary of a task: properties with types/defaults/choices, then the rules."""
        out = [f"MolSpin {task.type} task.", "", "Properties (aliases in brackets):"]
        for prop in task.properties.values():
            parts = [f"{prop.name} ({prop.value_type})"]
            if prop.aliases:
                parts.append(f"[{', '.join(prop.aliases)}]")
            if prop.choices:
                parts.append(f"one of {', '.join(prop.choices)}")
            if prop.default is not None:
                parts.append(f"default {prop.default}")
            out.append("  " + " ".join(parts))
        groups = (("requires", "Requirements"), ("conflicts", "Cannot be combined"),
                  ("scoped", "Only applies in some modes"))
        for kind, title in groups:
            messages = [c.message for c in task.constraints if c.kind == kind]
            if messages:
                out += ["", f"{title}:"] + [f"  - {m}" for m in dict.fromkeys(messages)]
        return "\n".join(out).replace("\\", "\\\\").replace('"""', "'''")

    def _task_base_lines(self):
        """A ``TaskBase`` class whose ``__init__`` overloads carry one docstring per task, so editors show
        the properties and rules of the task type while a Task is being created."""
        lines = ["if TYPE_CHECKING:", "    from typing import overload", "    from typing_extensions import Literal, Unpack",
                 "", "", "class TaskBase:",
                 '    """Constructor signatures for Task, generated from the MolSpin spec sheet."""', ""]
        for task in self.tasks.values():
            doc = "\n".join(("        " + l) if l else "" for l in self.task_docstring(task).split("\n"))
            lines += ["    if TYPE_CHECKING:", "",
                      "        @overload",
                      f"        def __init__(self, name: str, type: \"Literal['{task.type}']\", "
                      f"**properties: \"Unpack[{task.type}Properties]\") -> None:",
                      f'            """{doc.lstrip()}',
                      '            """', "            ...", ""]
        lines += ["    if TYPE_CHECKING:", "", "        @overload",
                  "        def __init__(self, name: str, type: str, **properties) -> None:",
                  '            """A task type without a spec sheet; properties are not checked."""',
                  "            ...", "",
                  "    def __init__(self, name, type, **properties):",
                  "        self.name = name", "        self.type = type", "        self.properties = dict(properties)"]
        return ["", ""] + lines


def find_source_root(molspin=None):
    """Find a MolSpin checkout (the directory containing ``RunSection/General``) from an explicit path,
    ``MOLSPIN_SOURCE`` / ``MOLSPIN_PATH`` / ``MOLSPIN_HOME`` or the ``molspin`` executable on PATH.
    Executables are followed up their parent directories, so a build folder inside the source tree works."""
    candidates = [molspin, os.environ.get("MOLSPIN_SOURCE"), os.environ.get("MOLSPIN_PATH"),
                  os.environ.get("MOLSPIN_HOME"), shutil.which("molspin"), shutil.which("MolSpin")]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).resolve()
        for folder in [path, *path.parents][:8]:
            if (folder / "RunSection" / "General").is_dir():
                return folder
    return None


_SHEET_CACHE = {}


def get_spec_sheet(refresh=False):
    """Process-wide spec sheet: scans the installed MolSpin source once, else the bundled copy."""
    if refresh or "sheet" not in _SHEET_CACHE:
        _SHEET_CACHE["sheet"] = MolSpinSpecBuilder.build()
    return _SHEET_CACHE["sheet"]


class MolSpinSpecBuilder:
    """Builds a `SpecSheet` for the general tasks from a MolSpin source tree."""

    TASK_CLASS = re.compile(r"make_shared<General::(\w+)::(Task\w+)>")
    TASK_NAME = re.compile(r'_tasktype\s*==\s*' + _STRING + r'|_tasktype\.compare\(' + _STRING + r'\)')
    GET_CALL = re.compile(r'\b(?:\w+\.|\w+->)?(Get|GetList)\(\s*' + _STRING + r'\s*,\s*([\w.]+)')
    READ_CALL = re.compile(r'\bRead\w+\(\s*\w+\s*,\s*\{([^}]*)\}\s*,\s*([\w.]+)')
    ERROR = re.compile(r'\berror\s*=\s*((?:"(?:[^"\\]|\\.)*"\s*)+);')

    def __init__(self, source_root):
        self.root = Path(source_root)
        self.run_section = self.root / "RunSection"

    @classmethod
    def build(cls, molspin=None, bundled=BUNDLED_SPEC):
        """Scan the installed MolSpin source, or fall back to the bundled unverified sheet."""
        root = find_source_root(molspin)
        if root is not None:
            return cls(root).build_sheet()
        if Path(bundled).is_file():
            sheet = SpecSheet.from_json(bundled)
            sheet.verified = False
            return sheet
        raise FileNotFoundError("No MolSpin source tree found and no bundled spec is available. "
                                "Set MOLSPIN_SOURCE or pass the MolSpin path.")

    def build_sheet(self):
        sheet = SpecSheet(verified=True, source_root=str(self.root))
        for folder_name, class_name, aliases in self._find_tasks():
            task_type = class_name[len("Task"):]
            task = self._scan_task(task_type, aliases, self.run_section / "General" / folder_name)
            sheet.tasks[task_type] = task
        return sheet

    def _find_tasks(self):
        text = (self.run_section / "RunSection_CreateTask.cpp").read_text(encoding="utf-8", errors="replace")
        tasks, last = [], 0
        for match in self.TASK_CLASS.finditer(text):
            names = [a or b for a, b in self.TASK_NAME.findall(text[last:match.start()])]
            last = match.end()
            if match.group(2) in ("TaskHSGeneral", "TaskSSGeneral", "TaskMultiSSGeneral"):
                tasks.append((match.group(1), match.group(2), names))
        return tasks

    def _scan_task(self, task_type, aliases, folder):
        files = sorted(p for p in folder.glob("*") if p.suffix in (".cpp", ".h"))
        texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in files}
        # Only the execution plan and task read the task's own properties; other files in the folder
        # (relaxation builders, state preparation) read properties of Interaction/State objects.
        task_files = {p: t for p, t in texts.items() if p.suffix == ".cpp" and
                      (p.name.endswith("ExecutionPlan.cpp") or p.name.startswith("Task"))}
        task = TaskSpec(type=task_type, aliases=aliases)
        for path, text in task_files.items():
            for keys, target, offset, is_read in self._property_calls(text):
                self._add_property(task, keys, target, offset, is_read, path, text, texts)
        for path, text in task_files.items():
            self._add_constraints(task, path, text)
        return task

    def _property_calls(self, text):
        calls = []
        for m in self.GET_CALL.finditer(text):
            calls.append((m.start(), m.end(), [m.group(2)], m.group(3), m.group(1) == "GetList" and "list" or False))
        for m in self.READ_CALL.finditer(text):
            keys = re.findall(_STRING, m.group(1))
            if keys:
                calls.append((m.start(), m.end(), keys, m.group(2), True))
        calls.sort(key=lambda c: c[:2])
        grouped = []
        for start, end, keys, target, is_read in calls:
            # ``Get("a", x) || Get("b", x)`` reads one property under two names
            if grouped and "||" in text[grouped[-1][3]:start] and re.fullmatch(r"[\s|()]*", text[grouped[-1][3]:start]) \
                    and grouped[-1][1].split(".")[-1] == target.split(".")[-1]:
                grouped[-1][0].extend(keys)
                grouped[-1][3] = end
            else:
                grouped.append([list(keys), target, start, end, is_read])
        return [(keys, target, start, is_read) for keys, target, start, _, is_read in grouped]

    def _add_property(self, task, keys, target, offset, is_read, path, text, texts):
        keys = [k.lower() for k in keys]
        existing = next((task.properties[k] for k in keys if k in task.properties), None)
        if existing is not None:
            for k in keys:
                if k not in existing.names:
                    existing.aliases.append(k)
            return
        name = target.split(".")[-1]
        if is_read == "list":
            value_type, default = "list", None
        elif is_read:
            # ReadString targets are reused locals; the default is the value assigned just before the call
            assigned = re.findall(r'\b' + re.escape(name) + r'\s*=\s*' + _STRING, text[:offset])
            value_type, default = "string", (assigned[-1] if assigned else None)
        else:
            value_type, default = self._declaration(name, texts, text)
        line = text.count("\n", 0, offset) + 1
        prop = PropertySpec(name=keys[0], aliases=keys[1:], value_type=value_type, default=default,
                            description=self._comment_above(text, line),
                            source=f"{path.relative_to(self.root).as_posix()}:{line}")
        task.properties[prop.name] = prop

    @staticmethod
    def _comment_above(text, line):
        lines = text.splitlines()
        comment, i = [], line - 2
        while i >= 0 and lines[i].strip().startswith("//"):
            comment.insert(0, lines[i].strip().lstrip("/").strip())
            i -= 1
        return " ".join(comment)

    def _declaration(self, name, texts, local_text):
        pattern = re.compile(r'(?<![\w.])(?:const\s+)?(' + _TYPE_PATTERN + r')\s+&?' + re.escape(name) +
                             r'\s*(?:=\s*([^;,{]+?))?\s*[;,={)]')
        found = None
        for source in [local_text, *(t for t in texts.values() if t is not local_text)]:
            for m in pattern.finditer(source):
                result = (_CPP_TYPES[m.group(1)], self._literal(m.group(2)))
                if result[1] is not None:
                    return result
                found = found or result
        return found or ("unknown", None)

    @staticmethod
    def _literal(text):
        if text is None:
            return None
        text = text.strip()
        if text in ("true", "false"):
            return text == "true"
        if re.fullmatch(r"-?\d+", text):
            return int(text)
        if re.fullmatch(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?f?", text):
            return float(text.rstrip("f"))
        if re.fullmatch(_STRING, text):
            return text[1:-1]
        return None

    def _add_constraints(self, task, path, text):
        known = {n.lower(): p.name for p in task.properties.values() for n in p.names}
        for m in self.ERROR.finditer(text):
            message = "".join(re.findall(_STRING, m.group(1)))
            line = text.count("\n", 0, m.start()) + 1
            source = f"{path.relative_to(self.root).as_posix()}:{line}"
            lowered = message.lower()
            keys = []
            for token in re.findall(r"[a-z_]+", lowered):
                name = known.get(token)
                if name and name not in keys:
                    keys.append(name)
            if not keys:
                continue
            choice = re.match(r"(\w+) must be (.+)$", message)
            if choice and choice.group(1).lower() in known:
                options = [o.strip() for o in re.split(r",\s*(?:or\s+)?|\s+or\s+|/", choice.group(2))]
                if all(re.fullmatch(r"[\w\-]+", o) for o in options):
                    prop = task.properties[known[choice.group(1).lower()]]
                    if not prop.choices:
                        prop.choices = options
                    continue
            if any(c in lowered for c in _CONFLICT_CUES):
                kind = "conflicts"
            elif any(c in lowered for c in _REQUIRE_CUES):
                kind = "requires"
            elif any(c in lowered for c in _SCOPE_CUES):
                kind = "scoped"
            elif any(c in lowered for c in _RANGE_CUES):
                kind = "range"
            else:
                continue
            if kind == "requires":
                before = lowered.split(" requires ")[0]
                subject = [known[t] for t in re.findall(r"[a-z_]+", before) if t in known]
                if not subject:
                    continue
                keys = [subject[0]] + [k for k in keys if k != subject[0]]
            task.constraints.append(Constraint(kind=kind, keys=keys, message=message, source=source))


TYPED_DICTS = Path(__file__).resolve().parent / "task_properties.py"


def update_bundled_files(molspin=None):
    """Rescan the MolSpin source and rewrite the bundled spec JSON and ``task_properties.py``.

    Run after updating MolSpin (``python -m MolSpinPy.utility.molspin_spec [path/to/MolSpin]``) and commit
    both files. Raises if no MolSpin source is found, so a stale fallback is never written back.
    """
    root = find_source_root(molspin)
    if root is None:
        raise FileNotFoundError("No MolSpin source tree found. Pass its path or set MOLSPIN_SOURCE.")
    sheet = MolSpinSpecBuilder(root).build_sheet()
    sheet.source_root = ""
    sheet.to_json(BUNDLED_SPEC)
    sheet.write_typed_dicts(TYPED_DICTS)
    _SHEET_CACHE.clear()
    return sheet


if __name__ == "__main__":
    import sys
    updated = update_bundled_files(sys.argv[1] if len(sys.argv) > 1 else None)
    for task in updated.tasks.values():
        print(f"{task.type}: {len(task.properties)} properties, {len(task.constraints)} constraints")
    print(f"Wrote {BUNDLED_SPEC} and {TYPED_DICTS}")
