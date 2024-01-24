
import abc
import asyncio
import anyio
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




async def entrypoint():

    # Initialize and register the tasks
    q2 = tasks.get_task_queue(queue_name = 'test', debug_enabled = True)
    
    q = tasks.get_task_queue(queue_name = 'global', debug_enabled = True)
    

    x = TestWorker()
    w = tasks.get_task_worker('test', queues = 'all', debug_enabled = True)
    
    # print(my_task.__class__)
    print(type(my_task))
    # print(TestWorker.task1.__class__)
    print(type(TestWorker.task1))
    print(type(x.task1))
    await q.enqueue('TestWorker.task1')
    # await x.task1(blocking = False)

    # await my_task(blocking = False)
    await q2.enqueue(my_task)
    
    await q.enqueue('TestWorker.task2')
    await x.task2(blocking = False)

    with anyio.move_on_after(10):
        await w.start()


if __name__ == '__main__':
    asyncio.run(entrypoint())