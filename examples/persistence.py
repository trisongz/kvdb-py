"""
This example demonstrates how to use `PersistentDict`
with various serializers and how to use it with `KVDBClient`
"""

import random
from pydantic import BaseModel, Field
from kvdb.client import KVDBClient


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

s.persistence['test_1'] = test_1
s.persistence['test_2'] = test_2

result_1 = s.persistence['test_1']
result_2 = s.persistence['test_2']

print(result_1, 'type', type(result_1))
print(result_2, 'type', type(result_2))


# Create a new Session that uses the JSON Serializer
# natively within the connection pool
s_json = KVDBClient.get_session(
    name = 's_json',
    serializer = 'json',
    persistence_base_key = 'test_json',
)

s_json.persistence['test_1'] = test_1
s_json.persistence['test_2'] = test_2

json_result_1 = s_json.persistence['test_1']
json_result_2 = s_json.persistence['test_2']

print(json_result_1, 'type', type(json_result_1))
print(json_result_2, 'type', type(json_result_2))

# Test assertions
assert result_1 == json_result_1
assert result_2 == json_result_2

# Delete the keys
s.persistence.pop('test_1')
s.persistence.pop('test_2')

s_json.persistence.pop('test_1')
s_json.persistence.pop('test_2')
