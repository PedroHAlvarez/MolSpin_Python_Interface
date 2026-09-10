import sys
import numpy as np
from  MolSpinPy import utility
from MolSpinPy.utility import imported
from MolSpinPy.utility import regex_functions
import math

class Vector:
    def __init__(self,vector_str):
        self.vector_str = vector_str
        self._values = None
    
    def parse_from_string(self):
        clean = self.vector_str.strip().replace('[', '').replace(']','').replace(',','')
        if not regex_functions.vector_input(clean):
            raise ValueError(f"Invalid vector input format: {self.vector_str}")
        self._values = np.fromstring(clean, sep=' ')
        return self._values
    
    #need to make a method to convert a numpy array to a vector
    
    def _resolve_type(self, other):
        if hasattr(other, 'value'):
            return other.value
        if isinstance(other,str):
            if regex_functions.vector_input(other):
                return np.fromstring(other, sep=' ')
            try:
                return float(other) #need to change to be able to check what other type it can be 
            except ValueError:
                raise TypeError(f"Math Error: Cannot operate on string '{other}'")
        if isinstance(other, (np.ndarray, list)):
            return np.array(other)
        if isinstance(other, (float, int, np.number)):
            return other
        raise TypeError(f"Unsupported operand type for Vector math: {type(other)}")
    
    def _validate_operation(self, other_val, op_name):
        my_shape = self.value.shape
        if np.isscaler(other_val):
            return True
        other_shape = np.shape(other_val)
        if op_name in['__add__','__sub__']:
            if my_shape != other_shape:
                raise TypeError(
                f"Dimensionality Mismatch: Cannot {op_name} {my_shape} and {other_shape}.")
        if op_name in ['__mul__']:
            pass 
        return True
    
    @property
    def value(self):
        if self._values is None:
            self.parse_from_string()
        return self._values
    
    def __str__(self):
        v = self.value
        return f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}"
    
    def multiply(self, other):
        return_vec = Vector("")
        if isinstance(other, float):
            new_val = self.value * other
            return_vec._values = new_val
        return return_vec
    
    def norm1(self):
        sum_squared = 0.0
        for i in range(0,3):
            sum_squared += self.value[i] * self.value[i]
        factor = 1 / math.sqrt(sum_squared)
        new_val = []
        for i in range(0,3):
            new_val.append(self.value[i] * factor)
        self._values = np.array(new_val, dtype=np.float64)
            
    
    #def __add__(self, other):
    #    val = self._resolve_type(other)
    #    self._validate_operation(val, 'addition')
    #    return self.value + val
    #def __radd__(self, other):
    #    return self.__add__(other)
    #def __sub__(self, other):
    #    val = self._resolve_type(other)
    #    self._validate_operation(val, 'subtraction')
    #    return self.value - val
    #def __mul__(self, other):
    #    val = self._resolve_type(other)
    #    self._validate_operation(other, 'multiply')
    #    return self.value * val
    #def __rmul__(self, other):
    #    return self.__mul__(other)
    #def __truediv__(self, other):
    #    val = self._resolve_type(other)
    #    self._validate_operation(other, 'divide')
    #    return self.value / other

    #def add(self,other):
        

    def dot(self,other):
        val = self._resolve_type(other)
        return np.dot(self.value, val)
    def cross(self, other):
        val = self._resolve_type(other)
        if np.shape(val) != (3,):
            raise TypeError("Cross product is only defined for 3D vectors.")
        return np.cross(self.value, val)
    def __neg__(self):
        return self.value * -1
    


    