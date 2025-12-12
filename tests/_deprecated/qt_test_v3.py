
import abc
import asyncio
import anyio
from kvdb import tasks
from kvdb.utils.logs import logger


def entrypoint_v4():

    task_context = tasks.create_context(disable_patch = False)

    # @tasks.register(queue_name='test')
    # async def my_task(*args, **kwargs):
    #     logger.info(f'Hello Worlddddddd {args} {kwargs}')
    #     return None

    @task_context.register_object()
    class TestWorker(abc.ABC):

        def __init__(self, *args, **kwargs):
            print('running init')

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



    q2 = tasks.get_task_queue(queue_name = 'test', debug_enabled = True)
    q = tasks.get_task_queue(queue_name = 'global', debug_enabled = True)
    x = TestWorker()
    
    n_workers = 1

    # with anyio.move_on_after(20):
    tasks.TaskManager.spawn_task_workers(
        num_workers=n_workers,
        worker_name = 'test',
        queues = 'all',
        debug_enabled = True,
    )



if __name__ == '__main__':
    entrypoint_v4()