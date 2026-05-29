from ..objects.ActionObject import Action

class ActionManager:
    def __init__ (self, registry = {}, history_size = 100):
        self._registry = registry
        self.registered_actions = {}
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
        self.registered_actions[target] = len(self._actions) - 1 
    def test_all(self):
        print("---Starting Action Tests---")
        _verified = self._verify_relationships()
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
    def _verify_relationships(self):
        has_warnings = False
        for target,action_idx in self.registered_actions.items():
            action_obj = self._actions[action_idx]
            if action_obj.parent is not None:
                parent_name = action_obj.parent.name
                if parent_name not in self.registered_actions:
                    print(f"Warning: Action {action_obj.name} has a parent {parent_name} that is not registered.")
                    has_warnings = True
        if not has_warnings:
            print("All action relationships are valid.")
        else:
            raise RuntimeError("There are warnings regarding action relationships. Please review the warnings above.")
        return has_warnings
    def flush(self):
        #currently nothing 
        for key, val in enumerate(self._registry):
            self._registry[val] = []


    

