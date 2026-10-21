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
        self.transitons = []
        self.properties = {}
        self.states = []

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
            self.states.append(state)
            if self.nuclei and not self._has_nuclei_in_definition(state.definition) and "spins(" not in state.definition:
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
                n_parts.append(f"spin({n_obj.name}) = |{m_val}>")
            
            if len(combo) == 1 and self.nuclei[0].spin == 1.0:
                suffix_map = {1: "_U", 0: "_Z", -1: "_D"}
                suffix = suffix_map.get(combo[0], f"_{combo[0]}")
            else:
                suffix = "_" + "_".join(str(i).replace("-", "m") for i in combo)

            new_name = base_state.name + suffix
            new_def = base_state.definition.rstrip(";") + "; " + "; ".join(n_parts) + ";"
            expanded.append(states.State(new_name, new_def))
            
        return expanded

    def add_transition(self, transition: transitions.Transition = None):
        if transition is not None:
            self.transitions.append(transition)
        return transition

    def _get_expanded_transitions_and_used_states(self):
        final_transitions = []
        used_states = set()

        if "initialstate" in self.properties:
            init_st = self.properties["initialstate"]
            init_name = init_st.name if hasattr(init_st, 'name') else str(init_st)
            used_states.add(init_name)

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
                # Expand transition across all nuclear permutations
                for suf in nucleus_suffixes:
                    expanded_source = source_name + suf
                    expanded_target = (target_name + suf) if target_name else None
                    expanded_name = f"{tr.name}{suf.upper()}" if not suf.startswith("_") else tr.name + suf.replace("_", "")
                    
                    used_states.add(expanded_source)
                    if expanded_target:
                        used_states.add(expanded_target)

                    new_tr = transitions.Transition(
                        name=expanded_name,
                        source=expanded_source,
                        rate=tr.rate,
                        targetsystem=tr.targetsystem,
                        targetstate=expanded_target
                    )
                    final_transitions.append(new_tr)
            else:
                used_states.add(source_name)
                if target_name:
                    used_states.add(target_name)
                final_transitions.append(tr)

        return final_transitions, used_states

    def add_transition(self, transition=None):
        if transition is not None:
            self.transitions.append(transition)
        return transition

    def set_property(self, key, value):
        self.properties[key] = value

    def _get_effective_states(self):
        """
        Implicitly expands base electron states across all nuclear spin configurations
        if nuclei are present in the spin system and the state doesn't already specify them.
        """
        if not self.nuclei:
            return self.states

        expanded_states = []
        nucleus_indices = [list(n.index_mapping.keys()) for n in self.nuclei]
        all_nuclear_combinations = list(itertools.product(*nucleus_indices))

        for st in self.states:
            def_str = st.definition
            nucleus_names = [n.name for n in self.nuclei]
            has_nuclei_specified = any(n_name in def_str for n_name in nucleus_names)

            if has_nuclei_specified or not def_str.strip() or "spins(" in def_str:
                # Keep state as-is if it already specifies nuclei, is empty (identity), or is a joint entangled state
                expanded_states.append(st)
            else:
                # Base electron state detected. Automatically expand across all nuclear configurations!
                for combo in all_nuclear_combinations:
                    n_parts = []
                    for n_obj, idx in zip(self.nuclei, combo):
                        m_val = n_obj.resolve_index(idx)
                        n_parts.append(f"spin({n_obj.name}) = |{m_val}>")
                    
                    # Generate intuitive suffixes (e.g. _U, _Z, _D for spin-1 nuclei)
                    if len(combo) == 1 and self.nuclei[0].spin == 1.0:
                        suffix_map = {1: "_U", 0: "_Z", -1: "_D"}
                        suffix = suffix_map.get(combo[0], f"_{combo[0]}")
                    else:
                        suffix = "_" + "_".join(str(i).replace("-", "m") for i in combo)

                    new_name = st.name + suffix
                    new_def = def_str.rstrip(";") + "; " + "; ".join(n_parts) + ";"
                    
                    expanded_states.append(states.State(new_name, new_def))

        return expanded_states
    
    def ConvertToDictionary(self):
        dict_data = {}
        dict_data['name'] = self.name
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
        for state in self.states:
            name, sub_dict = state.ConvertToDictionary()
            if sub_dict is not None:
                dict_data['states'][name] = sub_dict

        dict_data['transitions'] = {}
        for trans in self.transitions:
            name, sub_dict = trans.ConvertToDictionary()
            if sub_dict is not None:
                dict_data['transitions'][name] = sub_dict

        dict_data['properties'] = self.properties
        return self.name, dict_data
