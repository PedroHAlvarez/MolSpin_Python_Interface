#defines the project class which is the main overarching object that the users need

from . import ActionManager
from ..msd import FileTemplate , MsdHandling

class Project():
    def __init__(self, name):
        self.name = ""
        self.base_dict = {}
