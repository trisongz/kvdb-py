"""
Exceptions raised by the Redis client.
"""

from redis.exceptions import RedisError
from typing import Optional, Union, TYPE_CHECKING
from .utils.logs import logger


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
        *args,
        **kwargs,
    ):
        self.msg = msg
        if fatal is not None: self.fatal = fatal
        if verbose is not None: self.verbose = verbose
        if level is not None: self.level = level
        if traceback_depth is not None: self.traceback_depth = traceback_depth
        super().__init__(*args, **kwargs)
        if self.verbose: logger.log(self.level, self.log_msg)
    
    @property
    def log_msg(self) -> str:
        """
        Returns the log message
        """
        msg = f'[{self.__name__}]'
        if self.msg: msg += f' {self.msg}'
        if self.fatal: 
            import traceback
            msg += f'\n{traceback.format_exc(limit = self.traceback_depth)}'
        else: msg += f'\n{str(self)}'
        return msg.strip()


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

class ChildDeadlockedError(KVDBException):
    """
    Internal exception used to break deadlocks in the connection pool.
    """
    level = 'ERROR'
    traceback_depth = 2
    verbose = True
    

def transpose_error(
    exc: Union[RedisError, KVDBException, Exception],
    msg: Optional[str] = None,
    fatal: Optional[bool] = None,
    verbose: Optional[bool] = None,
) -> KVDBException:
    """
    Transposes the error to a KVDBException
    """
    if isinstance(exc, KVDBException): exc
    if isinstance(exc, RedisError):
        local_error_dict = locals()
        if exc.__name__ in local_error_dict:
            return local_error_dict[exc.__name__](msg = msg, fatal = fatal, verbose = verbose)
        return KVDBException(msg = msg, fatal = fatal, verbose = verbose)
    return exc
