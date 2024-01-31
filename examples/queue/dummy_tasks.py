"""
Dummy Tasks to test
"""

import abc
from kvdb import tasks
from kvdb.utils.logs import logger

# Create a new task context that will be used to register the tasks
# Any params passed to create_context will be used as partials for the register decorator
# that can subsequently be overriden by the kwargs passed to the register decorator

# Since no `queue_name` is passed, it will default to `global`
task_context = tasks.create_context(disable_patch = False)

# This will be registered to the `test` queue
@tasks.register(queue_name='test')
async def my_task(*args, **kwargs):
    logger.info(f'Hello Worlddddddd {args} {kwargs}')
    return None


# This will be registered to the `global` queue
# This decorator is required when using an object and
# registering the object's methods as tasks
# so that the object can be patched with initializers
# to add the registered functions to the task context
@task_context.register_object()
class TestWorker(abc.ABC):

    def __init__(self, *args, **kwargs):
        logger.info(f'initializing {self.__class__.__name__} {args} {kwargs}')

    # Both of these should work
    # @tasks.register(queue_name='global')
    @task_context.register()
    async def task1(self, ctx, *args, **kwargs):
        # This function will be passed the task context as the first argument
        # since it has `ctx` as the first argument
        # The task context is a singleton object that is shared across all tasks
        # that contains `Job`, `TaskWorker`
        # and any contexts that are initialized.
        logger.info(f'task 1 hello {ctx} {args} {kwargs} {self}')
        return 'hello_1'
    
    @task_context.register()
    async def task2(self, *args, **kwargs):
        logger.info(f'task 2 hello {args} {kwargs} {self}')
        return 'hello_2'

# Since we pass -i "dummy_tasks.initializer" to the kvdb-task command
# it will run this function to initialize the task context. If the 
# object is not initialized, then the functions will not be registered
def initializer():
    x = TestWorker()