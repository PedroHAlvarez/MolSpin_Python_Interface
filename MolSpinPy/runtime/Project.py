#defines the project class which is the main overarching object that the users need

from . import ActionManager
from ..msd import FileTemplate , MsdHandling

class Project():
    def __init__(self, name):
        self._name = name
        
        self._base_dict = {}
        self._compiled_dict = {}
        self._resolved_dict = {} #this is a combination of the base_dict and the compiled_dict
        
        self._manager = None
        self._settings = {} #will be upgraded to a class in future versions 
    def check_dict_structure(self,dict):
        pass
    def attach_MSD_file(self, filename):
        pass
    def attach_dict(self, dict):
        pass

    def attach_ActionManager(self, manager : ActionManager):
        self._manager = manager
    @property
    def manager(self):
        return self.manager
