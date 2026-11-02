from . import ActionVariable
from MolSpinPy.utility import code_capture
from MolSpinPy.utility import imported
import inspect
from functools import wraps
import warnings
import ast
import hashlib
import numbers
import textwrap
from types import SimpleNamespace

class ActionFunction:
    metadata_note = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        init = cls.__dict__.get('__init__')
        if init is None:
            return

        # Record the constructor arguments (outermost constructor only) so the
        # function can be described in the project metadata.
        @wraps(init)
        def recording_init(self, *args, **kw):
            first = '_init_config' not in self.__dict__
            if first:
                try:
                    bound = inspect.signature(init).bind(self, *args, **kw)
                    bound.apply_defaults()
                    config = dict(bound.arguments)
                    config.pop('self', None)
                except TypeError:
                    config = {}
                object.__setattr__(self, '_init_config', config)
            init(self, *args, **kw)
        cls.__init__ = recording_init

    def __init__(self):
        #required parameters
        self._step = 0
        self._steps_per_action = {}  # Track step counter for each action
        self._updated = False
        
        self._param = {}
        super().__setattr__('_state',SimpleNamespace())
        self._internal_func = None
        self._param_types = {}

    def __getattr__(self, name):
        params = self.__dict__.get('_param')
        if params is not None and name in params:
            return params[name]
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
    def __setattr__(self, name, value):
        if name.startswith('_'):
            super().__setattr__(name,value)
            return
        if name == 'metadata_note':
            super().__setattr__(name, value)
            return
        allowed = getattr(self,'_param_names',[])
        if name in allowed:
            if not hasattr(self, '_param'):
                super().__setattr__('_param', {})
            self._param[name] = value
            return
        raise AttributeError(f"No parameter named {name}")
    def DoStep(self, var : ActionVariable, action_id=None):
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
        
    def __metadata__(self):
        return self.metadata_note
    
class CustomActionFunction(ActionFunction):
    _CORE_ARGS = ('step', 'var', 'state')

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

        core = list(self._CORE_ARGS)
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

        self._param_names = [p for p in params if p not in self._CORE_ARGS]
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
        try:
            source = inspect.getsource(func)
            self._dependencies = code_capture.capture_dependencies(func)
        except (OSError, TypeError):
            # Functions restored from metadata have no file to read the source from.
            source = getattr(func, "__molspin_source__", None)
            if source is None:
                raise
            self._dependencies = list(getattr(func, "__molspin_dependencies__", []))
        source = textwrap.dedent(source)
        self._source = source
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
    def DoStep(self, var : ActionVariable, action_id=None):
        if action_id is None:
            action_id = id(var)
        
        if action_id not in self._steps_per_action:
            self._steps_per_action[action_id] = 0
        
        step = self._steps_per_action[action_id]
        result = self._invoke(step, var)
        
        if result is None:
            result = var.value
        
        self._steps_per_action[action_id] += 1
        self._updated = True
        return result

    def _invoke(self, step, var):
        return self._internal_func(step, var, self.state, **self._param)

    def _set_updated_to_false(self):
        self._updated = False

    def _get_updated(self):
        return self._updated

    def __metadata__(self):
        return self.metadata_note

    def add_metadata(self, md_string):
        self.metadata_note = md_string
    
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


class FeedbackActionFunction(CustomActionFunction):
    """A custom action whose later batches depend on the results of earlier ones.

    The decorated function runs once per batch member (a step) and receives, besides
    ``step``, ``var`` and ``state``, ``index`` (position in the batch) and ``generation``.
    A hook registered with ``@fn.on_generation`` runs between batches and receives
    ``results``, ``generation``, ``state`` and ``stop`` (any subset); it may return the next
    batch size or set ``state.next_batch``. ``state`` is empty during the first generation.
    """
    _CORE_ARGS = ('step', 'var', 'state', 'index', 'generation')
    _HOOK_ARGS = ('results', 'generation', 'state', 'stop')
    requires_results = True

    def __init__(self, func = None):
        super().__init__(func)
        self._index = 0
        self._generation = 0
        self._hook = None
        self._hook_source = None
        self._hook_dependencies = []
        self._stop_requested = False
        self._generation_log = []

    def _invoke(self, step, var):
        return self._internal_func(step, var, self.state, index=self._index,
                                   generation=self._generation, **self._param)

    def set_context(self, index, generation):
        self._index = index
        self._generation = generation

    def on_generation(self, hook):
        for pname, param in inspect.signature(hook).parameters.items():
            if pname not in self._HOOK_ARGS and param.default is inspect.Parameter.empty:
                raise TypeError(
                    f"Generation hook '{hook.__name__}' has unknown required argument '{pname}'. "
                    f"Available arguments: {', '.join(self._HOOK_ARGS)}"
                )
        self._hook = hook
        try:
            self._hook_source = textwrap.dedent(inspect.getsource(hook))
            self._hook_dependencies = code_capture.capture_dependencies(hook)
        except (OSError, TypeError):
            self._hook_source = None
            self._hook_dependencies = []
        return hook

    def _request_stop(self):
        self._stop_requested = True

    def Feedback(self, results, generation, batch_size):
        """Run the generation hook; returns (next_batch_size, stop_requested)."""
        self._stop_requested = False
        if hasattr(self.state, 'next_batch'):
            delattr(self.state, 'next_batch')
        next_batch = None
        if self._hook is not None:
            available = {'results': results, 'generation': generation,
                         'state': self.state, 'stop': self._request_stop}
            accepted = inspect.signature(self._hook).parameters
            next_batch = self._hook(**{k: v for k, v in available.items() if k in accepted})
            if next_batch is None:
                next_batch = getattr(self.state, 'next_batch', None)
        if next_batch is None:
            next_batch = batch_size
        if isinstance(next_batch, bool) or not isinstance(next_batch, numbers.Integral) or next_batch < 0:
            raise ValueError(f"Next batch size must be a non-negative integer, got {next_batch!r}")
        return int(next_batch), self._stop_requested

    def __metadata__(self):
        return {
            "note": self.metadata_note,
            "generation_hook_source": self._hook_source,
            "generation_hook_source_sha256": (
                hashlib.sha256(self._hook_source.encode("utf-8")).hexdigest() if self._hook_source else None
            ),
            "generation_hook_dependencies": list(self._hook_dependencies),
            "generation_log": list(self._generation_log),
        }


def FeedbackScript(func):
    sig = inspect.signature(func)
    params = sig.parameters

    @wraps(func)
    def wrapper(step, var, state, index = 0, generation = 0, **kwargs):
        valid_args = {k: v for k, v in kwargs.items() if k in params}
        for name, value in (('step', step), ('var', var), ('state', state),
                            ('index', index), ('generation', generation)):
            if name in params:
                valid_args[name] = value
        return func(**valid_args)
    return FeedbackActionFunction(wrapper)

#class LineSpaceAction(ActionFunction):
#    def __init__(self):
#        super(ActionFunction).__init__(self)

