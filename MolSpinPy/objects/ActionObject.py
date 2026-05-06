from . import ActionVariable

class Action():
    def __init__(self, target : ActionVariable):
        self.ptr = target
        self.