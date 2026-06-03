from .. import ActionFunction
import numpy as np
import enum
from MolSpinPy.maths.vector import Vector as vector

class FibonacciSphere(ActionFunction.ActionFunction):
    def __init__(self,num_points):
        super().__init__()
        self._param_names = ['points']
        self.points = self.FibonacciSpherePoints(num_points)
        self._param['points'] = self.points 
        self._internal_func = self.FibonacciSphereLogic
    def FibonacciSpherePoints(self, num_points):
        points = []
        phi = (1 + np.sqrt(5)) / 2  # Golden ratio
        for i in range(num_points):
            y = 1 - (i / float(num_points - 1)) * 2  # y goes from 1 to -1
            radius = np.sqrt(1 - y * y)  # radius at y
            theta = i * phi  # golden angle increment
            x = np.cos(theta) * radius
            z = np.sin(theta) * radius
            points.append((x, y, z))
        return np.array(points)
    def FibonacciSphereLogic(self, step, var, state, points):
        index = step % len(points)
        return points[index]
    def DoStep(self, var):
        val = self.FibonacciSphereLogic(self._step, var, self._state, self.points)
        self._step += 1
        return val

class RotateVector(ActionFunction.ActionFunction):
    class preset_axis(enum.Enum):
        X = vector("1.0 0.0 0.0")
        Y = vector("0.0 1.0 0.0")
        Z = vector("0.0 0.0 1.0")
    
    class frame(enum.Enum):
        lab = 1
        molecular = 2

    def __init__(self,axis : vector | preset_axis, angle : float, frame : frame = frame.lab):
        super().__init__()
        if not isinstance(axis, vector):
            raise AttributeError(f"Attribute axis has to be type Vector or preset_axis")
        self._param_names = ['angle']
        self._internal_func = self.RotateVectorLogic
        self._axis = axis.norm1()
        self._frame = frame
        self._param['angle'] = angle
        self._R = self.CreateRotationMatrix(angle)

    @property
    def rotation_matrix(self):
        return self._R
        
    def CreateRotationMatrix(self, angle):
        if self._frame == self.molecular:
            #need to rotate the axis according to the current orientation of the molecule
            pass
        #otherwise rotate in the lab frame which assumes z is the quantization axis
        #use the Rodrigues' rotation formula to create the rotation matrix
        #R = Icos(theta) + [u]x*sin(theta) + uu^T(1-cos(theta))
        #where [u]x is the skew-symmetric cross-product matrix of the unit rotation axis u
        # [ 0 -u_z u_y
        #  u_z 0 -u_x
        #  u_y u_x 0 ]
        #and uu^T is the outer product of u with itself
        # [
        #   u_x^2 u_x*u_y u_x*u_z
        #   u_x*u_y u_y^2 u_y*u_z
        #   u_x*u_z u_y*u_z u_z^2 ]

        #construct [u]x
        u = self._axis.value
        u_x, u_y, u_z = u
        skew_symmetric = np.array([[0, -u_z, u_y],
                                    [u_z, 0, -u_x],
                                    [-u_y, u_x, 0]])
        #construct uu^T
        outer_product = np.outer(u, u)
        #construct the rotation matrix
        I = np.eye(3)
        R = I * np.cos(angle) + skew_symmetric * np.sin(angle) + outer_product * (1 - np.cos(angle))
        return R

    def RotateVectorLogic(self, step, var, state, angle):
        v = var.value
        if len(v) != 3:
            raise ValueError(f"Variable to rotate has to be a 3D vector")
        rotated_v = np.dot(self._R, v)
        return rotated_v
    def DoStep(self, var):
        val = self.RotateVectorLogic(self._step, var, self._state, self._param['angle'])
        self._step += 1
        return val

