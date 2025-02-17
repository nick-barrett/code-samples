from functools import singledispatch
from typing import Any, List, Union
from dataclasses import dataclass


@dataclass
class PatchOpAdd:
    path: str
    value: Any


@dataclass
class PatchOpRemove:
    path: str


@dataclass
class PatchOpReplace:
    path: str
    value: Any


@dataclass
class PatchOpCopy:
    from_path: str
    to_path: str


@dataclass
class PatchOpMove:
    from_path: str
    to_path: str


PatchOp = Union[PatchOpAdd, PatchOpRemove, PatchOpReplace, PatchOpCopy, PatchOpMove]
PatchSet = List[PatchOp]


@singledispatch
def serialize_patch_op(op: PatchOp) -> dict:
    raise NotImplementedError


@serialize_patch_op.register
def _(op: PatchOpAdd) -> dict:
    return {"op": "add", "path": op.path, "value": op.value}


@serialize_patch_op.register
def _(op: PatchOpRemove) -> dict:
    return {"op": "remove", "path": op.path}


@serialize_patch_op.register
def _(op: PatchOpReplace) -> dict:
    return {"op": "replace", "path": op.path, "value": op.value}


@serialize_patch_op.register
def _(op: PatchOpCopy) -> dict:
    return {"op": "copy", "from": op.from_path, "path": op.to_path}


@serialize_patch_op.register
def _(op: PatchOpMove) -> dict:
    return {"op": "move", "from": op.from_path, "path": op.to_path}


def serialize_patch_set(patch_set: PatchSet) -> List[dict]:
    return [serialize_patch_op(op) for op in patch_set]
