from __future__ import annotations

"""
Retryable Functions and Classes
"""

import anyio
import inspect
import logging
import contextlib
from importlib.metadata import version
from tenacity import (
    retry, 
    wait_exponential, 
    stop_after_delay, 
    before_sleep_log, 
    retry_unless_exception_type, 
    retry_if_exception_type, 
    retry_if_exception
)
from kvdb.utils.helpers import lazy_function_wrapper
from typing import Optional, Union, Tuple, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from tenacity import WrappedFn

_excluded_funcs = [
    'parse_response', 
    'ping'
]


logger = logging.getLogger(__name__)


class retry_if_type(retry_if_exception):
    """
    Retries if the exception is of the given type
    """
    def __init__(
        self, 
        exception_types: Union[
            Type[BaseException],
            Tuple[Type[BaseException], ...],
        ] = Exception,
        excluded_types: Union[
            Type[BaseException],
            Tuple[Type[BaseException], ...],
        ] = None,
    ):
        self.exception_types = exception_types
        self.excluded_types = excluded_types
        super().__init__(lambda e: self.validate_exception(e))

    def validate_exception(self, e: BaseException) -> bool:
        # Exclude ping by default
        if e.args and e.args[0] == 'PING': 
            # print('EXCLUDED PING')
            return False
        return isinstance(e, self.exception_types) and not isinstance(e, self.excluded_types)


def get_retryable_wrapper(  
    enabled: bool = True,
    max_attempts: int = 15,
    max_delay: int = 60,
    logging_level: Union[str, int] = logging.DEBUG,
    **kwargs,
) -> 'WrappedFn':
    
    """
    Creates a retryable decorator
    """
    if not enabled: return None
    from kvdb import errors
    from redis import exceptions as rerrors
    if isinstance(logging_level, str): logging_level = getattr(logging, logging_level.upper())
    return retry(
        wait = wait_exponential(multiplier = 1.5, min = 1, max = max_attempts),
        stop = stop_after_delay(max_delay),
        before_sleep = before_sleep_log(logger, logging_level),
        retry = retry_if_type(
            exception_types = (
                errors.ConnectionError,
                errors.TimeoutError,
                errors.BusyLoadingError,
                rerrors.ConnectionError,
                rerrors.TimeoutError,
                rerrors.BusyLoadingError,
            ),
            excluded_types = (
                # errors.KVDBException,
                rerrors.AuthenticationError,
                rerrors.AuthorizationError,
                rerrors.InvalidResponse,
                rerrors.ResponseError,
                rerrors.NoScriptError,
            )
        )
    )


def get_retry(component: str) -> 'WrappedFn':
    """
    Gets the retry config for the given component
    """
    from kvdb.configs import settings
    return get_retryable_wrapper(
        **settings.retry.get_retry_config(component)
    )