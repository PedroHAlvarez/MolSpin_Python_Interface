from . import ActionVariable
from . import ActionFunction

import difflib


class Action():
    def __init__(self, target : ActionVariable, func = ActionFunction.ActionFunction, **kwargs):
        super().__setattr__('_ACTION_ARGS',{'duration','loop','interval','active','parent'})
        super().__setattr__('_ACTION_ARGS_TYPES',{
            'duration' : int,
            'loop' : bool,
            'interval' : int,
            'active' : bool,
            'parent' : Action
        })

        super().__setattr__('ptr',target)
        super().__setattr__('func',func)
        super().__setattr__('_FUNCTION_ARGS', list(getattr(func, '_param_names', {})))
        super().__setattr__('children', [])

        defaults = {
            'duration' : None,
            'loop' : False,
            'interval' : 1,
            'active' : True,
            'parent' : None
        }

        for key, value in kwargs.items():
            setattr(self,key,value)
        for key,val in defaults.items():
            if not hasattr(self,key):
                super().__setattr__(key,val)
        if self.parent:
            self.parent.add_child(self)
    
    def add_child(self, child):
        if child not in self.children:
            self.children.append(child)
    
    def __setattr__(self, name, value):
        if name.startswith('_') or name in ('ptr', 'func', 'children'):
            super().__setattr__(name,value)
            return
        if name in self._ACTION_ARGS:
            if value != None:
                if not isinstance(value, self._ACTION_ARGS_TYPES.get(name)):
                     raise TypeError(rf"{name} must have type {self._ACTION_ARGS_TYPES[name].__name__}, "
                                     rf"but got {type(value).__name__}")
            super().__setattr__(name, value)
            return
        if hasattr(self, 'func'):
            if name in self._FUNCTION_ARGS:
                if value != None:
                    expected = self.func._param_types.get(name)
                    if expected and value is not None:
                        if not isinstance(value,expected):
                            if expected is float and isinstance(value,int):
                                value = float(value)
                            else:
                                raise TypeError(rf"{name} must have type {expected.__name__}, "
                                                rf"but got {type(value).__name__}")
                setattr(self.func, name, value)
                return
        all = list(self._ACTION_ARGS) + list(self._FUNCTION_ARGS)
        suggestions = difflib.get_close_matches(name, all, n=1, cutoff = 0.6)
        error_msg = f"Action object has no attribute '{name}'."
        if suggestions:
            error_msg += f"Did you mean '{suggestions[0]}'?"
        raise AttributeError(error_msg)