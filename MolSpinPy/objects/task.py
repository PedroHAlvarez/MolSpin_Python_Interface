from ..utility.molspin_spec import get_spec_sheet
from ..utility.task_properties import TaskBase


class Task(TaskBase):
    """A MolSpin `Run { Task <name> {...} }` entry.

    The constructor signatures and their docstrings (properties, choices, defaults, requires/conflicts
    rules per task type) are generated from the MolSpin spec sheet into `utility/task_properties.py`
    and shown by editors while the task is being created. Refresh them with
    `python -m MolSpinPy.utility.molspin_spec`.

    When `type` is one of the general tasks (HSGeneral, SSGeneral, MultiSSGeneral) the matching
    `TaskSpec` is attached as `spec`. Other task types have `spec = None`. Properties are not validated yet.
    """

    @property
    def spec(self):
        """The `TaskSpec` for this task type, or None if MolSpinPy has no spec for it."""
        return get_spec_sheet().get(self.type)

    def allowed_properties(self):
        """Accepted property names including aliases (empty if the type has no spec)."""
        return self.spec.allowed_keys() if self.spec else []

    def required_properties(self):
        return self.spec.required_keys() if self.spec else []

    def property_spec(self, key):
        """The `PropertySpec` for a property name or alias, or None."""
        spec = self.spec
        name = spec.resolve_alias(key) if spec else None
        return spec.properties[name] if name else None

    def unknown_properties(self):
        """Set properties the spec does not recognise. Informational only, nothing is rejected."""
        spec = self.spec
        if spec is None:
            return []
        return [k for k in self.properties if spec.resolve_alias(k) is None]

    def set_property(self, key, value):
        self.properties[key] = value

    def ConvertToDictionary(self):
        dict_data = {"type": self.type}
        dict_data.update(self.properties)
        return self.name, dict_data
