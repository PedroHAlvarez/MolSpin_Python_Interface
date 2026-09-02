import sys
import numpy as np
from MolSpinPy import utility
from MolSpinPy.utility import imported
from MolSpinPy.utility import regex_functions
import math

class List:
    def __init__(self,list_str,sep = ' '):
        self.list_str = list_str
        self.sep = sep
        self._values = None
    def parse_from_string(self):
        clean = self.list_str.strip().replace('[', '').replace(']','').replace('"','')
        if not regex_functions.list_input(clean):
            raise ValueError(f"Invalid list input format: {self.list_str}")
        self._values = np.fromstring(clean, sep=self.sep)
        return self._values
    
    def _resolve_type(self, other):
        if hasattr(other, 'value'):
            return other.value
        if isinstance(other, str):
            if regex_functions.list_input(other):
                return np.fromstring(other, sep=self.sep)
            try:
                return float(other)
            except ValueError:
                raise TypeError(f"Math Error: Cannot operate on string '{other}'")
        if isinstance(other, (np.ndarray, list)):
            return np.array(other)
        if isinstance(other, (float, int, np.number)):
            return other
        raise TypeError(f"Unsupported operand type for MolSpinList math: {type(other)}")
    
    @classmethod
    def from_numpy(cls, array):
        obj = cls("")
        obj._values = np.array(array, dtype=np.float64)
        return obj
    
    def _validate_operation(self, other_val, op_name):
        my_shape = self.value.shape
        if np.isscalar(other_val):
            return True
        other_shape = np.shape(other_val)
        if op_name in ['__add__', '__sub__', '__mul__', '__truediv__']:
            if my_shape != other_shape:
                raise TypeError(
                    f"Dimensionality Mismatch: Cannot execute {op_name} between shapes {my_shape} and {other_shape}."
                )
        return True
    
    @property
    def value(self):
        if self._values is None:
            self.parse_from_string()
        return self._values

    @property
    def length(self):
        return len(self.value)
    
    def __str__(self):
        v = self.value
        return " ".join(f"{x:.6f}" for x in v)
    
    def __add__(self, other):
        val = self._resolve_type(other)
        self._validate_operation(val, '__add__')
        return List.from_numpy(self.value + val)

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        val = self._resolve_type(other)
        self._validate_operation(val, '__sub__')
        return List.from_numpy(self.value - val)

    def __rsub__(self, other):
        val = self._resolve_type(other)
        self._validate_operation(val, '__sub__')
        return List.from_numpy(val - self.value)

    def __mul__(self, other):
        val = self._resolve_type(other)
        self._validate_operation(val, '__mul__')
        return List.from_numpy(self.value * val)

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        val = self._resolve_type(other)
        self._validate_operation(val, '__truediv__')
        return List.from_numpy(self.value / val)

    def __rtruediv__(self, other):
        val = self._resolve_type(other)
        self._validate_operation(val, '__truediv__')
        return List.from_numpy(val / self.value)
    
    def multiply(self, other):
        return_list = List("")
        if isinstance(other, float):
            new_val = self.value * other
            return_list._values = new_val
        return return_list

    def norm1(self):
        sum_squared = 0.0
        for i in range(0,self.length):
            sum_squared += self.value[i] * self.value[i]
        factor = 1 / math.sqrt(sum_squared)
        new_val = []
        for i in range(0,self.length):
            new_val.append(self.value[i] * factor)
        self._values = np.array(new_val, dtype=np.float64)

    def __neg__(self):
        return List.from_numpy(self.value * -1)
        
    def dot(self, other):
        result = self._resolve_type(other)
        if isinstance(result, np.ndarray):
            return List.from_numpy(result)
        return np.dot(self.value, result)
    