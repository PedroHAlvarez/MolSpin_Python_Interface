from . import imported
re = imported.Import.import_custom_module("re")

def tensor_input(tensor_str):
    #check if tensor_str is in correct format for tensor input
    #either "x" for isotropic, "x,y,z" for anisotropic, or "x1,x2,x3; x4,x5,x6; x7,x8,x9" for matrix
    num = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
    triple = rf"{num}(?:\s*,\s*{num}){{2}}"
    pattern_str = rf"^\s*(?:{triple}(?:\s*;\s*{triple}){{2}}|{triple}|{num})\s*$"
    regex = re.compile(pattern_str)
    if regex.match(tensor_str):
        return tensor_str.strip()
    else:
        raise ValueError(f"Invalid tensor input format: {tensor_str}")
    
def test_tensor_input():
    valid_inputs = [
        "2.0",
        "1.0,2.0,3.0",
        "1.0,0.0,0.0;0.0,1.0,0.0;0.0,0.0,1.0",
        "-1.5",
        "2e-3",
        "1e+6, -2e-3, 3e-4",
        "1e+6,-2e-3,3e-4"
    ]
    invalid_inputs = [
        "abc",
        "1.0,2.0",
        "1.0;2.0;3.0",
        "1.0,2.0;3.0",
        "1.0,2.0;3.0;4.0",
        "1.0,2.0;3.0;a"
    ]
    for inp in valid_inputs:
        try:
            assert tensor_input(inp) == inp.strip()
            print(f"Valid input passed: {inp}")
        except ValueError as e:
            print(f"Valid input failed: {inp} - {e}")
    for inp in invalid_inputs:
        try:
            tensor_input(inp)
            print(f"Invalid input passed: {inp}")
        except ValueError as e:
            print(f"Invalid input correctly failed: {inp} - {e}")
