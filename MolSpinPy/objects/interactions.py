import enum
from MolSpinPy.maths.tensor import Tensor as tensor
from MolSpinPy.maths.vector import Vector as vector
from MolSpinPy.objects.spin_object import SpinObject
from . import ActionVariable
#from . import TimeDependance 

class InteractionType(enum.Enum):
    NOT_SET = 0
    
    #single spin interactions
    Zeeman = 1
    ZFS = 2
    LinearStarkShift = 3

    #double spin interactions
    Hyperfine = 4
    Dipolar = 5
    Exchange = 6

    #complex interactions
    SchultenWolynes = 7

#base interaction class
class Interaction:
    def __init__(self,name, spins):
        self.name = name
        self.type = InteractionType.NOT_SET
        self.spins = tuple(spins)
    
    def render_to_string(self):
        """Should be implemented by derived classes"""
        raise NotImplementedError("Subclasses must implement render_to_string method")
    def ConvertToDictionary(self):
        """Should be implemented by derived classes"""
        raise NotImplementedError("Subclasses must implement ConvertToDictionary method")


class SingleSpinInteraction(Interaction):
    def __init__(self, name, spins):
        if not isinstance(spins, (list, tuple, set)):
            spin_list = [spins]
        else:
            spin_list = list(spins)
        super().__init__(name, spin_list)
        self.type = InteractionType.NOT_SET
    @property
    def is_multi_spin(self): #this in regards to the actual interaction, not the number of spins it acts on
        return False
    @property
    def spin(self):
        return self.spins[0] if len(self.spins) == 1 else self.spins
    @property
    def spin_names(self):
        return [s.name if hasattr(s, 'name') else str(s) for s in self.spins]

class DoubleSpinInteraction(Interaction):
    def __init__(self, name, spin1, spin2):
        super().__init__(name, [spin1, spin2])
        self.type = InteractionType.NOT_SET
    @property
    def is_multi_spin(self):
        return True
    @property
    def spin1(self):
        return self.spins[0]
    @property
    def spin2(self):
        return self.spins[1]
    
class Zeeman_Interaction(SingleSpinInteraction):
    def __init__(self, name, spin : SpinObject, field : vector):
        super().__init__(name, spin)
        self.type = InteractionType.Zeeman
        self._field = field

    @property
    def field(self):
        return self._field
    @field.setter
    def field(self,field:vector):
        self._field = field
    def render_to_string(self):
        spin_name = self.spin.name if hasattr(self.spin, 'name') else str(self.spin)
        return f"zeeman({self.spin.name},{self._field.render_to_string()})"
    def ConvertToDictionary(self):
        spins_val = self.spin_names[0] if len(self.spin_names) == 1 else ", ".join(self.spin_names)
        dict_data = {
            "type": "singlespin",
            "spins": spins_val,
            "field": self._field.render_to_string()
        }
        return self.name, dict_data
    #field = ActionVariable.ActionVariable(field)

class ZFS_Interaction(SingleSpinInteraction):
    def __init__(self, name, spins, dvalue, evalue, prefactor=None, energyshift=True):
        super().__init__(name, spins)
        self.type = InteractionType.ZFS
        self._dvalue = dvalue
        self._evalue = evalue
        self._prefactor = prefactor
        self._energyshift = energyshift

    @property
    def dvalue(self):
        return self._dvalue
    @dvalue.setter
    def dvalue(self, val):
        self._dvalue = val

    @property
    def evalue(self):
        return self._evalue
    @evalue.setter
    def evalue(self, val):
        self._evalue = val

    def render_to_string(self):
        spin_name = self.spin.name if hasattr(self.spin, 'name') else str(self.spin)
        return f"zfs({spin_name},{self._dvalue},{self._evalue})"

    def ConvertToDictionary(self):
        spins_val = self.spin_names[0] if len(self.spin_names) == 1 else ", ".join(self.spin_names)
        dict_data = {
            "type": "zfs",
            "spins": spins_val,
            "dvalue": self._dvalue,
            "evalue": self._evalue,
            "prefactor": self._prefactor,
            "energyshift": self._energyshift
        }
        return self.name, dict_data

    #dvalue = ActionVariable.ActionVariable(dvalue)
    #evalue = ActionVariable.ActionVariable(evalue)

class Hyperfine_Interaction(DoubleSpinInteraction):
    def __init__(self, name, spin1, spin2, tensor : tensor):
        super().__init__(name, spin1, spin2)
        self.type = InteractionType.Hyperfine
        self._tensor = tensor

    @property
    def tensor(self):
        return self._tensor
    @tensor.setter
    def tensor(self, val : tensor):
        self._tensor = val

    def render_to_string(self):
        spin1_name = self.spin1.name if hasattr(self.spin1, 'name') else str(self.spin1)
        spin2_name = self.spin2.name if hasattr(self.spin2, 'name') else str(self.spin2)
        return f"hyperfine({spin1_name},{spin2_name},{self._tensor.render_to_string()})"

    def ConvertToDictionary(self):
        s1 = self.spin1.name if hasattr(self.spin1, 'name') else str(self.spin1)
        s2 = self.spin2.name if hasattr(self.spin2, 'name') else str(self.spin2)
        t_str = self._tensor.render_to_string() if hasattr(self._tensor, 'render_to_string') else str(self._tensor)
        dict_data = {
            "type": "hyperfine",
            "group1" : s1,
            "group2" : s2,
            "tensor": self._tensor.render_to_string()
        }
        return self.name, dict_data

    #tensor = ActionVariable.ActionVariable(tensor)
    
class Dipolar_Interaction(DoubleSpinInteraction):
    def __init__(self, name, spin1: SpinObject, spin2: SpinObject, tensor = None, r_vector: vector = None):
        super().__init__(name, spin1, spin2)
        self.type = InteractionType.Dipolar
        self._tensor = tensor
        self._r_vector = r_vector

        if self._tensor is None and self._r_vector is not None:
            # Calculate the dipolar tensor from the relative position vector
            r = self._r_vector.magnitude()
            if r == 0:
                raise ValueError("Relative position vector cannot be zero for dipolar interaction.")
            r_hat = self._r_vector.normalize()
            self._tensor = (1 / r**3) * (3 * tensor.outer(r_hat, r_hat) - tensor.identity())

        if self._tensor is None and self._r_vector is None:
            raise ValueError("Either tensor_val or relative_position must be provided for dipolar interaction.")

    def render_to_string(self):
        spin1_name = self.spin1.name if hasattr(self.spin1, 'name') else str(self.spin1)
        spin2_name = self.spin2.name if hasattr(self.spin2, 'name') else str(self.spin2)
        return f"dipolar({spin1_name},{spin2_name},{self._tensor.render_to_string()})"

    def ConvertToDictionary(self):
        s1 = self.spin1.name if hasattr(self.spin1, 'name') else str(self.spin1)
        s2 = self.spin2.name if hasattr(self.spin2, 'name') else str(self.spin2)
        t_str = self._tensor.render_to_string() if hasattr(self._tensor, 'render_to_string') else str(self._tensor)
        dict_data = {
            "type": "dipolar",
            "group1" : s1,
            "group2" : s2,
            "tensor": t_str
        }
        return self.name, dict_data

    #tensor = ActionVariable.ActionVariable(tensor)
    #r_vector = ActionVariable.ActionVariable(vector)

class Exchange_Interaction(DoubleSpinInteraction):
    def __init__(self, name, spin1: SpinObject, spin2: SpinObject, value):
        super().__init__(name, spin1, spin2)
        self.type = InteractionType.Exchange
        self._value = value

    def render_to_string(self):
        spin1_name = self.spin1.name if hasattr(self.spin1, 'name') else str(self.spin1)
        spin2_name = self.spin2.name if hasattr(self.spin2, 'name') else str(self.spin2)
        return f"exchange({spin1_name},{spin2_name},{self._value})"

    def ConvertToDictionary(self):
        s1 = self.spin1.name if hasattr(self.spin1, 'name') else str(self.spin1)
        s2 = self.spin2.name if hasattr(self.spin2, 'name') else str(self.spin2)
        dict_data = {
            "type": "exchange",
            "group1" : s1,
            "group2" : s2,
            "value": self._value
        }
        return self.name, dict_data

    #value = ActionVariable.ActionVariable(float)