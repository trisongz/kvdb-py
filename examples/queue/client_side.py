"""
This is a client-side example of how to use kvdb-py tasks

This will be able to remotely execute the tasks from `examples/queue/dummy_tasks.py`

To run this example, you will need to run the following commands:

  Terminal 1:

    # cwd: examples/queue
    $ kvdb-task -i "dummy_tasks.initializer" -n 1 -q "test" -q "global"
    >>>
    - [Worker ID]: 63f0e517-e3bd-4d6c-xxx-xxxx [Worker Name]: global-local-0 [Node Name]: computer.local 
    - [Concurrency]: 150/jobs, 50/broadcasts
    - [Queues]:
    - [test]      @ redis://localhost:6379/3 DB: 3, 1 functions, 0 cron jobs
            [Functions]: `['my_task']`
    - [global]    @ redis://localhost:6379/3 DB: 3, 2 functions, 0 cron jobs
            [Functions]: `['TestWorker.task1', 'TestWorker.task2']

  Terminal 2:
    
    # cwd: examples/queue
    $ python client_side.py
"""


import sys
import asyncio

from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import dummy_tasks
from kvdb import tasks


async def entrypoint():


    # Initialize and register the tasks
    x = dummy_tasks.TestWorker()

    q1 = tasks.get_task_queue(queue_name = 'global', debug_enabled = True)
    q2 = tasks.get_task_queue(queue_name = 'test', debug_enabled = True)

    # We can spawn tasks one of two ways. Either by calling the function directly
    # since we have it patched with a decorator
    # or by calling the task queue's enqueue method

    # Task 1 requires ctx, so it can only be called via the task queue
    await q1.enqueue('TestWorker.task1')
    # await x.task1(blocking = False)

    await q2.enqueue(dummy_tasks.my_task)
    await dummy_tasks.my_task(blocking = False)

    await q1.enqueue('TestWorker.task2')
    await x.task2(blocking = False)

    await q1(x.task1, blocking = False)


if __name__ == '__main__':
    asyncio.run(entrypoint())


    
