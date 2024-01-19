from __future__ import annotations

"""
The Task Queue
"""

import os
import gc
import abc
import json
import time
import asyncio
import typing
import contextlib


from tenacity import RetryError
from pydantic import Field, model_validator, validator
from kvdb.configs import settings
from kvdb.types.base import BaseModel, KVDBUrl
from kvdb.types.jobs import (
    Job,
    JobStatus,
    TERMINAL_JOB_STATUSES,
    UNSUCCESSFUL_TERMINAL_JOB_STATUSES,
    INCOMPLETE_JOB_STATUSES,
)

from typing import (
    Dict, 
    Any, 
    Optional, 
    Type, 
    Literal, 
    Union, 
    Callable, 
    List, 
    Tuple,
    Mapping, 
    TypeVar,
    overload,
    TYPE_CHECKING
)

if TYPE_CHECKING:
    from kvdb.io.serializers import SerializerT


class TaskQueueConfig(BaseModel):
    """
    Configuration for the Task Queue
    """
    name: Optional[str] = Field(None, alias = 'queue_name')
    prefix: Optional[str] = Field(None, description = 'The prefix for job keys')
    db: Optional[int] = Field(None, description = 'The database number to use', alias ='database')

    serializer: Optional[str] = None
    serializer_kwargs: Optional[Dict[str, Any]] = Field(None, description = 'The kwargs to pass to the serializer')

    # Compression Support for the Serializer
    compression: Optional[str] = None
    compression_level: Optional[int] = None

    max_concurrency: Optional[int] = None
    max_broadcast_concurrency: Optional[int] = None

    truncate_logs: Optional[Union[bool, int]] = None
    debug_enabled: Optional[bool] = None

    silenced_functions: Optional[List[Union[str, Tuple[str, List[str]]]]] = None


class TaskQueue(abc.ABC):

    config: Optional[TaskQueueConfig] = None

    @overload
    def __init__(self, config: TaskQueueConfig, **kwargs): ...

    @overload
    def __init__(
        self,
        name: Optional[str] = None,
        prefix: Optional[str] = None,
        db: Optional[int] = None,
        serializer: Optional[str] = None,
        serializer_kwargs: Optional[Dict[str, Any]] = None,
        compression: Optional[str] = None,
        compression_level: Optional[int] = None,
        max_concurrency: Optional[int] = None,
        max_broadcast_concurrency: Optional[int] = None,
        truncate_logs: Optional[Union[bool, int]] = None,
        debug_enabled: Optional[bool] = None,
        silenced_functions: Optional[List[Union[str, Tuple[str, List[str]]]]] = None,
        **kwargs
    ): ...


    def __init__(
        self,
        **kwargs
    ):
        """
        Initializes the Task Queue
        """
        if isinstance(kwargs.get('config'), TaskQueueConfig):
            self.config = kwargs.pop('config')
        else:
            self.config = TaskQueueConfig(**kwargs)
        
        self.serializer: 'SerializerT' = settings.tasks.get_serializer(
            serializer = self.config.serializer,
            serializer_kwargs = self.config.serializer_kwargs,
            compression = self.config.compression,
            compression_level = self.config.compression_level,
        )
        



