import re

class Lexer:
    def __init__(self,text):
        text = re.sub(r'//.*', '', text) #removes comments
        self.text = text
        token_quotes = r"''[^']*''|\[^\"]*\""
        token_identifiers = r"[\w\d\.\(\)\|<>+-]+"
        token_symbols = r"[={}();,]"
        pattern = f"({token_quotes}|{token_identifiers}|{token_symbols})"
        self.token_pattern = re.compile(pattern)
        self.tokens = self.token_pattern.findall(self.text)
        self.pos = 0
    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None
    def consume(self,expected=None):
        token = self.peek()
        if expected and token != expected:
            raise SyntaxError(f"Expected '{expected}', but found '{token}' at token position '{self.pos}")
        self.pos += 1
        return token

class RecursiveRenderer:
    def __init__(self,lexer:Lexer):
        self.lexer = lexer
        self.case_map = {}
    
    def _track_case(self, token : str):
        low_key = token.lower()
        if low_key not in self.case_map:
            self.case_map[low_key] = token
        return low_key

    def parse(self):
        data = {"spinsystems": {}, "actions" : {}, "settings" : {}, "outputs" : {}, "tasks" : {}}
        while self.lexer.peek():
            token = self.lexer.consume()
            low_token = token.lower()
            if low_token == "spinsystem":
                name = self.lexer.consume()
                self._track_case(token)
                self._track_case(name)
                data["spinsystems"][name] = self.parse_block()
            elif low_token == "run":
                self._track_case(token)
                content = self.parse_block()
                if "tasks" in content:
                    data["tasks"].update(content["tasks"])
            elif low_token == "settings":
                self._track_case(token)
                settings_content = self.parse_block()
                if "settings" in settings_content:
                    data["settings"].update(settings_content["settings"])
                if "actions" in settings_content:
                    data["actions"].update(settings_content["actions"])
                if "outputs" in settings_content:
                    data["outputs"].update(settings_content["outputs"])
        data["__case_map"] = self.case_map
        return data
    def parse_block(self):
        obj = {}
        self.lexer.consume("{")

        while self.lexer.peek() and self.lexer.peek() != "}":
            token = self.lexer.consume()
            low_token = token.lower()
            next = self.lexer.peek()
            if next == "{":
                self._track_case(token)
                obj[low_token] = self.parse_block()
            elif next == "=":
                self._track_case(token)
                self.lexer.consume("=")
                val_list = []
                bracket_stack = 0
                while self.lexer.peek():
                    curr = self.lexer.peek()
                    if "(" in curr: bracket_stack += curr.count("(")
                    if ")" in curr: bracket_stack -= curr.count(")")
                    if curr == ';' and bracket_stack == 0:
                        break;
                    
                    val_list.append(self.lexer.consume())
                self.lexer.consume(";")
                raw_line = " ".join(val_list)
                clean_line = re.sub(r'\s*,\s*', ', ', raw_line).strip()
                obj[low_token] = clean_line
            else:
                self._track_case(token)
                name = self.lexer.consume()
                self._track_case(name)
                content = self.parse_block()
                if low_token == "spin":
                    top_cat = f"{low_token}s"
                    if top_cat not in obj:
                        obj[top_cat] = {}
                    spin_type= content.get("type", "nucleus").lower()
                    category = "electrons" if spin_type == "electron" else "nuclei"
                    if category not in obj:
                        obj[top_cat][category] = {}
                    obj[top_cat][category][name] = content
                else:
                    if low_token[-1] != 's':
                        category = f"{low_token}s"
                        self._track_case(f"{token}s")
                    else:
                        category = f"{low_token}"
                        self._track_case(token)

                    if category not in obj:
                        obj[category] = {}
                    obj[category][name] = content
        self.lexer.consume("}")
        return obj