from . import spin_object
from . import interactions
from . import states
from . import transitions



class SpinSystem:
    def __init__(self, name):
        self.name = name
        self.electrons = [] 
        self.nuclei = []
        self.interactions = []
        self.transitons = []

    def add_electron(self, elec : spin_object.Electron = None):
        if elec == None:
            return
        else:
            self.electrons.append(elec)
    
    def ConvertToDictionary(self):
        dict = {}
        dict['spins'] = {}
        dict['spins']['electrons'] = {}
        dict['spins']['nuclei'] = {}
        for e in self.electrons:
            name, sub_dict = e.ConvertToDictionary()
            dict['spins']['electrons'][name] = sub_dict
        for n in self.nuclei:
            name, sub_dict = n.ConvertToDictionary()
            dict['spins']['nuclei'][name] = sub_dict
        return dict
