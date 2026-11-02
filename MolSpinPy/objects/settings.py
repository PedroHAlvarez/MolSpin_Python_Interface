class Settings:
    """Placeholder for the MolSpin `Settings { Settings <name> {...} }` block."""

    def __init__(self, name="general", steps=1, **properties):
        self.name = name
        self.properties = {"steps": steps}
        self.properties.update(properties)

    @property
    def steps(self):
        return self.properties["steps"]

    @steps.setter
    def steps(self, val):
        self.properties["steps"] = val

    def set_property(self, key, value):
        self.properties[key] = value

    def ConvertToDictionary(self):
        return self.name, dict(self.properties)
