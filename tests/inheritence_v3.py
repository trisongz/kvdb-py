
import abc
import sys
import inspect

from pydantic import BaseModel
from kvdb import tasks
from kvdb.tasks.base import BaseTaskWorker
from kvdb.utils.logs import logger
from typing import Callable, List, Optional, Type, Any, Dict, Union


class NewWorker(BaseTaskWorker):

    @tasks.register_abc
    async def task1(self, *args, **kwargs):
        logger.info(f'task 1 hello {args} {kwargs}', prefix = self.__class__.__name__)
        return 'hello_1'
    
    @tasks.register_abc
    async def task2(self, *args, **kwargs):
        logger.info(f'task 2 hello {args} {kwargs}', prefix = self.__class__.__name__)
        return 'hello_2'

    @tasks.register_abc(phase = 'startup')
    async def onstartup_2(self, *args, **kwargs):
        logger.info(f'onstartup 2 hello {args} {kwargs}', prefix = self.__class__.__name__)
        return 'hello_2'


class NewWorker2(BaseTaskWorker):

    @tasks.register_abc
    async def task1(self, *args, **kwargs):
        logger.info(f'task 1 hello {args} {kwargs}', prefix = self.__class__.__name__)
        return 'hello_1'
    
    @tasks.register_abc
    async def task2(self, *args, **kwargs):
        logger.info(f'task 2 hello {args} {kwargs}', prefix = self.__class__.__name__)
        return 'hello_2'

    @tasks.register_abc(phase = 'startup')
    async def onstartup_2(self, *args, **kwargs):
        logger.info(f'onstartup 2 hello {args} {kwargs}', prefix = self.__class__.__name__)
        return 'hello_2'


    def get_queue_name(self, *args, **kwargs) -> str:
        """
        Gets the queue name
        """
        if self.settings is not None and hasattr(self.settings, 'app_env'):
            return f'{self.worker_module_name}.{self.settings.app_env.name}.tasks2'
        return f'{self.worker_module_name}.tasks2'


class Worker1(NewWorker):

    @tasks.register_abc
    async def task3(self, *args, **kwargs):
        logger.info(f'task 3 hello {args} {kwargs}', prefix = self.__class__.__name__)
        return 'hello_3'
    

class Worker2(Worker1):
    fallback_enabled = True
    
    def __init__(self, *args, **kwargs):
        logger.info(f'worker2 init {args} {kwargs}', prefix = self.__class__.__name__)

    @tasks.register_abc
    async def task4(self, *args, **kwargs):
        logger.info(f'task 4 hello {args} {kwargs}', prefix = self.__class__.__name__)
        return 'hello_4'
    

    @tasks.register_abc(phase = 'startup')
    async def onstartup_3(self, *args, **kwargs):
        logger.info(f'onstartup 3 hello {args} {kwargs}', prefix = self.__class__.__name__)
        return 'hello_3'


# class TaskABC(abc.ABC):

async def entrypoint():
    w = Worker2()

    logger.info(f'worker {w}')

    await w.task1()
    await w.task2()
    await w.task3()
    await w.task4()

    # w1 = NewWorker2()
    # await w1.task2(blocking = True)


def get_worker():

    w = Worker2()

    logger.info(f'worker {w}')

    return w

# get_worker()

if __name__ == '__main__':
    import asyncio
    asyncio.run(entrypoint())