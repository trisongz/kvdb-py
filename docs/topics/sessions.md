# Overview

Sessions are the underlying object that contains the state of a single `KVDB` connection to a server. This session contains both asynchronous and synchronous methods for interacting with the server, as well as methods for managing the session itself.

The underlying connection pools are managed by the `KVDBClient` class, which is a singleton that manages all sessions. This allows you to create multiple sessions with different configurations, but still share the same underlying connection pool, unless there is any configuration differences that would require a new connection pool.

- [Session Manager](./session-manager.md)
- [API Reference](../api/sessions/api.md)

## Creating a Session

A session can be created by calling the `KVDBClient.get_session()` method. This method takes a number of arguments that can be used to configure the session. The following is a list of the arguments that can be passed to the `get_session()` method:

* `name`: The name of the session. Defaults to `default`. This should be a unique name for each session. If a session with the same name already exists, then the existing session will be returned.
* `url`: The URL to connect to. Defaults to `redis://localhost:6379/0`.
* `host`: The host to connect to. Defaults to `None`.
* `port`: The port to connect to. Defaults to `None`.
* `db_id`: The database to connect to. Defaults to `None`.
* `password`: The password to use when connecting. Defaults to `None`.
* `username`: The username to use when connecting. Defaults to `None`.

## Session Serialization

A session can be configured to use a serializer when serializing and deserializing data in-flight. This allows you to store almost any type of object when using any `set/get` methods without having to worry about serializing and deserializing prior.

Even with `json`, almost all data types and objects can be serialized by utilizing an intelligent deterministic storing of the object's metadata on serialization and then reconstructing the object on deserialization. This is done by storing the object's type and any additional metadata required to reconstruct the object. 

Serialization has first-class support for `pydantic` models and `dataclasses`.

This can be done by passing a serializer to the `get_session()` method. 
It is currently not recommended to mix serialization with sub-dependent libraries that may do encoding and decoding prior to passing the data to KV Store, as it can lead to serialization errors.

The following is a list of the arguments that can be passed to the `get_session()` method:

*  `serializer`: The serializer to use when serializing and deserializing data. Defaults to `None`. Set to `auto`, which defaults to `json` to automatically use a serializer based on the data type. Each type supports sub-libraries which will be used if they are installed. Additionally, you can pass a custom kwarg to try to import the serializer.
  Supported serializers (and sub-libraries based on priority):
    * `json`: The JSON serializer.
      Kwarg: `jsonlib`
      - [x] `simdjson`
      - [x] `orjson`
      - [x] `ujson`
      - [x] `json`
    * `msgpack`: The MessagePack serializer.
    * `pickle`: The pickle serializer.
      Kwarg: `picklelib`
        - [x] `cloudpickle`
        - [x] `dill`
        - [x] `pickle`

* `serializer_kwargs`: The keyword arguments to pass to the serializer when serializing and deserializing data. Defaults to `None`.
* `compression`: The compression algorithm to use when compressing and decompressing data. Defaults to `None`. 
  Supported compression algorithms:
    * `zstd`
    * `lz4`
    * `gzip`
    * `zlib`
* `compression_level`: The compression level to use when compressing data. Defaults to `None`, which will use the default compression level for the compression algorithm.
* `compression_enabled`: Whether or not compression should be enabled. Defaults to `None`. If `True` and `compression` is `None`, then it will be determined based on which compression algorithms are available. If `False`, then compression will be disabled.


## Example

The following is an example of creating a session:

```python

from kvdb import KVDBClient
from pydantic import BaseModel

class MyModel(BaseModel):
    name: str
    age: int

session_1 = KVDBClient.get_session(
    name='my-session',
    url='redis://:password@localhost:6379/0',
)

session_1.set('key', 'value')

# See how the value is automatically serialized and deserialized
session_2 = KVDBClient.get_session(
    name='my-session',
    url='redis://:password@127.0.0.1:6379/0',
    serializer='json',
)

# This demonstrates how the pydantic model is automatically serialized and deserialized
new_model = MyModel(name='John', age=30)
session_2.set(new_model.name, new_model)
src_model = session_2.get('John')

assert src_model == new_model
```
