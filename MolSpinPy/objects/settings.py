class Settings:
    """Placeholder for the MolSpin `Settings { Settings <name> {...} }` block.
    
    Terminology:
    - steps_per_simulation: Number of simulation steps within each MSD file (goes into MSD settings block)
    - This is separate from the Project.Deploy(steps=N) which controls how many MSD files to create
    """

    def __init__(self, name="general", steps_per_simulation=1, **properties):
        self.name = name
        self.properties = {"steps": steps_per_simulation}
        self.properties.update(properties)

    @property
    def steps_per_simulation(self):
        """Number of simulation steps within each MSD file."""
        return self.properties["steps"]

    @steps_per_simulation.setter
    def steps_per_simulation(self, val):
        self.properties["steps"] = val

    @property
    def steps(self):
        """Alias for steps_per_simulation for backward compatibility."""
        return self.properties["steps"]

    @steps.setter
    def steps(self, val):
        self.properties["steps"] = val

    def set_property(self, key, value):
        self.properties[key] = value

    def ConvertToDictionary(self):
        return self.name, dict(self.properties)
