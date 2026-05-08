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
        self._internal_func = self.logic
    def logic(self, step, var, state, sequence):
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
        val = self.logic(self._step, var, self._state, self.sequence)
        self._step += 1
        print(val)
        return val

