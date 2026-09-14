from contextlib import contextmanager
from typing import TypedDict, Unpack, Any
from typing_extensions import Annotated, Doc
class _FlagOptions(TypedDict, total=False):
    ASSERT_BINARY: Annotated[bool, Doc("Enable binary validation checks.")]
    ASSERT_DEPLOY: Annotated[bool, Doc("Enable deployment validation checks.")]
    ASSERT_GIT: Annotated[bool, Doc("Enable Git validation and synchronization checks.")]
    ASSERT_METADATA: Annotated[bool, Doc("Enable project metadata validation checks.")]
    ASSERT_OSW: Annotated[bool, Doc("OSW - Old Staging Workspace. Uses the legacy 'molspin_run_workspace' instead of the new 'molspin_workspace_project_name'.")]
class AssertFlags:
    _INITIAL_FLAGS = {
        "ASSERT_BINARY": True,
        "ASSERT_DEPLOY": True,
        "ASSERT_GIT": True,
        "ASSERT_METADATA": True,

        "ASSERT_OSW" : False #OSW- OLD STAGING WORKSPACE - INDICATES THAT THE FOLDER WE ARE LOOKING FOR IN THE HPC IS JUST "molspin_run_workspace" AND NOT THE NEW FORMAT.
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
    def override(cls, **kwargs: Unpack[_FlagOptions]):
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