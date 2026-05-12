import enum
import sys
from  MolSpinPy import utility
from MolSpinPy.utility import imported
from MolSpinPy.utility import regex_functions

#add documentation
class TensorType(enum.Enum):
    ISOTROPIC = 1
    ANISOTROPIC = 2
    MATRIX = 3
    NOT_SET = 0

class Tensor:
    def __init__(self, tensor_str):
        self.tensor_str = tensor_str
        self.type = TensorType.NOT_SET
        self.values = None
        self.derived_classes = [None]

    def parse_tensor(self):
        raise NotImplementedError("Subclasses must implement parse_tensor method")
    def render_tensor(self):
        raise NotImplementedError("Subclasses must implement render_tensor method")
    @staticmethod
    def convert_array_to_input_string(arr):
        if len(arr) == 3 or any(len(row) != 3 for row in arr):
            raise ValueError("Input array must be 3x3")
        elif(len(arr) == 3) and all(len(row) == 3 for row in arr):
            return "; ".join(", ".join(str(v) for v in row) for row in arr) #full matrix
        elif len(arr) == 9:
            return "; ".join(", ".join(str(arr[i*3 + j]) for j in range(3)) for i in range(3)) #full matrix
        elif len(arr) == 3:
            return ", ".join(str(v) for v in arr) #diagonal anisotropic or isotropic 
        elif len(arr) == 1:
            return str(arr[0]) #isotropic
        else:
            raise ValueError("Input array not valid")
        return ""
    #add static method for numpy array, pandas, custom covertor 
    
    @staticmethod
    def convert_numpy_array_to_input_string(arr):
        np = imported.ImportManager.import_numpy()
        if isinstance(arr, np.ndarray):
            if arr.shape == (3, 3):
                return "; ".join(",".join(str(v) for v in row) for row in arr) #full matrix
            elif arr.shape == (3,):
                return ",".join(str(v) for v in arr) #diagonal anisotropic or isotropic 
            elif arr.shape == (1,):
                return str(arr[0]) #isotropic
            else:
                raise ValueError("Input array not valid")
        else:
            raise ValueError("Input is not a numpy array")
    
    @staticmethod
    def convert_custom_data_type_array_to_input_string(arr, method):
        if isinstance(method, function):
            output = method(arr)
            if not isinstance(output, str):
                raise ValueError("Custom conversion method must return a string")
            #check that output string is in correct format for tensor input
            #either "x" for isotropic, "x,y,z" for anisotropic, or "x1,x2,x3; x4,x5,x6; x7,x8,x9" for matrix
            regex_functions.tensor_input(output) #will raise ValueError if not in correct format
            return output
        else:
            raise ValueError("Method must be a function")

def CreateTensor(input_str : str, type : str):
    rt = None
    if type == 'isotropic':
        rt = Isotropic(input_str)
    elif type == 'anisotropic':
        rt = Anisotropic(input_str)
    elif type == 'matrix':
        rt = Matrix(input_str)
    else:
        raise ValueError("Matrix type not recognised")
    return rt

#usage example: a = Isotropic("2")
class Isotropic(Tensor):
    def __init__(self, tensor_str):
        Tensor.__init__(self, tensor_str)
        self.type = TensorType.ISOTROPIC
        self.parse_tensor()
    def parse_tensor(self):
        try:
            self.values = float(self.tensor_str)
        except ValueError:
            print(f"Error parsing isotropic tensor value: {self.tensor_str}")
            sys.exit(1)
    def render_to_string(self):
        return f"isotropic({self.values})"
    def print_tensor(self):
        print(f"[{self.values} 0.0 0.0\n 0.0 {self.values} 0.0\n 0.0 0.0 {self.values}]")

class Anisotropic(Tensor):
    def __init__(self, tensor_str):
        Tensor.__init__(self, tensor_str)
        self.type = TensorType.ANISOTROPIC
        self.parse_tensor()
    def parse_tensor(self):
        try:
            parts = self.tensor_str.split(",")
            if len(parts) != 3:
                raise ValueError("Anisotropic tensor must have 3 components")
            self.values = [float(part.strip()) for part in parts]
        except ValueError:
            print(f"Error parsing anisotropic tensor value: {self.tensor_str}")
            sys.exit(1)
    def render_to_string(self):
        return f"anisotropic({', '.join(str(v) for v in self.values)})"
    def print_tensor(self):
        print(f"[{self.values[0]} 0.0 0.0\n 0.0 {self.values[1]} 0.0\n 0.0 0.0 {self.values[2]}]")

class Matrix(Tensor):
    def __init__(self, tensor_str):
        Tensor.__init__(self, tensor_str)
        self.type = TensorType.MATRIX
        self.parse_tensor()
    def parse_tensor(self):
        try:
            rows = self.tensor_str.split(";")
            if len(rows) != 3:
                raise ValueError("Matrix tensor must have 3 rows")
            self.values = []
            for row in rows:
                parts = row.split(",")
                if len(parts) != 3:
                    raise ValueError("Each row of matrix tensor must have 3 components")
                self.values.append([float(part.strip()) for part in parts])
        except ValueError:
            print(f"Error parsing matrix tensor value: {self.tensor_str}")
            sys.exit(1)
    def render_to_string(self):
        return f"matrix({'; '.join(', '.join(str(v) for v in row) for row in self.values)})"
    def print_tensor(self):
        print(f"[{self.values[0][0]} {self.values[0][1]} {self.values[0][2]}\n {self.values[1][0]} {self.values[1][1]} {self.values[1][2]}\n {self.values[2][0]} {self.values[2][1]} {self.values[2][2]}]")