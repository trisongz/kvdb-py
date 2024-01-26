from .base import BaseSerializer, BinaryBaseSerializer, ObjectValue, SchemaType
from ._json import JsonSerializer
from ._pickle import PickleSerializer
from ._msgpack import MsgPackSerializer
from typing import Any, Dict, Optional, Union, Type

SerializerT = Union[JsonSerializer, PickleSerializer, MsgPackSerializer, BaseSerializer]

def get_serializer(
    serializer: Optional[str] = None,
    **kwargs
) -> SerializerT:
    """
    Returns a Serializer
    """
    if serializer == 'auto':  serializer = None
    serializer = serializer or "json"
    if serializer in {"json", "orjson", "ujson", "simdjson"}:
        if serializer != "json" and "jsonlib" not in kwargs:
            kwargs["jsonlib"] = serializer
        return JsonSerializer(**kwargs)
    if serializer in {"pickle", "dill", "cloudpickle"}:
        if serializer != "pickle" and "picklelib" not in kwargs:
            kwargs["picklelib"] = serializer
        return PickleSerializer(**kwargs)
    if serializer == "msgpack":
        return MsgPackSerializer(**kwargs)
    raise ValueError(f"Invalid Serializer Type: {serializer}")