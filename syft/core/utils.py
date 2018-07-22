"""Framework agnostic static utility functions."""
import json
import re
import types
import functools
import logging

import torch
import syft
import syft as sy

class PythonEncoder():
    """
        Encode python and torch objects to be JSON-able
        In particular, (hooked) Torch objects are replaced by their id.
        Note that a python object is returned, not JSON.
    """
    def __init__(self, retrieve_tensorvar=False, retrieve_pointers=False):
        self.retrieve_tensorvar = retrieve_tensorvar
        self.retrieve_pointers = retrieve_pointers
        self.found_tensorvar = []
        self.found_pointers = []
        self.tensorvar_types = tuple([torch.autograd.Variable,
                                     torch.nn.Parameter,
                                     torch.FloatTensor,
                                     torch.DoubleTensor,
                                     torch.HalfTensor,
                                     torch.ByteTensor,
                                     torch.CharTensor,
                                     torch.ShortTensor,
                                     torch.IntTensor,
                                     torch.LongTensor])

    def encode(self, obj, retrieve_tensorvar=None, retrieve_pointers=None, private_local=True):
        """
            Performs encoding, and retrieves if requested all the tensors and
            Variables found
        """
        if retrieve_tensorvar is not None:
            self.retrieve_tensorvar = retrieve_tensorvar
        if retrieve_pointers is not None:
            self.retrieve_pointers = retrieve_pointers

        response = [self.python_encode(obj, private_local)]
        if self.retrieve_tensorvar:
            response.append(self.found_tensorvar)
        if self.retrieve_pointers:
            response.append(self.found_pointers)

        if len(response) == 1:
            return response[0]
        else:
            return tuple(response)

    def python_encode(self, obj, private_local):
        # Case of basic types
        if isinstance(obj, (int, float, str)) or obj is None:
            return obj
        # Tensors and Variable encoded with their id
        elif isinstance(obj, self.tensorvar_types):
            if not is_tensor_empty(obj):
                if self.retrieve_tensorvar:
                    self.found_tensorvar.append(obj)
                key = '__'+type(obj).__name__+'__'
                if isinstance(obj, torch.autograd.Variable):
                    data = self.python_encode(obj.data.parent, private_local)
                else:
                    data = obj.tolist()
                tensor = {
                    'type': str(obj.__class__).split("'")[1],
                    'torch_type': 'syft.' + type(obj).__name__,
                    'data': data
                }
                return {key: tensor}
            else:  # we have a _PointerTensor
                return self.python_encode(obj.child, private_local)
        # sy._SyftTensor (Pointer, Local)
        elif issubclass(obj.__class__, sy._SyftTensor):
            key = '__'+type(obj).__name__+'__'
            # If is _PointerTensor
            if isinstance(obj, sy._PointerTensor):
                data = {
                    'owner': obj.owner.id,
                    'id': obj.id,
                    'location': obj.location.id,
                    'id_at_location': obj.id_at_location,
                    'torch_type': obj.torch_type
                }
                if not private_local:
                    if obj.torch_type == 'syft.Variable' and obj.parent.data is not None:
                        data['child'] = self.python_encode(obj.parent.data.child, private_local) #.parent??
                    else:
                        data['child'] = None
                elif private_local and obj.torch_type == 'syft.Variable':
                    data['child'] = self.python_encode(obj.child, private_local)
                if self.retrieve_pointers:
                    self.found_pointers.append(obj)
            # If is _LocalTensor
            elif isinstance(obj, sy._LocalTensor):
                data = {
                    'owner': obj.owner.id,
                    'id': obj.id,
                    'torch_type': obj.torch_type
                }
                if not private_local:
                    if not is_tensor_empty(obj.child):
                        data['child'] = self.python_encode(obj.child, private_local)
                    else:
                        data['child'] = None
                elif private_local and obj.torch_type == 'syft.Variable':
                    data['child'] = self.python_encode(obj.child, private_local)
            else:
                raise Exception('This SyftTensor <', type(obj.child), '> is not yet supported.')
            return {key: data}
        # Lists
        elif isinstance(obj, list):
            return [self.python_encode(i, private_local) for i in obj]
        # Iterables non json-serializable
        elif isinstance(obj, (tuple, set, bytearray, range)):
            key = '__'+type(obj).__name__+'__'
            return {key: [self.python_encode(i, private_local) for i in obj]}
        # Slice
        elif isinstance(obj, slice):
            key = '__'+type(obj).__name__+'__'
            return {key: {'args': [obj.start, obj.stop, obj.step]}}
        # Dict
        elif isinstance(obj, dict):
            return {
                k: self.python_encode(v, private_local)
                for k, v in obj.items()
            }
        # Generator (transformed to list)
        elif isinstance(obj, types.GeneratorType):
            logging.warning("Generator args can't be transmitted")
            return []
        # worker
        elif isinstance(obj, (sy.SocketWorker, sy.VirtualWorker)):
            return {'__worker__': obj.id}
        # Else log the error
        else:
            raise ValueError('Unhandled type', type(obj))


class PythonJSONDecoder(json.JSONDecoder):
    """
        Decode JSON and reinsert python types when needed
        Retrieve Torch objects replaced by their id
    """
    def __init__(self, worker, *args, **kwargs):
        super(PythonJSONDecoder, self).__init__(*args, object_hook=self.custom_obj_hook, **kwargs)
        self.worker = worker
        self.tensorvar_types = tuple([torch.autograd.Variable,
                                     torch.nn.Parameter,
                                     torch.FloatTensor,
                                     torch.DoubleTensor,
                                     torch.HalfTensor,
                                     torch.ByteTensor,
                                     torch.CharTensor,
                                     torch.ShortTensor,
                                     torch.IntTensor,
                                     torch.LongTensor])

    def custom_obj_hook(self, dct):
        """
            Is called on every dict found. We check if some keys correspond
            to special keywords referring to a type we need to re-cast
            (e.g. tuple, or torch Variable).
            Note that in the case we have such a keyword, we will have created
            at encoding a dict with a single key value pair, so the return if
            the for loop is valid. TODO: fix this.
        """
        return self._dict_decode(dct)

    def _dict_decode(self, dct):
        pat = re.compile('__(.+)__')
        for key, obj in dct.items():
            if pat.search(key) is not None:
                obj_type = pat.search(key).group(1)
                # Case of a tensor or a Variable
                if obj_type in map(lambda x: x.__name__, self.tensorvar_types):
                    # TODO: Find a smart way to skip register and not leaking the info to the local worker
                    if obj_type == 'Variable':
                        data = obj['data'].child
                    else:
                        data = obj['data']
                    tensorvar = eval('sy.'+obj_type)(data)
                    self.worker.hook.local_worker.de_register(tensorvar)
                    return tensorvar
                # Syft tensor
                elif obj_type in map(lambda x: x.__name__, sy._SyftTensor.__subclasses__()):
                    if obj_type == '_LocalTensor':
                        if obj['owner'] == self.worker.id:  # If it's one of his own LocalTensor
                            syft_obj = self.worker.get_obj(obj['id'])
                        else:  # Else, it received it from someone else
                            # If there is data:
                            if 'child' in obj:
                                # We acquire the tensor
                                # (as it is a leaf it is already deserialized, see custom_obj_hook behaviour)
                                torch_obj = obj['child']
                                syft_obj = sy._LocalTensor(child=torch_obj,
                                                           parent=torch_obj,
                                                           torch_type='syft.' + type(torch_obj).__name__,
                                                           owner=self.worker,
                                                           id=obj['id'],
                                                           skip_register=True
                                                           )
                            else:  # Else there is no data
                                # We make a empty envelope/footprint of it
                                owner = self.worker.get_worker(obj['owner'])
                                tensor = eval(obj['torch_type'])() # TODO Guard
                                tensor.id = obj['id']
                                syft_obj = sy._LocalTensor(child=tensor,
                                                           parent=tensor,
                                                           torch_type=obj['torch_type'],
                                                           owner=owner,
                                                           id=obj['id'],
                                                           skip_register=True
                                                           )
                                self.worker.hook.local_worker.de_register(tensor)
                        return syft_obj
                    elif obj_type == '_PointerTensor':
                        # If local, we render the object or syft object
                        if obj['location'] == self.worker.id:
                            syft_obj = self.worker.get_obj(obj['id_at_location'])
                            return syft_obj
                        else:
                            # If there is data transmission:
                            if 'child' in obj:
                                # We acquire the tensor pointer
                                syft_obj = sy._PointerTensor(child=None,
                                                             parent=None,
                                                             torch_type=obj['torch_type'],
                                                             location=obj['location'],
                                                             id_at_location=obj['id_at_location'],
                                                             owner=self.worker,
                                                             id=obj['id'],
                                                             skip_register=True)
                                if syft_obj.torch_type == 'syft.Variable' and 'child' is not None:
                                    syft_obj.parent.data.parent = obj['child']

                            else:
                                # We recreate the pointer to be transmitted
                                owner = self.worker.get_worker(obj['owner'])
                                syft_obj = sy._PointerTensor(child=None,
                                                             parent=None,
                                                             torch_type=obj['torch_type'],
                                                             location=obj['location'],
                                                             id_at_location=obj['id_at_location'],
                                                             owner=owner,
                                                             id=obj['id'],
                                                             skip_register=True)
                            return syft_obj
                    else:
                        raise Exception('SyftTensor', obj_type, 'is not supported so far')
                # Case of a iter type non json serializable
                elif obj_type in ('tuple', 'set', 'bytearray', 'range'):
                    return eval(obj_type)(obj)
                # Case of a slice
                elif obj_type == 'slice':
                    return slice(*obj['args'])
                # Case of a worker
                elif obj_type == 'worker':
                    return self.worker.get_worker(obj)
                else:
                    return obj
            else:
                pass
        return dct


def compile_command(attr, args, kwargs, has_self=False, self=None):
    command = {
        'command': attr,
        'has_self': has_self,
        'args': args,
        'kwargs': kwargs
    }
    if has_self:
        command['self'] = self

    encoder = PythonEncoder()
    command, tensorvars, pointers = encoder.encode(command, retrieve_tensorvar=True, retrieve_pointers=True)

    # Get information about the location and owner of the pointers
    locations = []
    owners = []
    for pointer in pointers:
        locations.append(pointer.location)
        owners.append(pointer.owner)
    locations = list(set(locations))
    owners = list(set(owners))

    if len(locations) > 1:
        raise Exception('All pointers should point to the same worker')
    if len(owners) > 1:
        raise Exception('All pointers should share the same owner.')

    return command, locations, owners


def convert_local_syft_to_torch(obj, reverse=False, worker=None):
    # Case of basic types and slice
    if isinstance(obj, (int, float, str, slice)) or obj is None:
        return obj
    # Tensors and Variable
    elif isinstance(obj, tuple(torch.tensorvar_types)):
        return obj.create_local_tensor(worker) if reverse else obj
    # sy._SyftTensor (Pointer, Local)
    elif issubclass(obj.__class__, sy._SyftTensor):
        return obj.child if not reverse else obj
    # Lists
    elif isinstance(obj, list):
        return [convert_local_syft_to_torch(i, reverse=reverse) for i in obj]
    # Iterables non json-serializable
    elif isinstance(obj, (tuple, set, bytearray, range)):
        return type(obj)(convert_local_syft_to_torch(list(obj), reverse=reverse))
    # Dict
    elif isinstance(obj, dict):
        return {
            k: convert_local_syft_to_torch(v, reverse=reverse)
            for k, v in obj.items()
        }
    # Generator (transformed to list)
    elif isinstance(obj, types.GeneratorType):
        logging.warning("Generator args can't be transmitted")
        return []
    elif isinstance(obj, (sy.SocketWorker, sy.VirtualWorker)):
        return obj
    # Else log the error
    else:
        raise ValueError('Unhandled type', type(obj))


def assert_has_only_torch_tensorvars(obj):
    if isinstance(obj, (int, float, str)):
        return True
    elif torch.is_tensor(obj):
        return True
    elif isinstance(obj, (torch.autograd.Variable, )):
        return True
    elif isinstance(obj, (list, tuple)):
        rep = [assert_has_only_torch_tensorvars(o) for o in obj]
        return all(rep)
    elif isinstance(obj, dict):
        rep = [assert_has_only_torch_tensorvars(o) for o in obj.values()]
        return all(rep)
    elif isinstance(obj, slice):
        return True
    else:
        logging.warning('Obj is not tensorvar', obj)
        assert False


def assert_has_only_syft_tensors(obj):
    if isinstance(obj, (int, float, str)):
        return True
    elif issubclass(obj.__class__, sy._SyftTensor):
        return True
    elif isinstance(obj, (list, tuple)):
        rep = [assert_has_only_syft_tensors(o) for o in obj]
        return all(rep)
    elif isinstance(obj, dict):
        rep = [assert_has_only_torch_tensorvars(o) for o in obj.values()]
        return all(rep)
    elif isinstance(obj, slice):
        return True
    else:
        logging.warning('Obj is not syft tensor', obj)
        assert False


def is_tensor_empty(obj):
    # TODO Will break with PyTorch >= 0.4
    return obj.dim() == 0


def map_tuple(hook, args, func):
    if hook:
        return tuple(func(hook, x) for x in args)
    else:
        return tuple(func(x) for x in args)


def map_dict(hook, kwargs, func):
    if hook:
        return {key: func(hook, val) for key, val in kwargs.items()}
    else:
        return {key: func(val) for key, val in kwargs.items()}


def pass_method_args(method):
    """Wrapper gathering partialmethod object from method call."""
    @functools.wraps(method)
    def pass_args(*args, **kwargs):
        return functools.partialmethod(method, *args, **kwargs)
    return pass_args


def pass_func_args(func):
    """Wrapper gathering partial object from function call."""

    @functools.wraps(func)
    def pass_args(*args, **kwargs):
        # Return a new partial object which when called will behave like func called with the
        # positional arguments args and keyword arguments keywords. If more arguments are
        # supplied to the call, they are appended to args. If additional keyword arguments
        # are supplied, they extend and override keywords.
        # The partial() is used for partial function application which "freezes" some
        # portion of a function's arguments and/or keywords resulting in a new object
        # with a simplified signature.
        return functools.partial(func, *args, **kwargs)
    return pass_args
