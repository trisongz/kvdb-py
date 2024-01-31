"""
This is a client-side example of how to use kvdb-py tasks using the `TaskABC` class

This will be able to remotely execute the tasks from `examples/queue/dummy_class.py`

To run this example, you will need to run the following commands:

  Terminal 1:

    # cwd: examples/queue
    $ kvdb-task -i "dummy_class.initializer" -n 1 -q "global"
    >>>
    - [Worker ID]: 63f0e517-e3bd-4d6c-xxx-xxxx [Worker Name]: global-local-0 [Node Name]: computer.local 
    - [Concurrency]: 150/jobs, 50/broadcasts
    - [Queues]:
    - [Registered]: 5 functions, 0 cron jobs
        [Functions]: `['SubTestClass7.func_three', 'SubTestClass7.func_one', 'SubTestClass7.func_five', 'SubTestClass7.func_six', 'SubTestClass7.func_four']`

  Terminal 2:
    
    # cwd: examples/queue
    $ python client_side_class.py
"""


import sys
import asyncio
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import dummy_class
from kvdb import tasks
from kvdb.utils.logs import logger

async def entrypoint():
    # Initialize and register the tasks
    x = dummy_class.SubTestClass7()
    # y = dummy_tasks.InheritedWorker()

    q1 = tasks.get_task_queue(queue_name = 'global', debug_enabled = True)
    # q2 = tasks.get_task_queue(queue_name = 'test', debug_enabled = True)

    # We can spawn tasks one of two ways. Either by calling the function directly
    # since we have it patched with a decorator
    # or by calling the task queue's enqueue method

    # Task 1 requires ctx, so it can only be called via the task queue
    # await q1.enqueue('TestWorker.task1')
    await q1.enqueue('SubTestClass7.func_one')
    # This would fail because it is not registered
    # await q1.enqueue('SubTestClass7.func_two')
    await q1.enqueue('SubTestClass7.func_three')

    # Additionally, since the underlying function is patched with the register decorator
    # you can also call the function directly and it will be executed as a task
    # await x.func_one(blocking = False)
    # This would fail because it is not registered
    # await q1(x.func_two, blocking = False)
    # This would fail because it is only registered under the subclass
    await q1(x.func_three, blocking = False)
    
    

    # If `blocking` is set to `True`, then the task will be executed and will wait for the result
    # If `blocking` is set to `False`, then the task will be executed and will not wait for the result, but instead return a `Job` object

    # result_1 = await x.task2(blocking = True)
    # result_2 = await q1(x.task1, blocking = True)

    # logger.info(f'result_1: {result_1}')
    # logger.info(f'result_2: {result_2}')

    result_1 = await x.func_six(blocking = True)
    result_2 = await q1(x.func_six, blocking = True)

    logger.info(f'result_1: {result_1}')
    logger.info(f'result_2: {result_2}')


if __name__ == '__main__':
    asyncio.run(entrypoint())