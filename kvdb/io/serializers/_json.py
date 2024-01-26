from __future__ import annotations

import json
from typing import Any, Dict, Optional, Union, Type, TypeVar
from kvdb.utils.lazy import lazy_import
from kvdb.types.generic import (
    ENCODER_SERIALIZER_PREFIX,
    ENCODER_SERIALIZER_PREFIX_LEN,
    ENCODER_SERIALIZER_PREFIX_BYTES,
    ENCODER_SERIALIZER_PREFIX_BYTES_LEN,
)
from .base import BaseSerializer, ObjectValue, SchemaType, BaseModel, ModuleType, logger
from .utils import is_primitive, serialize_object, deserialize_object

try:
    import orjson
    _orjson_available = True
except ImportError:
    _orjson_available = False

try:
    import simdjson
    _simdjson_available = True
except ImportError:
    _simdjson_available = False

try:
    import ujson
    _ujson_available = True
except ImportError:
    _ujson_available = False


if _simdjson_available:
    default_json = simdjson

elif _orjson_available:
    default_json = orjson

elif _ujson_available:
    default_json = ujson

else:
    default_json = json

JsonLibT = TypeVar("JsonLibT")

class JsonSerializer(BaseSerializer):

    name: Optional[str] = "json"
    encoding: Optional[str] = "utf-8"
    jsonlib: JsonLibT = default_json
    disable_object_serialization: Optional[bool] = False

    def __init__(
        self, 
        jsonlib: Optional[Union[str, Any]] = None,
        compression: Optional[str] = None,
        compression_level: int | None = None, 
        encoding: str | None = None, 
        serialization_obj: Optional[Type[BaseModel]] = None,
        serialization_obj_kwargs: Optional[Dict[str, Any]] = None,
        disable_object_serialization: Optional[bool] = None,
        **kwargs
    ):
        super().__init__(compression, compression_level, encoding, **kwargs)
        self.serialization_obj = serialization_obj
        self.serialization_obj_kwargs = serialization_obj_kwargs or {}
        self.serialization_schemas: Dict[str, Type[BaseModel]] = {}
        if disable_object_serialization is not None:
            self.disable_object_serialization = disable_object_serialization
        if jsonlib is not None:
            if isinstance(jsonlib, str):
                jsonlib = lazy_import(jsonlib, is_module=True)
            assert hasattr(jsonlib, "dumps") and hasattr(jsonlib, "loads"), f"Invalid JSON Library: {jsonlib}"
            self.jsonlib = jsonlib
        self.jsonlib_name = self.jsonlib.__name__

    @classmethod
    def set_default_lib(cls, lib: Union[str, JsonLibT, ModuleType]) -> None:
        """
        Sets the default JSON library
        """
        global default_json
        if isinstance(lib, str):
            lib = lazy_import(lib, is_module=True)
        assert hasattr(lib, "dumps") and hasattr(lib, "loads"), f"Invalid JSON Library: {lib}"
        cls.jsonlib = lib
        default_json = lib

        
    def encode_value(self, value: Union[Any, SchemaType], **kwargs) -> str:
        """
        Encode the value with the JSON Library
        """
        try:
            value_dict = serialize_object(value, **self.serialization_obj_kwargs)
            # logger.info(f'Value Dict: {value_dict}')
            return self.jsonlib.dumps(value_dict, **kwargs)
        except Exception as e:
            if not self.is_encoder: logger.trace(f'Error Encoding Value: |r|({type(value)})|e| {str(value)[:1000]}', e, colored = True)
        try:
            return self.jsonlib.dumps(value, **kwargs)
        except Exception as e:
            if not self.is_encoder: 
                logger.info(f'Error Encoding Value: |r|({type(value)}) {e}|e| {str(value)[:1000]}', colored = True, prefix = self.jsonlib_name)
            if self.raise_errors: raise e
        return None


    def decode_one(self, value: str, **kwargs) -> Union[SchemaType, Dict, Any]:
        """
        Decode the value with the JSON Library
        """
        try:
            value = self.jsonlib.loads(value, **kwargs)
            if not self.disable_object_serialization and isinstance(value, dict) and '__class__' in value:
                obj_class_name = value.pop('__class__')
                if obj_class_name not in self.serialization_schemas:
                    self.serialization_schemas[obj_class_name] = lazy_import(obj_class_name)
                obj_class = self.serialization_schemas[obj_class_name]
                value = obj_class.model_validate(value)
            elif self.serialization_obj is not None:
                value = self.serialization_obj.model_validate(value)
            return value
        except Exception as e:
            if not self.is_encoder: logger.info(f'Error Decoding Value: |r|({type(value)}) {e}|e| {str(value)[:1000]}', colored = True, prefix = self.jsonlib_name)
            if self.raise_errors: raise e
        return None
    
    def check_encoded_value(self, value: Union[str, bytes]) -> Union[str, bytes]:
        """
        Check the encoded value to remove the prefix
        """
        if isinstance(value, bytes):
            logger.info(f'Value Bytes: {value}')
            if value.startswith(ENCODER_SERIALIZER_PREFIX_BYTES):
                value = value[ENCODER_SERIALIZER_PREFIX_BYTES_LEN:]
        elif isinstance(value, str):
            logger.info(f'Value Str: {value}')
            if value.startswith(ENCODER_SERIALIZER_PREFIX):
                value = value[ENCODER_SERIALIZER_PREFIX_LEN:]
        return value

    def decode_value(self, value: str, **kwargs) -> Union[SchemaType, Dict, Any]:
        """
        Decode the value with the JSON Library
        """
        try:
            # value = self.check_encoded_value(value)
            value = self.jsonlib.loads(value, **kwargs)
            return deserialize_object(value)
        except Exception as e:
            if not self.is_encoder: 
                logger.info(f'Error Decoding Value: |r|({type(value)}) {e}|e| {str(value)[:1000]}', colored = True, prefix = self.jsonlib_name)
            if self.raise_errors: raise e
        return None


        
    
    

    




