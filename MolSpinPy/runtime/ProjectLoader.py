import ast
import hashlib
import importlib
import inspect
import json
import math
import textwrap

import numpy as np

from .. import objects
from ..maths.list import List
from ..maths.vector import Vector
from ..objects import ActionFunction as ActionFunctionModule
from ..objects import object_spec
from ..utility import code_capture
from ..objects.ActionObject import Action
from .ActionManager import ActionManager
from .Project import Project, dictMode

SUPPORTED_FORMAT = 2
_BUILTIN_ACTION_PACKAGE = "MolSpinPy.objects.Actions."
_CUSTOM_FUNCTION_TYPE = "MolSpinPy.objects.ActionFunction.CustomActionFunction"


class ProjectLoader:
    """Rebuild a Project (input data, settings, tasks and actions) from its metadata JSON.

    Custom ``@ActionScript`` functions are restored by executing the source stored in the
    metadata, so this only happens when ``allow_code=True``. Only trust metadata you wrote.

    Stored code may use any module, but modules outside ``code_capture.ALLOWED_MODULES``
    are refused unless named in ``allow_modules`` (``True`` permits any module for this load
    only). The refusal lists the modules, so review them before permitting. Modules named in
    ``allow_modules`` are remembered in this installation's permitted-modules list
    (``code_capture.permitted_modules_path()``), which then extends the allow-list for later
    loads; pass ``remember_modules=False`` to permit them for this load only.
    """

    def __init__(self, metadata, allow_code=False, allow_modules=(), remember_modules=True):
        if isinstance(metadata, (str, bytes)) or hasattr(metadata, "__fspath__"):
            with open(metadata, "r", encoding="utf-8") as metadata_file:
                metadata = json.load(metadata_file)
        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a path to a metadata JSON file or a dictionary")
        fmt = metadata.get("metadata_format")
        if not isinstance(fmt, int) or fmt < SUPPORTED_FORMAT:
            raise ValueError(
                f"Unsupported metadata_format {fmt!r}; at least {SUPPORTED_FORMAT} is required to rebuild a project"
            )
        self.metadata = metadata
        self.allow_code = allow_code
        self.allow_modules = True if allow_modules is True else tuple(allow_modules or ())
        self.remember_modules = remember_modules

    def build(self, name=None):
        """Return a new Project. The metadata is not modified."""
        meta = self.metadata
        project = Project(name or meta["project"])

        base_input = json.loads(json.dumps(meta["base_input"]))
        base_input["__case_map"] = dict(meta.get("case_map", {}))
        project.attach_dict(base_input, mode=dictMode.REPLACE)
        if base_input.get("settings"):
            project._extract_settings()
        else:
            project._settings = dict(meta.get("settings", {}))

        self._check_template(project)

        sweep = meta.get("parameter_sweep", {})
        actions = sweep.get("actions", [])
        for spec in meta.get("object_systems", []):
            project.add_spin_system(object_spec.system_from_spec(spec))
        if actions:
            project.attach_ActionManager(self._build_manager(project, actions))
        return project

    def _check_template(self, project):
        from .Metadata import ProjectMetadata
        stored = self.metadata.get("template", {}).get("source")
        current = ProjectMetadata._template_source(project._template.raw_template)
        if stored is not None and stored != current:
            print("Warning: the template that wrote this metadata differs from the installed template.")

    def _build_manager(self, project, action_entries):
        entries = {entry["id"]: entry for entry in action_entries}
        built = {}

        def make(action_id):
            if action_id in built:
                return built[action_id]
            entry = entries[action_id]
            parent = make(entry["parent_id"]) if entry.get("parent_id") is not None else None
            built[action_id] = self._build_action(project, entry, parent)
            return built[action_id]

        for action_id in sorted(entries):
            make(action_id)

        manager = ActionManager(registry={})
        # Set every priority first: add_action derives a child's priority from its parent's.
        for action_id in sorted(entries):
            built[action_id].priority = entries[action_id].get("priority") or 0
        for action_id in sorted(entries):
            manager.add_action(built[action_id], priority=entries[action_id].get("priority") or 0)
        return manager

    def _build_action(self, project, entry, parent):
        binding = entry.get("binding")
        if binding is None and entry.get("key"):
            binding = {"kind": "dictionary", "key": entry["key"]}
        if binding is None:
            raise ValueError(
                f"Action {entry['id']} ({entry.get('target')}) was not bound to a project variable "
                "and cannot be rebuilt from metadata"
            )
        function = self._build_function(entry)

        timing = entry.get("timing", {})
        kwargs = {}
        if binding["kind"] == "dictionary":
            target = project.MSDdict
            kwargs["key"] = binding["key"]
        elif binding["kind"] == "object":
            owner = object_spec.resolve_object(
                project._spin_systems, binding["spin_system"], binding["collection"], binding["object"])
            target = getattr(owner, binding["attribute"])
        else:
            raise ValueError(f"Unknown binding kind {binding['kind']!r} for action {entry['id']}")
        for field in ("duration", "interval", "loop", "active"):
            if timing.get(field) is not None:
                kwargs[field] = timing[field]
        if parent is not None:
            kwargs["parent"] = parent
        if entry.get("function_type") == _CUSTOM_FUNCTION_TYPE:
            sequences = entry.get("sequences", {})
            for pname, pvalue in entry.get("function_parameters", {}).items():
                if pname in function._param_names and pname not in sequences:
                    kwargs[pname] = pvalue
            kwargs.update({k: v for k, v in sequences.items() if k in function._param_names})

        action = Action(target, function, **kwargs)
        if timing.get("start") is not None:
            action.start = timing["start"]  # not accepted as a constructor keyword by Action
        return action

    def _build_function(self, entry):
        function_type = entry.get("function_type")
        if function_type == _CUSTOM_FUNCTION_TYPE:
            return self._build_custom_function(entry)
        if not function_type or not function_type.startswith(_BUILTIN_ACTION_PACKAGE):
            raise ValueError(f"Refusing to load unknown action function type {function_type!r}")
        module_name, _, class_name = function_type.rpartition(".")
        cls = getattr(importlib.import_module(module_name), class_name, None)
        if not (inspect.isclass(cls) and issubclass(cls, ActionFunctionModule.ActionFunction)):
            raise ValueError(f"{function_type} is not an ActionFunction")
        return cls(**self._convert_config(cls, entry.get("function_config", {})))

    @staticmethod
    def _convert_config(cls, config):
        params = inspect.signature(cls.__init__).parameters
        converted = {}
        for pname, value in config.items():
            param = params.get(pname)
            annotation = param.annotation if param is not None else inspect.Parameter.empty
            if pname in ("direction", "axis") and isinstance(value, (list, tuple)):
                text = " ".join(repr(float(x)) for x in value)
                converted[pname] = List(text) if annotation is List else Vector(text)
            elif isinstance(value, str) and inspect.isclass(annotation) and hasattr(annotation, "__members__"):
                converted[pname] = annotation[value.split(".")[-1]]
            elif pname == "frame" and isinstance(value, str):
                converted[pname] = getattr(cls, "frame")[value.split(".")[-1]]
            else:
                converted[pname] = value
        return converted

    def _build_custom_function(self, entry):
        if not self.allow_code:
            raise PermissionError(
                f"Action {entry['id']} uses a custom function; pass allow_code=True to execute its stored source"
            )
        source = entry.get("function_source")
        if not source:
            raise ValueError(f"Action {entry['id']} has no stored function source")
        expected = entry.get("function_source_sha256")
        if expected and hashlib.sha256(source.encode("utf-8")).hexdigest() != expected:
            raise ValueError(f"Stored source for action {entry['id']} does not match its recorded hash")

        dependencies = entry.get("function_dependencies") or []
        expected_deps = entry.get("function_dependencies_sha256")
        if expected_deps and code_capture.dependencies_digest(dependencies) != expected_deps:
            raise ValueError(f"Stored dependencies for action {entry['id']} do not match their recorded hash")
        if dependencies and not expected_deps:
            raise ValueError(f"Action {entry['id']} has dependencies without a recorded hash")

        tree = ast.parse(textwrap.dedent(source))
        funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        if len(funcs) != 1:
            raise ValueError(f"Action {entry['id']} source must define exactly one function")
        func_def = funcs[0]
        func_def.decorator_list = []  # the decorator is re-applied below, whatever alias it used
        code_capture.check_modules_permitted(
            source, dependencies, self.allow_modules, label=f"custom function of action {entry['id']}")
        if self.remember_modules and self.allow_modules is not True:
            used = code_capture.external_modules(source, dependencies)
            code_capture.permit_modules([m for m in used if code_capture.module_allowed(m, self.allow_modules, use_stored=False)])
        namespace = {"np": np, "numpy": np, "math": math, "MolSpinPy": __import__("MolSpinPy")}
        code_capture.execute_dependencies(namespace, dependencies, self.allow_modules)
        exec(compile(ast.Module(body=[func_def], type_ignores=[]), "<molspin metadata>", "exec"), namespace)
        func = namespace[func_def.name]
        func.__molspin_source__ = source
        func.__molspin_dependencies__ = dependencies
        return objects.ActionScript(func)
