import os
from . import RecursiveRenderer
import numpy as np
import sys

def ConvertMSDtoDictionary(filename):
    if not os.path.isfile(filename):
        print(f"Error: The file '{filename}' does not exist.")
        return None
    with open(filename, "r") as f:
        text = f.read()
    lexer = RecursiveRenderer.Lexer(text)
    parser = RecursiveRenderer.RecursiveRenderer(lexer)
    return parser.parse()

def save_data_npz(header_names,lines, filename):
    data_rows = np.array(lines[1:])
    save_dict = {}
    save_dict['_group_map'] = data_rows[:,0]
    for i,name in enumerate(header_names):
        percent = int(((i+1) / len(header_names)) * 100)
        bar_length = 20
        filled_length = int(bar_length * (i+1) // len(header_names))
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        sys.stdout.write(f"\rSaving Data: |{bar}| {percent}% ({name[:15]})")
        sys.stdout.flush()

        if i == 0: continue
        col_data = data_rows[:,i]
        try:
            save_dict[name] = col_data.astype(float)
        except ValueError:
            save_dict[name] = col_data
    np.savez(filename, **save_dict)
    print(f"Saved {filename} to .npz file")

    