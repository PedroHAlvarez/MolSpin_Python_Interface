from .. import ActionFunction
import numpy as np

class LogSpaceScalar(ActionFunction.ActionFunction):
    def __init__(self,start,stop,num, base = 10, Exponent = True):
        super().__init__()
        if not Exponent: #that means the start and stop are not exponents and so can't be plugged into logspace directly 
            start = np.log(start)/np.log(base)
            stop = np.log(stop)/np.log(base)
        self._param_names = ['sequence']
        self.sequence = np.logspace(start,stop,num)
        self._param['sequence'] = self.sequence 
        self._internal_func = self.LogSpaceScalerLogic
    def LogSpaceScalerLogic(self, step, var, state, sequence):
        if step == 0:
            state.index = 0
        if state.index == len(sequence):
            state.index = 0
        if state.index < len(sequence):
            val = sequence[state.index]
            state.index += 1
            return val
        return var.value
    def DoStep(self, var):
        val = self.LogSpaceScalerLogic(self._step, var, self._state, self.sequence)
        self._step += 1
        #print(val)
        return val
    
from MolSpinPy.maths.vector import Vector
class LogSpaceVector(ActionFunction.ActionFunction):
    def __init__(self, start, stop, num, direction : Vector = None, Normalize = True, base = 10, Exponent = True):
        super().__init__()
        if direction == None:
            direction = Vector("0.0 0.0 1.0")
        if not isinstance(direction,Vector):
            raise AttributeError(f"Attribute direction has to be type Vector")
        if not Exponent: #that means the start and stop are not exponents and so can't be plugged into logspace directly 
            start = np.log(start)/np.log(base)
            stop = np.log(stop)/np.log(base)
        self._param_names = ['sequence']
        self.sequence = np.logspace(start,stop,num,base=base)
        self._param['sequence'] = self.sequence 
        self._internal_func = self.LogSpaceVectorLogic
        if(Normalize):
            direction.norm1()
        self._direction = direction
    def LogSpaceVectorLogic(self, step, var, state, sequence):
        if step == 0:
            state.index = 0
        if state.index == len(sequence):
            state.index = 0
        if state.index < len(sequence):
            val = sequence[state.index]
            state.index += 1
            val = self._direction.multiply(val)
            return val.value
        return var.value
    def DoStep(self, var):
        val = self.LogSpaceVectorLogic(self._step, var, self._state, self.sequence)
        self._step += 1
        #print(val)
        return val