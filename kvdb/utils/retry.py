from __future__ import annotations

"""
Retryable Functions and Classes
"""
import random
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
# from kvdb.utils.helpers import lazy_function_wrapper
from lazyops.libs.lazyload import lazy_function_wrapper
from typing import Optional, Union, Tuple, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from tenacity import WrappedFn
    from ..components.client import KVDB, AsyncKVDB, ClientT

_excluded_funcs = [
    'parse_response', 
    'ping'
]


logger = logging.getLogger(__name__)



def exponential_backoff(
    attempts: int,
    base_delay: float,
    max_delay: float = None,
    jitter: bool = True,
) -> float:
    """
    Get the next delay for retries in exponential backoff.

    attempts: Number of attempts so far
    base_delay: Base delay, in seconds
    max_delay: Max delay, in seconds. If None (default), there is no max.
    jitter: If True, add a random jitter to the delay
    """
    if max_delay is None:
        max_delay = float("inf")
    backoff = min(max_delay, base_delay * 2 ** max(attempts - 1, 0))
    if jitter:
        backoff = backoff * random.random()
    return backoff


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
    import kvdb.errors as errors
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


def create_retryable_client(
    client: Type['ClientT'],
    max_attempts: int = 15,
    max_delay: int = 60,
    logging_level: Union[str, int] = logging.DEBUG,

    verbose: Optional[bool] = False,
    **kwargs
) -> Type['ClientT']:
    """
    Creates a retryable KVDB client
    """
    if hasattr(client, '_is_retryable_wrapped'): return client
    decorator = get_retryable_wrapper(
        max_attempts = max_attempts,
        max_delay = max_delay,
        logging_level = logging_level,
        **kwargs
    )
    for attr in dir(client):
        if attr.startswith('_'): continue
        if attr in _excluded_funcs: continue
        attr_val = getattr(client, attr)
        if inspect.isfunction(attr_val) or inspect.iscoroutinefunction(attr_val):
            if verbose: logger.info(f'Wrapping {attr} with retryable decorator')
            setattr(client, attr, decorator(attr_val))
    setattr(client, '_is_retryable_wrapped', True)
    return client


def get_retry_for_component(component: str) -> 'WrappedFn':
    """
    Gets the retry config for the given component
    """
    from kvdb.configs import settings
    return get_retryable_wrapper(
        **settings.retry.get_retry_config(component)
    )

def get_retry(component: str) -> 'WrappedFn':
    """
    Gets the retry config for the given component
    """
    return lazy_function_wrapper(get_retry_for_component, component)

