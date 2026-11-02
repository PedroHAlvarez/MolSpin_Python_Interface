import enum
from MolSpinPy.maths import tensor
from . import ActionVariable

class SpinObjectType(enum.Enum):
    Electron = 1
    Nucleus = 2
    NOT_SET = 0

class SpinObject:

    #s_value = ActionVariable()

    def __init__(self,name):
        self.name = name
        self.type = SpinObjectType.NOT_SET
        self.physical = True #useful for something like a Schulten-Wolynes interaction 
        #self.s_value = 0.0
        #self.g_tensor = tensor.Isotropic("0")
        self.spin_map = self.index_mapping

    def set_physical(self, is_physical): 
        self.physical = is_physical 

    @property
    def index_mapping(self):
        s = getattr(self, '_s_value', 0.5)
        m_values = []
        curr = s
        while curr >= -s:
            m_values.append(curr)
            curr -= 1.0
        mapping = {}
        #mapping goes from -m to +m, so that the first index is -m and the last index is +m, this is also the case for non integer spins, e.g. 1/2, 3/2, etc.
        spin_type = 0 #0 for half integer, 1 for integer
        if len(m_values) % 2 == 0:
            spin_type = 0
        else:
            spin_type = 1
        max_map = 0
        min_map = 0
        if spin_type == 0:
            max_map = int(len(m_values) / 2)
            min_map = -max_map
        else:
            max_map = int((len(m_values) - 1) / 2)
            min_map = -max_map

        #now we can create the mapping
        for i in range(len(m_values)):
            index = max_map - i
            if spin_type == 0 and index == 0:
                index = -1
            mapping[index] = m_values[i]

        return mapping

    def resolve_index(self, index):
        """Resolves a user-passed index to its corresponding magnetic quantum number."""
        mapping = self.index_mapping
        if index in mapping:
            return mapping[index]
        raise ValueError(
            f"Invalid index {index} for spin '{self.name}' (s = {self._s_value}). "
            f"Allowed indices are: {list(mapping.keys())}"
        )


    def render_to_string(self):
        """Should be implemented by derived classes"""
        raise NotImplementedError("Subclasses must implement render_to_string method")
    def ConvertToDictionary(self):
        """Should be implemented by derived classes"""
        raise NotImplementedError("Subclasses must implement ConvertToDictionary method")

class Electron(SpinObject):
    def __init__(self, name):
        SpinObject.__init__(self, name)
        self.type = SpinObjectType.Electron
        self._s_value = 1.0/2.0
        self._g_tensor = tensor.Isotropic("2.0023")

    @property
    def spin(self):
        return self._s_value
    @property 
    def g_tensor(self):
        return self._g_tensor
    
    @g_tensor.setter
    def g_tensor(self, g_value):
        if isinstance(g_value, float):
            self._g_tensor = tensor.Isotropic(str(g_value))
        elif isinstance(g_value, str):
            self._g_tensor = tensor.Isotropic(g_value)
        elif isinstance(g_value, tensor.Tensor):
            self._g_tensor = g_value
        else:
            raise ValueError("Invalid g_tensor value")
    
    @spin.setter
    def spin(self,s_value):
        s_value_float = float(s_value)
        if s_value_float % 0.5 != 0:
            raise ValueError("Electron spin value must be a multiple of 1/2")
        self._s_value = s_value_float
        self.spin_map = self.index_mapping
    
    def render_to_string(self):
        return f"spin(electron, {self._s_value}, {self._g_tensor.render_to_string()})"
    def ConvertToDictionary(self):
        if not self.physical:
            return self.name, None
        dict = {}
        dict['spin'] = self._s_value
        dict['tensor'] = self._g_tensor.render_to_string()
        dict['type'] = "electron"
        return self.name, dict
    
    spin = ActionVariable.ActionVariable(spin)
    g_tensor = ActionVariable.ActionVariable(g_tensor)

class Nucleus(SpinObject):
    def __init__(self, name):
        SpinObject.__init__(self, name)
        self.type = SpinObjectType.Nucleus
        self._s_value = 1.0/2.0
        self._g_tensor = tensor.Isotropic("1.0")
    
    @property
    def spin(self):
        return self._s_value
    @property 
    def g_tensor(self):
        return self._g_tensor

    @g_tensor.setter
    def g_tensor(self, g_value):
        if isinstance(g_value, float):
            self._g_tensor = tensor.Isotropic(str(g_value))
        elif isinstance(g_value, str):
            self._g_tensor = tensor.Isotropic(g_value)
        elif isinstance(g_value, tensor.Tensor):
            self._g_tensor = g_value
        else:
            raise ValueError("Invalid g_tensor value")
    
    @spin.setter
    def spin(self,s_value):
        s_value_float = float(s_value)
        if s_value_float % 0.5 != 0:
            raise ValueError("Nuclear spin value must be a multiple of 1/2")
        self._s_value = s_value_float
        self.spin_map = self.index_mapping
    
    def render_to_string(self):
        return f"spin(nucleus, {self._s_value}, {self._g_tensor.render_to_string()})"
    def ConvertToDictionary(self):
        if not self.physical:
            return self.name, None
        dict = {}
        dict['spin'] = self._s_value
        dict['tensor'] = self._g_tensor.render_to_string()
        dict['type'] = "nucleus"
        return self.name, dict
    
    spin = ActionVariable.ActionVariable(spin)
    g_tensor = ActionVariable.ActionVariable(g_tensor)
    
    
    

    
