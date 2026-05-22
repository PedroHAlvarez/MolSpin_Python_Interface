import os
import re
import paramiko

from . import nodes

class FileTemplate:
    def __init__ (self, *, name):
        self.template_path = name
        self.raw_template = self.read_template()
    def read_template(self):
        with open(self.template_path, "r") as f:
            return f.read()
    def render(self, context):
        raw = "".join([node.render(context) for node in self.node_tree])
        #return raw
        return re.sub(r'^\s*$\n', '', raw, flags=re.MULTILINE)
    def render_to_file(self, context, output_path):
        rendered_content = self.render(context)
        with open(output_path, "w") as f:
            f.write(rendered_content)
    def render_to_file_ssh(self, context, output_path, sftp : paramiko.sftp_client):
        rendered_content = self.render(context)
        with sftp.file(output_path, 'w') as f:
            f.write(rendered_content)
    def compile_template(self):
        self.raw_text = re.sub(r"{% comment %}.*?{% endcomment %}", "", self.raw_template, flags=re.DOTALL)

        #tokenize the template
        pattern = r"({%.*?%}|{{.*?}})"
        self.tokens = re.split(pattern, self.raw_text, flags=re.DOTALL)
        self.compiled_tokens = []
        for token in self.tokens:
            if not token:
                continue
            if token.startswith("{%"):
                self.compiled_tokens.append(("LOGIC", token.strip("{% ").strip(" %}")))
            elif token.startswith("{{"):
                self.compiled_tokens.append(("VAR", token.strip("{{ ").strip(" }}").split("|")[0].strip()))
            else:
                self.compiled_tokens.append(("TEXT", token))

        token_iter = iter(self.compiled_tokens)
        self.node_tree = self.build_nodes(token_iter)
    def build_nodes(self, token_itr):
        node_tree = []
        structural_tags = ("if", "elif", "else", "for", "end")
        for token_type, content in token_itr:
            if token_type == "TEXT":
                #if node_tree and not isinstance(node_tree[-1], nodes.TextNode) and not isinstance(node_tree[-1], nodes.VarNode):
                    #content = re.sub(r'^\r?\n', '', content)
                node_tree.append(nodes.TextNode(content))
            elif token_type == "VAR":
                node_tree.append(nodes.VarNode(content))
            elif token_type == "LOGIC":
                if any(content.startswith(tag) for tag in structural_tags):
                    if node_tree and isinstance(node_tree[-1], nodes.TextNode):
                        node_tree[-1].text = re.sub(r'\n[ \t]*$', '', node_tree[-1].text)
                if content.startswith("end"):
                    return node_tree
                elif content.startswith("else") or content.startswith("elif"):
                    return ("BRANCH", content, node_tree)
                elif content.startswith("if"):
                    if_node = nodes.IfNode()
                    current_cond = content
                    while True:
                        res = self.build_nodes(token_itr)
                        if isinstance(res, tuple) and res[0] == "BRANCH":
                            if_node.add_branch(current_cond, res[2])
                            current_cond = res[1]
                        else:
                            if_node.add_branch(current_cond, res)
                            break
                    node_tree.append(if_node)
                elif content.startswith("for"):
                    children = self.build_nodes(token_itr)
                    node_tree.append(nodes.LoopNode(content, children))
                    
        return node_tree



def get_template(file_path, folder = "templates"):
    file_path = os.path.join(folder, file_path)
    absolute_path = os.path.abspath(file_path)
    if not hasattr(get_template, "_cache"):
        get_template._cache = {}
    if absolute_path not in get_template._cache:
        get_template._cache[absolute_path] = FileTemplate(name=absolute_path)
        get_template._cache[absolute_path].compile_template()
    return get_template._cache[absolute_path]


def _init_input_data():
        input_data = {}
        input_data['spinsystems'] = {'System': {}}
        input_data['spinsystems']['System']['spins'] = {}
        input_data['spinsystems']['System']['spins']['electrons'] = {}
        input_data['spinsystems']['System']['spins']['nuclei'] = {}
        input_data['spinsystems']['System']['interactions'] = {}
        input_data['spinsystems']['System']['states'] = {}
        input_data['spinsystems']['System']['transitions'] = {}
        input_data['spinsystems']['System']['properties'] = {}
        input_data['spinsystems']['System']['pulses'] = {}
        input_data['spinsystems']['System']['operators'] = {}
        input_data['settings'] = {}
        input_data['actions'] = {}
        input_data['outputs'] = {}
        input_data['tasks'] = {}
        input_data['spinsystems']['System']['states']['identity'] = {}
        return input_data

def test():
    template = get_template("BasicTemplate.msd")
    input_data = _init_input_data()
    input_data['spinsystems']['System']['spins']['electrons']['e1'] = {
        "spin" : 0.5,
        "tensor" : "isotropic(2)",
        "type" : "electron"
    }
    input_data['spinsystems']['System']['spins']['nuclei']['n1'] = {
        "spin" : 1,
        "tensor" : "isotropic(1)",
        "type" : "nucleus"
    }
    input_data['spinsystems']['System']['interactions']['int1'] = {
        "type" : "zeeman",
        "spins" : "e1",
        "field" : "'\'0 0 5e-5'\'",
    }
    input_data['spinsystems']['System']['interactions']['int2'] = {
        "type" : "hyperfine",
        "group" : "e1",
        "group2" : "n1",
        "tensor" : "isotropic(1.5)"
    }
    print(template.render_to_file(input_data, "output.msd"))
