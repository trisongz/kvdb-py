from __future__ import annotations

"""
Configuration for Task Queues and Workers
"""

from pydantic import Field, model_validator, validator
from kvdb.types.base import BaseModel, computed_field
from kvdb.utils.helpers import uuid1, uuid4
from kvdb.utils.logs import logger
from typing import Dict, Any, Optional, Type, Literal, Union, Callable, List, Mapping, TYPE_CHECKING
from .base import SerializerConfig


class KVDBTaskQueueConfig(SerializerConfig, BaseModel):
    """
    The KVDB Task Queue Config
    """

    queue_prefix: Optional[str] = Field('_kvq_', description = 'The prefix for job keys')
    cronjob_prefix: Optional[str] = 'cronjob'

    job_prefix: Optional[str] = 'job'
    job_key_method: Optional[str] = 'uuid4'
    job_timeout: Optional[int] = 60 * 15 # 15 minutes
    job_ttl: Optional[int] = None
    job_retries: Optional[int] = 1
    job_retry_delay: Optional[float] = 60.0 * 1 # 1 minute
    job_max_stuck_duration: Optional[float] = None

    max_concurrency: Optional[int] = 150
    max_broadcast_concurrency: Optional[int] = 50

    truncate_logs: Optional[Union[bool, int]] = 1000
    debug_enabled: Optional[bool] = None

    # Worker Timers
    # These mirror the default timers
    schedule_timer: Optional[int] = 1
    stats_timer: Optional[int] = 60
    sweep_timer: Optional[int] = 180
    abort_timer: Optional[int] = 1
    heartbeat_timer: Optional[int] = 5
    broadcast_timer: Optional[int] = 10


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
        if self.job_key_method == 'uuid1': return uuid1()
        elif self.job_key_method == 'uuid4': return uuid4()
        raise ValueError(f'Invalid job_key_method: {self.job_key_method}')

    

    