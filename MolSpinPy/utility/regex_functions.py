from . import imported
re = imported.Import.import_custom_module("re")


def tensor_input(tensor_str, bool = False):
    #check if tensor_str is in correct format for tensor input
    #either "x" for isotropic, "x,y,z" for anisotropic, or "x1,x2,x3; x4,x5,x6; x7,x8,x9" for matrix, sometimes can be a space instead of a comma 
    num = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
    triple = rf"{num}(?:\s*,\s*{num}){{2}}"
    pattern_str = rf"^\s*(?:{triple}(?:\s*;\s*{triple}){{2}}|{triple}|{num})\s*$"
    regex = re.compile(pattern_str)
    if regex.match(tensor_str):
        return tensor_str.strip() if not bool else True
    else:
        if(not bool):
            raise ValueError(f"Invalid tensor input format: {tensor_str}")
        else:
            return False

def vector_input(vector_str):
    #pattern = r'^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\s+[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\s+[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?$'
    #pattern = r'^\[?\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?(?:\s+[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?){2})\s*\]?$'
    num = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
    seperator = r"(?:[\s,]+)"
    body = rf"{num}{seperator}{num}{seperator}{num}"
    pattern = rf"^\s*[\[\(]?\s*({body})\s*[\]\)]?\s*$"
    if not isinstance(vector_str, str):
        raise ValueError(f"Invalid vector input format: {vector_str}")
        return False
    return bool(re.match(pattern, vector_str))

def is_float(s : str):
    if not isinstance(s,str):
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False
def is_valid_raw_tensor(s):
    s = s.strip().replace(" ", "")
    if not s.startswith('[[') and s.endswith(']]'):
        return False
    try:
        content = eval(s)
        if len(content) != 3: return False
        for row in content:
            if len(row) != 3: return False
        return True
    except:
        return False 
def normalize_delimiters(s):
    pattern = r'^[a-zA-Z]+\((.*)\)$'
    s = re.sub(pattern, r'\1', s.strip())
    s = s.replace(';', ' ; ')
    s = re.sub(r'\s+', ',', s.strip())
    s = s.replace(',;', ';').replace(';,',';').replace(',,',',')
    return s.strip(',')
def is_tensor(s : str):
    if not isinstance(s, str):
        return False, None, None
    s = s.strip()
    named = r'^(?P<type>isotropic|anisotropic|matrix)\s*\((?P<content>.*)\)$'
    match = re.match(named, s, re.IGNORECASE)
    if match:
        content = match.group('content')
        content = normalize_delimiters(content)
        valid = tensor_input(content,True)
        return valid, match.group('type'), content
    if is_valid_raw_tensor(s):
        clean = s.strip()
        matrix_input = clean.replace('],[',';').replace('] , [', ';')
        matrix_input = clean.replace('[', '').replace(']', '')
        return True, "matrix", matrix_input
    return False, None, None    
    

def GetType(str):
    valid = is_float(str)
    if valid:
        return "float", None, str
    valid = vector_input(str)
    if valid:
        return "vec", None, str
    valid, t, s = is_tensor(str)
    if valid:
        return "matrix", t, s 

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
