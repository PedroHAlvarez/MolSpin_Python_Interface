from contextlib import contextmanager

class AssertFlags:
    _INITIAL_FLAGS = {
        "ASSERT_BINARY": True,
        "ASSERT_DEPLOY": True,
        "ASSERT_GIT": True,
        "ASSERT_METADATA": True,
    }

    _flags = _INITIAL_FLAGS.copy()

    @classmethod
    def get(cls, name, default=None):
        if name not in cls._flags:
            return default
        return cls._flags[name]

    @classmethod
    def set(cls, name, value):
        cls._flags[name] = value

    @classmethod
    def register(cls, name, default_value=True):
        if name not in cls._flags:
            cls._flags[name] = default_value

    @classmethod
    def unregister(cls, name):
        if name in cls._flags:
            del cls._flags[name]

    @classmethod
    def reset(cls, name):
        if name in cls._INITIAL_FLAGS:
            cls._flags[name] = cls._INITIAL_FLAGS[name]
        else:
            cls._flags.pop(name, None)

    @classmethod
    def reset_all(cls):
        cls._flags = cls._INITIAL_FLAGS.copy()

    @classmethod
    @contextmanager
    def override(cls, **kwargs):
        original = {k: cls.get(k, default=None) for k in kwargs}
    
        for k, v in kwargs.items():
            cls.set(k, v)
            
        try:
            yield
        finally:
            for k, orig_val in original.items():
                if orig_val is None:
                    cls._flags.pop(k, None) 
                else:
                    cls.set(k, orig_val)