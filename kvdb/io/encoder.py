from __future__ import annotations

from kvdb.errors import DataError
from kvdb.utils.pool import Pooler
from typing import Any, Dict, Optional, Type, Union, Callable, TYPE_CHECKING

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
        decode_responses: Optional[bool] = True,
        serializer: Optional['SerializerT'] = None,
        **kwargs,
    ):
        self.encoding = encoding
        self.encoding_errors = encoding_errors
        self.decode_responses = decode_responses
        if serializer is not None: self.serializer = serializer.copy(
            raise_errors = True
        )

    def encode(self, value) -> bytes:
        """
        Return a bytestring or bytes-like representation of the value
        """
        if isinstance(value, (bytes, memoryview)): return value
        elif isinstance(value, (int, float)):
            value = repr(value).encode()
        elif not isinstance(value, str):
            if self.serializer is not None:
                value = self.serializer.encode(value)
            else:
                # a value we don't know how to deal with. throw an error
                typename = type(value).__name__
                raise DataError(
                    f"Invalid input of type: '{typename}'. "
                    f"Convert to a bytes, string, int or float first."
                )
        if isinstance(value, str):
            value = value.encode(self.encoding, self.encoding_errors)
        return value

    def decode(self, value, force=False) -> 'ObjectValue':
        """
        Return a unicode string from the bytes-like representation
        """
        if self.decode_responses or force:
            if isinstance(value, memoryview):
                value = value.tobytes()
            if isinstance(value, bytes):
                if self.serializer is not None:
                    value = self.serializer.decode(value)
                else:
                    value = value.decode(self.encoding, self.encoding_errors)
        return value
    
    async def aencode(self, value) -> bytes:
        """
        Return a bytestring or bytes-like representation of the value
        """
        return await Pooler.arun(self.encode, value)
    
    async def adecode(self, value, force=False) -> 'ObjectValue':
        """
        Return a unicode string from the bytes-like representation
        """
        return await Pooler.arun(self.decode, value, force=force)
