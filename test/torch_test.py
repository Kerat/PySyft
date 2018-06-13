from unittest import TestCase
from syft.core.hooks import TorchHook
from syft.core.hooks import torch
from syft.core.workers import VirtualWorker

from torch.autograd import Variable as Var

import json

class TestTorchTensor(TestCase):
    def test___repr__(self):

        hook = TorchHook(verbose=False)
        x = torch.FloatTensor([1,2,3,4,5])
        assert x.__repr__() == '\n 1\n 2\n 3\n 4\n 5\n[torch.FloatTensor of size 5]\n'

    def test_send_tensor(self):

        hook = TorchHook(verbose=False)
        local = hook.local_worker
        remote = VirtualWorker(id=1, hook=hook)

        x = torch.FloatTensor([1,2,3,4,5])
        x = x.send_(remote)
        assert x.id in remote._objects

    def test_get_tensor(self):

        hook = TorchHook(verbose=False)
        local = hook.local_worker
        remote = VirtualWorker(id=1, hook=hook)

        x = torch.FloatTensor([1,2,3,4,5])
        x = x.send_(remote)

        # at this point, the remote worker should have x in its objects dict
        assert x.id in remote._objects

        assert((x.get_() == torch.FloatTensor([1,2,3,4,5])).float().mean() == 1)

        # because .get_() was called, x should no longer be in the remote worker's objects dict
        assert x.id not in remote._objects


    def test_deser_tensor(self):

        unregistered_tensor = torch.FloatTensor.deser(torch.FloatTensor,{"data":[1,2,3,4,5]})
        assert (unregistered_tensor == torch.FloatTensor([1,2,3,4,5])).float().sum() == 5

    def test_deser_tensor_from_message(self):

        hook = TorchHook(verbose=False)

        message_obj = json.loads(' {"torch_type": "torch.FloatTensor", "data": [1.0, 2.0, 3.0, 4.0, 5.0], "id": 9756847736, "owners": [1], "is_pointer": false}')
        obj_type = hook.types_guard(message_obj['torch_type'])
        unregistered_tensor = torch.FloatTensor.deser(obj_type,message_obj)
        
        assert (unregistered_tensor == torch.FloatTensor([1,2,3,4,5])).float().sum() == 5

        # has not been registered
        assert unregistered_tensor.id != 9756847736


class TestTorchVariable(TestCase):

    def test_remote_backprop(self):

        hook = TorchHook(verbose=False)
        local = hook.local_worker
        remote = VirtualWorker(id=1, hook=hook)
        local.add_worker(remote)

        x = Var(torch.ones(2,2),requires_grad=True).send_(remote)
        x2 = Var(torch.ones(2,2)*2,requires_grad=True).send_(remote)

        y = x * x2

        y.sum().backward()

        # remote grads should be correct
        assert (remote._objects[x2.id].grad.data == torch.ones(2,2)).all()
        assert (remote._objects[x.id].grad.data == torch.ones(2,2)*2).all()

        assert (y.get().data == torch.ones(2,2)*2).all()

        assert (x.get().data == torch.ones(2,2)).all()
        assert (x2.get().data == torch.ones(2,2)*2).all()

        assert (x.grad.data == torch.ones(2,2)*2).all()
        assert (x2.grad.data == torch.ones(2,2)).all()



