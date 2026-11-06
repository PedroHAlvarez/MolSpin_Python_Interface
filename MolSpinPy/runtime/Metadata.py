import copy
import datetime
import enum
import hashlib
import json
import os
import platform
import re

from ..objects import object_spec
from ..utility import code_capture
from ..objects.ActionVariable import BoundVariable

class ProjectMetadata:
    """Build reproducibility metadata for a MolSpin project."""

    def __init__(self, project_name, template, base_input, manager=None, settings=None, spin_systems=None):
        self.project_name = project_name
        self.template = template
        self.base_input = copy.deepcopy(base_input)
        self.manager = manager
        self.settings = copy.deepcopy(settings or {})
        self.spin_systems = dict(spin_systems or {})
        # Captured at construction so that running the actions can't alter what is recorded.
        self.object_systems = [object_spec.system_to_spec(s) for s in self.spin_systems.values()]
        self._actions, self._action_tree_data = self._capture_actions()

    def _binding(self, action):
        target = getattr(action, "ptr", None)
        if isinstance(target, BoundVariable):
            location = object_spec.locate_object(self.spin_systems, target.instance)
            if location is None:
                raise ValueError(
                    f"Action on '{target.name}' targets an object that is not part of any spin system "
                    "added to the project, so it cannot be recorded"
                )
            system_name, collection, object_name = location
            return {"kind": "object", "spin_system": system_name, "collection": collection,
                    "object": object_name, "attribute": target.attribute}
        if getattr(action, "key", None):
            return {"kind": "dictionary", "key": action.key}
        return None

    def _capture_actions(self):
        if self.manager is None:
            return [], []
        registered_actions = list(getattr(self.manager, "_actions", []))
        action_tree = self._action_tree(registered_actions)
        flat = {}

        def collect(node):
            flat[node["id"]] = node
            for child in node["children"]:
                collect(child)
        for root in action_tree:
            collect(root)
        # Flat entries reference children by id; the tree carries the nested form.
        actions = [{**flat[i], "children": [c["id"] for c in flat[i]["children"]]} for i in sorted(flat)]
        return actions, action_tree

    @staticmethod
    def _value(value):
        if isinstance(value, dict):
            return {
                str(key): ProjectMetadata._value(item)
                for key, item in value.items()
                if key != "__case_map"
            }
        if isinstance(value, (list, tuple)):
            return [ProjectMetadata._value(item) for item in value]
        if isinstance(value, enum.Enum):
            return f"{type(value).__name__}.{value.name}"
        if hasattr(value, "tolist"):
            return ProjectMetadata._value(value.tolist())
        if hasattr(value, "item"):
            return value.item()
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if hasattr(value, "value") and not callable(value.value):
            return ProjectMetadata._value(value.value)
        return repr(value)

    @staticmethod
    def _template_source(template):
        return re.sub(
            r"{% comment %}.*?{% endcomment %}",
            "",
            template,
            flags=re.DOTALL,
        )

    def _action_metadata(self, action):
        target = getattr(action, "ptr", None)
        target_name = getattr(target, "name", None)
        if target_name is None:
            target_name = getattr(action, "_promise", None)

        function = getattr(action, "func", None)
        function_metadata = {}
        metadata_hook = getattr(function, "__metadata__", None)
        if callable(metadata_hook):
            function_metadata = self._value(metadata_hook()) or {}
        if not isinstance(function_metadata, dict):
            function_metadata = {"note": function_metadata}
        function_metadata.setdefault("note", getattr(function, "metadata_note", None))
        
        # Capture state namespace if present
        state_dict = {}
        state_obj = getattr(function, "_state", None)
        if state_obj is not None and hasattr(state_obj, "__dict__"):
            state_dict = self._value(state_obj.__dict__)
        
        action_metadata = {
            "id": None,
            "target": target_name,
            "key": getattr(action, "key", None),
            "binding": self._binding(action),
            "function": getattr(function, "name", type(function).__name__),
            "function_type": f"{type(function).__module__}.{type(function).__qualname__}",
            "function_config": {
                k: v for k, v in self._value(getattr(function, "_init_config", {})).items()
                if k != "func"
            },
            "function_source": getattr(function, "_source", None),
            "function_source_sha256": (
                hashlib.sha256(function._source.encode("utf-8")).hexdigest()
                if getattr(function, "_source", None) else None
            ),
            "function_dependencies": list(getattr(function, "_dependencies", [])),
            "function_external_modules": (
                code_capture.external_modules(getattr(function, "_source", None), getattr(function, "_dependencies", []))
                if getattr(function, "_source", None) else []
            ),
            "function_dependencies_sha256": (
                code_capture.dependencies_digest(function._dependencies)
                if getattr(function, "_dependencies", None) else None
            ),
            "function_metadata": function_metadata,
            "function_parameters": self._value(getattr(function, "_param", {})),
            "parameter_names": list(getattr(function, "_param_names", [])),
            "sequences": self._value(getattr(action, "_sequences", {})),
            "timing": {
                "start": getattr(action, "start", None),
                "duration": getattr(action, "duration", None),
                "interval": getattr(action, "interval", None),
                "loop": getattr(action, "loop", None),
                "active": getattr(action, "active", None),
            },
            "priority": self._value(getattr(action, "priority", None)),
            "parent": getattr(getattr(action, "parent", None), "name", None),
            "parent_id": None,
            "children": [],
        }
        
        # Only include state if it has content
        if state_dict:
            action_metadata["state"] = state_dict
        
        return action_metadata

    def _action_tree(self, actions):
        metadata_by_action = {}
        for index, action in enumerate(actions):
            action_metadata = self._action_metadata(action)
            action_metadata["id"] = index
            metadata_by_action[id(action)] = action_metadata

        roots = []
        for action in actions:
            action_metadata = metadata_by_action[id(action)]
            parent = getattr(action, "parent", None)
            if parent is None or id(parent) not in metadata_by_action:
                roots.append(action_metadata)
            else:
                parent_metadata = metadata_by_action[id(parent)]
                action_metadata["parent_id"] = parent_metadata["id"]
                parent_metadata["children"].append(action_metadata)
        return roots

    def as_dict(self, steps=None, steps_per_simulation=None, execution_mode=None, extra=None):
        actions = self._actions
        action_tree = self._action_tree_data

        metadata = {
            "metadata_format": 2,
            "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "project": self.project_name,
            "execution": {
                "mode": execution_mode,
                "steps": steps,
                "steps_per_simulation": steps_per_simulation,
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "template": {
                "path": os.path.abspath(self.template.template_path),
                "source": self._template_source(self.template.raw_template),
            },
            "base_input": self._value(self.base_input),
            "object_systems": self.object_systems,
            "case_map": self._value(self.base_input.get("__case_map", {})) if isinstance(self.base_input, dict) else {},
            "settings": self._value(self.settings),
            "parameter_sweep": {
                "action_count": len(actions),
                "actions": actions,
                "tree": action_tree,
            },
        }
        if extra:
            metadata["execution"].update(self._value(extra))
        return metadata

    def write(self, output_dir, steps=None, steps_per_simulation=None, execution_mode=None, extra=None):
        os.makedirs(output_dir, exist_ok=True)
        metadata = self.as_dict(steps, steps_per_simulation, execution_mode, extra)
        json_path = os.path.join(output_dir, f"{self.project_name}_metadata.json")
        markdown_path = os.path.join(output_dir, f"{self.project_name}_metadata.md")
        with open(json_path, "w", encoding="utf-8") as metadata_file:
            json.dump(metadata, metadata_file, indent=2, sort_keys=False)
        with open(markdown_path, "w", encoding="utf-8") as readable_file:
            readable_file.write(self._markdown(metadata))
        return json_path, markdown_path

    @staticmethod
    def _markdown(metadata):
        execution = metadata["execution"]
        sweep = metadata["parameter_sweep"]
        lines = [
            f"# MolSpin project metadata: {metadata['project']}",
            "",
            f"- Created (UTC): {metadata['created_utc']}",
            f"- Execution mode: {execution.get('mode')}",
            f"- Steps: {execution.get('steps')}",
            f"- Python: {execution.get('python')}",
            f"- Platform: {execution.get('platform')}",
            "",
            "## Base template",
            "",
            f"Source: `{metadata['template']['path']}`",
            "",
            "```text",
            metadata["template"]["source"].rstrip(),
            "```",
            "",
            "## Base input data",
            "",
            "```json",
            json.dumps(metadata["base_input"], indent=2),
            "```",
            "",
            "## Parameter sweep",
            "",
            f"Actions: {sweep['action_count']}",
            "",
        ]
        def render_action(action, depth=0):
            heading = "#" * (depth+3)
            action_lines = [
                f"{heading} Action {action['id']}: {action['target']}",
                f"- Key: `{action.get('key')}`",
                f"- Binding: `{json.dumps(action.get('binding'), sort_keys=True)}`",
                f"- Function: `{action['function']}` (`{action.get('function_type')}`)",
                f"- Function config: `{json.dumps(action.get('function_config', {}), sort_keys=True)}`",
                f"- Note: {action['function_metadata'].get('note') or 'None'}",
                f"- Parent: {action['parent']} (id: {action['parent_id']})",
                f"- Priority: {action['priority']}",
                f"- Timing: `{json.dumps(action['timing'], sort_keys=True)}`",
                f"- Function parameters: `{json.dumps(action['function_parameters'], sort_keys=True)}`",
            ]
            
            # Include state if present
            if "state" in action and action["state"]:
                action_lines.append(f"- State: `{json.dumps(action['state'], sort_keys=True)}`")
            if action.get("function_source"):
                action_lines.extend(["- Source:", "", "```python", action["function_source"].rstrip(), "```"])
            if action.get("function_external_modules"):
                action_lines.extend([
                    "",
                    f"> **WARNING:** this action uses modules outside the built-in allow-list: "
                    f"`{', '.join(action['function_external_modules'])}`. "
                    "Loading this metadata requires permitting them explicitly: "
                    f"`ProjectLoader(path, allow_code=True, allow_modules={action['function_external_modules']!r})`. "
                    "Permitted modules are then remembered on that installation.",
                    "",
                ])
            if action.get("function_dependencies"):
                action_lines.extend(["- Dependencies (executed before the function, in order):", "", "```python"])
                action_lines.extend(d["source"].rstrip() for d in action["function_dependencies"])
                action_lines.append("```")
            
            action_lines.append("")
            lines.extend(action_lines)
            for child in action["children"]:
                render_action(child, depth + 1)

        for action in sweep["tree"]:
            render_action(action)
        return "\n".join(lines)