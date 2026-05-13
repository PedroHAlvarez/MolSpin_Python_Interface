#defines the project class which is the main overarching object that the users need

from . import ActionManager
from ..msd import FileTemplate , MsdHandling
import enum

class dictMode(enum.Enum):
    REPLACE = 0
    CONCATINATE = 1

class Project():
    def __init__(self, name, template_structure = "BasicTemplate.msd"):
        self._name = name
        
        self._base_dict = {}
        self._compiled_dict = {}
        self._resolved_dict = {} #this is a combination of the base_dict and the compiled_dict
        
        self._manager = None
        self._settings = {} #will be upgraded to a class in future versions 
        self._template = FileTemplate.get_template(template_structure)
        self._dict_template = FileTemplate._init_input_data()

    def check_dict_structure(self,new_dict,current_template=None, path=""):
        if current_template is None:
            current_template = self._dict_template

        #MANDATORY = [['spinsystems','actions','settings','outputs','tasks'],['spins','interactions','states','transitions','properties','pulses','operators'],['electrons','nuclei']]
        errors = 0
        for key,value in new_dict.items():
            template_keys = list(current_template.keys())

            if isinstance(current_template, dict) and not current_template:
                continue

            if key in current_template:
                target_template = current_template[key]
            elif len(template_keys) == 1 and isinstance(current_template[template_keys[0]],dict):
                target_template = current_template[template_keys[0]]
            elif len(template_keys) == 1:
                target_template = list(current_template.values())[0]
            else:
                print(f"Key '{key}' is not permitted at {path}")
                errors += 1
                continue
            if isinstance(target_template, dict):
                if not isinstance(value, dict):
                    print(f"'{key}' must be a dictionary structure at {path}")
                    errors += 1
                else:
                    if not self.check_dict_structure(value, target_template, f"{path}{key}/"):
                        errors += 1
            else:
                if value is None:
                    print(f"Mandatory leaf '{key}' is null at {path}")
                    errors += 1
            #if key not in self._dict_template:
            #    print(f"Unexpected key found: {key}")
            #    errors += 1
            #    continue
            #elif isinstance(value, dict):
            #    if not isinstance(self._dict_template[key],dict):
            #        print(f"Type mismatch at {key}: Expected value, found dict")
            #        errors += 1
            #    else:
            #        is_valid = self.check_dict_structure(value)
            #        if not is_valid:
            #            errors += 1
        if errors > 0:
            return False
        else:
            return True
            
    def attach_MSD_file(self, filename):
        self._base_dict = MsdHandling.ConvertMSDtoDictionary(filename)
    def attach_dict(self, dict, mode = dictMode.REPLACE):
        if(self.check_dict_structure(dict)):
            if(self._base_dict != {} and mode == dictMode.REPLACE ):
                print(f"Warning: Overiding project dictionary")
                self._base_dict = dict
            elif (self._base_dict == {}):
                self._base_dict = dict
            elif(mode == dictMode.CONCATINATE):
                self._base_dict = self.ConcatinateDictionarys(self._base_dict, dict)
        else:
            raise ValueError(f"{dict.__name__()} is not in the required format")
    
    def ConcatinateDictionarys(self, base, incoming):
        for key,value in incoming.items():
            if key in base:
                if isinstance(base[key], dict) and isinstance(value, dict):
                    self.ConcatinateDictionarys(base[key], value)
                elif isinstance(base[key],list) and isinstance(value,list):
                    base[key].extend(value)
                else:
                    base[key] = value
            else:
                base[key] = value
        return base
            
    def attach_ActionManager(self, manager : ActionManager):
        self._manager = manager
    def _extract_settings(self):
        keys = []
        for val, key in enumerate(self.MSDdict['settings']):
            keys.append(key)
        self._settings = self.MSDdict['settings'][keys[0]]
    @property
    def manager(self):
        return self._manager
    @property 
    def MSDdict(self):
        return self._base_dict
    def _dryRun(self):
        steps = int(self._settings['steps'])
        for i in range(steps):
            self.manager.run(i)
