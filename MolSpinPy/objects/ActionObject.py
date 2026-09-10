from . import ActionVariable
from . import ActionFunction

import difflib
import numpy as np

class TimeManager():
    def __init__(self, Action):
        self.action = Action
        self.elapsed_ticks = 0
        self.completed_loops = 0
        self.death_offset = None
    def GetLocalTime(self, global_step):
        act = self.action
        clock_source= None
        current = act.parent
        while current is not None:
            if current.active:
                clock_source = current
                break
            current = current.parent
        if clock_source:
            p_loops = clock_source.time_manager.completed_loops
            #if p_loops < 1 and act.start:
            #    return None
            if p_loops < act.start: return None
            if(p_loops - act.start) % act.interval != 0: return None
            # Get per-action step counters
            clock_step = clock_source.func._steps_per_action.get(id(clock_source), 0)
            act_step = act.func._steps_per_action.get(id(act), 0)
            if clock_step != 1 and act_step != 0: return None
        else:
            if self.death_offset is None:
                self.death_offset = global_step
            relative_step = global_step-self.death_offset
            if relative_step < act.start: return None
            if (relative_step - act.start) % act.interval != 0: return None
        # Return per-action step counter
        return act.func._steps_per_action.get(id(act), 0)
class Action():
    def __init__(self, target, func = ActionFunction.ActionFunction, **kwargs):
        super().__setattr__('_ACTION_ARGS',{'duration','loop','interval','active','parent'})#, 'name', 'priority', 'value', 'state', 'effective_priority'})
        super().__setattr__('_ACTION_ARGS_TYPES',{
            'duration' : int,
            'start' : int,
            'loop' : bool,
            'interval' : int,
            'active' : bool,
            'parent' : Action
        })
        super().__setattr__('ptr',None)
        super().__setattr__('key', kwargs.get('key',None))

        if isinstance(target,dict) and self.key != None:
            self.ptr = ActionVariable.DictionaryBoundVariable(target,self.key)
        elif isinstance(target,str):
            self.ptr = None
            super().__setattr__('_promise',target)
        else:
            self.ptr = target
        
        super().__setattr__('func',func)
        super().__setattr__('_FUNCTION_ARGS', list(getattr(func, '_param_names', {})))
        super().__setattr__('children', [])
        super().__setattr__('time_manager', TimeManager(self))
        super().__setattr__('kill_parent', False)
        super().__setattr__('kill_self', False)
        super().__setattr__('kill_commands',{})

        defaults = {
            'duration' : None,
            'start' : 0,
            'loop' : False,
            'interval' : 1,
            'active' : True,
            'parent' : None,
        }

        super().__setattr__('_priority', 0)

        for key, value in kwargs.items():
            if key != 'key':
                setattr(self,key,value)
        for key,val in defaults.items():
            if not hasattr(self,key) and key != 'key':
                super().__setattr__(key,val)
        if self.parent:
            self.parent.add_child(self)

    @property
    def name(self):
        return self.ptr.name
    
    @property
    def priority(self):
        try:
            return int(self._priority)
        except (TypeError, ValueError):
            return 0
    
    @priority.setter
    def priority(self,z):
        if isinstance(z, tuple):
            self._priority = int(z[-1])
        else:
            self._priority = int(z)

    @property
    def effective_priority(self):
        if self.parent is None:
            return (self.priority,)
        return self.parent.effective_priority + (self.priority,)
    
    def add_child(self, child):
        if child not in self.children:
            self.children.append(child)
            if child.kill_parent == True:
                self.kill_commands[child] = False
    def bind_to(self,target, **kwargs):
        new_key = kwargs.get('key', self.key)
        if isinstance(target,dict) and new_key != None:
            self.ptr = ActionVariable.DictionaryBoundVariable(target,new_key)
        elif isinstance(target,str):
            self.ptr = None
            super().__setattr__('_promise',target)
        else:
            self.ptr = target

    def __setattr__(self, name, value):

        def value_check(value, name):
            if value != None:
                expected = self.func._param_types.get(name)
                if expected and value is not None:
                    if not isinstance(value,expected):
                        if expected is float and isinstance(value,int):
                            value = float(value)
                        else:
                            raise TypeError(rf"{name} must have type {expected.__name__}, "
                                            rf"but got {type(value).__name__}")

        if hasattr(self, name):
            super().__setattr__(name, value)
            return
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
                if isinstance(value, (list, np.ndarray)):
                    if not hasattr(self, '_sequences'):
                        super().__setattr__('_sequences', {})
                    self._sequences[name] = value
                    value_check(value[0],name)
                    setattr(self.func, name, value[0])
                    return
                elif value != None:
                    value_check(value, name)
                    setattr(self.func, name, value)
                    return
            if hasattr(self.func.state,name):
                raise AttributeError(
                    f"Ambiguous access: {name} exists in {self.func.name}'s internal state"
                    f"Use '*.state.{name} = value to update internal state"
                )
        all = list(self._ACTION_ARGS) + list(self._FUNCTION_ARGS)
        suggestions = difflib.get_close_matches(name, all, n=1, cutoff = 0.6)
        error_msg = f"Action object has no attribute '{name}'."
        if suggestions:
            error_msg += f"Did you mean '{suggestions[0]}'?"
        raise AttributeError(error_msg)
    def step(self,global_step, return_logic = False):
        if not self.active:
            return None if not return_logic else False 
        if self.kill_self:
            total = len(self.kill_commands)
            count = 0
            for idx, key in enumerate(self.kill_commands):
                if self.kill_commands[key]:
                    count += 1
            if count == total and total != 0:
                self.active = False
                return None if not return_logic else False

        local_step = self.time_manager.GetLocalTime(global_step)
        if local_step is None:
            return None if not return_logic else False
        if hasattr(self, '_sequences'):
            for name, seq in self._sequences.items():
                idx = local_step % len(seq)
                setattr(self.func, name, seq[idx])
        if self.duration is not None and local_step >= self.duration:
            if self.loop:
                self.time_manager.completed_loops += 1
                # Reset per-action step counter
                action_id = id(self)
                self.func._steps_per_action[action_id] = 0
                local_step = 0
            else:
                self.time_manager.completed_loops += 1
                self.active = False
                if self.kill_parent:
                    self.parent.kill_commands[self] = True
                return None if not return_logic else False
        if return_logic:
            action_id = id(self)
            if action_id not in self.func._steps_per_action:
                self.func._steps_per_action[action_id] = 0
            self.func._steps_per_action[action_id] += 1
            return True
        new_value = self.func.DoStep(self.ptr, action_id=id(self))
        self.ptr.value = new_value

        self.time_manager.elapsed_ticks += 1

    @staticmethod
    def can_upcast(res_type, t_type):
        try:
            if np.issubdtype(res_type, np.number) and np.issubdtype(t_type, np.number):
                return np.can_cast(res_type, t_type)
        except TypeError:
            pass
        return False

    def Test(self):
        from copy import copy
        print(f"---Testing {self.func.name}---")
        test_var = self.ptr.value
        test_type = type(test_var)
        state_snapshot = copy(self.func.state.__dict__)
        try:
            try:
                result = self.func._internal_func(0,test_var,self.func.state,**self.func._param) 
            except AttributeError as e:
                if "SimpleNamespace" in str(e):
                    raise AttributeError(f"Action '{self.func.name}' tried to access an uninitialized state variable. ") from e
            result_type = type(result)
            
            #array check
            if test_type == np.ndarray and (result_type == test_type or result_type == list):
                a = (len(result) == len(test_var))
                if not a:
                    res_shape = result.shape() if hasattr(result, 'shape') else f"[{len(result)}]"
                    test_shape = test_var.shape() if hasattr(test_var, 'shape') else f"[{len(test_var)}]"
                    raise ValueError(f"Dimensionality mismatch between, the return object of ActionScript: {res_shape} and the shape of the actionVariable: {test_shape}")#
                
            is_valid_type = (
                isinstance(result, test_type) 
                or (test_type == np.ndarray and isinstance(result, list))
                or self.can_upcast(result_type, test_type)
            )

            #final check
            if result is not None and not is_valid_type:
                raise ValueError(f"Type mismatch betweeen, the return object of ActionScript: {type(result).__name__} and the type of the actionVariable: {type(test_var).__name__}")
            
            print("PASSED")
            return True
        except Exception as e:
            print(f"FAILED: {str(e)}")
            raise e
        finally:
            self.func.state.__dict__.clear()
            self.func.state.__dict__.update(state_snapshot)
    @property
    def state(self):
        return self.func.state
    @property
    def value(self):
        return self.ptr.value