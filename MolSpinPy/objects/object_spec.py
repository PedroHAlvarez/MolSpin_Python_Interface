"""Lossless, JSON friendly descriptions of object-built spin systems.

Used by the project metadata to record spin systems and by the project loader to rebuild
them as real objects, so that actions bound to object variables can be restored.
"""
import numpy as np

from ..maths import tensor as tensor_module
from ..maths.list import List
from ..maths.vector import Vector
from . import interactions as inter
from . import spin_object
from .spin_system import SpinSystem
from .states import State
from .transitions import Transition
from .ActionVariable import BoundVariable

_COLLECTIONS = ("electrons", "nuclei", "interactions", "transitions")


def _name(obj):
    return obj.name if hasattr(obj, "name") else str(obj)


def encode_value(value):
    if isinstance(value, BoundVariable):
        value = value.value
    if isinstance(value, tensor_module.Tensor):
        values = value.values
        if value.type == tensor_module.TensorType.ISOTROPIC:
            return {"__tensor__": "isotropic", "values": values}
        if value.type == tensor_module.TensorType.ANISOTROPIC:
            return {"__tensor__": "anisotropic", "values": list(values)}
        return {"__tensor__": "matrix", "values": [list(row) for row in values]}
    if isinstance(value, Vector):
        return {"__vector__": [float(x) for x in value.value]}
    if isinstance(value, List):
        return {"__list__": [float(x) for x in value.value]}
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [encode_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): encode_value(v) for k, v in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "name"):
        return _name(value)
    raise TypeError(f"Cannot describe value of type {type(value).__name__} in metadata")


def decode_value(value):
    if isinstance(value, dict):
        if "__tensor__" in value:
            kind, values = value["__tensor__"], value["values"]
            if kind == "isotropic":
                return tensor_module.Isotropic(repr(float(values)))
            if kind == "anisotropic":
                return tensor_module.Anisotropic(", ".join(repr(float(v)) for v in values))
            return tensor_module.Matrix("; ".join(", ".join(repr(float(v)) for v in row) for row in values))
        if "__vector__" in value:
            return Vector(" ".join(repr(float(x)) for x in value["__vector__"]))
        if "__list__" in value:
            return List(" ".join(repr(float(x)) for x in value["__list__"]))
        return {k: decode_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode_value(v) for v in value]
    return value


def _spin_spec(spin):
    return {
        "name": spin.name,
        "spin": spin._s_value,
        "g_tensor": encode_value(spin._g_tensor),
        "physical": spin.physical,
    }


# class name -> (constructor attribute names after the spins, builder)
_INTERACTIONS = {
    "Zeeman_Interaction": (inter.Zeeman_Interaction, ("field",)),
    "ZFS_Interaction": (inter.ZFS_Interaction, ("dvalue", "evalue", "prefactor", "energyshift")),
    "Hyperfine_Interaction": (inter.Hyperfine_Interaction, ("tensor",)),
    "Dipolar_Interaction": (inter.Dipolar_Interaction, ("tensor", "r_vector")),
    "Exchange_Interaction": (inter.Exchange_Interaction, ("value",)),
}


def _interaction_spec(interaction):
    cls_name = type(interaction).__name__
    if cls_name not in _INTERACTIONS:
        raise TypeError(f"Interaction type {cls_name} cannot be described in metadata")
    _, fields = _INTERACTIONS[cls_name]
    return {
        "class": cls_name,
        "name": interaction.name,
        "spins": [_name(s) for s in interaction.spins],
        "fields": {f: encode_value(getattr(interaction, "_" + f)) for f in fields},
    }


def _transition_spec(transition):
    return {
        "name": transition.name,
        "source": _name(transition._source),
        "rate": encode_value(transition._rate),
        "targetsystem": None if transition._targetsystem is None else _name(transition._targetsystem),
        "targetstate": None if transition._targetstate is None else _name(transition._targetstate),
        "include_all_nuclear": transition.include_all_nuclear,
    }


def system_to_spec(system):
    return {
        "name": system.name,
        "electrons": [_spin_spec(e) for e in system.electrons],
        "nuclei": [_spin_spec(n) for n in system.nuclei],
        "interactions": [_interaction_spec(i) for i in system.interactions],
        "states": [{"name": s.name, "definition": s.definition} for s in system.base_states],
        "transitions": [_transition_spec(t) for t in system.transitions],
        "properties": encode_value(system.properties),
    }


def _build_spin(cls, spec):
    spin = cls(spec["name"])
    spin.spin = spec["spin"]
    spin.g_tensor = decode_value(spec["g_tensor"])
    spin.set_physical(spec.get("physical", True))
    return spin


def system_from_spec(spec):
    system = SpinSystem(spec["name"])
    spins = {}
    for s in spec["electrons"]:
        spins[s["name"]] = system.add_electron(_build_spin(spin_object.Electron, s))
    for s in spec["nuclei"]:
        spins[s["name"]] = system.add_nucleus(_build_spin(spin_object.Nucleus, s))
    for i in spec["interactions"]:
        cls = _INTERACTIONS[i["class"]][0]
        members = [spins[n] for n in i["spins"]]
        fields = {k: decode_value(v) for k, v in i["fields"].items()}
        if issubclass(cls, inter.SingleSpinInteraction):
            target = members[0] if len(members) == 1 else members
            system.add_interaction(cls(i["name"], target, **fields))
        else:
            system.add_interaction(cls(i["name"], members[0], members[1], **fields))
    for s in spec["states"]:
        system.add_state(State.from_text(s["name"], s["definition"]))
    for t in spec["transitions"]:
        system.add_transition(Transition(
            name=t["name"], source=t["source"], rate=decode_value(t["rate"]),
            targetsystem=t["targetsystem"], targetstate=t["targetstate"],
            include_all_nuclear=t["include_all_nuclear"],
        ))
    for key, value in decode_value(spec["properties"]).items():
        system.set_property(key, value)
    return system


def locate_object(spin_systems, instance):
    """Return (system name, collection, object name) for an object inside the given systems."""
    for system_name, system in spin_systems.items():
        for collection in _COLLECTIONS:
            for obj in getattr(system, collection):
                if obj is instance:
                    return system_name, collection, obj.name
    return None


def resolve_object(spin_systems, system_name, collection, object_name):
    for obj in getattr(spin_systems[system_name], collection):
        if obj.name == object_name:
            return obj
    raise KeyError(f"{collection[:-1]} '{object_name}' not found in spin system '{system_name}'")
