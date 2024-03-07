from __future__ import annotations

import contextlib
from kvdb.errors import DataError
from kvdb.utils.pool import Pooler
from kvdb.utils.logs import logger
from kvdb.types.generic import (
    ENCODER_SERIALIZER_PREFIX,
    ENCODER_SERIALIZER_PREFIX_LEN,
    ENCODER_SERIALIZER_PREFIX_BYTES,
    ENCODER_SERIALIZER_PREFIX_BYTES_LEN,
    ENCODER_NULL_VALUE,
)
from typing import Any, Dict, Optional, Type, Union, Callable, TYPE_CHECKING
# import redis._parsers.encoders

if TYPE_CHECKING:
    from .serializers import SerializerT, ObjectValue


class Encoder:
    """
    Encode strings to bytes-like and decode bytes-like to strings

    Supports the additional fallback to `SerializerT.encode` and `SerializerT.decode`
    """

    def __init__(
        self, 
        encoding: Optional[str] = 'utf-8',
        encoding_errors: Optional[str] = 'strict', 
        decode_responses: Optional[bool] = None,
        serializer: Optional['SerializerT'] = None,
        **kwargs,
    ):
        self.encoding = encoding
        self.encoding_errors = encoding_errors
        
        if serializer is not None: 
            serializer = serializer.copy(
                raise_errors = True
            )
            serializer.is_encoder = True
        self.serializer = serializer
        self.decode_responses = decode_responses if decode_responses is not None else \
            self.serializer is not None
        self._kwargs = kwargs
        self._kwargs['decode_responses'] = decode_responses
        self._kwargs['serializer'] = serializer
    
    def enable_serialization(self, serializer: Optional['SerializerT'] = None, decode_responses: Optional[bool] = None):
        """
        Enable serialization
        """
        if serializer is not None: 
            serializer = serializer.copy(
                raise_errors = True
            )
            serializer.is_encoder = True
        else:
            serializer = self._kwargs['serializer']
        self.serializer = serializer
        if decode_responses is not None:
            self.decode_responses = decode_responses
        else:
            self.decode_responses = self._kwargs['decode_responses']
            if self.decode_responses is None:
                self.decode_responses = True

    def disable_serialization(self, decode_responses: Optional[bool] = None):
        """
        Disable serialization
        """
        self.serializer = None
        if decode_responses is not None:
            self.decode_responses = decode_responses
        else:
            self.decode_responses = self._kwargs['decode_responses']
    
    @property
    def serialization_enabled(self) -> bool:
        """
        Returns whether serialization is enabled
        which requires a serializer and decode_responses
        """
        return self.serializer is not None and \
            self.decode_responses

    def encode(self, value) -> bytes:
        """
        Return a bytestring or bytes-like representation of the value
        """
        if isinstance(value, (bytes, memoryview)): return value
        if isinstance(value, (int, float)): return repr(value).encode()
        if isinstance(value, type(None)): return ENCODER_NULL_VALUE
        _serialized = False
        if not isinstance(value, str):
            if not self.serialization_enabled:
                typename = type(value).__name__
                raise DataError(
                    f"Invalid input of type: `{typename}` {value}. "
                    f"Convert to a bytes, string, int or float first."
                )
            value = self.serializer.encode(value)
            _serialized = True
        if isinstance(value, str):
            value = value.encode(self.encoding, self.encoding_errors)
        if _serialized: value = ENCODER_SERIALIZER_PREFIX_BYTES + value
        return value

    def decode(self, value, force=False) -> 'ObjectValue':
        """
        Return a unicode string from the bytes-like representation
        """
        if self.decode_responses or force or self.serialization_enabled: 
            if isinstance(value, memoryview):
                value = value.tobytes()
            
            if isinstance(value, bytes):
                if value == ENCODER_NULL_VALUE: return None
                if self.serializer is not None and value[:ENCODER_SERIALIZER_PREFIX_BYTES_LEN] == ENCODER_SERIALIZER_PREFIX_BYTES:
                    value = value[ENCODER_SERIALIZER_PREFIX_BYTES_LEN:]
                    with contextlib.suppress(Exception):
                        return self.serializer.decode(value)
                value = value.decode(self.encoding, self.encoding_errors)
            elif isinstance(value, str):
                if self.serializer is not None and value[:ENCODER_SERIALIZER_PREFIX_LEN] == ENCODER_SERIALIZER_PREFIX:
                    value = value[ENCODER_SERIALIZER_PREFIX_LEN:]
                    return self.serializer.decode(value)
        return value
    
    async def aencode(self, value) -> bytes:
        """
        Return a bytestring or bytes-like representation of the value
        """
        return await Pooler.arun(self.encode, value)
    
    async def adecode(self, value, force: bool = False) -> 'ObjectValue':
        """
        Return a unicode string from the bytes-like representation
        """
        return await Pooler.arun(self.decode, value, force=force)


try:
    import redis._parsers.encoders
    redis._parsers.encoders.Encoder = Encoder
except:
    try:
        import redis.connection
        redis.connection.Encoder = Encoder
    except:
        pass


# redis._parsers.encoders.Encoder = Encoder