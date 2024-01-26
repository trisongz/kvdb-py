from .base import BaseSerializer, BinaryBaseSerializer, ObjectValue, SchemaType
from ._json import JsonSerializer
from ._pickle import PickleSerializer
from ._msgpack import MsgPackSerializer
from types import ModuleType
from typing import Any, Dict, Optional, Union, Type, List

SerializerT = Union[JsonSerializer, PickleSerializer, MsgPackSerializer, BaseSerializer, BinaryBaseSerializer]

RegisteredSerializers: Dict[str, Type[SerializerT]] = {
    "json": JsonSerializer,
    "pickle": PickleSerializer,
    "msgpack": MsgPackSerializer,
}

RegisteredSerializerLibs: Dict[str, List[str]] = {
    "json": ["orjson", "ujson", "simdjson"],
    "pickle": ["dill", "cloudpickle"],
}

def get_default_serializer() -> str:
    """
    Returns the default serializer
    """
    from kvdb.configs.defaults import get_default_serializer
    return get_default_serializer()

def set_default_serializer(
    serializer: str,
    propogate: Optional[bool] = False,
) -> None:
    """
    Sets the default serializer

    :param serializer: The serializer to use
    :param propogate: Whether to propogate the change to all serializers
    """
    from kvdb.configs.defaults import set_default_serializer
    set_default_serializer(serializer, propogate)

def register_serializer(
    name: str,
    serializer: Type[SerializerT],
    override: Optional[bool] = False,
    set_as_default: Optional[bool] = False,
    propogate: Optional[bool] = False,
) -> None:
    """
    Registers a Serializer
    """
    global RegisteredSerializers
    if name in RegisteredSerializers and not override:
        raise ValueError(f"Serializer `{name}` already registered with {RegisteredSerializers[name]} and override is False")
    RegisteredSerializers[name] = serializer
    if set_as_default: set_default_serializer(name, propogate)

def set_default_serializer_lib(
    serializer: str,
    lib: Union[ModuleType, str],
):
    """
    Sets the default library for a serializer
    """
    if serializer not in RegisteredSerializers:
        raise ValueError(f"Serializer `{serializer}` is not registered. Please register the serializer first")
    RegisteredSerializers[serializer].set_default_lib(lib)

def register_serializer_lib(
    serializer: str,
    lib: Union[ModuleType, str],
    set_as_default_lib: Optional[bool] = False,
):
    """
    Registers a serializer library such as
    - Json: orjson, ujson, simdjson
    - Pickle: dill, cloudpickle
    """
    global RegisteredSerializerLibs
    if serializer not in RegisteredSerializers:
        raise ValueError(f"Serializer `{serializer}` is not registered. Please register the serializer first")
    if serializer not in RegisteredSerializerLibs:
        RegisteredSerializerLibs[serializer] = []
    if isinstance(lib, ModuleType):
        lib = lib.__name__
    if lib not in RegisteredSerializerLibs[serializer]:
        RegisteredSerializerLibs[serializer].append(lib)
    if set_as_default_lib: RegisteredSerializers[serializer].set_default_lib(lib)

def get_serializer(
    serializer: Optional[str] = None,
    **kwargs
) -> SerializerT:
    """
    Returns a Serializer
    """
    if serializer == 'auto':  serializer = None
    serializer = serializer or get_default_serializer()
    if serializer in RegisteredSerializers:
        return RegisteredSerializers[serializer](**kwargs)
    
    for kind, libs in RegisteredSerializerLibs.items():
        if serializer in libs:
            if f'{kind}lib' not in kwargs: kwargs[f'{kind}lib'] = serializer
            return RegisteredSerializers[kind](**kwargs)
    raise ValueError(f"Invalid Serializer Type: {serializer}")

def get_serializer_v1(
    serializer: Optional[str] = None,
    **kwargs
) -> SerializerT:
    """
    Returns a Serializer
    """
    if serializer == 'auto':  serializer = None
    serializer = serializer or get_default_serializer()
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