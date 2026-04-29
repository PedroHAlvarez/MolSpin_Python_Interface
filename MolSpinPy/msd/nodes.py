import re

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
        return self.text

class VarNode(Node):
    def __init__(self, var_name):
        Node.__init__(self)
        self.var_name = var_name
    def render(self, context):
        val = context
        for part in self.var_name.split("."):
            if isinstance(val, dict):
                val = val.get(part, "")
            else:
                return f"MISSING_VAR:{self.var_name}"
        if isinstance(val, str) and ' ' in val:
            if not (val.startswith("''") and val.endswith("''")):
                    val = f"''{val}''"
        return str(val)
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
        for item in iterable_dat:
            local_context = context.copy()
            if len(self.loop_var) == 2:
                local_context[self.loop_var[0]] = item[0]
                local_context[self.loop_var[1]] = item[1]
            else:
                local_context[self.loop_var[0]] = item
            for child in self.loop_body:
                results.append(child.render(local_context))
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
    
class IfNode(Node):
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
        val = context
        for part in condition.replace("if ", "").replace("elif ", "").split("."):
            if isinstance(val, dict):
                val = val.get(part)
            else:
                return False
        return bool(val)
    def __repr__(self):
        print(f"IfNode with {len(self.branches)} branches:")
        for condition, body in self.branches:
            print(f"Condition: {condition}")
            for child in body:
                print(f"  {child}")
        return ""


       
    

      