import os
from . import RecursiveRenderer

def ConvertMSDtoDictionary(filename):
    if not os.path.isfile(filename):
        print(f"Error: The file '{filename}' does not exist.")
        return None
    with open(filename, "r") as f:
        text = f.read()
    lexer = RecursiveRenderer.Lexer(text)
    parser = RecursiveRenderer.RecursiveRenderer(lexer)
    return parser.parse()

    