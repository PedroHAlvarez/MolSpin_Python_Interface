import enum
from MolSpinPy.maths.tensor import Tensor as tensor
from MolSpinPy.maths.vector import Vector as vector
from . import SpinObject
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
    def __init__(self, name, spin):
        super().__init__(name, [spin])
        self.type = InteractionType.NOT_SET
    @property
    def is_multi_spin(self):
        return False
    @property
    def spin(self):
        return self.spins[0]

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
        return f"zeeman({self.spin.name},{self._field.render_to_string()})"
    def ConvertToDictionary(self):
        dict = {}
        #stuff
        return self.name,dict
    field = ActionVariable.ActionVariable(field)
    
    

