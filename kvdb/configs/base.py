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

    serializer: Optional[str] = None # 'json'
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
        if serializer is None:
            return None
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



class WorkerTimerConfig(BaseModel):
    """
    Worker Timer Config
    """
    schedule: Optional[int] = Field(1, description = 'The recurring interval for the schedule timer in seconds')
    stats: Optional[int] = Field(60, description = 'The recurring interval for the stats timer in seconds')
    sweep: Optional[int] = Field(180, description = 'The recurring interval for the sweep timer in seconds')
    abort: Optional[int] = Field(1, description = 'The recurring interval for the abort timer in seconds')
    heartbeat: Optional[int] = Field(5, description = 'The recurring interval for the heartbeat timer in seconds')
    broadcast: Optional[int] = Field(10, description = 'The recurring interval for the broadcast timer in seconds')


class TaskQueueConfig(SerializerConfig, BaseModel):
    """
    Configuration for the Task Queue
    """
    queue_prefix: Optional[str] = Field('_kvq_', description = 'The prefix for job keys')
    queue_db_id: Optional[int] = Field(3, description = 'The database number to use')
    cronjob_prefix: Optional[str] = 'cronjob'
    serializer: Optional[str] = 'json'

    job_prefix: Optional[str] = 'job'
    job_key_method: Optional[str] = 'uuid4'
    job_timeout: Optional[int] = 60 * 15 # 15 minutes
    job_ttl: Optional[int] = None
    job_retries: Optional[int] = 1
    job_retry_delay: Optional[float] = 60.0 * 1 # 1 minute
    job_max_stuck_duration: Optional[float] = None
    job_function_kwarg_prefix: Optional[str] = None

    max_concurrency: Optional[int] = 150
    max_broadcast_concurrency: Optional[int] = 50

    truncate_logs: Optional[Union[bool, int]] = 1000
    debug_enabled: Optional[bool] = None

    queue_log_name: Optional[str] = None
    worker_log_name: Optional[str] = None

    socket_timeout: Optional[float] = None
    socket_connect_timeout: Optional[float] = 60.0
    socket_keepalive: Optional[bool] = True
    heartbeat_interval: Optional[float] = 15.0


    @model_validator(mode = 'after')
    def validate_task_queue(self):
        """
        Validate the task queue config

        Automatically set defaults for job_ttl and job_max_stuck_duration
        """
        if self.job_max_stuck_duration is None: self.job_max_stuck_duration = self.job_timeout * 4
        if self.job_ttl is None: self.job_ttl = self.job_timeout * 2
        return self
    
    def get_default_job_key(self) -> str:
        """
        Returns the default job key
        """
        from kvdb.utils.helpers import uuid1, uuid4
        if self.job_key_method == 'uuid1': return uuid1()
        elif self.job_key_method == 'uuid4': return uuid4()
        raise ValueError(f'Invalid job_key_method: {self.job_key_method}')

