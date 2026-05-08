from . import ActionVariable
from MolSpinPy.utility import imported
import inspect
from functools import wraps
import warnings
import ast
import textwrap
from types import SimpleNamespace

class ActionFunction:
    def __init__(self):
        #required parameters
        self._step = 0
        
        self._param = {}
        super().__setattr__('_state',SimpleNamespace())
        self._internal_func = None
        self._param_types = {}

    def __getattr__(self, name):
        if name in self.param:
            return self._param[name]
    def __setattr__(self, name, value):
        if name.startswith('_'):
            super().__setattr__(name,value)
            return
        allowed = getattr(self,'_param_names',[])
        if name in allowed:
            if not hasattr(self, '_param'):
                super().__setattr__('_param', {})
            self._param[name] = value
            return
        raise AttributeError(f"No parameter named {name}")
    def DoStep(self, var : ActionVariable):
        raise NotImplementedError("Sub classes should implement their own DoStep function")
    def BindValues(self,value_list = [], value_dictionary = {}, source_obj = None):
        raise NotImplementedError("Sub classes should implement their own BindValues function")
    
    @property
    def name(self):
        if self._internal_func:
            return self._internal_func.__name__
        return "UnnamedFunction"
    @property
    def state(self):
        return self._state
    @state.setter
    def state(self, value):
        if isinstance(value, dict):
            self._state = SimpleNamespace(**value)
        elif isinstance(value, SimpleNamespace):
            self._state = value
        else:
            raise TypeError("State must be a dictionary or a SimpleNamespace.")
    
class CustomActionFunction(ActionFunction):
    def __init__(self, func = None):
        super().__init__()
        if(func != None):
            self._staticFuncAnalysis(func)
        self._internal_func = func

    def AttachFunction(self, func):
        self._staticFuncAnalysis(func)
        self._internal_func = func
    
    def _staticFuncAnalysis(self,func):
        original_func = getattr(func,"__wrapped__",func)
        sig = inspect.signature(original_func)
        params = sig.parameters

        core = ['step', 'var', 'state']
        param_names = list(params.keys())
        for i,expected in enumerate(core):
            #if expected not in params:
            #    raise TypeError(f"Action function is missing required argument: '{expected}'")
            #if param_names[i] != expected:
            #    raise TypeError(
            #    f"Incorrect argument order. Argument #{i} must be '{expected}', "
            #    f"but found '{param_names[i]}' instead."
            #)
            if expected not in params:
                continue
            if params[expected].kind == inspect.Parameter.KEYWORD_ONLY:
                raise TypeError(f"'{expected}' must be a positional argument.")

        self._param_names = [p for p in params if p not in ('step', 'var', 'state')]
        self._param = {
            p: params[p].default
            for p in self._param_names
            if params[p].default is not inspect.Parameter.empty
        }

        self._param_types = {}
        for name in self._param_names:
            param = sig.parameters[name]

            if param.annotation is not inspect.Parameter.empty:
                self._param_types[name] = param.annotation
            elif param.default is not inspect.Parameter.empty and param.default is not None:
                self._param_types[name] = type(param.default)
            else:
                self._param_types[name] = None

        verified = self._verify_function_utility(func)
        return True & verified
    
    def _verify_function_utility(self, func):
        source = inspect.getsource(func)
        source = textwrap.dedent(source)
        tree = ast.parse(source)
        has_return = False
        modifies_var = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Return) and node.value is not None:
                has_return = True
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute):
                        if isinstance(target.value, ast.Name) and target.value.id == 'var':
                            modifies_var = True
                    elif isinstance(target, ast.Name) and target.id == 'var':
                        raise ValueError(f"Cannot assign directly to ActionVariable object 'var'. Are you trying to assign value to 'var.value'?")
        
        if not (has_return or modifies_var):
            raise ValueError(f"ActionFunction '{func.__name__}' is invalid.\n"
                             "It must either return a value or modify 'var' internally")
            return False
        return True
    
    def BindValues(self, value_list=[], value_dictionary={}, source_obj = None):
        if source_obj is not None:
            extracted_dict = {
                name : getattr(source_obj,name)
                for name in self._param_names
                if hasattr(source_obj,name)
            }
            value_dictionary = {**(value_dictionary or {}), **extracted_dict}
        if value_dictionary:
            for k,v in value_dictionary.items():
                for k in self._param:
                    self._param[k] = v
        if value_list:
            num_params = len(self._param_names)
            num_values = len(value_list)
            if num_values > num_params:
                warnings.warn(
                    f"Action '{self.__name__}' received {num_values} values, "
                    f"but only {num_params} are defined. Extra values ignored.",
                    category=RuntimeWarning,
                    stacklevel=2
                )
            for i,val in enumerate(value_list):
                if i < len(self._param_names):
                    key = self._param_names[i]
                    self._param[key] = val
                else:
                    break
    def DoStep(self, var : ActionVariable):
        result = self._internal_func(self._step, var, self.state, **self._param)
        if result == None:
            result = var.value
        self._step += 1
        return result
    
def ActionScript(func):
    sig = inspect.signature(func)
    params = sig.parameters

    @wraps(func)
    def wrapper(step,var,state,**kwargs):
        valid_args = {k: v for k,v in kwargs.items() if k in params}
        if 'step' in params:
            valid_args['step'] = step
        if 'var' in params:
            valid_args['var'] = var
        if 'state' in params:
            valid_args['state'] = state
        return func(**valid_args)
    return CustomActionFunction(wrapper)

#class LineSpaceAction(ActionFunction):
#    def __init__(self):
#        super(ActionFunction).__init__(self)

