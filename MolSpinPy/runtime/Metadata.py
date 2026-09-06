import copy
import datetime
import json
import os
import platform
import re


class ProjectMetadata:
    """Build reproducibility metadata for a MolSpin project."""

    def __init__(self, project_name, template, base_input, manager=None, settings=None):
        self.project_name = project_name
        self.template = template
        self.base_input = copy.deepcopy(base_input)
        self.manager = manager
        self.settings = copy.deepcopy(settings or {})

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
        if hasattr(value, "tolist"):
            return ProjectMetadata._value(value.tolist())
        if hasattr(value, "item"):
            return value.item()
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
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
        return {
            "id": None,
            "target": target_name,
            "function": getattr(function, "name", type(function).__name__),
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

    def as_dict(self, steps=None, execution_mode=None, extra=None):
        actions = []
        if self.manager is not None:
            registered_actions = list(getattr(self.manager, "_actions", []))
            actions = [self._action_metadata(action) for action in registered_actions]
            for index, action in enumerate(actions):
                action["id"] = index
            action_tree = self._action_tree(registered_actions)
        else:
            action_tree = []

        metadata = {
            "metadata_format": 1,
            "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "project": self.project_name,
            "execution": {
                "mode": execution_mode,
                "steps": steps,
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "template": {
                "path": os.path.abspath(self.template.template_path),
                "source": self._template_source(self.template.raw_template),
            },
            "base_input": self._value(self.base_input),
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

    def write(self, output_dir, steps=None, execution_mode=None, extra=None):
        os.makedirs(output_dir, exist_ok=True)
        metadata = self.as_dict(steps, execution_mode, extra)
        json_path = os.path.join(output_dir, "project_metadata.json")
        markdown_path = os.path.join(output_dir, "project_metadata.md")
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
            heading = "#" * min(depth + 3, 6)
            lines.extend([
                f"{heading} Action {action['id']}: {action['target']}",
                f"- Function: `{action['function']}`",
                f"- Note: {action['function_metadata'].get('note') or 'None'}",
                f"- Parent: {action['parent']} (id: {action['parent_id']})",
                f"- Priority: {action['priority']}",
                f"- Timing: `{json.dumps(action['timing'], sort_keys=True)}`",
                f"- Function parameters: `{json.dumps(action['function_parameters'], sort_keys=True)}`",
                "",
            ])
            for child in action["children"]:
                render_action(child, depth + 1)

        for action in sweep["tree"]:
            render_action(action)
        return "\n".join(lines)