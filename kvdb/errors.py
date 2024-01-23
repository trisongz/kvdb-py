"""
Exceptions raised by the Redis client.
"""

import functools
from redis.exceptions import RedisError
from typing import Optional, Union, Callable, TypeVar, TYPE_CHECKING
from .utils.logs import logger
from .utils.helpers import is_coro_func

if TYPE_CHECKING:
    from kvdb.types.jobs import Job


class KVDBException(Exception):

    verbose: Optional[bool] = None
    fatal: Optional[bool] = None
    level: Optional[str] = 'ERROR'
    traceback_depth: Optional[int] = None

    def __init__(
        self,
        msg: Optional[str] = None,
        fatal: Optional[bool] = None,
        verbose: Optional[bool] = None,
        level: Optional[str] = None,
        traceback_depth: Optional[int] = None,
        source_error: Optional[RedisError] = None,
        *args,
        **kwargs,
    ):
        
        self.msg = msg
        self.source_error = source_error
        if source_error is not None: self.msg += f'\n{source_error}'
        if fatal is not None: self.fatal = fatal
        if verbose is not None: self.verbose = verbose
        if level is not None: self.level = level
        if traceback_depth is not None: self.traceback_depth = traceback_depth
        super().__init__(*args, **kwargs)
        self.display()

    def display(self):
        """
        Displays the error
        """
        if self.verbose: 
            # if self.fatal:
            #     logger.trace(self.log_msg, self, level = self.level)
            # else:
                # logger.log(self.level, self.log_msg)
            logger.log(self.level, self.log_msg)

    @property
    def error_name(self) -> str:
        """
        Returns the error name
        """
        name = self.__class__.__name__
        if not self.source_error or name != 'KVDBException': return name
        return self.source_error.__class__.__name__
    
    @property
    def log_msg(self) -> str:
        """
        Returns the log message
        """
        msg = f'[{self.error_name}]'
        if self.msg: msg += f' {self.msg}'
        if self.fatal: 
            import traceback
            msg += f'\n{traceback.format_exc(limit = self.traceback_depth)}'
        #     msg += f'\n{traceback.format_exception(self, limit = self.traceback_depth)}'
        # else: msg += f'\n{str(self)}'
        msg += f'\n{str(self)}'
        return msg.strip()

class TimeoutError(KVDBException):
    """
    Raised when there is a timeout.
    """
    level = 'WARNING'
    traceback_depth = 1
    verbose = True

class BusyLoadingError(KVDBException):
    """
    Raised when the database is busy loading.
    """
    level = 'WARNING'
    traceback_depth = 1
    verbose = True


class DataError(KVDBException):
    """
    Raised when there is a problem with the data.
    """
    level = 'WARNING'
    traceback_depth = 1
    verbose = True


class ConnectionError(KVDBException):
    """
    Raised when there is a connection error.
    """
    level = 'ERROR'
    traceback_depth = 2
    verbose = True

class TimeoutError(KVDBException):
    """
    Raised when there is a timeout.
    """
    level = 'ERROR'
    traceback_depth = 1
    verbose = True
    fatal: Optional[bool] = True

class ChildDeadlockedError(KVDBException):
    """
    Internal exception used to break deadlocks in the connection pool.
    """
    level = 'ERROR'
    traceback_depth = 2
    verbose = True

class LockError(KVDBException):
    """
    Raised when there is a problem acquiring a lock.
    """
    level = 'ERROR'
    traceback_depth = 2
    verbose = False

class LockNotOwnedError(KVDBException):
    """
    Raised when trying to release a lock that we don't own.
    """
    level = 'ERROR'
    traceback_depth = 2
    verbose = False

class JobError(KVDBException):
    """
    Raised when a job fails
    """
    level = 'ERROR'
    traceback_depth = 2
    verbose = True

    def __init__(
        self,
        job: 'Job',
        msg: Optional[str] = None,
        *args,
        **kwargs,
    ):
        
        msg = msg or ""
        msg += f"Job {job.id} {job.status}\n\nThe above job failed with the following error:\n\n{job.error}"
        super().__init__(*args, msg = msg, **kwargs)
        self.job = job


def transpose_error(
    exc: Union[RedisError, KVDBException, Exception],
    msg: Optional[str] = None,
    fatal: Optional[bool] = None,
    verbose: Optional[bool] = None,
    **kwargs,
) -> KVDBException:
    """
    Transposes the error to a KVDBException
    """
    if isinstance(exc, KVDBException): exc
    if isinstance(exc, RedisError):
        local_error_dict = locals()
        if exc.__name__ in local_error_dict:
            return local_error_dict[exc.__name__](msg = msg, fatal = fatal, verbose = verbose, source_error = exc, **kwargs)
        return KVDBException(msg = msg, fatal = fatal, verbose = verbose, source_error = exc, **kwargs)
    return exc

RT = TypeVar('RT')

def capture_error(
    verbose: Optional[bool] = None,
    **error_kwargs,
) -> Callable[[Callable[..., RT]], Callable[..., RT]]:
    """
    Decorator to capture errors and transpose them to KVDBExceptions
    """
    def decorator(func):
        if is_coro_func(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    raise transpose_error(e, verbose = verbose, **error_kwargs)
            return wrapper

        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                raise transpose_error(e, verbose = verbose, **error_kwargs)
        return wrapper
    return decorator