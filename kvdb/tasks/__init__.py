from __future__ import annotations


from .base import TaskManager
from .queue import TaskQueue
from typing import Optional, Dict, Any, Callable, Awaitable, List, Tuple, Literal, TYPE_CHECKING, overload

if TYPE_CHECKING:
    from .base import Ctx, ReturnValue, ReturnValueT, FunctionT, TaskPhase, TaskResult, QueueTasks
    from .queue import QueueTasks


@overload
def register(
    name: Optional[str] = None,
    phase: Optional['TaskPhase'] = None,
    silenced: Optional[bool] = None,
    silenced_stages: Optional[List[str]] = None,
    default_kwargs: Optional[Dict[str, Any]] = None,
    cronjob: Optional[bool] = None,
    queue_name: Optional[str] = None,
    disable_patch: Optional[bool] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,
    attribute_match_type: Optional[Literal['any', 'all']] = None,
    **kwargs
) -> Callable[['FunctionT'], 'FunctionT']:
    """
    Registers a function to the queue_name
    """
    ...


def register(
    queue_name: Optional[str] = None,
    **kwargs
) -> Callable[['FunctionT'], 'FunctionT']:
    """
    Registers a function to the queue_name
    """
    return TaskManager.register(queue_name = queue_name, **kwargs)


@overload
def create_context(
    queue_name: Optional[str] = None,
    name: Optional[str] = None,
    phase: Optional[TaskPhase] = None,
    silenced: Optional[bool] = None,
    silenced_stages: Optional[List[str]] = None,
    default_kwargs: Optional[Dict[str, Any]] = None,
    cronjob: Optional[bool] = None,
    disable_patch: Optional[bool] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,
    attribute_match_type: Optional[Literal['any', 'all']] = None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> 'QueueTasks':
    """
    Creates a context
    """
    ...

def create_context(
    queue_name: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> 'QueueTasks':
    """
    Creates a context
    """
    return TaskManager.create_context(queue_name = queue_name, context = context, **kwargs)
