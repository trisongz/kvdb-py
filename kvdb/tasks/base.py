from __future__ import annotations

"""
A Base Task Worker with Common Methods
for convenience and readily subclassible
"""

from .abstract import TaskABC, logger
from typing import Callable, List, Optional, Type, Any, Dict, Union, TypeVar, Iterable, Awaitable, Set, Tuple, TYPE_CHECKING


if TYPE_CHECKING:
    
    from kvdb.types.jobs import CronJob, Job
    from kvdb.components.session import KVDBSession
    from .tasks import TaskFunction, Ctx
    from .worker import TaskWorker
    from lazyops.utils.logs import Logger
    from lazyops.libs.abcs.configs.base import AppSettings 

    TaskWorkerT = TypeVar('TaskWorkerT', bound = 'BaseTaskWorker')


RT = TypeVar('RT')


class BaseTaskWorker(TaskABC):
    """
    A Base Task Worker with Common Methods
    for convenience and readily subclassible

    The following the methods are designed to be subclassed

    Configuration:
    -------------
    - get_queue_config: Configures the Queue for the Worker. See `kvdb.tasks.queue.TaskQueue` for more parameters
    - get_worker_config: Configures the Worker for the Worker. See `kvdb.tasks.worker.TaskWorker` for more parameters
    - get_queue_name: Returns the Queue Name for the Worker
    - get_base_task_list: Returns the Base Task List
    - get_base_cronjob_list: Returns the Base Cronjob List

    Validation:
    -------------
    - validate_cronjob: Validates the Cronjob. Returns the Cronjob Configuration Kwargs
    - validate_function: Validates the Function. Returns the Function Configuration Kwargs

    Properties:
    -------------
    - worker_key

    Event Phases:
    -------------

    Startup:
    - cls_setup_init
    - cls_task_init
    - cls_startup_init
    - cls_shutdown_exit

    - pre_task_init
    - post_task_init
    - finalize_task_init
    - pre_startup_init
    - post_startup_init
    - finalize_startup_init

    Shutdown:
    - pre_shutdown_exit
    - post_shutdown_exit
    - finalize_shutdown_exit
    """
    name: Optional[str] = 'worker'
    kind: Optional[str] = 'svc'


    enabled: Optional[bool] = True
    cronjobs_enabled: Optional[bool] = True
    callbacks_enabled: Optional[bool] = True
    timeout: Optional[int] = 1800

    cron_schedules: Optional[Dict[str, Union[Any, 'CronJob']]] = {}
    cron_kwargs: Optional[Dict[str, Dict[str, Any]]] = {}

    worker_timeout: Optional[int] = 1800
    cron_configurations: Optional[Dict[str, Any]] = {}

    fallback_enabled: Optional[bool] = None # Fallback to executing the task locally if the queue is not available

    _worker_key: Optional[str] = None


    def __init_subclass__(cls, **kwargs):
        """
        Called when a subclass is created
        """
        super().__init_subclass__(**kwargs)
        from .main import TaskManager
        TaskManager.register_abc(cls_or_func=cls.run_task_init, phase = 'startup', set_ctx = True)
        TaskManager.register_abc(cls_or_func=cls.run_startup_init, phase = 'startup')
        TaskManager.register_abc(cls_or_func=cls.run_shutdown_exit, phase = 'shutdown')


    def cls_setup_init(self, *args, **kwargs):
        """
        Initialize and Setup Worker Component. This is designed to be subclassed.
        """
        pass

    def cls_pre_init(self, *args, **kwargs):
        """
        Initialize the Worker Component
        """
        from lazyops.libs.pooler import ThreadPooler
        self._kdb: Optional['KVDBSession'] = None

        self.pooler = ThreadPooler
        self.excluded_tasks: List[str] = []
        self.task_worker: Optional['TaskWorker'] = None
        self.registered_functions: Dict[str, 'TaskFunction'] = {}
        self.settings: Optional['AppSettings'] = None
        self.cls_setup_init(*args, **kwargs)
        if self.settings and hasattr(self.settings, 'module_name'):
            self.worker_module_name = self.settings.module_name
        else:
            self.worker_module_name: str = self.__class__.__module__.split(".")[0]
        self.configure(**kwargs)

    @property
    def is_primary_task_worker(self) -> bool:
        """
        Returns True if the Worker is the Primary Task Worker

        This is True for the first task worker within a node
        """
        if self.task_worker is None: return False
        return self.task_worker.is_primary_worker
    
    @property
    def is_main_task_worker(self) -> bool:
        """
        Returns True if the Worker is the Main Task Worker

        This is True for the first task worker within the primary node. 

        Should only be true for one worker
        """
        if self.task_worker is None: return False
        return self.is_primary_task_worker and self.task_worker.is_leader_process

    def set_task_worker(self, task_worker: 'TaskWorker') -> None:
        """
        Sets the Task Worker
        """
        self.task_worker = task_worker
        # self.logger.warning(f'Setting Task Worker: |g|{task_worker}|e|', colored = True, prefix = self.worker_key)
    
    def configure(self, **kwargs) -> None:
        """
        Configures the worker
        """
        self.configure_base_tasks(**kwargs)
        self.configure_base_cronjobs(**kwargs)

    def configure_base_tasks(
        self,
        excluded: Optional[List[str]] = None,
        **kwargs,
    ):
        """
        Register the Base Tasks
        """
        if excluded:
            self.excluded_tasks.extend(excluded)
            self.excluded_tasks = list(set(self.excluded_tasks))
    
    def configure_base_cronjobs(
        self,
        excluded: Optional[List[str]] = None,
        cron_schedules: Optional[Dict[str, Union[str, List, Dict]]] = None,
        cron_kwargs: Optional[Dict[str, Any]] = None,
        worker_timeout: Optional[int] = None,
        **kwargs,
    ):
        """
        Register the Base Cronjobs
        """
        if excluded:
            self.excluded_tasks.extend(excluded)
            self.excluded_tasks = list(set(self.excluded_tasks))
        if cron_schedules: self.cron_configurations.update(cron_schedules)
        if worker_timeout: self.worker_timeout = worker_timeout
        if cron_kwargs: self.cron_kwargs.update(cron_kwargs)
        

    async def cls_task_init(self, *args, **kwargs) -> None:
        """
        Class Init
        """
        self.logger.info(f'CronJobs: |g|{self.cronjobs_enabled}|e|, Callbacks: |g|{self.callbacks_enabled}|e|', colored = True, prefix = self.worker_key)
    
    async def pre_task_init(self, ctx: 'Ctx', *args, **kwargs) -> 'Ctx':
        """
        Pre init
        """
        pass

    async def post_task_init(self, ctx: 'Ctx', *args, **kwargs) -> 'Ctx':
        """
        Post init
        """
        pass

    async def finalize_task_init(self, ctx: 'Ctx', *args, **kwargs) -> 'Ctx':
        """
        Finalize init
        """
        pass

    # @TaskManager.register_abc(phase = 'startup', set_ctx = True)
    async def run_task_init(self, ctx: 'Ctx', *args, **kwargs) -> 'Ctx':
        """
        Runs the init
        """
        await self.cls_task_init(*args, **kwargs)
        ctx = await self.pre_task_init(ctx, *args, **kwargs)
        ctx = await self.post_task_init(ctx, *args, **kwargs)
        ctx = await self.finalize_task_init(ctx, *args, **kwargs)
        return ctx

    async def cls_startup_init(self, **kwargs) -> None:
        """
        Class Startup Init
        """
        pass
    
    async def pre_startup_init(self, **kwargs) -> None:
        """
        Pre Startup init
        """
        pass

    async def post_startup_init(self, **kwargs) -> None:
        """
        Post Startup init
        """
        pass

    async def finalize_startup_init(self, **kwargs) -> None:
        """
        Finalize Startup init
        """
        pass

    # @TaskManager.register_abc(phase = 'startup')
    async def run_startup_init(self, **kwargs) -> None:
        """
        Runs the startup init
        """
        await self.cls_startup_init(**kwargs)
        await self.pre_startup_init(**kwargs)
        await self.post_startup_init(**kwargs)
        await self.finalize_startup_init(**kwargs)
    

    async def cls_shutdown_exit(self, **kwargs) -> None:
        """
        Class Shutdown Exit
        """
        pass
    
    async def pre_shutdown_exit(self, **kwargs) -> None:
        """
        Pre Shutdown Exit
        """
        pass

    async def post_shutdown_exit(self, **kwargs) -> None:
        """
        Post Shutdown Exit
        """
        pass

    async def finalize_shutdown_exit(self, **kwargs) -> None:
        """
        Finalize Shutdown Exit
        """
        pass


    def get_queue_config(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Gets the queue config
        """
        return {
            'queue_log_name': f'{self.worker_module_name}.tasks',
            'serializer': 'pickle',
            'max_concurrency': 50,
        }
    

    def get_worker_config(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Get the worker config
        """
        return {
            'max_concurrency': 50,
        }

    def get_queue_name(self, *args, **kwargs) -> str:
        """
        Gets the queue name
        """
        if self.settings is not None and hasattr(self.settings, 'app_env'):
            return f'{self.worker_module_name}.{self.settings.app_env.name}.tasks'
        return f'{self.worker_module_name}.tasks'
    

    # @TaskManager.register_abc(phase = 'shutdown')
    async def run_shutdown_exit(self, **kwargs) -> None:
        """
        Runs the Shutdown Exit
        """
        await self.cls_shutdown_exit(**kwargs)
        await self.pre_shutdown_exit(**kwargs)
        await self.post_shutdown_exit(**kwargs)
        await self.finalize_shutdown_exit(**kwargs)
    
    def get_base_task_list(self) -> List[str]:
        """
        Gets the Base Task List
        """
        return []
    
    def get_base_cronjob_list(self) -> List[str]:
        """
        Gets the Base Cronjob List
        """
        return []

    def validate_cronjob(
        self,
        func: Union[str, Callable],
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Validates the Cronjob
        """
        # self.autologger.info(f'Validating Cronjob: |y|{func}|e| {kwargs}', colored = True)
        if not self.cronjobs_enabled: return None
        if func in self.excluded_tasks: return None
        cronjob_list = self.get_base_cronjob_list()
        if not cronjob_list or func not in cronjob_list: return None
        base_kwargs = self.cron_kwargs.get(func, {})
        if kwargs: base_kwargs.update(kwargs)
        default_kwargs = base_kwargs.get(func, kwargs.get('default_kwargs', {}))
        if 'timeout' not in default_kwargs: default_kwargs['timeout'] = self.worker_timeout
        schedule = self.cron_configurations.get(func, 'every 10 minutes')
        base_kwargs['default_kwargs'] = default_kwargs
        base_kwargs['cron'] = schedule
        return base_kwargs
    

    def validate_function(
        self,
        func: Union[str, Callable],
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Validates the Function
        """
        # self.autologger.info(f'Validating Function: |y|{func}|e|', colored = True)
        if func in self.excluded_tasks: return None
        function_list = self.get_base_task_list()
        if self.fallback_enabled and 'fallback_enabled' not in kwargs: 
            kwargs['fallback_enabled'] = True
        if not function_list: return kwargs
        function_list.extend([
            'run_task_init',
            'run_startup_init',
            'run_shutdown_exit'
        ])
        return None if func not in function_list else kwargs
    

    def set_registered_function(
        self,
        func: 'TaskFunction',
        **kwargs,
    ):
        """
        Sets the registered function
        """
        self.registered_functions[func.name] = func
        if func.is_cronjob: self.cron_schedules[func.name] = func.cronjob


    @property
    def logger(self) -> 'Logger':
        """
        Gets the logger
        """
        return logger if self.settings is None else self.settings.logger
    
    @property
    def null_logger(self) -> 'Logger':
        """
        Gets the null logger
        """
        return logger if self.settings is None else self.settings.null_logger

    @property
    def autologger(self) -> 'Logger':
        """
        Automatic Logger that is enabled in devel mode
        """
        return logger if self.settings is None else self.settings.autologger
    

    @property
    def worker_key(self) -> str:
        """
        Returns the service key for the job
        Each service has a unique key

        ex: 
          - {module_name}.{app_env}.{kind}.{name}
        """
        if self._worker_key is None:
            key = self.worker_module_name
            if self.settings is not None and hasattr(self.settings, 'app_env'):
                key += f'.{self.settings.app_env.name}'
            key += f'.{self.kind}.{self.name}'
            self._worker_key = key
        return self._worker_key
    
    @property
    def kdb(self) -> 'KVDBSession':
        """
        Gets the KVDB Session
        """
        if self._kdb is None:
            import kvdb
            self._kdb = kvdb.KVDBClient.get_session(name = self.name, serializer = 'json')
        return self._kdb


    def get_function_name(self, func: Union[str, Callable]) -> str:
        """
        Returns the function name
        """
        return f'{self.worker_key}:{(func.__name__ if callable(func) else func)}'
    
    def get_cronjob_key(self, func: Union[str, Callable]) -> str:
        """
        Returns the cronjob key for the unique key
        """
        return f'task:{self.get_function_name(func)}'

    def get_job_key(self, job_id: str, *keys: Iterable[Any]) -> str:
        """
        Returns the job key for the ServiceJob
        """
        keys = [str(key) for key in keys]
        return f'{job_id}:{":".join(keys)}'
    

    def get_next_cron_run(
        self,
        func: Union[Callable, str],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Gets the next cron run data
        """
        func_name = self.get_function_name(func)
        cron = self.cron_schedules.get(func_name)
        if cron is None:
            raise ValueError(f'No Cron Schedule found for |g|{func_name}|e|')
        return cron.get_next_cron_run_data(**kwargs)
        
    
    def __call__(
        self,
        func: Union[str, Callable[..., RT]],
        *args,
        blocking: Optional[bool] = False,
        **kwargs,
    ) -> Awaitable[Union['Job', RT]]:
        """
        Calls the function
        """
        method = self.queue.apply if blocking else self.queue.enqueue
        return method(
            self.get_function_name(func),
            *args,
            **kwargs,
        )
    
    def enqueue(
        self,
        func: Union[str, Callable[..., RT]],
        *args,
        **kwargs,
    ) -> Awaitable['Job']:
        """
        Enqueues the function
        """
        return self.queue.enqueue(
            self.get_function_name(func),
            *args,
            **kwargs,
        )
    
    def apply(
        self,
        func: Union[str, Callable[..., RT]],
        *args,
        **kwargs,
    ) -> Awaitable[RT]:
        """
        Applies the function
        """
        return self.queue.apply(
            self.get_function_name(func),
            *args,
            **kwargs,
        )
    

    async def retrieve_job(
        self,
        request_id: Optional[str] = None,
        job_id: Optional[str] = None,
        job: Optional[Job] = None,
        blocking: Optional[bool] = None,
        raise_error: Optional[bool] = False,
        **kwargs,
    ) -> Optional[Tuple[Optional[Job], str]]:
        """
        Retrieves a job

        Returns a tuple of: [job, job_id]
        """
        job_id = job_id or request_id or job.id
        if job is None: job = await self.queue.job(job_id, raise_error = raise_error)
        if job and blocking: job = await self.queue.wait_for_job(job, return_result = False)
        return (job, job_id)
    

    async def retrieve_job_if_exists(
        self,
        request_id: Optional[str] = None,
        raise_error: Optional[bool] = False,
    ) -> Optional[Job]:
        """
        Retrieves the Job if it exists
        """
        if request_id is None: return None
        return await self.queue.job(request_id, raise_error = raise_error)

