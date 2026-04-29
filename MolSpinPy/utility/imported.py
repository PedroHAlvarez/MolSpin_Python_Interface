from .singleton import Singleton

class ImportManager(metaclass=Singleton):
    def __init__(self):
        self.imported_modules = dict()
    
    def add_import(self, module_name, module):
        self.imported_modules[module_name] = module
    
    def get_imports(self):
        return self.imported_modules
    
    def import_custom_module(self, module_name):
        if module_name not in self.imported_modules:
            module = __import__(module_name)
            self.add_import(module_name, module)
            return module
        else:
            return self.imported_modules[module_name]
    
    def import_numpy(self):
        return self.import_custom_module("numpy")
    def import_pandas(self):
        return self.import_custom_module("pandas")

Import = ImportManager()