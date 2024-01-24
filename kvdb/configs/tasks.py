from __future__ import annotations

"""
Configuration for Task Queues and Workers
"""

from pydantic import Field, model_validator, validator
from kvdb.types.base import BaseModel, computed_field
from kvdb.utils.helpers import uuid1, uuid4
from kvdb.utils.logs import logger
from typing import Dict, Any, Optional, Type, Literal, Union, Callable, List, Mapping, TYPE_CHECKING
from .base import SerializerConfig, TaskQueueConfig


class KVDBTaskQueueConfig(TaskQueueConfig):
    """
    The KVDB Task Queue Config
    """
    pass
    