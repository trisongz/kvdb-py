# Overview

The `KVDBSessionManager` (accessed as `kvdb.KVDBClient`) class provides a context manager interface for managing sessions with the KVDB server. It keeps track and registration of all active sessions and provides a simple interface for managing session operations. It inherits from a `ProxyObject` Singleton to lazily initialize and prevent multiple instances of the session manager.

- [Sessions](./sessions.md)
- [API Reference](../api/session-manager/api.md)

## Basic Usage

```python

import kvdb
from pydantic import BaseModel

# Explicitly define the config. Otherwise it will use the defaults, which are determined via environment variables.
# session = KVDBClient.get_session(name="default", url=os.environ.get("REDIS_URL|KVDB_URL|KEYDB_URL|MEMCACHED_URL"))

# Alternative methods that achieve the same result
# session = kvdb.from_url(name="default", url="redis://localhost:6379/0", serializer='json')
# session = kvdb.get_session(name="default", url="redis://localhost:6379/0", serializer='json')

session = kvdb.KVDBClient.get_session(name="default", url="redis://localhost:6379/0", serializer='json')

class MyModel(BaseModel):
    name: str
    age: int

# This demonstrates how the pydantic model is automatically serialized and deserialized
new_model = MyModel(name='John', age=30)
session.set(new_model.name, new_model)
src_model = session.get('John')

assert src_model == new_model

# Without explicitly defining the serailizer, the same would fail.

session2 = kvdb.KVDBClient.get_session(name="test-1")
# This will fail because the serializer is not defined
session2.set(new_model.name, new_model)

```
