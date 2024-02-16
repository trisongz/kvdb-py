from __future__ import annotations

"""
KVDB Worker Spawn / Start Methods
"""
import os
import sys
import signal
import asyncio
import atexit
import contextlib
import functools
import multiprocessing as mp
from kvdb.utils.logs import logger
from kvdb.utils.lazy import app_env
from importlib import import_module
from typing import Optional, Union, List, Dict, Any, Type, Tuple, Callable, TYPE_CHECKING, overload

if TYPE_CHECKING:
    from .tasks import QueueTasks
    from .queue import TaskQueue
    from .worker import TaskWorker
    from .types import TaskFunction, CronJob

_WorkerProcesses: Dict[str, Dict[str, Union[mp.Process, 'TaskWorker', 'asyncio.Task', 'asyncio.AbstractEventLoop']]] = {}
_WorkerExitRegistered = False

def register_worker_process(
    worker_name: str,
    task_worker: Optional['TaskWorker'] = None,
    process: Optional[mp.Process] = None,
    task: Optional[asyncio.Task] = None,
    loop: Optional[asyncio.AbstractEventLoop] = None,
):
    """
    Registers a worker process
    """
    global _WorkerProcesses
    if worker_name not in _WorkerProcesses:
        _WorkerProcesses[worker_name] = {}
    if task_worker is not None:
        _WorkerProcesses[worker_name]['task_worker'] = task_worker
    if process is not None:
        _WorkerProcesses[worker_name]['process'] = process
    if task is not None:
        _WorkerProcesses[worker_name]['task'] = task
    if loop is not None:
        _WorkerProcesses[worker_name]['loop'] = loop

def exit_worker_loop(
    loop: asyncio.AbstractEventLoop,
    task: asyncio.Task,
):
    """
    Exits the worker loop
    """
    if not task.cancelled():
        task.cancel()
    if loop is not None:
        loop.stop()
        loop.close()


def exit_task_workers(timeout: Optional[int] = 5.0, worker_names: Optional[List[str]] = None):
    """
    Exits all registered task workers
    """
    global _WorkerProcesses
    worker_names = worker_names or list(_WorkerProcesses.keys())
    for worker_name, values in _WorkerProcesses.items():
        if worker_name not in worker_names: continue
        if values.get('task'):
            loop, task = values.get('loop'), values.get('task')
            exit_worker_loop(loop, task)
            continue
        process, task_worker = values.get('process'), values.get('task_worker')
        if process is None: continue
        if process._closed: continue
        process.join(timeout)
        try:
            process.terminate()
            process.close()
        except Exception as e:
            logger.error(f'[{worker_name}] Error Stopping process: {e}')
            try:
                signal.pthread_kill(process.ident, signal.SIGKILL)
                process.join(timeout)
                process.terminate()
            except Exception as e:
                logger.error(f'[{worker_name}] Error Killing process: {e}')
                with contextlib.suppress(Exception):
                    process.kill()
                    process.close()
        finally:
            process = None

    for worker_name in worker_names:
        if worker_name in _WorkerProcesses:
            del _WorkerProcesses[worker_name]


def lazy_worker_import(
    dotted_path: str,
    absolute: Optional[bool] = True,
) -> Union[Any, Callable[..., Any]]:
    """
    A modified version of lazyops.utils.lazy.lazy_import that allows for
    lazily initializing a worker class
    """
    sys.path.append(os.getcwd())
    try:
        return import_module(dotted_path)
    except ImportError as e:
        logger.debug(f'Failed to import `{dotted_path}`: {e}')
    try:
        module_path, class_name = dotted_path.strip(' ').rsplit('.', 1)
    except ValueError as e:
        logger.error(f'"{dotted_path}" doesn\'t look like a module path')
        raise ImportError(f'"{dotted_path}" doesn\'t look like a module path') from e
    module = import_module(module_path)
    # Add the module to the globals
    # if absolute:
    #     globals()[module_path] = module
    #     curr_globals = globals()
    #     for obj in dir(module):
    #         if obj.startswith('__'): continue
    #         if obj in curr_globals: continue
    #         # # globals()[obj] = __import__(f'{module_path}.{obj}', fromlist = [obj])
    #         # globals()[obj] = eval(f'{module_path}.{obj}')
    #         globals()[obj] = getattr(module, obj)
    #         # curr_globals[obj] = getattr(module, obj)
    #     # sys.modules[dotted_path] = module
    #     logger.info(f'Added module to globals: `{module} - {class_name}`: {globals().keys()}`')
    try:
        return getattr(module, class_name)
    except AttributeError as e:
        return module


def spawn_new_task_worker(
    worker_name: Optional[str] = None,
    worker_imports: Optional[Union[str, List[str]]] = None,
    worker_cls: Optional[str] = None,
    worker_class: Optional[Type['TaskWorker']] = None,
    worker_config: Optional[Dict[str, Any]] = None,
    worker_queues: Optional[Union[str, List[str]]] = None,
    
    worker_functions: Optional[List['TaskFunction']] = None,
    worker_cron_jobs: Optional[List['CronJob']] = None,
    worker_startup: Optional[Union[List[Callable], Callable,]] = None,
    worker_shutdown: Optional[Union[List[Callable], Callable,]] = None,
    worker_before_process: Optional[Callable] = None,
    worker_after_process: Optional[Callable] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,

    queue_names: Optional[Union[str, List[str]]] = None,
    queue_config: Optional[Dict[str, Any]] = None,
    queue_class: Optional[Type['TaskQueue']] = None,

    max_concurrency: Optional[int] = None,
    max_broadcast_concurrency: Optional[int] = None,

    debug_enabled: Optional[bool] = False,
    task_debug_enabled: Optional[bool] = False,
    
    _is_primary: Optional[bool] = True,

    # Controls the method in which the worker is spawned
    use_new_event_loop: Optional[bool] = None,
    use_asyncio_task: Optional[bool] = False,
    disable_worker_start: Optional[bool] = False,

    **kwargs,
) -> 'TaskWorker':  # sourcery skip: low-code-quality
    """
    Spawns a new task worker

    This method allows initialization of a new task worker with a new process through
    various mechanisms.

    If `worker_cls` is specified, then the worker class is imported and instantiated
      - If the `worker_cls` is a Type[TaskWorker], then it is instantiated directly
      - If the `worker_cls` is an initialized TaskWorker, then it is used directly and configured
    
    If `worker_class` is specified, then it is instantiated directly and configured
    
    If `worker_imports` is specified, then the provided functions/modules are imported to
    initialize any registrations of tasks/cron jobs
        Example: worker_imports = ['my_module.tasks', 'my_module.tasks.init_function']

    `queue_names` are initialized prior to `worker_queues` to ensure that
    all tasks are registered before the worker starts

    """
    queue_config = queue_config or {}
    worker_config = worker_config or {}
    update_workers = []
    if worker_imports:
        if isinstance(worker_imports, str):
            worker_imports = [worker_imports]
        if (debug_enabled or task_debug_enabled) and _is_primary:
            logger.info(f'Importing worker imports: `|g|{worker_imports}|e|`', prefix = worker_name, colored = True)
        for worker_import in worker_imports:
            module_or_func = lazy_worker_import(worker_import)
            if callable(module_or_func) or isinstance(module_or_func, type):
                module_or_func = module_or_func()
            if hasattr(module_or_func, 'get_worker_config'):
                if config := module_or_func.get_worker_config():
                    worker_config.update(config)
            if hasattr(module_or_func, 'get_queue_config'):
                if config := module_or_func.get_queue_config():
                    queue_config.update(config)
            if hasattr(module_or_func, 'set_task_worker'):
                # logger.warning(f'Updating worker: `{module_or_func}`', prefix = worker_name)
                update_workers.append(module_or_func)
            # else:
            #     logger.warning(f'No set_task_worker method found for worker: `{module_or_func}`', prefix = worker_name)
    
    if max_broadcast_concurrency:
        if 'max_broadcast_concurrency' not in queue_config: queue_config['max_broadcast_concurrency'] = max_broadcast_concurrency
        if 'max_broadcast_concurrency' not in worker_config: worker_config['max_broadcast_concurrency'] = max_broadcast_concurrency
    
    if max_concurrency:
        if 'max_concurrency' not in queue_config: queue_config['max_concurrency'] = max_concurrency
        if 'max_concurrency' not in worker_config: worker_config['max_concurrency'] = max_concurrency
    
    if queue_class: 
        if isinstance(queue_class, str):
            queue_class = lazy_worker_import(queue_class)
        queue_config['task_queue_class'] = queue_class
    if 'debug_enabled' not in worker_config: worker_config['debug_enabled'] = debug_enabled or task_debug_enabled
    if 'debug_enabled' not in queue_config: queue_config['debug_enabled'] = debug_enabled or task_debug_enabled
    if _is_primary:
        worker_attributes = worker_attributes or {}
        worker_attributes['is_primary_index'] = _is_primary
    worker_config.update(
        {
            'functions': worker_functions,
            'cron_jobs': worker_cron_jobs,
            'startup': worker_startup,
            'shutdown': worker_shutdown,
            'before_process': worker_before_process,
            'after_process': worker_after_process,
            'worker_attributes': worker_attributes,
        }
    )
    worker_config = {k: v for k, v in worker_config.items() if v is not None}
    from .main import TaskManager
    # We initialize the queues so that they register the tasks
    if queue_names:
        task_queues = TaskManager.get_worker_queues(
            queues = queue_names, 
            task_queue_class = queue_class,
            disable_lock = True,
            **queue_config,
        )
    if worker_class and isinstance(worker_class, str):
        worker_class = lazy_worker_import(worker_class)
    task_worker = TaskManager.get_task_worker_from_import(
        worker_name = worker_name,
        worker_cls = worker_cls,
        worker_config = worker_config,
        queues = worker_queues or queue_names,
        task_worker_class = worker_class,
        queue_kwargs = queue_config,
        disable_lock = True,
        **kwargs,
    )
    register_worker_process(worker_name, task_worker = task_worker)
    if update_workers:
        # logger.warning(f'Updating worker: `{task_worker.worker_name}`', prefix = worker_name)
        for update_worker in update_workers:
            update_worker.set_task_worker(task_worker)
    
    if disable_worker_start: return task_worker

    # if debug_enabled:
    # logger.info(f'Spawning worker: `{task_worker.worker_name}`')
    if use_new_event_loop is None: use_new_event_loop = not use_asyncio_task
    if use_asyncio_task:
        if use_new_event_loop:
            loop = asyncio.new_event_loop()
            task = loop.create_task(task_worker.start())
            register_worker_process(worker_name, task = task, loop = loop)
        else:
            task = asyncio.create_task(task_worker.start())
            register_worker_process(worker_name, task = task)
    else:
        loop = asyncio.new_event_loop() if use_new_event_loop else asyncio.get_event_loop()
        loop.run_until_complete(task_worker.start())
    return task_worker

@functools.lru_cache(maxsize=1)
def get_worker_start_index() -> int:
    """
    Gets the worker start index
    """
    from lazyops.utils.system import is_in_kubernetes, get_host_name
    if is_in_kubernetes() and get_host_name()[-1].isdigit():
        return int(get_host_name()[-1])
    return 0

def create_worker_names(
    worker_name: Optional[str] = 'global',
    worker_name_sep: Optional[str] = '-',
    num_workers: Optional[int] = 1,
    start_index: Optional[int] = None,
    disable_env_name: Optional[bool] = False,
) -> List[str]:
    """
    Creates worker names based on the provided parameters
    """
    if num_workers is None: num_workers = 1
    if start_index is None: 
        start_index = get_worker_start_index() * num_workers
    if worker_name is None: worker_name = 'global'
    if worker_name_sep is None: worker_name_sep = '-'
    if not disable_env_name:
        worker_name = f'{worker_name}{worker_name_sep}{app_env.name}'
    return [f'{worker_name}{worker_name_sep}{i+start_index}' for i in range(num_workers)]

@overload
def start_task_workers_with_mp(
    num_workers: Optional[int] = 1,
    start_index: Optional[int] = None,

    worker_name: Optional[str] = 'global',
    worker_name_sep: Optional[str] = '-',

    worker_imports: Optional[Union[str, List[str]]] = None,
    worker_cls: Optional[str] = None,
    worker_class: Optional[Type['TaskWorker']] = None,
    worker_config: Optional[Dict[str, Any]] = None,
    worker_queues: Optional[Union[str, List[str]]] = None,
    
    worker_functions: Optional[List['TaskFunction']] = None,
    worker_cron_jobs: Optional[List['CronJob']] = None,
    worker_startup: Optional[Union[List[Callable], Callable,]] = None,
    worker_shutdown: Optional[Union[List[Callable], Callable,]] = None,
    worker_before_process: Optional[Callable] = None,
    worker_after_process: Optional[Callable] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,

    queue_names: Optional[Union[str, List[str]]] = None,
    queue_config: Optional[Dict[str, Any]] = None,
    queue_class: Optional[Type['TaskQueue']] = None,

    max_concurrency: Optional[int] = None,
    max_broadcast_concurrency: Optional[int] = None,

    debug_enabled: Optional[bool] = False,
    task_debug_enabled: Optional[bool] = False,
    use_new_event_loop: Optional[bool] = True,
    disable_env_name: Optional[bool] = False,

    terminate_timeout: Optional[float] = 5.0,
    **kwargs,
) -> Dict[str, Dict[str, Union[mp.Process, 'TaskWorker']]]:
    """
    Starts multiple task workers using multiprocessing

    This method allows initialization of multiple task workers with new processes through
    various mechanisms.

    - `num_workers` specifies the number of workers to start
    - `start_index` specifies the starting index for the worker names
    - `worker_name` specifies the worker name prefix
    - `worker_name_sep` specifies the worker name separator

    If `worker_cls` is specified, then the worker class is imported and instantiated
      - If the `worker_cls` is a Type[TaskWorker], then it is instantiated directly
      - If the `worker_cls` is an initialized TaskWorker, then it is used directly and configured
    
    If `worker_imports` is specified, then the provided functions/modules are imported to
    initialize any registrations of tasks/cron jobs
        Example: worker_imports = ['my_module.tasks', 'my_module.tasks.init_function']

    `queue_names` are initialized prior to `worker_queues` to ensure that
    all tasks are registered before the worker starts
    """
    ...

    

def start_task_workers_with_mp(
    num_workers: Optional[int] = 1,
    start_index: Optional[int] = None,
    worker_name: Optional[str] = 'global',
    worker_name_sep: Optional[str] = '-',
    disable_env_name: Optional[bool] = False,

    terminate_timeout: Optional[float] = 5.0,
    **kwargs,
) -> Dict[str, Dict[str, Union[mp.Process, 'TaskWorker']]]:
    """
    Starts multiple task workers using multiprocessing

    This method allows initialization of multiple task workers with new processes through
    various mechanisms.
    """

    global _WorkerExitRegistered
    worker_names = create_worker_names(
        worker_name = worker_name,
        worker_name_sep = worker_name_sep,
        num_workers = num_workers,
        start_index = start_index,
        disable_env_name = disable_env_name,
    )
    for n, name in enumerate(worker_names):
        process = mp.Process(
            target = spawn_new_task_worker,
            kwargs = {
                'worker_name': name,
                '_is_primary': n == 0,
                **kwargs,
            }
        )
        process.start()
        register_worker_process(name, process = process)
    if not _WorkerExitRegistered:
        atexit.register(exit_task_workers, terminate_timeout)
        _WorkerExitRegistered = True
    return {name: _WorkerProcesses[name] for name in worker_names}


@overload
def astart_task_workers_with_tasks(
    num_workers: Optional[int] = 1,
    start_index: Optional[int] = None,

    worker_name: Optional[str] = 'global',
    worker_name_sep: Optional[str] = '-',

    worker_imports: Optional[Union[str, List[str]]] = None,
    worker_cls: Optional[str] = None,
    worker_class: Optional[Type['TaskWorker']] = None,
    worker_config: Optional[Dict[str, Any]] = None,
    worker_queues: Optional[Union[str, List[str]]] = None,
    
    worker_functions: Optional[List['TaskFunction']] = None,
    worker_cron_jobs: Optional[List['CronJob']] = None,
    worker_startup: Optional[Union[List[Callable], Callable,]] = None,
    worker_shutdown: Optional[Union[List[Callable], Callable,]] = None,
    worker_before_process: Optional[Callable] = None,
    worker_after_process: Optional[Callable] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,

    queue_names: Optional[Union[str, List[str]]] = None,
    queue_config: Optional[Dict[str, Any]] = None,
    queue_class: Optional[Type['TaskQueue']] = None,

    max_concurrency: Optional[int] = None,
    max_broadcast_concurrency: Optional[int] = None,

    disable_env_name: Optional[bool] = False,
    debug_enabled: Optional[bool] = False,
    task_debug_enabled: Optional[bool] = False,
    use_new_event_loop: Optional[bool] = False,

    terminate_timeout: Optional[float] = 5.0,
    **kwargs,
) -> Dict[str, Dict[str, Union[asyncio.Task, 'TaskWorker']]]:
    """
    Starts multiple task workers using multiprocessing

    This method allows initialization of multiple task workers with new processes through
    various mechanisms.

    - `num_workers` specifies the number of workers to start
    - `start_index` specifies the starting index for the worker names
    - `worker_name` specifies the worker name prefix
    - `worker_name_sep` specifies the worker name separator

    If `worker_cls` is specified, then the worker class is imported and instantiated
      - If the `worker_cls` is a Type[TaskWorker], then it is instantiated directly
      - If the `worker_cls` is an initialized TaskWorker, then it is used directly and configured
    
    If `worker_imports` is specified, then the provided functions/modules are imported to
    initialize any registrations of tasks/cron jobs
        Example: worker_imports = ['my_module.tasks', 'my_module.tasks.init_function']

    `queue_names` are initialized prior to `worker_queues` to ensure that
    all tasks are registered before the worker starts
    """
    ...

    
async def astart_task_workers_with_tasks(
    num_workers: Optional[int] = 1,
    start_index: Optional[int] = None,
    worker_name: Optional[str] = 'global',
    worker_name_sep: Optional[str] = '-',
    disable_env_name: Optional[bool] = False,

    terminate_timeout: Optional[float] = 5.0,
    use_new_event_loop: Optional[bool] = False,
    **kwargs,
) -> Dict[str, Dict[str, Union[asyncio.Task, 'TaskWorker']]]:
    """
    Starts multiple task workers using asyncio.tasks

    This method allows initialization of multiple task workers with new processes through
    various mechanisms.
    """
    global _WorkerExitRegistered
    worker_names = create_worker_names(
        worker_name = worker_name,
        worker_name_sep = worker_name_sep,
        num_workers = num_workers,
        start_index = start_index,
        disable_env_name = disable_env_name,
    )
    for n, name in enumerate(worker_names):
        task_worker = spawn_new_task_worker(
            worker_name = name,
            _is_primary = n == 0,
            use_asyncio_task = True,
            use_new_event_loop = use_new_event_loop,
            **kwargs,
        )
    if not _WorkerExitRegistered:
        atexit.register(exit_task_workers, terminate_timeout)
        _WorkerExitRegistered = True
    return {name: _WorkerProcesses[name] for name in worker_names}

def start_task_workers_with_tasks(
    num_workers: Optional[int] = 1,
    start_index: Optional[int] = None,
    worker_name: Optional[str] = 'global',
    worker_name_sep: Optional[str] = '-',
    disable_env_name: Optional[bool] = False,

    terminate_timeout: Optional[float] = 5.0,
    use_new_event_loop: Optional[bool] = None,
    **kwargs,
) -> Dict[str, Dict[str, Union[asyncio.Task, 'TaskWorker']]]:
    """
    Wrapper for astart_task_workers_with_tasks that spawns the task workers in a separate process
    Starts multiple task workers using asyncio.tasks

    This method allows initialization of multiple task workers with new processes through
    various mechanisms.
    """
    # Determine if there is a running event loop
    with contextlib.suppress(Exception):
        if asyncio.get_running_loop().is_running():
            asyncio.get_running_loop().create_task(
                astart_task_workers_with_tasks(
                    num_workers = num_workers,
                    start_index = start_index,
                    worker_name = worker_name,
                    worker_name_sep = worker_name_sep,
                    disable_env_name = disable_env_name,
                    terminate_timeout = terminate_timeout,
                    use_new_event_loop = use_new_event_loop,
                    **kwargs,
                )
            )
            return _WorkerProcesses

    # Start the task workers in a separate process
    return start_task_workers_with_mp(
        num_workers = num_workers,
        start_index = start_index,
        worker_name = worker_name,
        worker_name_sep = worker_name_sep,
        disable_env_name = disable_env_name,
        terminate_timeout = terminate_timeout,
        use_new_event_loop = use_new_event_loop,
        **kwargs,
    )



@overload
def start_task_workers(
    num_workers: Optional[int] = 1,
    start_index: Optional[int] = None,

    worker_name: Optional[str] = 'global',
    worker_name_sep: Optional[str] = '-',

    worker_imports: Optional[Union[str, List[str]]] = None,
    worker_cls: Optional[str] = None,
    worker_class: Optional[Type['TaskWorker']] = None,
    worker_config: Optional[Dict[str, Any]] = None,
    worker_queues: Optional[Union[str, List[str]]] = None,
    
    worker_functions: Optional[List['TaskFunction']] = None,
    worker_cron_jobs: Optional[List['CronJob']] = None,
    worker_startup: Optional[Union[List[Callable], Callable,]] = None,
    worker_shutdown: Optional[Union[List[Callable], Callable,]] = None,
    worker_before_process: Optional[Callable] = None,
    worker_after_process: Optional[Callable] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,

    queue_names: Optional[Union[str, List[str]]] = None,
    queue_config: Optional[Dict[str, Any]] = None,
    queue_class: Optional[Type['TaskQueue']] = None,

    max_concurrency: Optional[int] = None,
    max_broadcast_concurrency: Optional[int] = None,

    disable_env_name: Optional[bool] = False,
    debug_enabled: Optional[bool] = False,
    task_debug_enabled: Optional[bool] = False,
    method: Optional[str] = 'mp',
    use_new_event_loop: Optional[bool] = None,
    disable_worker_start: Optional[bool] = False,
    terminate_timeout: Optional[float] = 5.0,
    **kwargs,
) -> Union[Dict[str, Dict[str, Union[mp.Process, asyncio.Task, 'TaskWorker']]], List['TaskWorker']]:
    """
    Starts multiple task workers using either multiprocessing or asyncio.tasks

    Method can be either `Multiprocessing` (`mp`, `process`) or `asyncio.Task` (`tasks`, `asyncio`)

    If `disable_worker_start` is True, then the workers are initialized but not started and 
    the worker objects are returned

    This method allows initialization of multiple task workers with new processes through
    various mechanisms.

    - `num_workers` specifies the number of workers to start
    - `start_index` specifies the starting index for the worker names
    - `worker_name` specifies the worker name prefix
    - `worker_name_sep` specifies the worker name separator

    If `worker_cls` is specified, then the worker class is imported and instantiated
      - If the `worker_cls` is a Type[TaskWorker], then it is instantiated directly
      - If the `worker_cls` is an initialized TaskWorker, then it is used directly and configured
    
    If `worker_imports` is specified, then the provided functions/modules are imported to
    initialize any registrations of tasks/cron jobs
        Example: worker_imports = ['my_module.tasks', 'my_module.tasks.init_function']

    `queue_names` are initialized prior to `worker_queues` to ensure that
    all tasks are registered before the worker starts
    """
    ...


def start_task_workers(
    num_workers: Optional[int] = 1,
    start_index: Optional[int] = None,

    worker_name: Optional[str] = 'global',
    worker_name_sep: Optional[str] = '-',
    method: Optional[str] = 'mp',
    use_new_event_loop: Optional[bool] = None,
    disable_worker_start: Optional[bool] = False,
    disable_env_name: Optional[bool] = False,
    terminate_timeout: Optional[float] = 5.0,
    **kwargs,
) -> Union[Dict[str, Dict[str, Union[mp.Process, asyncio.Task, 'TaskWorker']]], List['TaskWorker']]:
    """
    Starts multiple task workers using either multiprocessing or asyncio.tasks
    """

    if not disable_worker_start:
        if method in ['mp', 'process']:
            return start_task_workers_with_mp(
                num_workers = num_workers,
                start_index = start_index,
                worker_name = worker_name,
                worker_name_sep = worker_name_sep,
                disable_env_name = disable_env_name,
                terminate_timeout = terminate_timeout,
                **kwargs,
            )
        elif method in ['task', 'tasks', 'asyncio']:
            return start_task_workers_with_tasks(
                num_workers = num_workers,
                start_index = start_index,
                worker_name = worker_name,
                worker_name_sep = worker_name_sep,
                disable_env_name = disable_env_name,
                use_new_event_loop = use_new_event_loop,
                terminate_timeout = terminate_timeout,
                **kwargs,
            )
        raise ValueError(f'Invalid method: `{method}`')
    
    worker_names = create_worker_names(
        worker_name = worker_name,
        worker_name_sep = worker_name_sep,
        num_workers = num_workers,
        start_index = start_index,
        disable_env_name = disable_env_name,
    )
    task_workers: List['TaskWorker'] = []
    for n, name in enumerate(worker_names):
        task_worker = spawn_new_task_worker(
            worker_name = name,
            _is_primary = n == 0,
            use_new_event_loop = use_new_event_loop,
            disable_worker_start = disable_worker_start,
            **kwargs,
        )
        task_workers.append(task_worker)
    return task_workers






