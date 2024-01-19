from __future__ import annotations

"""
Base Config Types
"""
from enum import Enum
from pathlib import Path

from pydantic import Field, model_validator, validator
from kvdb.types.base import BaseModel, computed_field
from kvdb.utils.logs import logger
from kvdb.utils.lazy import temp_data, app_env

from typing import Dict, Any, Optional, Type, Literal, Union, Callable, List, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.io.serializers import SerializerT
    from kvdb.io.encoder import Encoder


class SerializerConfig(BaseModel):
    """
    The Serializer Config
    """

    serializer: Optional[str] = 'json'
    serializer_kwargs: Optional[Dict[str, Any]] = Field(default_factory=dict, description = 'The kwargs to pass to the serializer')

    # Compression Support for the Serializer
    compression: Optional[str] = None
    compression_level: Optional[int] = None
    compression_enabled: Optional[bool] = False

    encoding: Optional[str] = 'utf-8'
    decode_responses: Optional[bool] = None
    

    @model_validator(mode = 'after')
    def validate_serializer(self):
        """
        Validate the serializer config
        """
        if self.compression is None and self.compression_level is None:
            from kvdb.io.compression import get_default_compression
            self.compression, self.compression_level = get_default_compression(enabled = self.compression_enabled)
            if self.compression and not temp_data.has_logged('kvdb_default_compression'):
                logger.info(f'Setting default compression to {self.compression} with level {self.compression_level}')
        if self.serializer_kwargs is None: self.serializer_kwargs = {}
        return self
    

    def get_serializer(
        self,
        serializer: Optional[str] = None,
        serializer_kwargs: Optional[Dict[str, Any]] = None,
        compression: Optional[str] = None,
        compression_level: Optional[int] = None,
        raise_errors: Optional[bool] = False,
        encoding: Optional[str] = None,
        **kwargs
    ) -> 'SerializerT':
        """
        Returns the serializer
        """
        from kvdb.io.serializers import get_serializer
        serializer = self.serializer if serializer is None else serializer
        serializer_kwargs = self.serializer_kwargs if serializer_kwargs is None else serializer_kwargs
        compression = self.compression if compression is None else compression
        compression_level = self.compression_level if compression_level is None else compression_level
        encoding = self.encoding if encoding is None else encoding
        return get_serializer(
            serializer = serializer,
            serializer_kwargs = serializer_kwargs,
            compression = compression,
            compression_level = compression_level,
            encoding = encoding,
            raise_errors = raise_errors,
            **kwargs
        )
    
    def get_encoder(
        self,
        serializer: Optional[str] = None,
        serializer_enabled: Optional[bool] = True,
        serializer_kwargs: Optional[Dict[str, Any]] = None,
        compression: Optional[str] = None,
        compression_level: Optional[int] = None,
        raise_errors: Optional[bool] = False,
        encoding: Optional[str] = None,
        decode_responses: Optional[bool] = None,
        **kwargs
    ) -> 'Encoder':
        """
        Returns the encoder
        """
        _serializer = self.get_serializer(
            serializer = serializer,
            serializer_kwargs = serializer_kwargs,
            compression = compression,
            compression_level = compression_level,
            raise_errors = raise_errors,
            encoding = encoding,
            **kwargs
        ) if serializer_enabled else None
        from kvdb.io.encoder import Encoder
        encoding = self.encoding if encoding is None else encoding
        decode_responses = self.decode_responses if decode_responses is None else decode_responses
        return Encoder(
            encoding = encoding,
            serializer = _serializer,
            decode_responses = decode_responses,
        )


class PersistenceConfig(BaseModel):
    """
    Persistence Config
    """

    prefix: Optional[str] = Field(None, description = 'The prefix for the persistence key')