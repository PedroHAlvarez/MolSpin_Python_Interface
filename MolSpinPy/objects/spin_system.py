from . import spin_object
from . import interactions
from . import states
from . import transitions
import itertools


class SpinSystem:
    def __init__(self, name):
        self.name = name
        self.electrons = [] 
        self.nuclei = []
        self.interactions = []
        self.transitions = []
        self.properties = {}
        self.states = []
        self.base_states = []  # Store the original states before any expansion

    def add_electron(self, elec: spin_object.Electron = None):
        if elec is not None:
            self.electrons.append(elec)
        return elec
    
    def add_nucleus(self, nuc: spin_object.Nucleus = None):
        if nuc is not None:
            self.nuclei.append(nuc)
        return nuc

    def add_interaction(self, interaction: interactions.Interaction = None):
        if interaction is not None:
            self.interactions.append(interaction)
        return interaction

    def add_state(self, state: states.State = None):
        if state is not None:
            self.base_states.append(state)  # Store the original state
            self.states.append(state)
            if self.nuclei and not self._has_nuclei_in_definition(state.definition):
                expanded = self._generate_nuclear_permutations(state)
                for exp_st in expanded:
                    self.states.append(exp_st)
        return state

    def _has_nuclei_in_definition(self, definition_str):
        if not self.nuclei:
            return False
        return any(n.name in definition_str for n in self.nuclei)

    def _generate_nuclear_permutations(self, base_state):
        nucleus_indices = [list(n.index_mapping.keys()) for n in self.nuclei]
        all_combos = list(itertools.product(*nucleus_indices))
        expanded = []
        
        for combo in all_combos:
            n_parts = []
            for n_obj, idx in zip(self.nuclei, combo):
                m_val = n_obj.resolve_index(idx)
                
                # Format whole numbers as clean integers (|0>, |1>, |-1>) 
                if isinstance(m_val, (int, float)) and float(m_val).is_integer():
                    m_str = str(int(m_val))
                else:
                    m_str = str(m_val)
                    
                n_parts.append(f"spin({n_obj.name}) = |{m_str}>")
            
            # Explicitly handle single nucleus suffix mapping (including index 0 for _Z)
            if len(combo) == 1 and self.nuclei[0].spin == 1.0:
                suffix_map = {1: "_U", 0: "_Z", -1: "_D"}
                suffix = suffix_map.get(combo[0], f"_{combo[0]}")
            else:
                suffix = "_" + "_".join(str(i).replace("-", "m") for i in combo)

            new_name = base_state.name + suffix
            new_def = base_state.definition.rstrip(";") + "; " + "; ".join(n_parts)
            expanded.append(states.State(new_name, new_def))
            
        return expanded

    def add_transition(self, transition: transitions.Transition = None):
        if transition is not None:
            self.transitions.append(transition)
        return transition

    def add_transition(self, transition=None):
        if transition is not None:
            self.transitions.append(transition)
        return transition

    def set_property(self, key, value):
        self.properties[key] = value

    def _get_expanded_transitions(self):
        final_transitions = []
        nucleus_suffixes = []
        if self.nuclei:
            if len(self.nuclei) == 1 and self.nuclei[0].spin == 1.0:
                nucleus_suffixes = ["_U", "_Z", "_D"]
            else:
                nucleus_indices = [list(n.index_mapping.keys()) for n in self.nuclei]
                nucleus_suffixes = ["_" + "_".join(str(i).replace("-", "m") for i in combo) for combo in itertools.product(*nucleus_indices)]

        for tr in self.transitions:
            source_name = tr.source.name if hasattr(tr.source, 'name') else str(tr.source)
            target_name = tr.targetstate.name if hasattr(tr.targetstate, 'name') and tr.targetstate else (str(tr.targetstate) if tr.targetstate else None)
            
            if tr.include_all_nuclear and self.nuclei and not any(source_name.endswith(suf) for suf in ["_U", "_Z", "_D"]):
                for suf in nucleus_suffixes:
                    expanded_source = source_name + suf
                    expanded_target = (target_name + suf) if target_name else None
                    expanded_name = f"{tr.name}{suf.upper()}" if not suf.startswith("_") else tr.name + suf.replace("_", "")
                    
                    new_tr = transitions.Transition(
                        name=expanded_name,
                        source=expanded_source,
                        rate=tr.rate,
                        targetsystem=tr.targetsystem,
                        targetstate=expanded_target
                    )
                    final_transitions.append(new_tr)
            else:
                final_transitions.append(tr)
        return final_transitions

    def _get_used_states(self, expanded_transitions):
        used_states = set()

        if "initialstate" in self.properties:
            init_st = self.properties["initialstate"]
            init_name = init_st.name if hasattr(init_st, 'name') else str(init_st)
            used_states.add(init_name)

        for tr in expanded_transitions:
            source_name = tr.source.name if hasattr(tr.source, 'name') else str(tr.source)
            target_name = tr.targetstate.name if hasattr(tr.targetstate, 'name') and tr.targetstate else (str(tr.targetstate) if tr.targetstate else None)
            
            used_states.add(source_name)
            if target_name:
                used_states.add(target_name)

        return used_states

    def _get_filtered_states(self, used_states):
        base_names = {st.name for st in self.base_states}
        filtered = []
        for st in self.states:
            is_base_state = st.name in base_names
            if is_base_state or st.name in used_states:
                filtered.append(st)
        return filtered

    
    def ConvertToDictionary(self):
        expanded_transitions = self._get_expanded_transitions()
        used_states = self._get_used_states(expanded_transitions)
        filtered_states = self._get_filtered_states(used_states)

        dict_data = {}
        dict_data['spins'] = {}
        dict_data['spins']['electrons'] = {}
        dict_data['spins']['nuclei'] = {}
        
        for e in self.electrons:
            name, sub_dict = e.ConvertToDictionary()
            if sub_dict is not None:
                dict_data['spins']['electrons'][name] = sub_dict
                
        for n in self.nuclei:
            name, sub_dict = n.ConvertToDictionary()
            if sub_dict is not None:
                dict_data['spins']['nuclei'][name] = sub_dict

        dict_data['interactions'] = {}
        for inter in self.interactions:
            name, sub_dict = inter.ConvertToDictionary()
            if sub_dict is not None:
                dict_data['interactions'][name] = sub_dict

        dict_data['states'] = {}
        for state in filtered_states:
            name, sub_dict = state.ConvertToDictionary()
            if sub_dict is not None:
                dict_data['states'][name] = sub_dict

        dict_data['transitions'] = {}
        for trans in expanded_transitions:
            name, sub_dict = trans.ConvertToDictionary()
            if sub_dict is not None:
                dict_data['transitions'][name] = sub_dict

        dict_data['properties'] = self.properties
        return self.name, dict_data
