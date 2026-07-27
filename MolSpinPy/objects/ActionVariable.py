from MolSpinPy import utility
from MolSpinPy import maths
class ActionVariable:
    def __init__(self, prop):
        self.fget = prop.fget
        self.fset = prop.fset
        self.name = prop.fget.__name__
        self.owner = None
    def __set_name__(self,owner,name):
        self.owner = owner
    def __get__(self, instance, owner):
        if instance is None:
            return self
        return BoundVariable(instance,self)
    def __set__(self, instance, value):
        if self.fset is None:
            raise AttributeError(f"{self.name} is read-only")
        self.fset(instance, value)


    #def __getattr__(self, name):
    #    return getattr(self._target, name)
    #def __repr__(self):
    #    return f"Wrapper"
class DictionaryBoundVariable:
    def __init__(self, registry, key, **kwargs):
        self.registry = registry
        self.key = key
        self.name = key
        self.sep = kwargs.get('sep', ' ')
        self.type = 'None'
    def _get_target(self):
        keys = self.key.split('.')
        current = self.registry
        for key in keys[:-1]:
            current = current[key]
        return current,keys[-1].lower() if len(keys) > 1 else keys[0].lower()
    #will need to change this properly to handle all the different data types
    @property
    def value(self):
        container,final_key = self._get_target()
        val = container[final_key]
        t,v,c = utility.regex_functions.GetType(val)
        if t == 'float':
            val = float(val)
        elif t == 'vec':
            val = maths.vector.Vector(val)
        elif t == 'matrix':
            val = maths.tensor.CreateTensor(c,v)
        elif t == 'list':
            val = maths.list.List(val, sep=self.sep)
        else:
            raise ValueError("Type not supported")
        self.type = t
        return getattr(val, 'value', val)
    @value.setter
    def value(self,val):
        container,final_key = self._get_target()
        item = container[final_key]
        if hasattr(item, 'value'):
            item.value = val
        elif self.type == 'list':
            container[final_key] = self.sep.join(map(str,val))
        else:
            container[final_key] = str(val)

    def __repr__(self):
        return f"DictHandle({self.key}: {self.value})"
    
    @classmethod
    def test_create(cls,registry, key, **kwargs):
        try:
            handle = cls(registry, key, **kwargs)
            _ = handle.value
            return True
        except Exception as e:
            print(f"Error creating DictionaryBoundVariable for key '{key}': {e}")
            return False
    
class BoundVariable:
    def __init__(self, instance, descriptor : ActionVariable):
        self.instance = instance
        self.descriptor = descriptor
    @property
    def value(self):
        return self.descriptor.fget(self.instance)
    @value.setter
    def value(self,val):
        if self.descriptor.fset is None:
            raise AttributeError(f"Variable '{self.descriptor.name}' is read-only")
        self.descriptor.fset(self.instance,val)
    def __str__(self): return str(self.value)
    def __repr__(self): return f"Handle({self.value})"

    def __eq__(self, other): return self.value == other
    def __lt__(self, other): return self.value < other
    def __gt__(self, other): return self.value > other

    def __new__(cls,instance,descriptor):
        target = descriptor.fget(instance)
        t_type = type(target)

        proxy_name = f"Bound_{t_type.__name__}"
        proxy_class = type(proxy_name, (cls,t_type), {})
        return super(BoundVariable,proxy_class).__new__(proxy_class)
    
    #def __add__(self, other): return self.value + other
    #def __radd__(self, other): return other + self.value
    #def __float__(self, other)