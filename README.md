![Documentation](https://github.com/trisongz/kvdb-py/actions/workflows/build-docs.yaml/badge.svg)
![PyPI package](https://img.shields.io/pypi/v/kvdb-py?color=%2334D058&label=PyPI%20Package)

**Source code**: [https://github.com/trisongz/kvdb-py](https://github.com/trisongz/kvdb-py)

**Documentation and examples**: [https://trisongz.github.io/kvdb-py](https://trisongz.github.io/kvdb-py/)

# kvdb-py
 Key-Value DB Python Client Abstraction built on top of Redis

## Overview

This library builds upon the experience of my previous library, [aiokeydb-py](https://github.com/trisongz/aiokeydb-py) and the learnings and take-aways from maintaining it and using it in production. While `aiokeydb` supports `redispy` < 5.0, this library only supports `redispy` >= 5.0. 

Supports:

- [x] Redis
- [x] KeyDB
- [x] Dragonfly
- [ ] Memcached
- [ ] DynamoDB
- [ ] tikv


The goals of this library are:

- Provide a simple abstraction over the Redis client that allows both async and sync code, and adding minor tweaks in underlying implementation to make it more performant, and dynamic.

- Provide a unified interface for interacting with various Key-Value DBs, such as Redis, Memcached, etc. Inspired by [gokv](https://github.com/philippgille/gokv)

- Enable interacting with multiple Key-Value DBs at the same time, with the same API

- Enable usage of Key-Value DBs in the same manner as a native Python dictionary

- Provide a task queue implementation that can be used to distribute work across multiple workers.

- Capability to customize and override the underlying classes easily without requiring to manually patch objects.

### Why not use `redispy` directly?

`Redispy` is a great library, and this library itself is built on top of it. However, `redispy` lacks certain quality of life features that make it ready to use out of the box without having to extend the library to support these features. 

`kvdb` also provides a powerful in-flight serialization and deserialization mechanism that allows you to store almost any type of object in the Key-Value DB without having to worry about serializing and deserializing the data prior to storing it. This is done by storing the object's type and any additional metadata required to reconstruct the object. You can read more about this in the [Serialization](./examples/sessions/README.md#session-serialization) section.

Additionally, `kvdb` provides a unified async and sync interface for interacting with the Key-Value DB, rather than having to use two separate clients and instantiate two separate connections, defined as a `KVDBSession`. Each underlying `session` can share the same connection pool, so long as the `ConnectionPool` configuration is the same, meaning spawning multiple sessions will not saturate the connection pool.

`kvdb` utilizes singleton objects that manage instances of objects, such as `KVDBSession` and `Cachify`. This helps ensure performance and reduce memory usage by preventing the creation of multiple instances of the same object.


## Installation

```bash
pip install kvdb-py
```


## Usage

Check out the [examples](./examples/README.md) directory for examples on how to use this library.

---
### Quick Example

```python
from kvdb import KVDBClient
from pydantic import BaseModel

# Explicitly define the config. Otherwise it will use the defaults, which are determined via environment variables.

# session = KVDBClient.get_session(name="default", url=os.environ.get("REDIS_URL|KVDB_URL|KEYDB_URL|MEMCACHED_URL"))

session = KVDBClient.get_session(name="default", url="redis://localhost:6379/0", serializer='json')

class MyModel(BaseModel):
    name: str
    age: int

# This demonstrates how the pydantic model is automatically serialized and deserialized
new_model = MyModel(name='John', age=30)
session.set(new_model.name, new_model)
src_model = session.get('John')

assert src_model == new_model

# Without explicitly defining the serailizer, the same would fail.

session2 = KVDBClient.get_session(name="test-1")
# This will fail because the serializer is not defined
session2.set(new_model.name, new_model)

```

---
### Task Queues

This is a client-side example of how to use kvdb-py tasks.

By Default, `tasks` will use `db_id=3` for the task queue to prevent collisions with other data. You can change this by passing `db_id` to the `register` decorator or `create_context` function. If you do, ensure that the queue you are using also uses the same `db_id`.

This will be able to remotely execute the tasks from `examples/queue/dummy_tasks.py`

To run this example, you will need to run the following commands:

Terminal 1:

```bash
# cwd: examples/queue
$ kvdb-task -i "dummy_tasks.initializer" -n 1 -q "test" -q "global"

# Output:
- [Worker ID]: 63f0e517-e3bd-4d6c-xxx-xxxx [Worker Name]: global-local-0 [Node Name]: computer.local 
- [Concurrency]: 150/jobs, 50/broadcasts
- [Queues]:
- [test]      @ redis://localhost:6379/3 DB: 3, 1 functions, 0 cron jobs
        [Functions]: `['my_task']`
- [global]    @ redis://localhost:6379/3 DB: 3, 2 functions, 0 cron jobs
        [Functions]: `['TestWorker.task1', 'TestWorker.task2']
```

Terminal 2:

```bash
# cwd: examples/queue
$ python client_side.py
```

#### The Server Side Example:

```python
# dummy_task.py


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
        logger.info(f'initializing {args} {kwargs}')

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
```

#### The Client Side Example:


```python
# client_side.py

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

    await q1.enqueue('TestWorker.task2')

    # You can also enqueue a function directly by passing the function
    await q2.enqueue(dummy_tasks.my_task)

    # Additionally, since the underlying function is patched with the register decorator
    # you can also call the function directly and it will be executed as a task
    await dummy_tasks.my_task(blocking = False)
    await x.task2(blocking = False)
    await q1(x.task1, blocking = False)

    # If `blocking` is set to `True`, then the task will be executed and will wait for the result

    # If `blocking` is set to `False`, then the task will be executed and will not wait for the result, but instead return a `Job` object

    result_1 = await x.task2(blocking = True)
    result_2 = await q1(x.task1, blocking = True)

    logger.info(f'result_1: {result_1}')
    logger.info(f'result_2: {result_2}')
    assert result_1 == 'hello_2'
    assert result_2 == 'hello_1'


if __name__ == '__main__':
    asyncio.run(entrypoint())

```

---
### Caching

Below are two examples of how to use the caching functionality of `kvdb-py`. The first example demonstrates how to use the caching functionality with any functions, and the second example demonstrates how to use the caching functionality with an object.

See the following files for more examples:

- [examples/caching/basic.py](./examples/caching/basic.py) for an example of how to use caching with functions

- [examples/caching/objects.py](./examples/caching/objects.py) for an example of how to use caching with an object

- [examples/caching/context.py](./examples/caching/context.py) for an example of how to use caching with a pre-defined context


```python

import time
import abc
import asyncio
from lazyops.utils.times import Timer
from kvdb.io import cachify
from kvdb.utils.logs import logger

DEBUG_ENABLED = False

@cachify.register(ttl = 10, verbosity = 2 if DEBUG_ENABLED else None, cache_max_size = 15)
async def async_fibonacci(number: int):
    if number == 0: return 0
    elif number == 1: return 1
    return await async_fibonacci(number - 1) + await async_fibonacci(number - 2)

@cachify.register(ttl = 10, verbosity = 2 if DEBUG_ENABLED else None)
def fibonacci(number: int):
    if number == 0: return 0
    elif number == 1: return 1
    return fibonacci(number - 1) + fibonacci(number - 2)

# No Cache Versions
async def async_fibonacci_nc(number: int):
    if number == 0: return 0
    elif number == 1: return 1
    return await async_fibonacci_nc(number - 1) + await async_fibonacci_nc(number - 2)

def fibonacci_nc(number: int):
    if number == 0: return 0
    elif number == 1: return 1
    return fibonacci_nc(number - 1) + fibonacci_nc(number - 2)

## Object Caching
@cachify.register_object()
class TestObject(abc.ABC):

    def __init__(self, *args, **kwargs):
        logger.info('running init')

    @cachify.register(ttl = 10, verbosity = 2 if DEBUG_ENABLED else None, cache_max_size = 15)
    async def async_fibonacci(self, number: int):
        if number == 0: return 0
        elif number == 1: return 1
        return await self.async_fibonacci(number - 1) + await self.async_fibonacci(number - 2)

    @cachify.register(ttl = 10, verbosity = 2 if DEBUG_ENABLED else None)
    def fibonacci(self, number: int):
        if number == 0: return 0
        elif number == 1: return 1
        return self.fibonacci(number - 1) + self.fibonacci(number - 2)

    # No Cache Versions
    async def async_fibonacci_nc(self, number: int):
        if number == 0: return 0
        elif number == 1: return 1
        return await self.async_fibonacci_nc(number - 1) + await self.async_fibonacci_nc(number - 2)

    def fibonacci_nc(self, number: int):
        if number == 0: return 0
        elif number == 1: return 1
        return self.fibonacci_nc(number - 1) + self.fibonacci_nc(number - 2)
```

### Persistence

An additional feature of `kvdb-py` is the ability to access a `Dict`-like object that is persisted to the Key-Value DB. This is useful for storing data that needs to be accessed by multiple processes or machines. This is powered by the underlying `PersistentDict` from `lazyops`, with `kvdb-py` providing the backend to the Key-Value DB.

```python


import random
from pydantic import BaseModel, Field
from kvdb import KVDBClient

class NewObject(BaseModel):
    x: int = Field(default_factory = lambda: random.randint(0, 100))


test_1 = NewObject()
test_2 = NewObject(x = 1)

# Create a new Session that does not use a Serializer
# and uses the default connection pool
s = KVDBClient.get_session(
    name = 'default',
    persistence_base_key = 'test',
    persistence_serializer = 'json',
)

# You can set the attributes directly
# or call the underlying `persistence` object
s['test_1'] = test_1
s['test_2'] = test_2

# s.persistence['test_1'] = test_1
# s.persistence['test_2'] = test_2

result_1 = s['test_1']
result_2 = s['test_2']
# result_1 = s.persistence['test_1']
# result_2 = s.persistence['test_2']

print(result_1, 'type', type(result_1))
print(result_2, 'type', type(result_2))


# Create a new Session that uses the JSON Serializer
# natively within the connection pool
s_json = KVDBClient.get_session(
    name = 's_json',
    serializer = 'json',
    persistence_base_key = 'test_json',
)

s_json['test_1'] = test_1
s_json['test_2'] = test_2
# s_json.persistence['test_1'] = test_1
# s_json.persistence['test_2'] = test_2

json_result_1 = s_json['test_1']
json_result_2 = s_json['test_2']
# json_result_1 = s_json.persistence['test_1']
# json_result_2 = s_json.persistence['test_2']

print(json_result_1, 'type', type(json_result_1))
print(json_result_2, 'type', type(json_result_2))

# Test assertions
assert result_1 == json_result_1
assert result_2 == json_result_2

# Delete the keys
del s['test_1']
del s['test_2']
# s.delitem('test_1')
# s.delitem('test_2')
# s.persistence.pop('test_1')
# s.persistence.pop('test_2')

del s_json['test_1']
del s_json['test_2']
# s_json.persistence.pop('test_1')
# s_json.persistence.pop('test_2')

## Additionally, you can initialize a new persistence object directly
p = s_json.get_persistence(
    name = 'p',
    base_key = 'test_pickle',
    serializer = 'pickle',
)

p['test_1'] = test_1
p['test_2'] = test_2


```


### Customization

Since no objects/settings are initialized until they are first directly called, you can easily customize and define configurations for the underlying objects. For example, if you want to use a different serializer, you can do the following:

```python

from kvdb.io.serializers import set_default_serializer, set_default_serializer_lib, register_serializer

# Set the default serializer to use
# If `propogate=True` This will set the default serializer to pickle for all modules, such as cache, tasks, etc. Otherwise, it will only affect instances where `serializer=None`.

set_default_serializer('pickle', propagate = True) 

# Set the default serializer library to use
set_default_serializer_lib('cloudpickle')

# You can also register a custom serializer
register_serializer('custom-serializer', MySerializerClass, set_as_default = True, propogate = True)


# Alternatively, you can selectively modify the default serializer for certain modules
from kvdb.configs import set_default_serializer_for, set_default_kvdb_url

set_default_kvdb_url('redis://remote.redis.com:6379/0')
set_default_serializer_for('custom-serializer', 'session', 'task')

from kvdb import KVDBClient

session = KVDBClient.get_session()

class MyModel(BaseModel):
    name: str
    age: int

# This demonstrates how the pydantic model is automatically serialized and deserialized
new_model = MyModel(name='John', age=30)
session.set(new_model.name, new_model)
src_model = session.get('John')

# The session will use the custom serializer for the session
assert src_model == new_model
```





