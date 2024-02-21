from __future__ import annotations

"""
A Generic KVDB Worker Class that can be inherited from
"""

import abc
from kvdb.utils.logs import logger
from kvdb.utils.lazy import lazy_import
from typing import Callable, List, Optional, Type, Any, Dict, Union, TypeVar, Awaitable, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.types.jobs import CronJob
    from .tasks import TaskFunction, Ctx


RT = TypeVar('RT')


class TaskABC(abc.ABC):
    """
    An Abstract Base Class for Tasks that 
    properly registers all subclasses that inherit from it
    and implements all the necessary methods
    """

    default_queue_name: Optional[str] = None

    __task_functions__: Set[str] = set()
    __task_subclasses__: Dict[str, Type['TaskABC']] = {}
    __task_function_partials__: Dict[str, Dict[str, Any]] = {}

    __kvdb_initializers__: List[Union[str, Callable]] = []
    __kvdb_obj_id__: Optional[str] = None
    __kvdb_patched__: bool = True

    # __kvdb_cls_inits__: List[Callable] = []


    def __init_subclass__(cls, **kwargs):
        """
        Called when a subclass is created
        """
        super().__init_subclass__(**kwargs)
        cls.__kvdb_obj_id__ = cls.__get_task_obj_id__(cls)
        cls.__task_subclasses__[cls.__kvdb_obj_id__] = cls
        cls.__task_function_partials__ = cls.__task_function_partials__.get(cls.__kvdb_obj_id__, {})

        from .main import TaskManager
        TaskManager._register_abc(cls)

    @staticmethod
    def __get_task_obj_id__(cls_or_func: Union[Type['TaskABC'], Callable]) -> Union[str, Tuple[str, str]]:
        """
        Get the task object id
        """
        if isinstance(cls_or_func, type):
            return f'{cls_or_func.__module__}.{cls_or_func.__name__}'
        elif callable(cls_or_func):
            func_id = f'{cls_or_func.__module__}.{cls_or_func.__qualname__}'
            return func_id.rsplit('.', 1)
        raise ValueError(f'Invalid type {type(cls_or_func)} for cls_or_func')
    

    def get_queue_name(self, *args, **kwargs) -> str:
        """
        Get the queue name for the task
        This can be overriden by the subclass
        """
        return self.default_queue_name
    
    
    def get_worker_config(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Get the worker config
        """
        return None

    def get_queue_config(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Get the queue config
        """
        return None
    

    def get_worker_attributes(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Get the worker attributes
        """
        return None


    def cls_init(self, *args, **kwargs):
        """
        Any initialization that should be done for the class

        This is called immediately after the class is initialized
        """
        pass


    def cls_pre_init(self, *args, **kwargs):
        """
        Any initialization that should be done for the class

        This is called immediately before the class is registered
        """
        pass


    def cls_post_init(self, *args, **kwargs):
        """
        Any initialization that should be done for the class

        This is called immediately after the class is registered
        """
        pass


    def cls_finalize_init(self, *args, **kwargs):
        """
        Any initialization that should be done for the class

        This is called immediately after the class is registered
        """
        pass

    
    def register_task_class(self, *args, **kwargs):
        """
        Register the task class
        """
        pass

    def get_function_name(self, func: Callable) -> Optional[str]:
        """
        Get the function name

        This can be overriden by the subclass
        """
        return None
    
    def get_cronjob_name(self, func: Callable) -> Optional[str]:
        """
        Get the cronjob name

        This can be overriden by the subclass
        """
        return None
    
    def validate_cronjob(self, func: Callable, **kwargs) -> Dict[str, Any]:
        """
        Validate the cronjob
        """
        return kwargs
    
    def validate_function(self, func: Callable, **kwargs) -> Dict[str, Any]:
        """
        Validate the function
        """
        return kwargs
    
    def set_registered_function(self, func: Callable, **kwargs):
        """
        Set the registered function
        """
        pass

    @classmethod
    def __add_task_function_partials__(
        cls,
        func: str,
        **kwargs
    ):
        """
        Add the task function partials
        """
        if func not in cls.__task_function_partials__: cls.__task_function_partials__[func] = {}
        if kwargs: cls.__task_function_partials__[func].update(kwargs)
        # logger.info(f'[{cls.__name__}] [PARTIALS] {func} {cls.__task_function_partials__[func]}')

    def __get_task_function_partials__(
        self, 
        func: str, 
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Return the task function partials
        """
        base_partials = self.__task_function_partials__.get('cls', {})
        if func in self.__task_function_partials__ and self.__task_function_partials__[func]:
            base_partials.update(self.__task_function_partials__[func])
        # if kwargs: base_partials.update(kwargs)
        # obj_id = self.__kvdb_obj_id__
        # logger.info(f'[{obj_id}] [PARTIALS] {func} {base_partials}: {self.__task_function_partials__}: {kwargs}')
        return base_partials
        # return self.__task_function_partials__.get(func, {})
        # If it's not a nested dict, return the value
    


    def __register_abc_task_init__(self, *args, **kwargs):
        # sourcery skip: low-code-quality
        """
        Register the task class and runs the registration hook
        """
        from .main import TaskManager, autologger
        TaskManager.compile_tasks()
        queue_name = self.get_queue_name(*args, **kwargs)

        self.queue_task = TaskManager.get_queue(queue_name)
        if self.__kvdb_obj_id__ in TaskManager._task_initialized_abcs.get(self.queue_task.queue_name, []):
            # logger.warning(f'[{self.queue_task.queue_name}] Task {self.__kvdb_obj_id__} already initialized')
            return
        
        func_methods = TaskManager._task_registered_abc_functions.get(self.__kvdb_obj_id__, [])
        if not func_methods: 
            try:
                from kvdb.utils.patching import get_parent_object_class_names
                parents = get_parent_object_class_names(self.__class__)
                last_parent = parents[1]
                func_methods = TaskManager._task_registered_abc_functions[last_parent].copy()
                if not func_methods: 
                    autologger.warning(f'[{self.__kvdb_obj_id__}] No functions registered for parent {last_parent}')
                    return
                autologger.info(f'[{self.__kvdb_obj_id__}] Got functions from parent {last_parent}: {func_methods}')
                # Merge the partials from the parent
                if last_parent in TaskManager._task_unregistered_abc_partials:
                    for func in func_methods:
                        if func not in self.__task_function_partials__ and func in TaskManager._task_unregistered_abc_partials[last_parent]:
                            self.__task_function_partials__[func] = TaskManager._task_unregistered_abc_partials[last_parent].get(func, {}).copy()
                            autologger.info(f'[{self.__kvdb_obj_id__}] Merged partials from parent {last_parent} for {func}: {self.__task_function_partials__[func]}')

            except Exception as e:
                autologger.warning(f'[{self.__kvdb_obj_id__}] No functions registered for {self.__class__.__name__}: {e}')
                return

            # logger.warning(f'[{self.__kvdb_obj_id__}] No functions registered for {self.__class__.__name__}')
            # return

        # logger.info(f'[{self.queue_task.queue_name}] [ABC] {self.__kvdb_obj_id__} {func_methods}')
        for func in func_methods:
            func_kws = self.__get_task_function_partials__(func, **kwargs)
            # logger.info(f'[{self.queue_task.queue_name}] [ABC] {func} {func_kws}')
            if worker_attr := self.get_worker_attributes(func):
                func_kws['worker_attributes'] = worker_attr

            src_func = getattr(self, func)
            if 'cron' in func_kws or 'cronjob' in func_kws:
                # logger.info(f'[{self.queue_task.queue_name}] [CRON] {func} {func_kws}')
                func_kws = self.validate_cronjob(func, **func_kws)
                # if func_kws is None: 
                #     if not (func_kws := self.validate_function(func, **func_kws)):
                #         continue
                if func_kws is None: continue

                # cronjob_kws = self.validate_cronjob(func, **func_kws)
                # if cronjob_kws is None: 
                #     if not (cronjob_kws := self.validate_function(func, **func_kws)):
                #         continue
                # func_kws = cronjob_kws
                if name := self.get_cronjob_name(src_func):
                    func_kws['name'] = name
                elif name := self.get_function_name(src_func):
                    func_kws['name'] = name
            else:
                func_kws = self.validate_function(func, **func_kws)
                if func_kws is None: continue
                if name := self.get_function_name(src_func):
                    func_kws['name'] = name

            if 'name' not in func_kws:
                func_kws['name'] = f'{self.__class__.__name__}.{func}'

            # logger.error(f'[{self.queue_task.queue_name}] [SET] {func} {func_kws}')
            out_func = self.queue_task.register(function = src_func, subclass_name = self.__class__.__name__, **func_kws)
            if not func_kws.get('disable_patch'):
                setattr(self, func, out_func)
            self.set_registered_function(self.queue_task.functions[self.queue_task.last_registered_function], **func_kws)
        if self.queue_task.queue_name not in TaskManager._task_initialized_abcs:
            TaskManager._task_initialized_abcs[self.queue_task.queue_name] = set()
        TaskManager._task_initialized_abcs[self.queue_task.queue_name].add(self.__kvdb_obj_id__)
        self.queue = TaskManager.get_task_queue(queue_name = self.queue_task.queue_name, **(self.get_queue_config() or {}))
            

    def __kvdb_post_init_hook__(self, *args, **kwargs):
        """
        The patched post init hook
        """
        for initializer in self.__kvdb_initializers__:
            if isinstance(initializer, str):
                initializer = getattr(self, initializer)
            initializer(self.__kvdb_obj_id__, *args, **kwargs)

    def __task_init__(self, *args, **kwargs):
        """
        The init method

        This is called immediately before the class is initialized
        """
        # logger.info(f'[{self.queue_task.queue_name}] [INIT] {self.__kvdb_obj_id__} {args} {kwargs}')
        self.cls_pre_init(*args, **kwargs)
        self.__kvdb_post_init_hook__(*args, **kwargs)
        self.cls_init(*args, **kwargs)
        self.cls_post_init(*args, **kwargs)
        self.cls_finalize_init(*args, **kwargs)

    

    def __new__(cls, *args, **kwargs):
        """
        This initializes the class and calls `__task_init__`
        """
        instance = super().__new__(cls)
        instance.__task_init__(*args, **kwargs)
        return instance
    
    # def __init__(self, )

    # def __init__(self, *args, **kwargs):
    #     """
    #     The patched init method
    #     """
    #     # super().__init__(*args, **kwargs)
    #     # logger.info(f'[[INIT] {self.__kvdb_obj_id__} {args} {kwargs}')
    #     self.__src_init__(*args, **kwargs)
    


