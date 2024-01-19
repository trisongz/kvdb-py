from __future__ import annotations

import contextlib
from kvdb.errors import DataError
from kvdb.utils.pool import Pooler
from typing import Any, Dict, Optional, Type, Union, Callable, TYPE_CHECKING
import redis._parsers.encoders

if TYPE_CHECKING:
    from .serializers import SerializerT, ObjectValue

# Add support for this to enable faster encoding and decoding by detecting the type
ENCODER_SERIALIZER_PREFIX = b'_kvdbenc_'
ENCODER_SERIALIZER_PREFIX_LEN = len(ENCODER_SERIALIZER_PREFIX)

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
        
        if serializer is not None: serializer = serializer.copy(
            raise_errors = True
        )
        self.serializer = serializer
        self.decode_responses = decode_responses if decode_responses is not None else \
            self.serializer is not None

    def encode(self, value) -> bytes:
        """
        Return a bytestring or bytes-like representation of the value
        """
        if isinstance(value, (bytes, memoryview)): return value
        if isinstance(value, (int, float)): return repr(value).encode()
        _serialized = False
        if not isinstance(value, str):
            if self.serializer is None:
                typename = type(value).__name__
                raise DataError(
                    f"Invalid input of type: '{typename}'. "
                    f"Convert to a bytes, string, int or float first."
                )
            value = self.serializer.encode(value)
            _serialized = True
        if isinstance(value, str):
            value = value.encode(self.encoding, self.encoding_errors)
        if _serialized: value = ENCODER_SERIALIZER_PREFIX + value
        return value

    def decode(self, value, force=False) -> 'ObjectValue':
        """
        Return a unicode string from the bytes-like representation
        """
        if self.decode_responses or force:
            if isinstance(value, memoryview):
                value = value.tobytes()
            if isinstance(value, bytes):
                if self.serializer is not None and value[:ENCODER_SERIALIZER_PREFIX_LEN] == ENCODER_SERIALIZER_PREFIX:
                    value = value[ENCODER_SERIALIZER_PREFIX_LEN:]
                    with contextlib.suppress(Exception):
                        return self.serializer.decode(value)
                value = value.decode(self.encoding, self.encoding_errors)
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

redis._parsers.encoders.Encoder = Encoder