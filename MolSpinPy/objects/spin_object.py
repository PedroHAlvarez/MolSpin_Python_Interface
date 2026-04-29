import enum
import MolSpinPy.maths.tensor as tensor

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

class Electron(SpinObject):
    def __init__(self, name):
        SpinObject.__init__(self, name)
        self.type = SpinObjectType.Electron
        self.s_value = 1.0/2.0
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
            raise ValueError("Electron spin value must be a multiple of 1/2")
        self.s_value = s_value_float
    def render_to_string(self):
        return f"spin(electron, {self.s_value}, {self.g_tensor.render_to_string()})"
    def ConvertToDictionary(self):
        dict = {}
        dict['spin'] = self.s_value
        dict['tensor'] = self.g_tensor.render_to_string()
        dict['type'] = "electron"
        return self.name, dict

class Nucleus(SpinObject):
    def __init__(self, name):
        SpinObject.__init__(self, name)
        self.type = SpinObjectType.Nucleus
        self.s_value = 1.0/2.0
        self.g_tensor = tensor.Isotropic("1.0")
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
            raise ValueError("Nuclear spin value must be a multiple of 1/2")
        self.s_value = s_value_float
    def render_to_string(self):
        return f"spin(nucleus, {self.s_value}, {self.g_tensor.render_to_string()})"
    def ConvertToDictionary(self):
        dict = {}
        dict['spin'] = self.s_value
        dict['tensor'] = self.g_tensor.render_to_string()
        dict['type'] = "nucleus"
        return self.name, dict

    
