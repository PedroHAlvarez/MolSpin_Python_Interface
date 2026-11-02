class Task:
    """Placeholder for a MolSpin `Run { Task <name> {...} }` entry."""

    def __init__(self, name, type, **properties):
        self.name = name
        self.type = type
        self.properties = dict(properties)

    def set_property(self, key, value):
        self.properties[key] = value

    def ConvertToDictionary(self):
        dict_data = {"type": self.type}
        dict_data.update(self.properties)
        return self.name, dict_data
