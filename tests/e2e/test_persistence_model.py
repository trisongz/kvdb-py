
import pytest
from pydantic import BaseModel
from kvdb.components.persistence import KVDBStatefulBackend

TEST_URL = "redis://localhost:6379/10"

class User(BaseModel):
    id: int
    name: str
    email: str

@pytest.mark.asyncio
async def test_persistence_pydantic_serialization():
    # Setup persistence backend with serialization
    pdict = KVDBStatefulBackend.as_persistent_dict(
        url=TEST_URL, 
        base_key="test:pdict:model:unique", 
        serializer="json",
        async_enabled=True,
        name="persistence_model_unique"
    )
    await pdict.aclear()

    user = User(id=1, name="Alice", email="alice@example.com")

    # Set
    await pdict.aset("user:1", user)
    
    # Get
    # Note: KVDB persistence might return dict or object depending on configuration
    # By default, KVDB persistence with serialization stores the object as serialized string
    # and decodes it back. However, without specifying `serialization_enabled` explicitly on the 
    # persistent dict wrapper if relying on underlying session defaults, behavior might vary.
    # But `as_persistent_dict` usually creates its own session/backend.
    
    retrieved_user_data = await pdict.aget("user:1")
    
    # If using 'json' serializer, it should come back as dict or object depending on implementation details
    # KVDB's Encoder/Serializer typically restores logic. 
    # Since we didn't pass specific Type for deserialization here (it's a generic dict),
    # it likely returns a dict representation of the Pydantic model effectively.
    
    if isinstance(retrieved_user_data, User):
         assert retrieved_user_data.id == 1
         assert retrieved_user_data.name == "Alice"
    elif isinstance(retrieved_user_data, dict):
        assert retrieved_user_data['id'] == 1
        assert retrieved_user_data['name'] == "Alice"
    else:
        # Fallback if it comes as bytes (shouldn't if serializer is working)
        pytest.fail(f"Unexpected type returned: {type(retrieved_user_data)}")

    # Delete
    await pdict.adelete("user:1")
    assert await pdict.aget("user:1") is None
