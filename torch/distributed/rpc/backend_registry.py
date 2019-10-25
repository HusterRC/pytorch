from __future__ import absolute_import, division, print_function, unicode_literals

import collections
import enum

import torch.distributed.distributed_c10d as dc10d
from torch.distributed import ProcessGroupAgent


BackendValue = collections.namedtuple("BackendValue", ["init_backend_handler"])

# Create an enum type, `BackendType`, with empty members.
BackendType = enum.Enum(value="BackendType", names={})


def _is_backend_name_registered(backend_name):
    return backend_name in BackendType.__members__.keys()


def register_backend(backend_name, init_backend_handler):
    """Registers a new RPC backend.

    Arguments:
        backend (str): backend string to identify the handler.
        handler (function): Handler that is invoked when the
            `_init_rpc()` function is called with a backend.
             This returns the agent.
    """
    if _is_backend_name_registered(backend_name):
        raise RuntimeError("RPC backend {}: already registered".format(backend_name))
    # Create a new enum type, `BackendType`, with extended members.
    global BackendType
    existing_enum_dict = {member.name: member.value for member in BackendType}
    extended_enum_dict = dict(
        {backend_name: BackendValue(init_backend_handler=init_backend_handler)},
        **existing_enum_dict
    )
    BackendType = enum.Enum(value="BackendType", names=extended_enum_dict)
    return BackendType[backend_name]


def init_backend(backend, *args, **kwargs):
    return backend.value.init_backend_handler(*args, **kwargs)


def process_group_init_backend_handler(
    store,
    self_name,
    self_rank,
    worker_name_to_id,
    num_send_recv_threads,
    *args,
    **kwargs
):
    # Initialize ProcessGroup.
    if not dc10d.is_initialized():
        world_size = len(worker_name_to_id)
        dc10d.init_process_group(
            backend="gloo", store=store, rank=self_rank, world_size=world_size
        )

    group = dc10d._get_default_group()
    assert group is not None, "Failed to initialize default ProcessGroup."

    if (self_rank != -1) and (self_rank != group.rank()):
        raise RuntimeError(
            "self_rank argument {} doesn't match pg rank {}".format(
                self_rank, group.rank()
            )
        )
    if (worker_name_to_id is not None) and (len(worker_name_to_id) != group.size()):
        raise RuntimeError(
            "worker_name_to_id argument {} doesn't match pg size {}".format(
                worker_name_to_id, group.size()
            )
        )
    # TODO: add try-except and destroy _agent in all processes if any fails.
    return ProcessGroupAgent(self_name, group, num_send_recv_threads)


register_backend("PROCESS_GROUP", process_group_init_backend_handler)
