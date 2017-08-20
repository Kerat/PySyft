import numpy as np
from ...tensor import TensorBase


class PaillierTensor(TensorBase):

    def __init__(self, public_key, data=None, input_is_decrypted=True):
        self.encrypted = True

        self.public_key = public_key
        if(type(data) == np.ndarray and input_is_decrypted):
            self.data = public_key.encrypt(data, True)
        else:
            self.data = data

    def __add__(self, tensor):
        """Performs element-wise addition between two tensors"""

        if(not isinstance(tensor, TensorBase)):
            # try encrypting it
            tensor = self.public_key.encrypt(tensor)
            return PaillierTensor(self.public_key, self.data + tensor, False)

        if(type(tensor) == TensorBase):
            tensor = PaillierTensor(self.public_key, tensor.data)

        return PaillierTensor(self.public_key, self.data + tensor.data, False)

    def __mul__(self, tensor):
        """Performs element-wise addition between two tensors"""

        if(isinstance(tensor, TensorBase)):
            if(not tensor.encrypted):
                result = self.data * tensor.data
                o = PaillierTensor(self.public_key, result, False)
                return o
            else:
                return NotImplemented
        else:
            return PaillierTensor(self.public_key, self.data * tensor, False)

    def sum(self, dim=None):
        """Returns the sum of all elements in the input array."""
        if not self.encrypted:
            return NotImplemented

        if dim is None:
            return self.data.sum()
        else:
            return self.data.sum(axis=dim)


class Float():

    def __init__(self, public_key, data=None):
        """Wraps pointer to encrypted Float with an interface that numpy
        can use."""

        self.public_key = public_key
        if(data is not None):
            self.data = self.public_key.pk.encrypt(data)
        else:
            self.data = None

    def decrypt(self, secret_key):
        return secret_key.decrypt(self)

    def __add__(self, y):
        """Adds two encrypted Floats together."""

        out = Float(self.public_key, None)
        out.data = self.data + y.data
        return out

    def __sub__(self, y):
        """Subtracts two encrypted Floats."""

        out = Float(self.public_key, None)
        out.data = self.data - y.data
        return out

    def __mul__(self, y):
        """Multiplies two Floats. y may be encrypted or a simple Float."""

        if(type(y) == type(self)):
            out = Float(self.public_key, None)
            out.data = self.data * y.data
            return out
        elif(type(y) == int or type(y) == float):
            out = Float(self.public_key, None)
            out.data = self.data * y
            return out
        else:
            return None

    def __truediv__(self, y):
        """Divides two Floats. y may be encrypted or a simple Float."""

        if(type(y) == type(self)):
            out = Float(self.public_key, None)
            out.data = self.data / y.data
            return out
        elif(type(y) == int):
            out = Float(self.public_key, None)
            out.data = self.data / y
            return out
        else:
            return None

    def __repr__(self):
        """This is kindof a boring/uninformative __repr__"""

        return 'e'

    def __str__(self):
        """This is kindof a boring/uninformative __str__"""

        return 'e'
