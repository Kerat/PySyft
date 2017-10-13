from syft import TensorBase
import numpy as np
from syft.nonlin import sigmoid, PolyApproximator
import unittest


# Here's our "unit tests".
class NonlinTests(unittest.TestCase):
    def test_sigmoid(self):

        a = TensorBase(np.array([1, 2, 3]))
        approx = sigmoid(a)
        self.assertEqual(approx[0], 0.70788285770000015)
        self.assertEqual(approx[1], 0.87170293820000011)
        self.assertEqual(approx[2], 0.96626517229999997)


class TestPolyApproximators(unittest.TestCase):
    def test_poly_approx_sigmoid(self):

        sigmoid = PolyApproximator(lambda x: 1 / (1 + np.exp(-x))).output

        a = TensorBase(np.array([.1, .2, .3, .4]))
        b = TensorBase(np.ones(4))

        siga = sigmoid(a)
        sigb = sigmoid(b)

        self.assertEqual(siga[0], 0.52158376423960751)
        self.assertEqual(siga[1], 0.54311827756855013)

        self.assertEqual(sigb[0], 0.7078828574)
        self.assertEqual(sigb[1], 0.7078828574)
        self.assertEqual(sigb[2], 0.7078828574)
        self.assertEqual(sigb[3], 0.7078828574)
