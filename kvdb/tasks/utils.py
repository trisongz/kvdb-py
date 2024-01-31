from __future__ import annotations

import typing
import operator
import asyncio

from inspect import signature
from typing import Literal, Union, Dict, Any, Tuple, Optional, Callable, List, TYPE_CHECKING
from types import ModuleType, FunctionType

if TYPE_CHECKING:
    from kvdb.types.jobs import Job, CronJob
    from .types import TaskFunction
    from .worker import TaskWorker


AttributeMatch = Literal['all', 'any', 'none', None]
AttributeMatchType = Union[AttributeMatch, int]

TRACE_CHAIN_LIMIT: typing.Optional[int] = 4

# If the attribute match type is an integer, then it is the number of attributes that must match

def get_comparison(
    source_value: Any,
    target_value: Any,
) -> bool:
    """
    Gets the comparison operator
    """
    if isinstance(target_value, str):
        if target_value.startswith('!'):
            op = operator.ne
            target_value = target_value[1:].strip()
        elif target_value.startswith('>='):
            op = operator.ge
            target_value = target_value[2:].strip()
        elif target_value.startswith('<='):
            op = operator.le
            target_value = target_value[2:].strip()
        elif target_value.startswith('>'):
            op = operator.gt
            target_value = target_value[1:].strip()
        elif target_value.startswith('<'):
            op = operator.lt
            target_value = target_value[1:].strip()
        elif target_value.startswith('in') or '~' in target_value:
            op = operator.contains
            target_value = target_value[2:].strip() if target_value.startswith('in') else target_value.split('~')[-1].strip()
        else:
            op = operator.eq
        if target_value.isnumeric():
            target_value = float(target_value)
    
    elif isinstance(target_value, (int, float)):
        op = operator.gt

    elif isinstance(target_value, bool):
        op = operator.eq
        if not isinstance(source_value, bool):
            source_value = bool(source_value)
        
    elif isinstance(target_value, (list, tuple)):
        op = operator.contains
        if not isinstance(source_value, (list, tuple)):
            source_value = [source_value]
    
    else:
        op = operator.eq
    
    if isinstance(source_value, (int, float)) and not isinstance(target_value, (int, float)):
        target_value = float(target_value)
    
    return op(source_value, target_value)

    

def determine_match_from_attributes(
    source_attributes: Dict[str, Any], # The source attributes [Worker]
    target_attributes: Dict[str, Any], # The target attributes [Function]
    attribute_match_type: AttributeMatchType,
) -> bool:
    """
    Determines if the worker attributes match

    :param source_attributes: The source attributes
    :param target_attributes: The target attributes

    :param attribute_match_type: The attribute match type

    :returns: True if the attributes match

    example:
    
    worker_attributes = {'n_gpus': 2}
    function_attributes = {'n_gpus': '>= 1'}
    determine_match_from_attributes(worker_attributes, function_attributes, 'all')
    True
    """
    if attribute_match_type is None or isinstance(attribute_match_type, str) and attribute_match_type == 'none': return True
    source_keys = set(source_attributes.keys())
    target_keys = set(target_attributes.keys())
    shared_keys = source_keys.intersection(target_keys)
    if not shared_keys: return False
    n_matched = 0
    for key in shared_keys:
        if get_comparison(source_attributes[key], target_attributes[key]):
            n_matched += 1
            if isinstance(attribute_match_type, int) and n_matched >= attribute_match_type:
                return True
            elif attribute_match_type == 'any':
                return True

    if isinstance(attribute_match_type, int) and n_matched >= attribute_match_type:
        return True
    elif attribute_match_type == 'all':
        return n_matched == len(shared_keys)
    return False


def get_func_name(func: typing.Union[str, typing.Callable, 'TaskFunction', 'CronJob', 'Job', ], prefix: Optional[str] = None) -> str:
    """
    Returns the function name
    """
    base = f'{prefix}:' if prefix else ''
    if isinstance(func, str): return f'{base}{func}'
    if callable(func): 
        # return f'{base}{func.__module__}.{func.__name__}'
        return f'{base}{func.__qualname__}'

    # CronJob
    if hasattr(func, 'function_name') and isinstance(func.function_name, str): return f'{base}{func.function_name}'

    # Job
    if hasattr(func, 'function') and isinstance(func.function, str): return f'{base}{func.function}'

    # TaskFunction
    return f'{base}{func.name}' if hasattr(func, 'name') else f'{base}{func}'



def get_exc_error(
    job: typing.Optional['Job'] = None, 
    func: typing.Optional[typing.Union[str, typing.Callable]] = None,
    chain: typing.Optional[bool] = True,
    limit: typing.Optional[int] = TRACE_CHAIN_LIMIT,
) -> str:
    import traceback
    from kvdb.configs import settings

    error = traceback.format_exc(chain=chain, limit=limit)
    err_msg = f'node={settings.host}, {error}'
    if func: err_msg = f'func={get_func_name(func)}, {err_msg}'
    elif job: err_msg = f'job={job.short_repr}, {err_msg}'
    return error


def is_cls_or_self_method(func: Callable) -> bool:
    """
    Checks if the method is from a class or self
    """
    sig = signature(func)
    return 'self' in sig.parameters or 'cls' in sig.parameters


def is_uninit_method(func: Callable) -> bool:
    """
    Checks if the method is from an non-initialized object
    """
    return type(func) == FunctionType and is_cls_or_self_method(func)


def create_task_worker_loop(
    task_worker: 'TaskWorker',
    new_loop: Optional[bool] = True,
) -> Union[asyncio.Task, asyncio.AbstractEventLoop]:
    """
    Creates a task worker loop
    """
    if new_loop:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(task_worker.start())
        return loop
    
    return asyncio.create_task(task_worker.start())