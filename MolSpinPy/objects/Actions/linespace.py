from .. import ActionFunction
import numpy as np
class LineSpaceScalar(ActionFunction.ActionFunction):
    def __init__(self, start, stop, num = None, spacing = None):
        super().__init__()
        if num == None and spacing == None:
            raise AttributeError(f"Both num and spacing can't be populated")
        if num == None:
            num = np.ceil((stop-start)/spacing)
        self._param_names = ['sequence']
        self.sequence = np.linspace(start,stop,num)
        self._param['sequence'] = self.sequence 
        self._internal_func = self.LineSpaceScalerLogic
    def LineSpaceScalerLogic(self, step, var, state, sequence):
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
        val = self.LineSpaceScalerLogic(self._step, var, self._state, self.sequence)
        self._step += 1
        #print(val)
        return val
    
from MolSpinPy.maths.vector import Vector
class LineSpaceVector(ActionFunction.ActionFunction):
    def __init__(self, start, stop, num = None, spacing = None, direction : Vector = None, Normalize = True):
        super().__init__()
        if direction == None:
            direction = Vector("0.0 0.0 1.0")
        if not isinstance(direction,Vector):
            raise AttributeError(f"Attribute direction has to be type Vector")
        if num == None:
            num = np.ceil((stop-start)/spacing)
        self._param_names = ['sequence']
        self.sequence = np.linspace(start,stop,num)
        self._param['sequence'] = self.sequence 
        self._internal_func = self.LineSpaceVectorLogic
        if(Normalize):
            direction.norm1()
        self._direction = direction
    def LineSpaceVectorLogic(self, step, var, state, sequence):
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
        val = self.LineSpaceVectorLogic(self._step, var, self._state, self.sequence)
        self._step += 1
        #print(val)
        return val
    
#class LineSpaceTensor(ActionFunction.ActionFunction):
#    def __init__(self):
#        super().__init__()
