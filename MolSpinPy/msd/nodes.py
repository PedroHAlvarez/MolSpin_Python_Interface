import re
from MolSpinPy.utility import regex_functions

class Node:
    def __init__(self):
        self.type = self.__class__.__name__
    def render(self, context):
        raise NotImplementedError("Subclasses must implement render method")
    def __repr__(self):
        return f"<{self.type} Node>"

class TextNode(Node):
    def __init__(self, text):
        Node.__init__(self)
        self.text = text
    def render(self, context = None):
        case_map = context.get("__case_map")
        if not case_map:
            return self.text
        return case_map.get(self.text.lower(), self.text)

class VarNode(Node):
    def __init__(self, var_name):
        Node.__init__(self)
        self.var_name = var_name
        self.parts = var_name.split(".")
        self.regex_check = [regex_functions._match_vector, regex_functions._internal_brackets]
    def render(self, context):
        val = context
        case_map = context.get("__case_map") or {}
        for part in self.parts:
            if isinstance(val, dict):
                val = val.get(part, "")
            else:
                return f"MISSING_VAR:{self.var_name}"
        
        if isinstance(val, str):
            # Both checks only ever alter strings containing one of these markers.
            if "[" in val or "matrix" in val or "anisotropic" in val:
                prev_val = val
                for fn in self.regex_check:
                    val = fn(val)
                    if val != prev_val:
                        return str(val)
        if isinstance(val, str) and ' ' in val and not ',' in val:
            if not ('(' in val or '|' in val or '<' in val or '>' in val):
                if not (val.startswith('"') and val.endswith('"')):
                    val = f'"{val}"'
        if not case_map:
            return str(val)
        display_val = case_map.get(str(val).lower(), str(val))         
        return display_val
class LoopNode(Node):
    def __init__(self, loop_header, loop_body):
        Node.__init__(self)
        self.loop_header = loop_header
        self.loop_body = loop_body
        self.parse_loop_header()
    def parse_loop_header(self):
        parts = re.search(r"for\s+(.+?)\s+in\s+(.+)", self.loop_header)
        self.loop_var = [v.strip() for v in parts.group(1).split(",")]
        self.data_path = parts.group(2).strip()
    def render(self, context, suffix = '.items'):
        path = self.data_path.replace(suffix, '')
        iterable_dat = self.resolve_path(path, context)
        if self.data_path.endswith(suffix):
            if isinstance(iterable_dat, dict):
                iterable_dat = iterable_dat.items()
            elif not isinstance(iterable_dat, list):
                return f"MISSING_VAR:{self.data_path}"
        results = []
        append = results.append
        body = self.loop_body
        two_vars = len(self.loop_var) == 2
        v0 = self.loop_var[0]
        v1 = self.loop_var[1] if two_vars else None
        # One scratch context is reused; children never retain a reference to it.
        local_context = context.copy()
        for item in iterable_dat:
            if two_vars:
                local_context[v0] = item[0]
                local_context[v1] = item[1]
            else:
                local_context[v0] = item
            for child in body:
                append(child.render(local_context))
        return "".join(results)
    def resolve_path(self, path, context):
        val = context
        for part in path.split("."):
            if isinstance(val, dict):
                val = val.get(part, "")
            else:
                return f"MISSING_VAR:{path}"
        return val
    def __repr__(self):
        print(f"<LoopNode: {self.loop_header}>")
        for child in self.loop_body:
            print(child)
        return ""
    
_PATH_PATTERN = re.compile(r'\b(?!(?:and|or|not|xor)\b)[a-zA-Z_][\w\.]*\b')

class IfNode(Node):
    _expr_cache = {}
    def __init__ (self):
        Node.__init__(self)
        self.branches = []
    def add_branch(self, condition, body):
        self.branches.append((condition, body))
    def render(self, context):
        for condition, body in self.branches:
            if condition is None or self.evaluate_condition(condition, context):
                return "".join(child.render(context) for child in body)
        return ""
    def evaluate_condition(self, condition, context):
        expr = self._expr_cache.get(condition)
        if expr is None:
            expr = condition.replace("if ", "").replace("elif ", "").strip()
            self._expr_cache[condition] = expr
        def resolve_path(match):
            path = match.group(0)
            val = context
            for part in path.split("."):
                if isinstance(val,dict):
                    val = val.get(part)
                else:
                    val = None
                    break
            return "True" if self.is_truthy(val) else "False"
        processed_expr = _PATH_PATTERN.sub(resolve_path,expr)
        processed_expr = processed_expr.replace(" xor ", " ^ ")
        try:
            return eval(processed_expr, {"__builtins__": None},{})
        except Exception:
            return False
    def __repr__(self):
        print(f"IfNode with {len(self.branches)} branches:")
        for condition, body in self.branches:
            print(f"Condition: {condition}")
            for child in body:
                print(f"  {child}")
        return ""
    
    @staticmethod
    def is_truthy(value):
        if isinstance(value, (dict,list)):
            return len(value) > 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("true", "yes", "1" , "on"): return True
            if normalized in ("false", "no", "0", "off", ""): return False
        return bool(value)


       
    

      