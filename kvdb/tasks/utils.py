from __future__ import annotations

import typing
import operator
from typing import Literal, Union, Dict, Any, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.types.jobs import Job

AttributeMatch = Literal['all', 'any', 'none', None]
AttributeMatchType = Union[AttributeMatch, int]

TRACE_CHAIN_LIMIT: typing.Optional[int] = 2

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


def get_func_name(func: typing.Union[str, typing.Callable]) -> str:
    """
    Returns the function name
    """
    return func.__name__ if callable(func) else func


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
