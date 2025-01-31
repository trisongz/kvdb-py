from __future__ import annotations

"""
KVDB Task CLI
"""
import os
import json
import typer
import time
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Callable, Awaitable, List, Union, Type, AsyncGenerator, Iterable, Tuple, Literal, TYPE_CHECKING, overload


cmd = typer.Typer(
   name = "KVDB Task CLI",
   help = "Invoke KVDB Tasks",
   invoke_without_command = True,
)

@cmd.command()
def start(
    worker_name: Optional[str] = typer.Argument(None, help = "Worker name"),

    num_workers: Optional[int] = typer.Option(1, '-n', help = "Number of workers"),
    start_index: Optional[int] = typer.Option(None, help = "Start index"),

    worker_name_sep: Optional[str] = typer.Option('-', help = "Worker name separator"),
    worker_imports: Optional[List[str]] = typer.Option(None, '-i', help = "Worker imports"),
    worker_cls: Optional[str] = typer.Option(None, help = "Worker Module to Import"),
    worker_class: Optional[str] = typer.Option(None, help = "TaskWorker Class to instantiate the worker from"),
    worker_config: Optional[str] = typer.Option(None, '-wc', help = "Worker config. Can be a JSON string, path to a JSON file, or a module path"),
    worker_queues: Optional[List[str]] = typer.Option(None, '-wq', help = "Worker queues"),
    worker_attributes: Optional[List[str]] = typer.Option(None, '-a', help = "Worker attributes. Should be in the form of key=value"),

    queue_names: Optional[List[str]] = typer.Option(None, '-q', help = "Queue names"),
    queue_config: Optional[str] = typer.Option(None, '-qc', help = "Queue config. Can be a JSON string, path to a JSON file, or a module path"),
    queue_class: Optional[str] = typer.Option(None, help = "TaskQueue Class to instantiate the queue from"),

    max_concurrency: Optional[int] = typer.Option(None, help = "Max concurrency"),
    max_broadcast_concurrency: Optional[int] = typer.Option(None, help = "Max broadcast concurrency"),

    disable_env_name: Optional[bool] = typer.Option(False, help = "Disable env name"),
    debug_enabled: Optional[bool] = typer.Option(False, '--debug', help = "Debug enabled"),
    task_debug_enabled: Optional[bool] = typer.Option(False, '--tdebug', help = "Task debug enabled"),
    method: Optional[str] = typer.Option('mp', help = "Method to use to start the worker. Can be mp, tasks, or asyncio"),
    use_new_event_loop: Optional[bool] = typer.Option(None, help = "Use new event loop"),
    terminate_timeout: Optional[float] = typer.Option(5.0, help = "Terminate timeout"),
):  # sourcery skip: low-code-quality
    """
    Starts a task worker group
    """
    if debug_enabled:
        os.environ['KVDB_DEBUG'] = 'True'
    if task_debug_enabled:
        os.environ['KVDB_TASK_DEBUG'] = 'True'
    kwargs = locals()
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    from kvdb.utils.logs import logger
    from lzo.utils.helpers import build_dict_from_list, build_dict_from_str
    # from lazyops.utils.helpers import build_dict_from_list, build_dict_from_str
    from kvdb.tasks.spawn import start_task_workers, lazy_worker_import

    if worker_config:
        if '{' in worker_config or '[' in worker_config:
            worker_config = build_dict_from_str(worker_config)
        elif '.json' in worker_config:
            worker_config = json.loads(Path(worker_config).read_text())
        else:
            worker_config = lazy_worker_import(worker_config)
        kwargs['worker_config'] = worker_config
    
    if queue_config:
        if '{' in queue_config or '[' in queue_config:
            queue_config = build_dict_from_str(queue_config)
        elif '.json' in queue_config:
            queue_config = json.loads(Path(queue_config).read_text())
        else:
            queue_config = lazy_worker_import(queue_config)
        kwargs['queue_config'] = queue_config
    
    if worker_attributes:
        kwargs['worker_attributes'] = build_dict_from_list(worker_attributes)
    else:
        _ = kwargs.pop('worker_attributes', None)
    
    if 'all' in worker_queues: kwargs['worker_queues'] = 'all'
    elif not worker_queues: _ = kwargs.pop('worker_queues', None)
    if 'all' in queue_names: kwargs['queue_names'] = 'all'
    elif not queue_names: _ = kwargs.pop('queue_names', None)
    logger.info(f"Starting task workers with kwargs: {kwargs}")
    try:
        start_task_workers(**kwargs)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt. Exiting...")
        sys.exit(0)
    
    except Exception as e:
        logger.exception(e)
        sys.exit(1)


def main():
    """
    Main entrypoint
    """
    cmd()

if __name__ == "__main__":
    cmd()