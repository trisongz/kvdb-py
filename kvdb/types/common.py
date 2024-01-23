"""
Common Types
"""

from enum import Enum
from typing import Any

"""
Job Statuses
"""

class JobStatus(str, Enum):
    NEW = "NEW"
    DEFERRED = "DEFERRED"
    QUEUED = "QUEUED"
    ACTIVE = "ACTIVE"
    ABORTED = "ABORTED"
    FAILED = "FAILED"
    COMPLETE = "COMPLETE"


INCOMPLETE_JOB_STATUSES = {
    JobStatus.NEW, 
    JobStatus.DEFERRED, 
    JobStatus.QUEUED, 
    JobStatus.ACTIVE
}
TERMINAL_JOB_STATUSES = {
    JobStatus.COMPLETE, 
    JobStatus.FAILED, 
    JobStatus.ABORTED
}
UNSUCCESSFUL_TERMINAL_JOB_STATUSES = TERMINAL_JOB_STATUSES - {
    JobStatus.COMPLETE
}


"""
Worker Statuses
"""

class WorkerStatus(str, Enum):
    STARTUP = "STARTUP"
    ACTIVE = "ACTIVE"
    SHUTDOWN = "SHUTDOWN"



class AppEnv(str, Enum):
    CICD = "cicd"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    LOCAL = "local"

    @classmethod
    def from_env(cls, env_value: str) -> "AppEnv":
        """
        Get the app environment from the environment variables
        """
        env_value = env_value.lower()
        if "cicd" in env_value or "ci/cd" in env_value:
            return cls.CICD
        if "prod" in env_value:
            return cls.PRODUCTION
        if "dev" in env_value:
            return cls.DEVELOPMENT
        if "staging" in env_value:
            return cls.STAGING
        if "local" in env_value:
            return cls.LOCAL
        raise ValueError(f"Invalid app environment: {env_value} ({type(env_value)})")
    
    def __eq__(self, other: Any) -> bool:
        """
        Equality operator
        """
        if isinstance(other, str):
            return self.value == other.lower()
        return self.value == other.value if isinstance(other, AppEnv) else False

    @property
    def is_devel(self) -> bool:
        """
        Returns True if the app environment is development
        """
        return self in [
            AppEnv.LOCAL,
            AppEnv.CICD,
            AppEnv.DEVELOPMENT
        ]

    @property
    def is_local(self) -> bool:
        """
        Returns True if the app environment is local
        """
        return self in [
            AppEnv.LOCAL,
            AppEnv.CICD,
        ]

    @property
    def name(self) -> str:
        """
        Returns the name in lower
        """
        return self.value.lower()


class CachePolicy(str, Enum):
    """
    The cache policy for cachify

    LRU: Least Recently Used
        Discards the least recently used items first by timestamp
    LFU: Least Frequently Used
        Discards the least frequently used items first by hits
    FIFO: First In First Out
        Discards the oldest items first by timestamp
    LIFO: Last In First Out
        Discards the newest items first by timestamp
    """
    LRU = 'LRU'
    LFU = 'LFU'
    FIFO = 'FIFO'
    LIFO = 'LIFO'

