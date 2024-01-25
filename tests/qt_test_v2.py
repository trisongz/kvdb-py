
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


def entrypoint_v4():
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


async def entrypoint_v3():

    # Initialize and register the tasks
    q2 = tasks.get_task_queue(queue_name = 'test', debug_enabled = True)
    q = tasks.get_task_queue(queue_name = 'global', debug_enabled = True)
    x = TestWorker()
    
    n_workers = 10

    with anyio.move_on_after(20):
        # tasks.TaskManager.spawn_task_workers(
        #     num_workers=n_workers,
        #     worker_name = 'test',
        #     queues = 'all',
        #     debug_enabled = True,
        # )
        await tasks.TaskManager.start_task_workers(
            num_workers=n_workers,
            worker_name = 'test',
            queues = 'all',
            debug_enabled = True,
        )

            
        await q.enqueue('TestWorker.task1')
        # await x.task1(blocking = False)

        # await my_task(blocking = False)
        await q2.enqueue(my_task)
        
        await q.enqueue('TestWorker.task2')
        await x.task2(blocking = False)
        


async def entrypoint_v2():

    # Initialize and register the tasks
    q2 = tasks.get_task_queue(queue_name = 'test', debug_enabled = True)
    q = tasks.get_task_queue(queue_name = 'global', debug_enabled = True)
    x = TestWorker()
    
    n_workers = 10

    await q.enqueue('TestWorker.task1')
    # await x.task1(blocking = False)

    # await my_task(blocking = False)
    await q2.enqueue(my_task)
    
    await q.enqueue('TestWorker.task2')
    await x.task2(blocking = False)


    from anyio.from_thread import start_blocking_portal
    from concurrent.futures import as_completed

    with anyio.move_on_after(20):
        # with start_blocking_portal() as portal:
        futures = []
        for i in range(n_workers):
            w = await tasks.aget_task_worker(worker_name=f'test-{i}', queues = 'all', debug_enabled = True)
            logger.info(f'Starting worker {w.worker_name}')
            task = asyncio.create_task(w.start())
            await asyncio.sleep(0.5)
            futures.append(task)
        await asyncio.wait(futures, return_when=asyncio.ALL_COMPLETED)
        # await asyncio.(*futures)



    

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


    await tasks.enqueue('TestWorker.task1')
    # await x.task1(blocking = False)
    await tasks.enqueue(my_task, queue_name='test')
    
    await tasks.enqueue('TestWorker.task2')

    with anyio.move_on_after(10):
        await w.start()


if __name__ == '__main__':
    # entrypoint_v4()
    asyncio.run(entrypoint_v3())