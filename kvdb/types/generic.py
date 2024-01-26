from __future__ import annotations

"""
Generic types for KVDB
"""
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Awaitable, Iterable, TypeVar, Union

from typing import Any, ClassVar, TypeVar, overload
from typing_extensions import Literal, Self, TypeAlias

from redis.compat import Protocol

if TYPE_CHECKING:
    from kvdb.components.connection_pool import (
        ConnectionPool,
        AsyncConnectionPool
    )
    from kvdb.io.encoder import Encoder



Number = Union[int, float]
EncodedT = Union[bytes, memoryview]
DecodedT = Union[str, int, float]
EncodableT = Union[EncodedT, DecodedT]
AbsExpiryT = Union[int, datetime]
ExpiryT = Union[int, timedelta]
ZScoreBoundT = Union[float, str]  # str allows for the [ or ( prefix
BitfieldOffsetT = Union[int, str]  # str allows for #x syntax
_StringLikeT = Union[bytes, str, memoryview]
KeyT = _StringLikeT  # Main redis key space
PatternT = _StringLikeT  # Patterns matched against keys, fields etc
FieldT = EncodableT  # Fields within hash tables, streams and geo commands
KeysT = Union[KeyT, Iterable[KeyT]]
ChannelT = _StringLikeT
GroupT = _StringLikeT  # Consumer group
ConsumerT = _StringLikeT  # Consumer name
StreamIdT = Union[int, _StringLikeT]
ScriptTextT = _StringLikeT
TimeoutSecT = Union[int, float, _StringLikeT]
# Mapping is not covariant in the key type, which prevents
# Mapping[_StringLikeT, X] from accepting arguments of type Dict[str, X]. Using
# a TypeVar instead of a Union allows mappings with any of the permitted types
# to be passed. Care is needed if there is more than one such mapping in a
# type signature because they will all be required to be the same key type.
AnyKeyT = TypeVar("AnyKeyT", bytes, str, memoryview)
AnyFieldT = TypeVar("AnyFieldT", bytes, str, memoryview)
AnyChannelT = TypeVar("AnyChannelT", bytes, str, memoryview)


class CommandsProtocol(Protocol):
    connection_pool: Union["AsyncConnectionPool", "ConnectionPool"]

    def execute_command(self, *args, **options):
        ...


class ClusterCommandsProtocol(CommandsProtocol, Protocol):
    encoder: "Encoder"

    def execute_command(self, *args, **options) -> Union[Any, Awaitable]:
        ...


_Value: TypeAlias = bytes | float | int | str
_Key: TypeAlias = str | bytes

# Lib returns str or bytes depending on value of decode_responses
_StrType = TypeVar("_StrType", bound=str | bytes)

_VT = TypeVar("_VT")
_T = TypeVar("_T")

SYM_EMPTY: bytes
EMPTY_RESPONSE: str
NEVER_DECODE: str

_LockType = TypeVar("_LockType")

class Constant(tuple):
    "Pretty display of immutable constant."

    def __new__(cls, name):
        return tuple.__new__(cls, (name,))

    def __repr__(self):
        return f'{self[0]}'

ENOVAL = Constant('ENOVAL')

ENCODER_SERIALIZER_PREFIX = '_kvdbenc_'
ENCODER_SERIALIZER_PREFIX_LEN = len(ENCODER_SERIALIZER_PREFIX)

ENCODER_SERIALIZER_PREFIX_BYTES = b'_kvdbenc_'
ENCODER_SERIALIZER_PREFIX_BYTES_LEN = len(ENCODER_SERIALIZER_PREFIX_BYTES)