"""
Common Types
"""

from enum import Enum

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
