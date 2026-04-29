import enum
import maths.tensor as tensor

class SpinObjectType(enum.Enum):
    Electron = 1
    Nucleus = 2
    NOT_SET = 0

class SpinObject:
    def __init__(self,name):
        self.name = name
        self.type = SpinObjectType.NOT_SET
        self.s_value = 0.0
        self.g_tensor = tensor.Isotropic("0")

class ElectronSpin(SpinObject):
    def __init__(self, name):
        SpinObject.__init__(self, name)
        self.type = SpinObjectType.Electron
        self.s_value = 0.5
        self.g_tensor = tensor.Isotropic("2.023")
    def set_g_tensor(self, g_value):
        if isinstance(g_value, float):
            self.g_tensor = tensor.Isotropic(str(g_value))
        elif isinstance(g_value, str):
            self.g_tensor = tensor.Isotropic(g_value)
        elif isinstance(g_value, tensor.Tensor):
            self.g_tensor = g_value
        else:
            raise ValueError("Invalid g_tensor value")
    def set_spin_value(self,s_value):
        s_value_float = float(s_value)
        if s_value_float % 0.5 != 0:
            raise ValueError("Electron spin value must be a multiple of 0.5")
        self.s_value = s_value_float
    
