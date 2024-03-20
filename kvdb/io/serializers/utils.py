"""
Serialization Utilities
"""
import abc
import datetime
import dataclasses
import contextlib
from uuid import UUID
from enum import Enum
from kvdb.utils.logs import logger
from kvdb.utils.lazy import lazy_import
from .base import BaseModel
from ._pickle import default_pickle
from typing import Optional, Union, Any, Dict, List, Tuple, Callable, Type, Mapping, TypeVar, TYPE_CHECKING

try:
    import numpy as np
    
except ImportError:
    np = None

SerializableObject = TypeVar('SerializableObject')
serialization_class_registry: Dict[str, Type[SerializableObject]] = {}

def is_primitive(value, exclude_bytes: Optional[bool] = False) -> bool:
    """
    Check if a value is a primitive type
    """
    if exclude_bytes and isinstance(value, bytes): return False
    return isinstance(value, (int, float, bool, str, bytes, type(None)))


def get_object_classname(obj: SerializableObject) -> str:
    """
    Get the classname of an object
    """
    return f"{obj.__class__.__module__}.{obj.__class__.__name__}"

def get_object_class(name: str) -> Type[SerializableObject]:
    """
    Get the class of an object
    """
    global serialization_class_registry
    if name not in serialization_class_registry:
        serialization_class_registry[name] = lazy_import(name)
    return serialization_class_registry[name]

def register_object_class(obj: SerializableObject) -> str:
    """
    Register the object class
    """
    global serialization_class_registry
    obj_class_name = get_object_classname(obj)
    if obj_class_name not in serialization_class_registry:
        serialization_class_registry[obj_class_name] = obj.__class__
    return obj_class_name


def serialize_object(
    obj: SerializableObject,
    **kwargs
) -> Union[Dict[str, Any], List[Dict[str, Any]], Any]:
    """
    Helper to serialize an object

    Args:
        obj: the object to serialize

    Returns:
        the serialized object in dict
        {
            "__type__": ...,
            "value": ...,
        }
    """
    if obj is None: return None

    if isinstance(obj, BaseModel) or hasattr(obj, 'model_dump'):
        obj_class_name = register_object_class(obj)

        obj_value = obj.model_dump(mode = 'json', round_trip = True, **kwargs)
        # for k,v in obj_value.items():
        #     # if isinstance(v, BaseModel) or hasattr(v, 'model_dump'):
        #     #     obj_value[k] = serialize_object(v)
        #     if not is_primitive(v):
        #         obj_value[k] = serialize_object(v)
        # logger.info(f'Pydantic Serializing Object: |r|({type(obj)})|e| {str(obj_value)[:1000]}', colored = True)
        return {
            "__type__": "pydantic",
            "__class__": obj_class_name,
            "value": obj_value,
        }

    if is_primitive(obj, exclude_bytes = True):
        return obj

    if isinstance(obj, (list, tuple)):
        return [serialize_object(item) for item in obj]

    if isinstance(obj, dict):
        if "__type__" in obj: return obj
        return {key: serialize_object(value) for key, value in obj.items()}
    
    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return {
            "__type__": "datetime",
            "value": obj.isoformat(),
        }

    if isinstance(obj, datetime.timedelta):
        return {
            "__type__": "timedelta",
            "value": obj.total_seconds(),
        }
    
    if isinstance(obj, dataclasses.InitVar) or dataclasses.is_dataclass(obj):
        obj_class_name = register_object_class(obj)
        return {
            "__type__": "dataclass",
            "__class__": obj_class_name,
            "value": dataclasses.asdict(obj),
        }

    if hasattr(obj, 'as_posix'):
        obj_class_name = register_object_class(obj)
        return {
            "__type__": "path",
            "__class__": obj_class_name,
            "value": obj.as_posix(),
        }

    if isinstance(obj, (bytes, bytearray)):
        return {
            "__type__": "bytes",
            "value": obj.hex(),
        }

    if isinstance(obj, (set, frozenset)):
        return {
            "__type__": "set",
            "value": list(obj),
        }
    
    if isinstance(obj, Enum):
        obj_class_name = register_object_class(obj)
        return {
            "__type__": "enum",
            "__class__": obj_class_name,
            "value": obj.value,
        }
    
    if isinstance(obj, UUID):
        return {
            "__type__": "uuid",
            "value": str(obj),
        }

    if isinstance(obj, abc.ABC):
        logger.info(f'Pickle Serializing Object: |r|({type(obj)}) {str(obj)[:1000]}', colored = True)
        obj_bytes = default_pickle.dumps(obj)
        return {
            "__type__": "pickle",
            "value": obj_bytes.hex(),
        }


    if hasattr(obj, "numpy"):  # Checks for TF tensors without needing the import
        return {
            "__type__": "tensor",
            "value": obj.numpy().tolist(),
        }
    
    if hasattr(obj, 'tolist'): # Checks for torch tensors without importing
        return {
            "__type__": "tensor",
            "value": obj.tolist(),
        }

    if np is not None:
        if isinstance(obj, (np.int_, np.intc, np.intp, np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64)):
            obj_class_name = register_object_class(obj)
            return {
                "__type__": "numpy",
                "__class__": obj_class_name,
                "value": int(obj),
            }

        if isinstance(obj, (np.float_, np.float16, np.float32, np.float64)):
            obj_class_name = register_object_class(obj)
            return {
                "__type__": "numpy",
                "__class__": obj_class_name,
                "value": float(obj),
            }

    # Try one shot encoding objects
    # with contextlib.suppress(Exception):
    
    try:
        logger.info(f'Pickle Serializing Object: |r|({type(obj)}) {str(obj)[:1000]}', colored = True)
        obj_bytes = default_pickle.dumps(obj)
        return {
            "__type__": "pickle",
            "value": obj_bytes.hex(),
        }
    except Exception as e:
        
        logger.info(f'Error Serializing Object: |r|({type(obj)}) {e}|e| {str(obj)[:1000]}', colored = True)
    
    raise TypeError(f"Cannot serialize object of type {type(obj)}")


def deserialize_object(obj: Union[Dict[str, Any], List[Dict[str, Any]], Any], schema_map: Optional[Dict[str, str]] = None) -> SerializableObject:
    # sourcery skip: extract-duplicate-method
    """
    Deserialize an object

    Args:
        obj: the object to deserialize
    """
    if obj is None: return None
    if isinstance(obj, (list, tuple)):
        return [deserialize_object(item) for item in obj]

    if isinstance(obj, dict):
        if "__type__" not in obj:
            return {key: deserialize_object(value) for key, value in obj.items()}
        
        obj_type = obj["__type__"]
        obj_value = obj["value"]
        if '__class__' in obj and schema_map is not None and obj['__class__'] in schema_map:
            obj['__class__'] = schema_map[obj['__class__']]


        if obj_type == "pydantic":
            obj_class_type = obj["__class__"]
            
            obj_class = get_object_class(obj_class_type)
            # for k,v in obj_value.items():
            #     if not is_primitive(v):
            #         obj_value[k] = deserialize_object(v)
            return obj_class(**obj_value)
        
        if obj_type == "pickle":
            try:
                obj_value = bytes.fromhex(obj_value)
                return default_pickle.loads(obj_value)
            except Exception as e:
                raise TypeError(f"Cannot deserialize object of type {obj_type}: {e}") from e
        
        if obj_type == "datetime":
            return datetime.datetime.fromisoformat(obj_value)
        
        if obj_type == "timedelta":
            return datetime.timedelta(seconds=obj_value)
        
        if obj_type == "dataclass":
            obj_class_type = obj["__class__"]
            # if schema_map is not None and obj_class_type in schema_map:
            #     obj_class_type = schema_map[obj_class_type]
            obj_class = get_object_class(obj_class_type)
            return obj_class(**obj_value)
        
        if obj_type == "path":
            obj_class = get_object_class(obj["__class__"])
            return obj_class(obj_value)
        
        if obj_type == "enum":
            obj_class = get_object_class(obj["__class__"])
            return obj_class(obj_value)
        
        if obj_type == "uuid":
            return UUID(obj_value)

        if obj_type == "bytes":
            return bytes.fromhex(obj_value)
        
        if obj_type == "set":
            return set(obj_value)
        
        raise TypeError(f"Cannot deserialize object of type {obj_type}")

    return obj



