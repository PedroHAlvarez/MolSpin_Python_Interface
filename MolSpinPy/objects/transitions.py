from . import ActionVariable

class Transition:
    def __init__(self, name, source, rate, targetsystem=None, targetstate=None, include_all_nuclear=False):
        self.name = name
        self._source = source
        self._rate = rate
        self._targetsystem = targetsystem
        self._targetstate = targetstate
        self.include_all_nuclear = include_all_nuclear

    @property
    def source(self):
        return self._source
    @source.setter
    def source(self, val):
        self._source = val

    @property
    def rate(self):
        return self._rate
    @rate.setter
    def rate(self, val):
        self._rate = val

    @property
    def targetsystem(self):
        return self._targetsystem
    @targetsystem.setter
    def targetsystem(self, val):
        self._targetsystem = val

    @property
    def targetstate(self):
        return self._targetstate
    @targetstate.setter
    def targetstate(self, val):
        self._targetstate = val

    def render_to_string(self):
        source_name = self._source.name if hasattr(self._source, 'name') else str(self._source)
        s = f"Transition {self.name} {{ source = {source_name};"
        if self._targetsystem is not None:
            ts_name = self._targetsystem.name if hasattr(self._targetsystem, 'name') else str(self._targetsystem)
            s += f" targetsystem = {ts_name};"
        if self._targetstate is not None:
            tstate_name = self._targetstate.name if hasattr(self._targetstate, 'name') else str(self._targetstate)
            s += f" targetstate = {tstate_name};"
        s += f" rate = {self._rate}; }}"
        return s

    def ConvertToDictionary(self):
        source_name = self._source.name if hasattr(self._source, 'name') else str(self._source)
        dict_data = {
            "source": source_name,
            "rate": self._rate
        }
        if self._targetsystem is not None:
            dict_data["targetsystem"] = self._targetsystem.name if hasattr(self._targetsystem, 'name') else str(self._targetsystem)
        if self._targetstate is not None:
            dict_data["targetstate"] = self._targetstate.name if hasattr(self._targetstate, 'name') else str(self._targetstate)
        return self.name, dict_data

    rate = ActionVariable.ActionVariable(rate)