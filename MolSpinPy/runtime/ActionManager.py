from ..objects.ActionObject import Action

class ActionManager:
    def __init__ (self, registry = {}, history_size = 100):
        self._registry = registry
        self._actions = []
        self._is_tested = False
        self._is_sorted = False
        self._buffer = history_size
    def add_action(self, action_instance : Action, priority = 0):
        if action_instance.parent is not None:
            action_instance.priority = action_instance.effective_priority
        else:
            action_instance.priority = priority
        self._actions.append(action_instance)
        target = action_instance.name
        if target not in self._registry:
            self._registry[target] = []
    def test_all(self):
        print("---Starting Action Tests---")
        try:
            for action in self._actions:
                action.Test()
            self._is_tested = True
            print("All actions passed")
        except Exception as e:
            print(f"Action testing failed: {str(e)}")
            raise e 
    def run(self,current_step):
        if not self._is_sorted:
            self._actions.sort(key=lambda x: x.priority, reverse=True)
        if not self._is_tested:
            self.test_all()
        for action in self._actions:
            action.step(current_step)
            self._registry[action.name].append({
                'step' : current_step,
                'v' : action.value
            })
        if current_step % self._buffer == 0 and current_step > 0:
            self.flush()
    def flush(self):
        #currently nothing 
        for key, val in enumerate(self._registry):
            self._registry[val] = []


    

