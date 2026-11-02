from . import ActionVariable

class State:
    def __init__(self, name, definition):
        """
        State constructor (Default: Numeric Index Mapping).
        
        Accepts:
        1. Product states (dict): maps spin objects to integer indices centered around 0.
           Example: {e1: 1, n14: 1} -> spin(e1) = |0.5>; spin(N14) = |1.0>;
           
        2. Entangled / Joint states (tuple/list): ([spin_list], terms_list)
           where terms_list is a list of (coefficient_or_sign, [index_list]).
           Example: ([TrpH, FAD], [(+1, [1, -1]), (-1, [-1, 1])]) 
           -> spins(TrpH,FAD) = |0.5,-0.5>-|-0.5,0.5>;
        3. raw text expressions (str): a string representation of the state, which will be parsed into a dictionary.
           Example: "1/sqrt(2) * (|0.5,-0.5> - |-0.5,0.5>)" -> spins(TrpH,FAD) = |0.5,-0.5>-|-0.5,0.5>;
           
        For raw text expressions, use State.from_text(name, text_expr).
        """
        self.name = name
        self._definition = self._parse_definition(definition)

    def _parse_definition(self, definition):
        if isinstance(definition, str):
            return definition
        elif isinstance(definition, dict):
            # 1. Product state via spin-to-index dictionary
            parts = []
            for spin_obj, index in definition.items():
                spin_name = spin_obj.name if hasattr(spin_obj, 'name') else str(spin_obj)
                m_val = spin_obj.resolve_index(index)
                parts.append(f"spin({spin_name}) = |{m_val}>")
            return "; ".join(parts)# + (";" if parts else "")
        elif isinstance(definition, (list, tuple)) and len(definition) == 2 and isinstance(definition[0], (list, tuple)):
        # 2. Entangled / joint state via index arrays: ([spin1, spin2, ...], terms)
            spins_list, terms = definition
            spin_names = [s.name if hasattr(s, 'name') else str(s) for s in spins_list]
            spins_str = ",".join(spin_names)

            term_strings = []
            for coeff, indices in terms:
                # Resolve each index against its respective spin object's mapping
                m_vals = [spin.resolve_index(idx) for spin, idx in zip(spins_list, indices)]
                m_str = ",".join(str(m) for m in m_vals)

                # Format coefficient and sign cleanly
                if coeff == 1.0 or coeff == "+1" or coeff == "+":
                    term_str = f"|{m_str}>"
                    if term_strings:  # Prepend '+' operator for subsequent positive terms
                        term_str = "+" + term_str
                elif coeff == -1.0 or coeff == "-1" or coeff == "-":
                    term_str = f"-|{m_str}>"
                else:
                    sign_prefix = "+" if coeff > 0 and term_strings else ""
                    term_str = f"{sign_prefix}{coeff}*|{m_str}>"

                term_strings.append(term_str)

            expr = "".join(term_strings)
            return f"spins({spins_str}) = {expr}"
    
        elif isinstance(definition, str):
            return definition
    
        else:
            return str(definition)

    @property
    def definition(self):
        return self._definition

    @definition.setter
    def definition(self, val):
        self._definition = val

    def render_to_string(self):
        if not self._definition.strip():
            return f"State {self.name} {{}}"
        return f"State {self.name} {{ {self._definition} }}"

    def split_definition(self):
        """
        Splits the definition string into multiple componentns based on semi colons
        and splits each component into a key-value pair based on the first '=' sign.
        """

        components = [comp.strip() for comp in self._definition.split(";") if comp.strip()]
        split_components = []
        for comp in components:
            if '=' in comp:
                key, value = comp.split("=", 1)
                split_components.append((key.strip(), value.strip()))
            else:
                split_components.append((None, comp))
        return split_components

    def ConvertToDictionary(self):
        state_components = self.split_definition()
        dict_data = {}
        for key, value in state_components:
            if key is not None:
                dict_data[key] = value
            else:
                dict_data[f"component_{len(dict_data)+1}"] = value
        return self.name, dict_data

    @classmethod
    def from_text(cls, name, text_expression: str):
        """Alternative constructor: creates a state explicitly from a raw text expression string."""
        obj = cls.__new__(cls)
        obj.name = name
        obj._definition = text_expression
        return obj

    #definition = ActionVariable.ActionVariable(definition)