import enum
import sys

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
            return "; ".join(", ".join(str(v) for v in row) for row in arr)
        elif len(arr) == 3:
            return ", ".join(str(v) for v in arr)
        elif len(arr) == 1:
            return str(arr[0])
        else:
            raise ValueError("Input array not valid")
        return ""

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