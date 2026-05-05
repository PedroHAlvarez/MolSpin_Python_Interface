import re

class Lexer:
    def __init__(self,text):
        text = re.sub(r'//.*', '', text) #removes comments
        self.text = text
        token_quotes = r"''[^']*''|\[^\"]*\""
        token_identifiers = r"[\w\d\.\(\)\|<>+-]+"
        token_symbols = r"[={}();]"
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
    def parse(self):
        data = {"spinsystems": {}, "actions" : {}, "settings" : {}, "outputs" : {}, "tasks" : {}}
        while self.lexer.peek():
            token = self.lexer.consume()
            if token.lower() == "spinsystem":
                name = self.lexer.consume()
                data["spinsystems"][name] = self.parse_block()
            elif token.lower() == "run":
                content = self.parse_block()
                if "tasks" in content:
                    data["tasks"].update(content["tasks"])
            elif token.lower() == "settings":
                settings_content = self.parse_block()
                if "settings" in settings_content:
                    data["settings"].update(settings_content["settings"])
                if "actions" in settings_content:
                    data["actions"].update(settings_content["actions"])
                if "outputs" in settings_content:
                    data["outputs"].update(settings_content["outputs"])
        return data
    def parse_block(self):
        obj = {}
        self.lexer.consume("{")

        while self.lexer.peek() and self.lexer.peek() != "}":
            token = self.lexer.consume()
            next = self.lexer.peek()
            if next == "{":
                obj[token.lower()] = self.parse_block()
            elif next == "=":
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
                obj[token.lower()] = " ".join(val_list)
            else:
                name = self.lexer.consume()
                content = self.parse_block()
                if token.lower() == "spin":
                    top_cat = f"{token.lower()}s"
                    if top_cat not in obj:
                        obj[top_cat] = {}
                    spin_type= content.get("type", "nucleus").lower()
                    category = "electrons" if spin_type == "electron" else "nuclei"
                    if category not in obj:
                        obj[top_cat][category] = {}
                    obj[top_cat][category][name] = content
                else:
                    if token.lower()[-1] != 's':
                        category = f"{token.lower()}s"
                    else:
                        category = f"{token.lower()}"

                    if category not in obj:
                        obj[category] = {}
                    obj[category][name] = content
        self.lexer.consume("}")
        return obj