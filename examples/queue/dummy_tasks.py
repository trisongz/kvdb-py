"""
Dummy Tasks to test
"""

import abc
from kvdb import tasks
from kvdb.utils.logs import logger

task_context = tasks.create_context(disable_patch = False)

@tasks.register(queue_name='test')
async def my_task(*args, **kwargs):
    logger.info(f'Hello Worlddddddd {args} {kwargs}')
    return None

@task_context.register_object()
class TestWorker(abc.ABC):

    def __init__(self, *args, **kwargs):
        logger.info(f'initializing {args} {kwargs}')

    # Both of these should work
    # @tasks.register()
    @task_context.register()
    async def task1(self, ctx, *args, **kwargs):
        logger.info(f'task 1 hello {ctx} {args} {kwargs} {self}')
        return None
    
    @task_context.register()
    async def task2(self, *args, **kwargs):
        logger.info(f'task 2 hello {args} {kwargs} {self}')
        return None

def initializer():
    x = TestWorker()